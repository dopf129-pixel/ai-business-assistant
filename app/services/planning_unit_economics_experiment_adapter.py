"""Strict allowlists for durable unit-economics experiment projections."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.unit_economics_experiment_plan_service import (
    UnitEconomicsExperimentPlanService,
)


class PlanningUnitEconomicsExperimentAdapter:
    """Normalize storage contracts; raw source responses never cross this boundary."""

    SNAPSHOT_SCHEMA_VERSION = 1
    EXPERIMENT_SCHEMA_VERSION = 1
    EXPERIMENT_PLAN_SCHEMA_VERSION = 1
    PHASE_SCHEMA_VERSION = 1
    RESULT_SCHEMA_VERSION = 1
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
        fields = {
            "schema_version", "status", "source_as_of", "snapshot_refs",
            "baseline_profit_per_unit_rub", "candidate_profit_per_unit_rub",
            "delta_profit_per_unit_rub", "quantity_basis", "window",
            "quality_gates", "limitations", "outcome",
        }
        statuses = {
            "READY", "WAITING_FOR_DATA", "INSUFFICIENT_DATA", "INCOMPARABLE",
            "NO_CLEAR_DIFFERENCE", "BETTER", "WORSE", "TIE",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.RESULT_SCHEMA_VERSION
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
        return {
            "schema_version": cls.RESULT_SCHEMA_VERSION, "status": payload["status"],
            "source_as_of": as_of, "snapshot_refs": list(refs), **amounts,
            "quantity_basis": payload["quantity_basis"], "window": window,
            "quality_gates": normalized_gates, "limitations": list(limitations),
            "outcome": payload["outcome"],
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
