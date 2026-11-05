"""Build a privacy-safe detail/export view from an exact frozen experiment snapshot."""

import hashlib
import json
from decimal import Decimal, InvalidOperation

from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)
from services.planning_extended_scenario_adapter import PlanningExtendedScenarioAdapter


class UnitEconomicsExperimentSnapshotViewService:
    """Project persisted revisions without refreshing sources or recalculating economics."""

    MAX_VIEW_BYTES = 64 * 1024
    _IDENTITY_FIELDS = ("owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema")
    _INPUT_FIELDS = (
        "price", "cost", "commission_rate", "advertising_rate", "advertising_mode",
        "advertising_cost_per_unit", "discount_points_rate", "logistics_per_unit",
        "last_mile_per_unit", "acquiring_per_unit", "tax_mode", "tax_rate",
        "minimum_tax_rate", "cross_docking_per_unit",
    )
    _PROJECTION_MONEY_FIELDS = (
        "revenue", "discount_points", "taxable_revenue", "commission", "advertising",
        "fees", "profit_before_tax", "tax", "effective_tax_rate", "profit",
        "margin_percent", "cross_docking", "additional_unit_expenses",
    )
    _QUANTITY_METRICS = (
        "ordered_units", "delivered_units", "cancelled_units", "returned_units",
        "successful_sale_units", "buyout_rate_percent", "buyout_sample_size",
        "successful_unit_denominator", "sample_days",
    )
    _COMPLETENESS_KEYS = (
        "successful_units", "returns", "analytics", "window", "deduplication",
    )

    @classmethod
    def project(cls, frozen_snapshot):
        """Return the single safe read model used by detail UI and owner exports."""
        if (not isinstance(frozen_snapshot, dict) or frozen_snapshot.get("error") is not False
                or frozen_snapshot.get("read_only") is not True
                or frozen_snapshot.get("source_io") is not False):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_REQUIRED")
        experiment = frozen_snapshot.get("experiment")
        frozen = frozen_snapshot.get("frozen_inputs")
        if not isinstance(experiment, dict) or not isinstance(frozen, dict):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_INVALID")
        if set(frozen) != {"plan", "expense_snapshot", "tariff", "quantity"}:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_INVALID")
        if (experiment.get("status") not in {
                "DRAFT", "READY", "BASELINE_ACTIVE", "BASELINE_REVIEW",
                "CANDIDATE_READY", "CANDIDATE_ACTIVE", "CANDIDATE_REVIEW",
                "PAUSED", "CANCELLED", "COMPLETED", "ARCHIVED",
            }
                or type(experiment.get("state_revision")) is not int
                or experiment["state_revision"] < 1
                or type(experiment.get("result_revision")) is not int
                or experiment["result_revision"] < 0
                or type(experiment.get("schema_version")) is not int
                or experiment["schema_version"] != 1):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_INVALID")

        identity = {key: experiment.get(key) for key in cls._IDENTITY_FIELDS}
        if any(not isinstance(value, str) or not value for value in identity.values()):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_INVALID")
        scope = {"owner_id": identity["owner_id"], "store_id": identity["store_id"]}
        config = PlanningUnitEconomicsExperimentAdapter.normalize_experiment(
            experiment.get("config"), scope,
        )
        if (config is None or any(config["identity"].get(key) != identity[key]
                                  for key in cls._IDENTITY_FIELDS)
                or experiment.get("status") is None):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_SCOPE_MISMATCH")

        plan = frozen.get("plan")
        snapshot = frozen.get("expense_snapshot")
        if not isinstance(plan, dict) or not isinstance(snapshot, dict):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_INVALID")
        plan_payload = plan.get("payload")
        if (not isinstance(plan_payload, dict)
                or type(plan.get("revision")) is not int or plan["revision"] < 1
                or type(plan.get("schema_version")) is not int
                or plan.get("schema_version") != plan_payload.get("schema_version")):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_PLAN_INVALID")
        if (not isinstance(plan_payload, dict)
                or type(plan_payload.get("calculation_version")) is not int
                or plan.get("calculation_version") != plan_payload.get("calculation_version")
                or plan_payload.get("schema_version") not in {1, 2, 3, 4}
                or {1: 1, 2: 2, 3: 2, 4: 2}.get(plan_payload.get("schema_version"))
                != plan_payload.get("calculation_version")
                or not isinstance(plan_payload.get("items"), list)
                or not 1 <= len(plan_payload["items"]) <= 10
                or not isinstance(plan.get("document_id"), str)
                or plan.get("document_id") != config["source_references"]["plan"]["document_id"]
                or plan["revision"] != config["source_references"]["plan"]["revision"]):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_PLAN_INVALID")
        matching_items = [
            item for item in plan_payload["items"]
            if cls._plan_item_matches(item, identity)
        ]
        if len(matching_items) != 1:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_PLAN_SCOPE_MISMATCH")
        item = matching_items[0]
        economics, cost_basis = cls._economics_projection(
            item, identity,
            expected_expense_snapshot_id=config["source_references"]["expense_snapshot_id"],
        )
        if economics is None:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_ECONOMICS_INVALID")

        snapshot_payload = snapshot.get("payload")
        expense_identity = snapshot_payload.get("identity") if isinstance(snapshot_payload, dict) else None
        if snapshot.get("snapshot_id") != config["source_references"]["expense_snapshot_id"]:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_EXPENSE_REFERENCE_MISMATCH")
        readiness = PlanningUnitEconomicsExperimentAdapter.normalize_expense_snapshot(
            snapshot_payload, scope,
        )
        if (readiness is None or type(snapshot.get("schema_version")) is not int
                or snapshot.get("schema_version") != readiness["schema_version"]):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_EXPENSE_SNAPSHOT_INVALID")
        if readiness is None or any(
            readiness["identity"].get(key) != identity[key] for key in cls._IDENTITY_FIELDS
        ) or any(expense_identity.get(key) != identity[key] for key in cls._IDENTITY_FIELDS):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_EXPENSE_SCOPE_MISMATCH")
        coverage = cls._coverage_projection(readiness["readiness"])
        if coverage is None:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_COVERAGE_INVALID")

        tariff = cls._revision_projection(
            frozen.get("tariff"), config["source_references"]["tariff"], "tariff", identity,
        )
        if tariff is None:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_TARIFF_REVISION_MISMATCH")
        quantity = cls._quantity_projection(
            frozen.get("quantity"), config["source_references"]["observation"], identity,
        )
        if quantity is None:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_QUANTITY_REVISION_MISMATCH")

        snapshot_digest = hashlib.sha256(json.dumps(
            readiness["readiness"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        revisions = {
            "experiment_state_revision": experiment["state_revision"],
            "experiment_result_revision": experiment["result_revision"],
            "plan_schema_version": plan["schema_version"],
            "plan_calculation_version": plan_payload["calculation_version"],
            "plan_revision": plan["revision"],
            "expense_snapshot_schema_version": snapshot["schema_version"],
            "expense_snapshot_fingerprint": snapshot_digest,
            "tariff_revision": tariff["revision"],
            "quantity_result_revision": quantity["result_revision"],
        }
        limits = [
            "FROZEN_PLAN_PROJECTION_NOT_RECALCULATED",
            "SOURCES_NOT_RELOADED_FOR_DETAIL_OR_EXPORT",
            "PRICE_RESPONSE_AND_CAUSALITY_NOT_ESTIMATED",
        ]
        if coverage["coverage_complete"] is not True:
            limits.append("EXPENSE_COVERAGE_INCOMPLETE")
        if config["calculation_mode"] != cost_basis["mode"]:
            limits.append("PLAN_COST_BASIS_MODE_MISMATCH")
        if cost_basis["origin"] not in {"CONFIRMED", "MANUAL_ASSUMPTION"}:
            limits.append("EXTENDED_COST_BASIS_NOT_CONFIRMED")
        if cost_basis.get("reference_status") == "MISMATCH":
            limits.append("COST_BASIS_REFERENCE_DIFFERS_FROM_EXPERIMENT_SNAPSHOT")
        if "MANUAL_ASSUMPTION" in economics["input_origins"].values() or (
            cost_basis["origin"] == "MANUAL_ASSUMPTION"
        ):
            limits.append("OWNER_ASSUMPTIONS_PRESENT")
        if economics["projection"].get("available") is not True:
            limits.append("SAVED_PLAN_ECONOMICS_UNAVAILABLE")
        if quantity["status"] == "UNKNOWN":
            limits.append("QUANTITY_EVIDENCE_NOT_ATTACHED")
        view = {
            "schema_version": 1,
            "status": "AVAILABLE",
            "experiment_status": experiment["status"],
            "calculation_mode": config["calculation_mode"],
            "metric": config["metric"],
            "candidate_prices_rub": [cls._cents(item) for item in config["candidate_prices_cents"]],
            "decision_threshold_rub": config["decision_threshold_rub"],
            "planned_duration_days": config["planned_duration_days"],
            "control_flags": config["control_flags"],
            "revisions": revisions,
            "economics": economics,
            "expense_coverage": coverage,
            "tariff": tariff,
            "quantity_evidence": quantity,
            "cost_basis": cost_basis,
            "model_limits": sorted(set(limits)),
            "read_only": True,
            "source_io": False,
            "recalculated": False,
        }
        try:
            encoded = json.dumps(view, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_VIEW_INVALID")
        if len(encoded) > cls.MAX_VIEW_BYTES:
            return cls._error("UNIT_ECONOMICS_EXPERIMENT_VIEW_TOO_LARGE")
        return {"error": False, "view": view}

    @classmethod
    def _economics_projection(cls, item, identity, *, expected_expense_snapshot_id):
        if not isinstance(item, dict):
            return None, None
        inputs = item.get("inputs")
        projection = item.get("projection")
        provenance = item.get("provenance")
        if not isinstance(inputs, dict) or not isinstance(projection, dict) or not isinstance(provenance, dict):
            return None, None
        safe_inputs = {}
        for key in cls._INPUT_FIELDS:
            if key not in inputs:
                continue
            value = inputs[key]
            if key == "tax_mode":
                if value is None:
                    safe_inputs[key] = None
                elif value not in {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}:
                    return None, None
                else:
                    safe_inputs[key] = value
            elif key == "advertising_mode":
                if value not in {None, "ABSOLUTE_PER_SUCCESSFUL_UNIT"}:
                    return None, None
                safe_inputs[key] = value
            elif value is None:
                safe_inputs[key] = None
            else:
                safe = cls._decimal(value)
                if safe is None:
                    return None, None
                safe_inputs[key] = safe
        safe_projection = {}
        if type(projection.get("available")) is not bool:
            return None, None
        safe_projection["available"] = projection["available"]
        if "status" in projection:
            status = projection["status"]
            if not isinstance(status, str) or status not in {
                "READY", "INCOMPLETE_INPUTS", "SOURCE_UNAVAILABLE", "SOURCE_STALE",
                "UNSUPPORTED_SCHEME", "TARGET_NOT_CONFIRMED", "BUDGET_EXHAUSTED",
            }:
                return None, None
            safe_projection["status"] = status
        for field in ("missing_inputs", "invalid_inputs"):
            values = projection.get(field, [])
            if not isinstance(values, list) or len(values) > 20 or any(
                not isinstance(value, str) or value not in cls._INPUT_FIELDS for value in values
            ):
                return None, None
            safe_projection[field] = sorted(set(values))
        for field in cls._PROJECTION_MONEY_FIELDS:
            if field not in projection:
                continue
            value = projection[field]
            if value is None:
                safe_projection[field] = None
            else:
                safe = cls._decimal(value)
                if safe is None:
                    return None, None
                safe_projection[field] = safe
        tariff_origin = cls._safe_origin(provenance.get("commission_rate"))
        safe = {
            "inputs": safe_inputs,
            "input_origins": {
                "price": cls._safe_origin(provenance.get("price")),
                "cost": cls._safe_origin(provenance.get("cost")),
                "commission_rate": tariff_origin,
            },
            "projection": safe_projection,
        }
        expected_identity = {
            **identity,
            "sale_schema": identity["sale_schema"],
        }
        extended = item.get("extended_scenario")
        strict = item.get("strict_return_evidence")
        if extended is None:
            if strict is not None:
                return None, None
            basis = {
                "mode": "NOT_APPLIED", "origin": "NOT_APPLIED", "signature": None,
                "per_unit_rub": None, "scope": None, "numerator_rub": None,
                "denominator_units": None, "denominator_kind": None,
                "reference_status": "NOT_APPLICABLE",
            }
        else:
            projected = PlanningExtendedScenarioAdapter.project_extended(extended)
            if projected is None:
                return None, None
            normalized_strict = None
            if projected["calculation_mode"] == "STRICT_RETAINED_COHORT":
                normalized_strict = PlanningExtendedScenarioAdapter.project_strict_evidence(
                    strict, expected_identity,
                )
                if normalized_strict is None:
                    return None, None
            elif strict is not None:
                return None, None
            basis = PlanningExtendedScenarioAdapter.observation_cost_basis(
                projected, normalized_strict, expected_identity=expected_identity,
            )
            if basis is None:
                return None, None
            reference_status = (
                "MATCH"
                if projected["expense_snapshot_ref"] == expected_expense_snapshot_id
                else "MISMATCH"
            )
            if reference_status == "MISMATCH":
                basis["origin"] = "UNCONFIRMED"
            basis = {
                **basis,
                "reference_status": reference_status,
                "scope": projected["scope"],
                "numerator_rub": (
                    format(sum((Decimal(row["numerator_rub"]) for row in projected["components"]), Decimal("0")), "f")
                    if projected["calculation_mode"] == "WINDOW_COST_ALLOCATION"
                    else normalized_strict["strict_retained_cohort_loss"]["loss_pool_rub"]
                ),
                "denominator_units": projected["denominator_units"],
                "denominator_kind": projected["numerator_and_denominator_basis"]["denominator"],
            }
        safe["extended_cost_basis"] = basis
        return safe, basis

    @classmethod
    def _coverage_projection(cls, readiness):
        if not isinstance(readiness, dict):
            return None
        fields = ("status", "scope_kind", "window", "coverage_status", "coverage_complete",
                  "denominator", "component_counts", "components", "read_only", "api_calls")
        if any(field not in readiness for field in fields):
            return None
        components = []
        for row in readiness["components"]:
            if not isinstance(row, dict):
                return None
            components.append({
                "component_key": row["component_key"], "status": row["status"],
                "source": row["source"], "applicability": row["applicability"],
                "evidence_status": row["evidence_status"],
                "observed_amount_rub": row["observed_amount_rub"],
                "observed_units": row["observed_units"],
                "applied_amount_rub": row["applied_amount_rub"],
                "applied_units": row["applied_units"],
                "unit_amount_rub": row["unit_amount_rub"],
                "reason_codes": list(row["reason_codes"]),
            })
        return {
            "status": readiness["status"], "scope_kind": readiness["scope_kind"],
            "window": dict(readiness["window"]),
            "coverage_status": readiness["coverage_status"],
            "coverage_complete": readiness["coverage_complete"],
            "denominator": dict(readiness["denominator"]),
            "component_counts": dict(readiness["component_counts"]),
            "components": components,
            "read_only": readiness["read_only"], "api_calls": readiness["api_calls"],
        }

    @classmethod
    def _revision_projection(cls, frozen, reference, kind, identity):
        if reference is None:
            if frozen is not None:
                return None
            return {"revision": None, "status": "NOT_ATTACHED"}
        if not isinstance(frozen, dict) or not isinstance(reference, dict):
            return None
        if kind == "tariff":
            if (frozen.get("profile_id") != reference.get("profile_id")
                    or frozen.get("revision") != reference.get("revision")
                    or type(frozen.get("revision")) is not int):
                return None
            profile = frozen.get("profile")
            profile_identity = profile.get("identity") if isinstance(profile, dict) else None
            if (not isinstance(profile, dict) or not isinstance(profile.get("bands"), list)
                    or not isinstance(profile_identity, dict)
                    or any(profile_identity.get(key) != identity[key] for key in (
                        "product_id", "offer_id", "sku",
                    ))
                    or profile.get("sale_schema") != identity["sale_schema"]):
                return None
            return {
                "revision": frozen["revision"], "status": "ATTACHED",
                "origin": cls._safe_origin(profile.get("origin")),
                "confirmed_by_owner": profile.get("confirmed_by_owner") is True,
                "effective_from": profile.get("effective_from"),
                "effective_to": profile.get("effective_to"),
                "band_count": len(profile["bands"]),
            }
        return None

    @classmethod
    def _quantity_projection(cls, frozen, reference, identity):
        if reference is None:
            if frozen is not None:
                return None
            return {"status": "UNKNOWN", "result_revision": None,
                    "metrics": {}, "completeness": {}}
        if (not isinstance(frozen, dict) or frozen.get("observation_id") != reference.get("observation_id")
                or frozen.get("result_revision") != reference.get("result_revision")
                or type(frozen.get("result_revision")) is not int):
            return None
        observation = frozen.get("observation")
        result = frozen.get("result")
        if (not isinstance(observation, dict) or not isinstance(result, dict)
                or result.get("schema_version") != 1
                or result.get("status") not in {
                    "AVAILABLE", "INSUFFICIENT_DATA", "SOURCE_UNAVAILABLE", "STALE",
                    "INCOMPARABLE", "CONFLICT", "UNSUPPORTED_SCHEME",
                }):
            return None
        observed_identity = observation.get("identity")
        if (observation.get("store_id") != identity["store_id"]
                or not isinstance(observed_identity, dict)
                or any(observed_identity.get(key) != identity[key] for key in (
                    "product_id", "offer_id", "sku", "sale_schema",
                ))):
            return None
        raw_metrics = result.get("metrics")
        raw_completeness = result.get("completeness")
        if not isinstance(raw_metrics, dict) or not isinstance(raw_completeness, dict):
            return None
        metrics = {}
        for key in cls._QUANTITY_METRICS:
            if key not in raw_metrics:
                continue
            value = raw_metrics[key]
            if value is None or type(value) is int:
                metrics[key] = value
            elif isinstance(value, str) and key.endswith("percent"):
                safe = cls._decimal(value)
                if safe is None:
                    return None
                metrics[key] = safe
            else:
                return None
        completeness = {}
        for key in cls._COMPLETENESS_KEYS:
            if key in raw_completeness:
                value = raw_completeness[key]
                status = value.get("status") if isinstance(value, dict) else value
                if not isinstance(status, str) or len(status) > 64:
                    return None
                completeness[key] = status
        return {
            "status": result.get("status") if isinstance(result.get("status"), str) else "UNKNOWN",
            "result_revision": frozen["result_revision"],
            "window": dict(result.get("window", {})) if isinstance(result.get("window"), dict) else {},
            "metrics": metrics, "completeness": completeness,
        }

    @staticmethod
    def _plan_item_matches(item, identity):
        if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
            return False
        source = item["identity"]
        scheme = source.get("scheme")
        return (
            source.get("store_id") == identity["store_id"]
            and source.get("product_id") == identity["product_id"]
            and source.get("offer_id") == identity["offer_id"]
            and source.get("sku") == identity["sku"]
            and str(scheme or "FBO").upper() == identity["sale_schema"]
        )

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if not number.is_finite() or abs(number.adjusted()) > 12 or len(number.as_tuple().digits) > 28:
            return None
        return format(number, "f")

    @classmethod
    def _safe_origin(cls, value):
        text = value.casefold() if isinstance(value, str) else ""
        if "manual" in text or "owner" in text:
            return "MANUAL_ASSUMPTION"
        if "confirm" in text or "official" in text or "current_price_point" in text:
            return "CONFIRMED"
        return "UNKNOWN"

    @staticmethod
    def _cents(value):
        return format(Decimal(value) / Decimal("100"), ".2f")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
