"""Build a bounded, read-only applicability view from unit-economics snapshots."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class UnitEconomicsReadinessViewService:
    """Project snapshot coverage without fetching, persisting, or changing evidence."""

    MAX_COMPONENTS = 64
    MAX_UNITS = 1_000_000_000
    MAX_AMOUNT = Decimal("999999999999.99")
    SOURCE_CODES = frozenset({
        "OZON_SELLER_FINANCE", "OZON_PERFORMANCE", "OZON_ANALYTICS",
        "OZON_SELLER_API", "CROSS_DOCKING_EVIDENCE", "OWNER_INPUT", "UNKNOWN",
    })
    APPLICABILITY_CODES = frozenset({
        "WINDOW_MODEL_INPUT", "RECONCILIATION_ONLY", "OUT_OF_SCOPE", "UNKNOWN",
    })
    SNAPSHOT_STATUSES = frozenset({
        "COMPLETE", "SHORT_HISTORY", "PARTIAL", "UNAVAILABLE", "INCOMPARABLE",
        "RATE_LIMITED", "TIME_BUDGET_EXHAUSTED", "REQUEST_BUDGET_EXHAUSTED",
    })
    COMPONENT_STATUSES = frozenset({"COMPLETE", "PARTIAL", "INCOMPARABLE"})
    _KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

    @classmethod
    def build(cls, snapshot, component_metadata=None):
        """Return a public projection. No source calls are made by this method."""
        validated = cls._validate_snapshot(snapshot)
        if validated is None:
            return cls._error("UNIT_ECONOMICS_READINESS_SNAPSHOT_INVALID")
        if component_metadata is None:
            component_metadata = {}
        if not isinstance(component_metadata, dict) or len(component_metadata) > cls.MAX_COMPONENTS:
            return cls._error("UNIT_ECONOMICS_READINESS_METADATA_INVALID")
        if any(key not in validated["components"] for key in component_metadata):
            return cls._error("UNIT_ECONOMICS_READINESS_METADATA_INVALID")

        rows = []
        for key in sorted(validated["components"]):
            evidence = validated["components"][key]
            metadata = cls._metadata(component_metadata.get(key))
            rows.append(cls._project_component(key, evidence, validated, metadata))

        counts = {status: 0 for status in ("INCLUDED", "EXCLUDED", "UNKNOWN")}
        for row in rows:
            counts[row["status"]] += 1
        overall = cls._overall_status(validated["coverage_status"], counts)
        return {
            "error": False,
            "schema_version": 1,
            "status": overall,
            "scope_kind": validated["scope_kind"],
            "window": validated["window"],
            "coverage_status": validated["coverage_status"],
            "coverage_complete": validated["coverage_complete"],
            "denominator": validated["denominator"],
            "component_counts": counts,
            "components": rows,
            "read_only": True,
            "api_calls": 0,
        }

    @classmethod
    def build_pair(cls, pair, reference_metadata=None, phase_metadata=None):
        """Project reference and phase independently; never merge their totals."""
        if (
            not isinstance(pair, dict)
            or pair.get("error") is not False
            or pair.get("combined") is not False
            or pair.get("comparison_eligibility") not in {"DENOMINATOR_COMPATIBLE", "INCOMPARABLE"}
            or not isinstance(pair.get("reference"), dict)
            or not isinstance(pair.get("phase"), dict)
            or pair["reference"].get("identity") != pair["phase"].get("identity")
        ):
            return cls._error("UNIT_ECONOMICS_READINESS_PAIR_INVALID")
        reference = cls.build(pair["reference"], reference_metadata)
        phase = cls.build(pair["phase"], phase_metadata)
        if reference.get("error") or phase.get("error"):
            return cls._error("UNIT_ECONOMICS_READINESS_PAIR_INVALID")
        if (
            reference["scope_kind"] != "REFERENCE_56_COMPLETED_LOCAL_DAYS"
            or phase["scope_kind"] != "EXPERIMENT_PHASE_WINDOW"
        ):
            return cls._error("UNIT_ECONOMICS_READINESS_PAIR_INVALID")
        overlaps = not (
            reference["window"]["to_date"] < phase["window"]["from_date"]
            or phase["window"]["to_date"] < reference["window"]["from_date"]
        )
        comparison_eligibility = (
            "INCOMPARABLE" if overlaps else pair["comparison_eligibility"]
        )
        return {
            "error": False,
            "status": "COMPLETE" if reference["status"] == phase["status"] == "COMPLETE" else "PARTIAL",
            "reference": reference,
            "phase": phase,
            "comparison_eligibility": comparison_eligibility,
            "comparison_reasons": ["WINDOWS_OVERLAP"] if overlaps else [],
            "combined": False,
            "read_only": True,
            "api_calls": 0,
        }

    @classmethod
    def _validate_snapshot(cls, value):
        if (
            not isinstance(value, dict)
            or value.get("error") is not False
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
        ):
            return None
        identity = value.get("identity")
        if (
            not isinstance(identity, dict)
            or set(identity) != {"owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema"}
            or any(not isinstance(item, str) or not item or len(item) > 128 for item in identity.values())
            or identity.get("sale_schema") not in {"FBO", "FBS"}
        ):
            return None
        if value.get("model_scope") != "WINDOW_COST_ALLOCATION":
            return None
        scope = value.get("scope_kind")
        if scope not in {"REFERENCE_56_COMPLETED_LOCAL_DAYS", "EXPERIMENT_PHASE_WINDOW"}:
            return None
        window = value.get("window")
        if not isinstance(window, dict) or set(window) != {"from_date", "to_date", "date_basis", "timezone"}:
            return None
        try:
            start = date.fromisoformat(window["from_date"])
            end = date.fromisoformat(window["to_date"])
        except (TypeError, ValueError):
            return None
        if (
            start > end or window.get("date_basis") != "LOCAL_CALENDAR_DAY"
            or not isinstance(window.get("timezone"), str) or not window["timezone"]
            or len(window["timezone"]) > 128
        ):
            return None
        as_of_raw = value.get("as_of_local_date")
        try:
            as_of = date.fromisoformat(as_of_raw)
        except (TypeError, ValueError):
            return None
        window_days = (end - start).days + 1
        if scope == "REFERENCE_56_COMPLETED_LOCAL_DAYS":
            if window_days != 56 or end.toordinal() != as_of.toordinal() - 1:
                return None
        elif window_days > 28 or end >= as_of:
            return None
        coverage = value.get("coverage")
        if (
            not isinstance(coverage, dict)
            or coverage.get("status") not in cls.SNAPSHOT_STATUSES
            or type(coverage.get("complete")) is not bool
            or coverage["complete"] != (coverage["status"] == "COMPLETE")
        ):
            return None
        denominator = value.get("denominator")
        if (
            not isinstance(denominator, dict)
            or type(denominator.get("units")) is not int
            or not 0 <= denominator["units"] <= cls.MAX_UNITS
            or denominator.get("kind") not in {None, "ORDERED_UNITS_WINDOW", "SOLD_UNITS_WINDOW"}
            or denominator["units"] > 0 and denominator.get("kind") is None
        ):
            return None
        components = value.get("components")
        if not isinstance(components, dict) or not 1 <= len(components) <= cls.MAX_COMPONENTS:
            return None
        normalized = {}
        for key, row in components.items():
            if not isinstance(key, str) or cls._KEY_RE.fullmatch(key) is None or not isinstance(row, dict):
                return None
            if row.get("status") not in cls.COMPONENT_STATUSES:
                return None
            amount = cls._money(row.get("observed_numerator_rub"))
            observed_units = row.get("observed_denominator_units")
            unit_amount = cls._money(row.get("unit_expense_rub"), optional=True)
            if (
                amount is None or type(observed_units) is not int
                or not 0 <= observed_units <= cls.MAX_UNITS
                or observed_units != denominator["units"]
                or row.get("rate_status") not in {"AVAILABLE", "ZERO_DENOMINATOR", "UNAVAILABLE"}
                or type(row.get("covered_days")) is not int or row["covered_days"] < 0
                or type(row.get("missing_segments")) is not int or row["missing_segments"] < 0
                or row["covered_days"] > window_days
                or row["status"] == "COMPLETE" and not coverage["complete"]
            ):
                return None
            if unit_amount is not None and denominator["units"] > 0:
                expected_rate = (Decimal(amount) / denominator["units"]).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                if Decimal(unit_amount) != expected_rate:
                    return None
            normalized[key] = {
                "evidence_status": row["status"],
                "amount_rub": amount,
                "observed_units": observed_units,
                "unit_amount_rub": unit_amount,
                "rate_status": row["rate_status"],
                "covered_days": row["covered_days"],
                "missing_segments": row["missing_segments"],
            }
        revision = value.get("source_revision")
        if not isinstance(revision, str) or re.fullmatch(r"[a-f0-9]{64}", revision) is None:
            return None
        return {
            "scope_kind": scope,
            "window": {key: window[key] for key in ("from_date", "to_date", "timezone")},
            "coverage_status": coverage["status"],
            "coverage_complete": coverage["complete"],
            "denominator": {"units": denominator["units"], "kind": denominator["kind"]},
            "components": normalized,
            "source_revision": revision,
        }

    @classmethod
    def _metadata(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"source", "applicability"}:
            return None
        source = value.get("source")
        applicability = value.get("applicability")
        if (
            source not in cls.SOURCE_CODES
            or applicability not in cls.APPLICABILITY_CODES
        ):
            return None
        return {"source": source, "applicability": applicability}

    @classmethod
    def _project_component(cls, key, evidence, snapshot, metadata):
        reason_codes = []
        source = metadata["source"] if metadata is not None else "UNKNOWN"
        applicability = metadata["applicability"] if metadata is not None else "UNKNOWN"
        status = "UNKNOWN"
        applied_amount = None
        applied_units = None
        unit_amount = None
        if metadata is None:
            reason_codes.append("SOURCE_METADATA_MISSING_OR_INVALID")
        elif source == "UNKNOWN" or applicability == "UNKNOWN":
            reason_codes.append("SOURCE_OR_APPLICABILITY_UNKNOWN")
        elif applicability in {"RECONCILIATION_ONLY", "OUT_OF_SCOPE"}:
            status = "EXCLUDED"
            reason_codes.append(
                "RECONCILIATION_ONLY" if applicability == "RECONCILIATION_ONLY" else "OUT_OF_SCOPE"
            )
        elif evidence["evidence_status"] != "COMPLETE":
            reason_codes.append("COMPONENT_EVIDENCE_" + evidence["evidence_status"])
        elif not snapshot["coverage_complete"]:
            reason_codes.append("SNAPSHOT_COVERAGE_" + snapshot["coverage_status"])
        elif snapshot["denominator"]["units"] <= 0 or evidence["rate_status"] == "ZERO_DENOMINATOR":
            reason_codes.append("ZERO_DENOMINATOR")
        elif evidence["unit_amount_rub"] is None:
            reason_codes.append("COMPONENT_RATE_UNAVAILABLE")
        else:
            status = "INCLUDED"
            applied_amount = evidence["amount_rub"]
            applied_units = snapshot["denominator"]["units"]
            unit_amount = evidence["unit_amount_rub"]
            if Decimal(applied_amount) == 0:
                reason_codes.append("COMPLETE_ZERO_AMOUNT")
        return {
            "component_key": key,
            "status": status,
            "source": source,
            "applicability": applicability,
            "evidence_status": evidence["evidence_status"],
            "observed_amount_rub": evidence["amount_rub"],
            "observed_units": evidence["observed_units"],
            "applied_amount_rub": applied_amount,
            "applied_units": applied_units,
            "unit_amount_rub": unit_amount,
            "reason_codes": sorted(set(reason_codes)),
        }

    @staticmethod
    def _overall_status(coverage_status, counts):
        if coverage_status == "INCOMPARABLE":
            return "INCOMPARABLE"
        if coverage_status == "UNAVAILABLE":
            return "UNAVAILABLE"
        if coverage_status in {"RATE_LIMITED", "TIME_BUDGET_EXHAUSTED", "REQUEST_BUDGET_EXHAUSTED"}:
            return coverage_status
        if coverage_status == "COMPLETE" and counts["UNKNOWN"] == 0:
            return "COMPLETE"
        return "PARTIAL"

    @classmethod
    def _money(cls, value, *, optional=False):
        if value is None and optional:
            return None
        if not isinstance(value, str) or len(value) > 32:
            return None
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
        if not amount.is_finite() or abs(amount) > cls.MAX_AMOUNT:
            return None
        return format(amount.quantize(Decimal("0.01")), ".2f")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "api_calls": 0}
