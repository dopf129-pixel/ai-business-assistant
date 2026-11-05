"""Strict allowlists for durable unit-economics experiment projections."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.unit_economics_experiment_plan_service import (
    UnitEconomicsExperimentPlanService,
)
from services.unit_price_tariff_resolver import UnitPriceTariffResolver


class PlanningUnitEconomicsExperimentAdapter:
    """Normalize storage contracts; raw source responses never cross this boundary."""

    SNAPSHOT_SCHEMA_VERSION = 1
    EXPERIMENT_SCHEMA_VERSION = 1
    EXPERIMENT_PLAN_SCHEMA_VERSION = 1
    PHASE_SCHEMA_VERSION = 1
    RESULT_SCHEMA_VERSION = 2
    OWNER_DECISION_SCHEMA_VERSION = 1
    MAX_SNAPSHOT_BYTES = 64 * 1024
    MAX_AMOUNT = Decimal("999999999999.99")
    _HEX_256 = re.compile(r"^[a-f0-9]{64}$")
    _HEX_128 = re.compile(r"^[a-f0-9]{32}$")
    _CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    _MONEY = re.compile(r"^-?(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$")
    _IDENTITY_FIELDS = frozenset({
        "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
    })
    _READINESS_STATUSES = frozenset({
        "COMPLETE", "PARTIAL", "UNAVAILABLE", "INCOMPARABLE", "RATE_LIMITED",
        "TIME_BUDGET_EXHAUSTED", "REQUEST_BUDGET_EXHAUSTED",
    })
    _COVERAGE_STATUSES = frozenset({
        "COMPLETE", "SHORT_HISTORY", "PARTIAL", "UNAVAILABLE", "INCOMPARABLE",
        "RATE_LIMITED", "TIME_BUDGET_EXHAUSTED", "REQUEST_BUDGET_EXHAUSTED",
    })
    _SOURCE_CODES = frozenset({
        "OZON_SELLER_FINANCE", "OZON_PERFORMANCE", "OZON_ANALYTICS",
        "OZON_SELLER_API", "CROSS_DOCKING_EVIDENCE", "OWNER_INPUT", "UNKNOWN",
    })
    _APPLICABILITY_CODES = frozenset({
        "WINDOW_MODEL_INPUT", "RECONCILIATION_ONLY", "OUT_OF_SCOPE", "UNKNOWN",
    })
    _OUTCOMES = frozenset({
        "CONTINUE_COLLECTING", "FIX_DATA_OR_CONDITIONS", "NO_CLEAR_DIFFERENCE",
        "CANDIDATE_BETTER_IN_MODEL", "BASELINE_BETTER_IN_MODEL", "INCOMPARABLE",
    })
    _OWNER_DECISIONS = frozenset({
        "KEEP_BASELINE_PRICE", "SELECT_EVALUATED_CANDIDATE", "CONTINUE_TEST",
        "STOP_WITHOUT_PRICE_CHANGE",
    })

    @classmethod
    def normalize_identity(cls, value, scope):
        if not isinstance(value, dict) or set(value) != cls._IDENTITY_FIELDS:
            return None
        if (value.get("owner_id") != scope.get("owner_id")
                or value.get("store_id") != scope.get("store_id")
                or value.get("sale_schema") not in {"FBO", "FBS"}):
            return None
        limits = {"owner_id": 80, "store_id": 80, "product_id": 80,
                  "offer_id": 120, "sku": 64}
        normalized = {}
        for key, limit in limits.items():
            raw = value.get(key)
            if not isinstance(raw, str) or not raw.strip() or len(raw.strip()) > limit:
                return None
            normalized[key] = raw.strip()
        normalized["sale_schema"] = value["sale_schema"]
        return normalized

    @classmethod
    def normalize_expense_snapshot(cls, payload, scope):
        if (not isinstance(payload, dict)
                or set(payload) != {"schema_version", "identity", "readiness"}
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.SNAPSHOT_SCHEMA_VERSION):
            return None
        identity = cls.normalize_identity(payload.get("identity"), scope)
        readiness = cls._normalize_readiness(payload.get("readiness"))
        if identity is None or readiness is None:
            return None
        return {
            "schema_version": cls.SNAPSHOT_SCHEMA_VERSION,
            "identity": identity,
            "readiness": readiness,
        }

    @classmethod
    def _normalize_readiness(cls, value):
        required = {
            "error", "schema_version", "status", "scope_kind", "window",
            "coverage_status", "coverage_complete", "denominator",
            "component_counts", "components", "read_only", "api_calls",
        }
        if (not isinstance(value, dict) or set(value) != required
                or value.get("error") is not False
                or type(value.get("schema_version")) is not int
                or value["schema_version"] != 1
                or value.get("status") not in cls._READINESS_STATUSES
                or value.get("scope_kind") not in {
                    "REFERENCE_56_COMPLETED_LOCAL_DAYS", "EXPERIMENT_PHASE_WINDOW",
                }
                or value.get("coverage_status") not in cls._COVERAGE_STATUSES
                or type(value.get("coverage_complete")) is not bool
                or value["coverage_complete"] != (value["coverage_status"] == "COMPLETE")
                or value.get("read_only") is not True
                or type(value.get("api_calls")) is not int
                or value["api_calls"] != 0):
            return None
        window = value.get("window")
        if (not isinstance(window, dict)
                or set(window) != {"from_date", "to_date", "date_basis", "timezone"}
                or window.get("date_basis") != "LOCAL_CALENDAR_DAY"):
            return None
        try:
            start = date.fromisoformat(window["from_date"])
            end = date.fromisoformat(window["to_date"])
            if not isinstance(window.get("timezone"), str) or not window["timezone"]:
                return None
            ZoneInfo(window["timezone"])
        except (TypeError, ValueError, ZoneInfoNotFoundError, OSError):
            return None
        days = (end - start).days + 1
        if (start > end
                or value["scope_kind"] == "REFERENCE_56_COMPLETED_LOCAL_DAYS" and days != 56
                or value["scope_kind"] == "EXPERIMENT_PHASE_WINDOW" and not 1 <= days <= 28):
            return None
        denominator = value.get("denominator")
        if (not isinstance(denominator, dict) or set(denominator) != {"units", "kind"}
                or type(denominator.get("units")) is not int
                or not 0 <= denominator["units"] <= 1_000_000_000
                or denominator.get("kind") not in {
                    None, "ORDERED_UNITS_WINDOW", "SOLD_UNITS_WINDOW",
                }
                or denominator["units"] > 0 and denominator["kind"] is None):
            return None
        components = value.get("components")
        counts = value.get("component_counts")
        if (not isinstance(components, list) or len(components) > 64
                or not isinstance(counts, dict)
                or set(counts) != {"INCLUDED", "EXCLUDED", "UNKNOWN"}
                or any(type(counts[key]) is not int or counts[key] < 0 for key in counts)):
            return None
        normalized_components = []
        seen = set()
        calculated_counts = {key: 0 for key in ("INCLUDED", "EXCLUDED", "UNKNOWN")}
        fields = {
            "component_key", "status", "source", "applicability", "evidence_status",
            "observed_amount_rub", "observed_units", "applied_amount_rub",
            "applied_units", "unit_amount_rub", "reason_codes",
        }
        for row in components:
            if (not isinstance(row, dict) or set(row) != fields
                    or not isinstance(row.get("component_key"), str)
                    or cls._CODE.fullmatch(row["component_key"]) is None
                    or row["component_key"] in seen
                    or row.get("status") not in calculated_counts
                    or row.get("source") not in cls._SOURCE_CODES
                    or row.get("applicability") not in cls._APPLICABILITY_CODES
                    or row.get("evidence_status") not in {"COMPLETE", "PARTIAL", "INCOMPARABLE"}
                    or type(row.get("observed_units")) is not int
                    or row["observed_units"] != denominator["units"]):
                return None
            observed = cls._money(row.get("observed_amount_rub"), nonnegative=True)
            applied = cls._money(row.get("applied_amount_rub"), optional=True, nonnegative=True)
            unit_amount = cls._money(row.get("unit_amount_rub"), optional=True, nonnegative=True)
            applied_units = row.get("applied_units")
            reason_codes = row.get("reason_codes")
            if (observed is None or applied is None and row.get("applied_amount_rub") is not None
                    or unit_amount is None and row.get("unit_amount_rub") is not None
                    or (applied_units is not None and (
                        type(applied_units) is not int or applied_units != denominator["units"]
                    ))
                    or not isinstance(reason_codes, list) or len(reason_codes) > 16
                    or any(not isinstance(code, str) or cls._CODE.fullmatch(code) is None
                           for code in reason_codes)
                    or reason_codes != sorted(set(reason_codes))):
                return None
            if row["status"] == "INCLUDED":
                if applied is None or unit_amount is None or applied_units != denominator["units"]:
                    return None
            elif applied is not None or unit_amount is not None or applied_units is not None:
                return None
            seen.add(row["component_key"])
            calculated_counts[row["status"]] += 1
            normalized_components.append({
                "component_key": row["component_key"], "status": row["status"],
                "source": row["source"], "applicability": row["applicability"],
                "evidence_status": row["evidence_status"],
                "observed_amount_rub": observed, "observed_units": row["observed_units"],
                "applied_amount_rub": applied, "applied_units": applied_units,
                "unit_amount_rub": unit_amount, "reason_codes": list(reason_codes),
            })
        if calculated_counts != counts:
            return None
        if normalized_components != sorted(normalized_components, key=lambda item: item["component_key"]):
            return None
        return {
            "error": False, "schema_version": 1, "status": value["status"],
            "scope_kind": value["scope_kind"],
            "window": {key: window[key] for key in (
                "from_date", "to_date", "date_basis", "timezone",
            )},
            "coverage_status": value["coverage_status"],
            "coverage_complete": value["coverage_complete"],
            "denominator": deepcopy(denominator),
            "component_counts": calculated_counts,
            "components": normalized_components,
            "read_only": True, "api_calls": 0,
        }

    @classmethod
    def normalize_experiment(cls, payload, scope, *, allow_incomplete=False):
        fields = {
            "schema_version", "identity", "title", "metric", "calculation_mode",
            "source_references", "candidate_prices_cents", "decision_threshold_rub",
            "planned_duration_days", "currency", "control_flags",
        }
        plan_fields = {
            "plan_schema_version", "candidate_price_bounds_cents",
            "maturity_min_days", "maturity_min_units",
        }
        if not isinstance(payload, dict):
            return None
        payload_fields = set(payload)
        if payload_fields != fields and payload_fields != fields | plan_fields:
            return None
        if (type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.EXPERIMENT_SCHEMA_VERSION):
            return None
        identity = cls.normalize_identity(payload.get("identity"), scope)
        if identity is None:
            return None
        title = cls._title(payload.get("title"))
        mode = payload.get("calculation_mode")
        prices = payload.get("candidate_prices_cents")
        duration = payload.get("planned_duration_days")
        threshold = cls._money(payload.get("decision_threshold_rub"), nonnegative=True)
        flags = payload.get("control_flags")
        has_plan = set(payload) == fields | plan_fields
        incomplete_prices_allowed = allow_incomplete and has_plan
        if (title is None or payload.get("metric") != "MAX_RUB_PER_UNIT"
                or mode not in {"WINDOW_COST_ALLOCATION", "STRICT_RETAINED_COHORT"}
                or not isinstance(prices, list)
                or not (2 <= len(prices) <= 10
                        or incomplete_prices_allowed and len(prices) == 0)
                or any(type(item) is not int or not 1 <= item <= 999_999_999_999_999
                       for item in prices)
                or len(set(prices)) != len(prices)
                or type(duration) is not int or not 3 <= duration <= 28
                or threshold is None or Decimal(threshold) < Decimal("0.01")
                or payload.get("currency") != "RUB"
                or not isinstance(flags, dict)
                or set(flags) != {"inventory", "promotion", "advertising", "card", "cost", "tariff"}
                or any(value not in {"UNCHANGED", "CHANGED", "UNKNOWN", "NOT_APPLICABLE"}
                       for value in flags.values())):
            return None
        references = cls._normalize_source_references(payload.get("source_references"))
        if references is None:
            return None
        normalized = {
            "schema_version": cls.EXPERIMENT_SCHEMA_VERSION,
            "identity": identity, "title": title, "metric": "MAX_RUB_PER_UNIT",
            "calculation_mode": mode, "source_references": references,
            "candidate_prices_cents": sorted(prices),
            "decision_threshold_rub": threshold,
            "planned_duration_days": duration, "currency": "RUB",
            "control_flags": {key: flags[key] for key in sorted(flags)},
        }
        if has_plan:
            bounds = UnitEconomicsExperimentPlanService.normalize_price_bounds(
                payload.get("candidate_price_bounds_cents"),
            )
            if (type(payload.get("plan_schema_version")) is not int
                    or payload.get("plan_schema_version")
                    != cls.EXPERIMENT_PLAN_SCHEMA_VERSION
                    or payload.get("maturity_min_days")
                    != UnitEconomicsExperimentPlanService.MIN_MATURITY_DAYS
                    or payload.get("maturity_min_units")
                    != UnitEconomicsExperimentPlanService.MIN_MATURITY_UNITS
                    or payload.get("candidate_price_bounds_cents") is not None
                    and bounds is None):
                return None
            if bounds is not None and prices and any(
                price < bounds["min_price_cents"] or price > bounds["max_price_cents"]
                for price in prices
            ):
                return None
            normalized.update({
                "plan_schema_version": cls.EXPERIMENT_PLAN_SCHEMA_VERSION,
                "candidate_price_bounds_cents": bounds,
                "maturity_min_days": UnitEconomicsExperimentPlanService.MIN_MATURITY_DAYS,
                "maturity_min_units": UnitEconomicsExperimentPlanService.MIN_MATURITY_UNITS,
            })
            readiness = UnitEconomicsExperimentPlanService.evaluate(normalized)
            if not allow_incomplete and not readiness["eligible_for_ready"]:
                return None
        return normalized

    @classmethod
    def _normalize_source_references(cls, value):
        if not isinstance(value, dict) or set(value) != {
            "plan", "expense_snapshot_id", "tariff", "observation",
        }:
            return None
        plan = value.get("plan")
        if (not isinstance(plan, dict) or set(plan) != {"document_id", "revision"}
                or not isinstance(plan.get("document_id"), str)
                or not 1 <= len(plan["document_id"]) <= 80
                or type(plan.get("revision")) is not int or plan["revision"] < 1):
            return None
        snapshot = value.get("expense_snapshot_id")
        if not isinstance(snapshot, str) or cls._HEX_256.fullmatch(snapshot) is None:
            return None
        tariff = value.get("tariff")
        if tariff is not None and (
            not isinstance(tariff, dict) or set(tariff) != {"profile_id", "revision"}
            or not isinstance(tariff.get("profile_id"), str)
            or cls._HEX_128.fullmatch(tariff["profile_id"]) is None
            or type(tariff.get("revision")) is not int or tariff["revision"] < 1
        ):
            return None
        observation = value.get("observation")
        if observation is not None and (
            not isinstance(observation, dict)
            or set(observation) != {"observation_id", "result_revision"}
            or not isinstance(observation.get("observation_id"), str)
            or cls._HEX_128.fullmatch(observation["observation_id"]) is None
            or type(observation.get("result_revision")) is not int
            or observation["result_revision"] < 1
        ):
            return None
        return {
            "plan": {"document_id": plan["document_id"], "revision": plan["revision"]},
            "expense_snapshot_id": snapshot,
            "tariff": deepcopy(tariff), "observation": deepcopy(observation),
        }

    @classmethod
    def normalize_phase(cls, payload, identity):
        fields = {
            "schema_version", "kind", "segment_number", "planned_price_cents",
            "expense_snapshot_id", "planned_from_date", "planned_to_date",
            "timezone", "control_flags",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.PHASE_SCHEMA_VERSION
                or payload.get("kind") not in {"BASELINE", "CANDIDATE"}
                or type(payload.get("segment_number")) is not int
                or not 1 <= payload["segment_number"] <= 10
                or type(payload.get("planned_price_cents")) is not int
                or not 1 <= payload["planned_price_cents"] <= 999_999_999_999_999
                or not isinstance(payload.get("expense_snapshot_id"), str)
                or cls._HEX_256.fullmatch(payload["expense_snapshot_id"]) is None):
            return None
        start = cls._date(payload.get("planned_from_date"))
        end = cls._date(payload.get("planned_to_date"))
        timezone = payload.get("timezone")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
            return None
        flags = payload.get("control_flags")
        if (start is None or end is None or end < start or (end - start).days + 1 > 28
                or not isinstance(timezone, str) or not 1 <= len(timezone) <= 128
                or not isinstance(flags, dict)
                or set(flags) != {"inventory", "promotion", "advertising", "card", "cost", "tariff"}
                or any(value not in {"UNCHANGED", "CHANGED", "UNKNOWN", "NOT_APPLICABLE"}
                       for value in flags.values())):
            return None
        return {
            "schema_version": cls.PHASE_SCHEMA_VERSION, "kind": payload["kind"],
            "segment_number": payload["segment_number"],
            "planned_price_cents": payload["planned_price_cents"],
            "expense_snapshot_id": payload["expense_snapshot_id"],
            "planned_from_date": start.isoformat(), "planned_to_date": end.isoformat(),
            "timezone": timezone,
            "control_flags": {key: flags[key] for key in sorted(flags)},
        }

    @classmethod
    def normalize_result(cls, payload):
        base_fields = {
            "schema_version", "status", "source_as_of", "snapshot_refs",
            "baseline_profit_per_unit_rub", "candidate_profit_per_unit_rub",
            "delta_profit_per_unit_rub", "quantity_basis", "window",
            "quality_gates", "limitations", "outcome",
        }
        schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
        fields = base_fields if schema_version == 1 else base_fields | {"comparison"}
        statuses = {
            "READY", "WAITING_FOR_DATA", "INSUFFICIENT_DATA", "INCOMPARABLE",
            "NO_CLEAR_DIFFERENCE", "BETTER", "WORSE", "TIE",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] not in {1, cls.RESULT_SCHEMA_VERSION}
                or payload.get("status") not in statuses
                or payload.get("outcome") not in cls._OUTCOMES
                or payload.get("quantity_basis") not in {
                    "ORDERED_UNITS_WINDOW", "SOLD_UNITS_WINDOW",
                    "RETAINED_UNITS_EXACT_COHORT", None,
                }):
            return None
        as_of = cls._timestamp(payload.get("source_as_of"))
        refs = payload.get("snapshot_refs")
        if (as_of is None or not isinstance(refs, list) or not 1 <= len(refs) <= 10
                or any(not isinstance(ref, str) or cls._HEX_256.fullmatch(ref) is None for ref in refs)
                or len(set(refs)) != len(refs)):
            return None
        amounts = {}
        for key in ("baseline_profit_per_unit_rub", "candidate_profit_per_unit_rub",
                    "delta_profit_per_unit_rub"):
            amount = cls._money(payload.get(key), optional=True)
            if payload.get(key) is not None and amount is None:
                return None
            amounts[key] = amount
        if amounts["baseline_profit_per_unit_rub"] is not None and amounts[
            "candidate_profit_per_unit_rub"
        ] is not None:
            expected_delta = format((
                Decimal(amounts["candidate_profit_per_unit_rub"])
                - Decimal(amounts["baseline_profit_per_unit_rub"])
            ).quantize(Decimal("0.01")), ".2f")
            if amounts["delta_profit_per_unit_rub"] != expected_delta:
                return None
        elif amounts["delta_profit_per_unit_rub"] is not None:
            return None
        window = payload.get("window")
        if window is not None:
            if (not isinstance(window, dict)
                    or set(window) != {"from_date", "to_date", "timezone"}):
                return None
            start, end = cls._date(window.get("from_date")), cls._date(window.get("to_date"))
            try:
                ZoneInfo(window.get("timezone"))
            except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
                return None
            if start is None or end is None or start > end or (end - start).days + 1 > 28:
                return None
            if not isinstance(window.get("timezone"), str) or len(window["timezone"]) > 128:
                return None
            window = {"from_date": start.isoformat(), "to_date": end.isoformat(),
                      "timezone": window["timezone"]}
        gates = payload.get("quality_gates")
        if not isinstance(gates, list) or len(gates) > 32:
            return None
        normalized_gates = []
        for gate in gates:
            if (not isinstance(gate, dict) or set(gate) != {"gate", "status", "reason_code"}
                    or not isinstance(gate.get("gate"), str)
                    or cls._CODE.fullmatch(gate["gate"]) is None
                    or gate.get("status") not in {"PASS", "FAIL", "UNKNOWN", "WARNING"}
                    or not isinstance(gate.get("reason_code"), str)
                    or cls._CODE.fullmatch(gate["reason_code"]) is None):
                return None
            normalized_gates.append(dict(gate))
        limitations = payload.get("limitations")
        if (not isinstance(limitations, list) or len(limitations) > 32
                or any(not isinstance(item, str) or cls._CODE.fullmatch(item) is None
                       for item in limitations)
                or len(set(limitations)) != len(limitations)):
            return None
        normalized = {
            "schema_version": payload["schema_version"], "status": payload["status"],
            "source_as_of": as_of, "snapshot_refs": list(refs), **amounts,
            "quantity_basis": payload["quantity_basis"], "window": window,
            "quality_gates": normalized_gates, "limitations": list(limitations),
            "outcome": payload["outcome"],
        }
        if payload["schema_version"] == cls.RESULT_SCHEMA_VERSION:
            comparison = cls._normalize_experiment_comparison(payload.get("comparison"))
            if payload.get("comparison") is not None and comparison is None:
                return None
            if comparison is not None:
                expected_delta = (
                    Decimal(comparison["candidate"]["profit_per_unit_rub"])
                    - Decimal(comparison["baseline"]["profit_per_unit_rub"])
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if amounts["delta_profit_per_unit_rub"] != format(expected_delta, ".2f"):
                    return None
                baseline_profit = Decimal(comparison["baseline"]["profit_per_unit_rub"])
                expected_relative = None
                if baseline_profit > 0:
                    expected_relative = format(
                        (expected_delta / baseline_profit * Decimal("100")).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP,
                        ), ".2f",
                    )
                if comparison["relative_delta_percent"] != expected_relative:
                    return None
                expected_outcome, expected_status = (
                    ("NO_CLEAR_DIFFERENCE", "NO_CLEAR_DIFFERENCE")
                    if expected_delta == 0 or abs(expected_delta) < Decimal(comparison["decision_threshold_rub"])
                    else ("CANDIDATE_BETTER_IN_MODEL", "BETTER") if expected_delta > 0
                    else ("BASELINE_BETTER_IN_MODEL", "WORSE")
                )
                if (amounts["baseline_profit_per_unit_rub"]
                        != comparison["baseline"]["profit_per_unit_rub"]
                        or amounts["candidate_profit_per_unit_rub"]
                        != comparison["candidate"]["profit_per_unit_rub"]
                        or payload["quantity_basis"] != "SOLD_UNITS_WINDOW"
                        or payload["outcome"] != expected_outcome
                        or payload["status"] != expected_status
                        or window != comparison["candidate"]["window"]):
                    return None
            elif any(amounts[key] is not None for key in amounts) or payload["quantity_basis"] is not None:
                return None
            normalized["comparison"] = comparison
        return normalized

    @classmethod
    def _normalize_experiment_comparison(cls, value):
        fields = {
            "schema_version", "decision_threshold_rub", "profit_basis",
            "relative_delta_percent", "baseline_collection_hash", "candidate_collection_hash",
            "baseline_readiness_revision", "candidate_readiness_revision",
            "baseline_phase_state_revision", "candidate_phase_state_revision",
            "baseline_control_event_revision", "candidate_control_event_revision",
            "baseline", "candidate",
        }
        if (not isinstance(value, dict) or set(value) != fields
                or type(value.get("schema_version")) is not int
                or value["schema_version"] != 1
                or value.get("profit_basis") != "FINANCE_NET_MINUS_SAVED_COGS_AND_TAX"):
            return None
        threshold = cls._money(value.get("decision_threshold_rub"), nonnegative=True)
        if threshold is None or Decimal(threshold) < Decimal("0.01"):
            return None
        for key in ("baseline_collection_hash", "candidate_collection_hash"):
            if (not isinstance(value.get(key), str)
                    or cls._HEX_256.fullmatch(value[key]) is None):
                return None
        for key in (
            "baseline_readiness_revision", "candidate_readiness_revision",
            "baseline_phase_state_revision", "candidate_phase_state_revision",
            "baseline_control_event_revision", "candidate_control_event_revision",
        ):
            minimum = 0 if key.endswith("control_event_revision") else 1
            if type(value.get(key)) is not int or value[key] < minimum:
                return None
        relative = cls._money(value.get("relative_delta_percent"), optional=True)
        if value.get("relative_delta_percent") is not None and relative is None:
            return None
        phases = {}
        money_keys = {
            "gross_seller_revenue_rub", "discount_points_rub", "finance_net_rub",
            "acquiring_rub", "commission_rub", "logistics_rub", "other_fees_rub",
            "performance_cpc_reconciliation_rub", "saved_cogs_per_unit_rub",
            "saved_cogs_total_rub", "tax_rub", "profit_before_tax_rub",
            "profit_total_rub", "profit_per_unit_rub",
        }
        nonnegative_money = {
            "gross_seller_revenue_rub", "discount_points_rub",
            "performance_cpc_reconciliation_rub", "saved_cogs_per_unit_rub",
            "saved_cogs_total_rub", "tax_rub",
        }
        phase_fields = {
            "window", "source_as_of", "seller_price_cents", "quantity_basis",
            "sold_units", "tax_mode", "tax_rate_percent",
            "minimum_tax_rate_percent", *money_keys,
        }
        for name in ("baseline", "candidate"):
            phase = value.get(name)
            if not isinstance(phase, dict) or set(phase) != phase_fields:
                return None
            window = phase.get("window")
            if (not isinstance(window, dict)
                    or set(window) != {"from_date", "to_date", "timezone"}):
                return None
            start, end = cls._date(window.get("from_date")), cls._date(window.get("to_date"))
            try:
                ZoneInfo(window.get("timezone"))
            except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
                return None
            as_of = cls._timestamp(phase.get("source_as_of"))
            price = phase.get("seller_price_cents")
            units = phase.get("sold_units")
            if (start is None or end is None or start > end or (end - start).days < 2
                    or (end - start).days >= 28
                    or not isinstance(window.get("timezone"), str)
                    or len(window["timezone"]) > 128
                    or as_of is None or type(price) is not int or price < 1
                    or phase.get("quantity_basis") != "SOLD_UNITS_WINDOW"
                    or type(units) is not int or not 1 <= units <= 1_000_000_000
                    or phase.get("tax_mode") not in {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}):
                return None
            tax_rate = cls._money(phase.get("tax_rate_percent"), optional=True, nonnegative=True)
            minimum_tax_rate = cls._money(
                phase.get("minimum_tax_rate_percent"), optional=True, nonnegative=True,
            )
            if ((phase["tax_mode"] == "NONE" and (tax_rate is not None or minimum_tax_rate is not None))
                    or (phase["tax_mode"] == "USN_INCOME" and (tax_rate is None or minimum_tax_rate is not None))
                    or (phase["tax_mode"] == "USN_INCOME_MINUS_EXPENSES"
                        and (tax_rate is None or minimum_tax_rate is None))):
                return None
            money = {}
            for key in money_keys:
                normalized_amount = cls._money(
                    phase.get(key), nonnegative=key in nonnegative_money,
                )
                if normalized_amount is None:
                    return None
                money[key] = normalized_amount
            if Decimal(money["saved_cogs_total_rub"]) != (
                Decimal(money["saved_cogs_per_unit_rub"]) * units
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
                return None
            if Decimal(money["profit_before_tax_rub"]) != (
                Decimal(money["finance_net_rub"]) - Decimal(money["saved_cogs_total_rub"])
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
                return None
            if Decimal(money["profit_total_rub"]) != (
                Decimal(money["profit_before_tax_rub"]) - Decimal(money["tax_rub"])
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
                return None
            if Decimal(money["profit_per_unit_rub"]) != (
                Decimal(money["profit_total_rub"]) / units
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
                return None
            phases[name] = {
                "window": {"from_date": start.isoformat(), "to_date": end.isoformat(),
                           "timezone": window["timezone"]},
                "source_as_of": as_of, "seller_price_cents": price,
                "quantity_basis": phase["quantity_basis"], "sold_units": units,
                "tax_mode": phase["tax_mode"], "tax_rate_percent": tax_rate,
                "minimum_tax_rate_percent": minimum_tax_rate, **money,
            }
        if relative is not None and Decimal(phases["baseline"]["profit_per_unit_rub"]) <= 0:
            return None
        if phases["baseline"]["tax_mode"] != phases["candidate"]["tax_mode"]:
            return None
        if (phases["baseline"]["tax_rate_percent"] != phases["candidate"]["tax_rate_percent"]
                or phases["baseline"]["minimum_tax_rate_percent"]
                != phases["candidate"]["minimum_tax_rate_percent"]
                or phases["baseline"]["saved_cogs_per_unit_rub"]
                != phases["candidate"]["saved_cogs_per_unit_rub"]):
            return None
        if not cls._comparison_windows_match(phases["baseline"], phases["candidate"]):
            return None
        return {
            "schema_version": 1, "decision_threshold_rub": threshold,
            "profit_basis": "FINANCE_NET_MINUS_SAVED_COGS_AND_TAX",
            "relative_delta_percent": relative, **phases,
            "baseline_collection_hash": value["baseline_collection_hash"],
            "candidate_collection_hash": value["candidate_collection_hash"],
            "baseline_readiness_revision": value["baseline_readiness_revision"],
            "candidate_readiness_revision": value["candidate_readiness_revision"],
            "baseline_phase_state_revision": value["baseline_phase_state_revision"],
            "candidate_phase_state_revision": value["candidate_phase_state_revision"],
            "baseline_control_event_revision": value["baseline_control_event_revision"],
            "candidate_control_event_revision": value["candidate_control_event_revision"],
        }

    @classmethod
    def normalize_owner_decision(cls, payload):
        fields = {
            "schema_version", "decision_type", "result_phase_id", "result_revision",
            "selected_phase_id",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.OWNER_DECISION_SCHEMA_VERSION
                or payload.get("decision_type") not in cls._OWNER_DECISIONS
                or not isinstance(payload.get("result_phase_id"), str)
                or cls._HEX_128.fullmatch(payload["result_phase_id"]) is None
                or type(payload.get("result_revision")) is not int
                or not 1 <= payload["result_revision"] <= 20):
            return None
        selected = payload.get("selected_phase_id")
        requires_selected = payload["decision_type"] in {
            "KEEP_BASELINE_PRICE", "SELECT_EVALUATED_CANDIDATE",
        }
        if requires_selected:
            if not isinstance(selected, str) or cls._HEX_128.fullmatch(selected) is None:
                return None
        elif selected is not None:
            return None
        return {
            "schema_version": cls.OWNER_DECISION_SCHEMA_VERSION,
            "decision_type": payload["decision_type"],
            "result_phase_id": payload["result_phase_id"],
            "result_revision": payload["result_revision"],
            "selected_phase_id": selected,
        }

    @classmethod
    def _comparison_windows_match(cls, baseline, candidate):
        base_window, candidate_window = baseline["window"], candidate["window"]
        if base_window["timezone"] != candidate_window["timezone"]:
            return False
        base_start = date.fromisoformat(base_window["from_date"])
        base_end = date.fromisoformat(base_window["to_date"])
        candidate_start = date.fromisoformat(candidate_window["from_date"])
        candidate_end = date.fromisoformat(candidate_window["to_date"])
        base_days = (base_end - base_start).days + 1
        candidate_days = (candidate_end - candidate_start).days + 1
        if (base_end >= candidate_start or base_days != candidate_days
                or cls._weekday_counts(base_start, base_end)
                != cls._weekday_counts(candidate_start, candidate_end)):
            return False
        zone = ZoneInfo(base_window["timezone"])
        baseline_as_of = datetime.fromisoformat(baseline["source_as_of"].replace("Z", "+00:00"))
        candidate_as_of = datetime.fromisoformat(candidate["source_as_of"].replace("Z", "+00:00"))
        baseline_lag = (baseline_as_of.astimezone(zone).date() - base_end).days
        candidate_lag = (candidate_as_of.astimezone(zone).date() - candidate_end).days
        return baseline_lag >= 0 and candidate_lag >= 0 and abs(baseline_lag - candidate_lag) <= 1

    @staticmethod
    def _weekday_counts(start, end):
        counts = [0] * 7
        current = start
        while current <= end:
            counts[current.weekday()] += 1
            current = date.fromordinal(current.toordinal() + 1)
        return tuple(counts)

    @classmethod
    def normalize_phase_collection(cls, payload, scope):
        """Normalize one private, bounded collection projection for a phase."""
        fields = {
            "schema_version", "experiment_id", "phase_id", "observation_id",
            "identity", "status", "collected_at", "window", "seller_price_cents",
            "source_statuses", "metrics", "price_history_verified", "limitations",
            "budget",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != 1
                or any(not isinstance(payload.get(key), str)
                       or cls._HEX_128.fullmatch(payload[key]) is None
                       for key in ("experiment_id", "phase_id", "observation_id"))
                or payload.get("status") not in {"COMPLETE", "PARTIAL", "UNAVAILABLE", "CANCELLED"}
                or payload.get("price_history_verified") is not False):
            return None
        identity = cls.normalize_identity(payload.get("identity"), scope)
        collected_at = cls._timestamp(payload.get("collected_at"))
        if identity is None or collected_at is None:
            return None
        window = payload.get("window")
        if (not isinstance(window, dict)
                or set(window) != {"from_date", "to_date", "timezone", "date_basis"}
                or window.get("date_basis") != "SOURCE_CALENDAR_DATE"
                or not isinstance(window.get("timezone"), str)
                or len(window["timezone"]) > 128):
            return None
        start = cls._date(window.get("from_date"))
        end = cls._date(window.get("to_date"))
        try:
            ZoneInfo(window["timezone"])
        except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
            return None
        if start is None or end is None or start > end or (end - start).days + 1 > 28:
            return None
        price = payload.get("seller_price_cents")
        if type(price) is not int or not 1 <= price <= UnitPriceTariffResolver.MAX_PRICE_CENTS:
            return None

        source_statuses = payload.get("source_statuses")
        source_keys = {
            "FINANCE", "PERFORMANCE", "RETURNS", "OWNER_DECLARED_PRICE",
            "SELLER_PRICE", "ANALYTICS", "TARIFF", "COST", "TAX",
        }
        source_values = {"COMPLETE", "PARTIAL", "SOURCE_UNAVAILABLE", "RATE_LIMITED", "NOT_REQUESTED"}
        if not isinstance(source_statuses, list) or not 1 <= len(source_statuses) <= len(source_keys):
            return None
        normalized_sources = []
        seen_sources = set()
        for source in source_statuses:
            if (not isinstance(source, dict)
                    or set(source) != {"source_key", "status", "reason_code"}
                    or source.get("source_key") not in source_keys
                    or source.get("source_key") in seen_sources
                    or source.get("status") not in source_values
                    or not isinstance(source.get("reason_code"), str)
                    or cls._CODE.fullmatch(source["reason_code"]) is None):
                return None
            seen_sources.add(source["source_key"])
            normalized_sources.append(dict(source))
        if normalized_sources != sorted(normalized_sources, key=lambda item: item["source_key"]):
            return None

        metric_keys = {
            "gross_seller_revenue", "discount_points", "finance_net", "acquiring",
            "commission", "logistics", "other_fees", "cpc_spend",
            "successful_sale_units", "ordered_units", "delivered_units",
            "cancelled_units", "returned_units", "buyout_rate_percent",
            "buyout_sample_size",
        }
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict) or set(metrics) != metric_keys:
            return None
        normalized_metrics = {}
        for key in (
            "gross_seller_revenue", "discount_points", "finance_net", "acquiring",
            "commission", "logistics", "other_fees", "cpc_spend",
        ):
            amount = cls._money(metrics.get(key), optional=True)
            if metrics.get(key) is not None and amount is None:
                return None
            normalized_metrics[key] = amount
        for key in (
            "successful_sale_units", "ordered_units", "delivered_units",
            "cancelled_units", "returned_units", "buyout_sample_size",
        ):
            count = metrics.get(key)
            if count is not None and (type(count) is not int or not 0 <= count <= 1_000_000_000):
                return None
            normalized_metrics[key] = count
        buyout = cls._money(metrics.get("buyout_rate_percent"), optional=True, nonnegative=True)
        if (metrics.get("buyout_rate_percent") is not None
                and (buyout is None or Decimal(buyout) > Decimal("100.00"))):
            return None
        normalized_metrics["buyout_rate_percent"] = buyout

        limitations = payload.get("limitations")
        if (not isinstance(limitations, list) or len(limitations) > 32
                or any(not isinstance(item, str) or cls._CODE.fullmatch(item) is None
                       for item in limitations)
                or limitations != sorted(set(limitations))):
            return None
        budget = payload.get("budget")
        budget_keys = {
            "http_attempts", "http_attempt_limit", "elapsed_seconds",
            "time_budget_seconds", "reason_code",
        }
        if (not isinstance(budget, dict) or set(budget) != budget_keys
                or any(type(budget.get(key)) is not int or budget[key] < 0
                       for key in budget_keys - {"reason_code"})
                or budget["http_attempts"] > budget["http_attempt_limit"]
                or budget["http_attempt_limit"] > 128
                or budget["time_budget_seconds"] > 120
                or budget["elapsed_seconds"] > budget["time_budget_seconds"]
                or not isinstance(budget.get("reason_code"), str)
                or cls._CODE.fullmatch(budget["reason_code"]) is None):
            return None
        return {
            "schema_version": 1,
            "experiment_id": payload["experiment_id"], "phase_id": payload["phase_id"],
            "observation_id": payload["observation_id"], "identity": identity,
            "status": payload["status"], "collected_at": collected_at,
            "window": {"from_date": start.isoformat(), "to_date": end.isoformat(),
                       "timezone": window["timezone"], "date_basis": "SOURCE_CALENDAR_DATE"},
            "seller_price_cents": price, "source_statuses": normalized_sources,
            "metrics": normalized_metrics, "price_history_verified": False,
            "limitations": list(limitations), "budget": dict(budget),
        }

    @classmethod
    def _money(cls, value, *, optional=False, nonnegative=False):
        if value is None and optional:
            return None
        if not isinstance(value, str) or cls._MONEY.fullmatch(value) is None:
            return None
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
        if (not amount.is_finite() or abs(amount) > cls.MAX_AMOUNT
                or nonnegative and amount < 0):
            return None
        return format(amount.quantize(Decimal("0.01")), ".2f")

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.isoformat() == value else None

    @staticmethod
    def _timestamp(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        from datetime import datetime, timezone
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _title(value):
        if not isinstance(value, str) or "\x00" in value:
            return None
        normalized = " ".join(value.split())
        return normalized if 1 <= len(normalized) <= 80 else None
