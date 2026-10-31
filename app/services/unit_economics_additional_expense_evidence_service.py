"""Resolve storage and mapped additional expenses without double counting."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re


class UnitEconomicsAdditionalExpenseEvidenceService:
    """Project normalized storage/service components into disjoint evidence buckets."""

    _BUILTIN_COMPONENTS = {
        "FINANCE_PAID_STORAGE": ("STORAGE", "STORAGE"),
        "FINANCE_PLACEMENT": ("PLACEMENT", "PLACEMENT"),
        "FINANCE_CROSS_DOCKING": ("CROSS_DOCKING", "CROSS_DOCKING"),
    }
    _RELEVANT_CATEGORIES = frozenset({"STORAGE", "PLACEMENT", "CROSS_DOCKING", "OTHER_SERVICE"})
    _EXACT_ORIGINS = frozenset({"OFFICIAL_SOURCE", "DETERMINISTIC_DERIVATION"})
    _FINAL_CORRECTIONS = frozenset({"FINAL_AS_OF", "CORRECTED_AS_OF"})
    _MONEY_QUANTUM = Decimal("0.01")
    _MAX_AMOUNT = Decimal("999999999999.99")
    _MAX_COMPONENTS = 64
    _SAFE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    _SAFE_MAPPING_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

    @classmethod
    def resolve(cls, snapshot, additional_service_mapping=None):
        """Return category and ownership evidence; no unit rate is inferred here."""
        normalized = cls._snapshot(snapshot)
        if normalized is None:
            return cls._error("UNIT_ECONOMICS_ADDITIONAL_EXPENSE_SNAPSHOT_INVALID")
        mapping = cls._mapping(additional_service_mapping)
        if mapping is None:
            return cls._error("UNIT_ECONOMICS_ADDITIONAL_EXPENSE_MAPPING_INVALID")

        buckets = {
            "STORAGE": cls._empty_bucket("STORAGE"),
            "PLACEMENT": cls._empty_bucket("PLACEMENT"),
            "CROSS_DOCKING": cls._empty_bucket("CROSS_DOCKING"),
        }
        for service_key in mapping["service_keys"]:
            buckets[f"ADDITIONAL_SERVICE:{service_key}"] = cls._empty_bucket(
                f"ADDITIONAL_SERVICE:{service_key}"
            )
        unmapped = cls._empty_bucket("UNMAPPED_ADDITIONAL_SERVICE")
        unmapped["status"] = "MISSING"
        invalid_component_count = 0
        out_of_scope_component_count = 0

        for component in normalized["components"]:
            key = component.get("component_key")
            category = component.get("category")
            if key in cls._BUILTIN_COMPONENTS:
                expected_category, bucket_key = cls._BUILTIN_COMPONENTS[key]
                bucket = buckets[bucket_key]
                allowed_categories = (
                    {None, expected_category}
                    if component.get("status") == "CONFIRMED_ZERO"
                    else {expected_category}
                )
                if category not in allowed_categories:
                    cls._add_invalid(bucket, "COMPONENT_CATEGORY_KEY_MISMATCH")
                    invalid_component_count += 1
                    continue
            elif key in mapping["by_component_key"]:
                expected_category = "OTHER_SERVICE"
                service_key = mapping["by_component_key"][key]
                bucket = buckets[f"ADDITIONAL_SERVICE:{service_key}"]
                allowed_categories = (
                    {None, expected_category}
                    if component.get("status") == "CONFIRMED_ZERO"
                    else {expected_category}
                )
                if category not in allowed_categories:
                    cls._add_invalid(bucket, "COMPONENT_CATEGORY_KEY_MISMATCH")
                    invalid_component_count += 1
                    continue
            elif category in cls._RELEVANT_CATEGORIES:
                bucket = unmapped
                if category in {"STORAGE", "PLACEMENT", "CROSS_DOCKING"}:
                    unmapped["category"] = "UNMAPPED_STORAGE_OR_SERVICE"
                    unmapped["reasons"].add("BUILTIN_COMPONENT_KEY_MISMATCH")
                if bucket["status"] != "CONFLICT":
                    bucket["status"] = "UNMAPPED"
                bucket["reasons"].add("EXPLICIT_COMPONENT_MAPPING_REQUIRED")
                bucket["component_count"] += 1
                amount = cls._amount(component.get("normalized_expense_rub"))
                if amount is not None and component.get("status") == "PRESENT":
                    bucket["observed"] += amount
                    bucket["unknown"] += amount
                invalid_component_count += 1
                continue
            else:
                out_of_scope_component_count += 1
                continue

            cls._record_component(
                bucket,
                component,
                delegated=bucket["category"] == "CROSS_DOCKING",
            )

        for bucket in buckets.values():
            cls._finalize_bucket(bucket, cls._snapshot_complete(normalized))
        cls._finalize_bucket(unmapped, cls._snapshot_complete(normalized))
        status = "COMPLETE" if cls._snapshot_complete(normalized) and not invalid_component_count else (
            "PARTIAL" if normalized["coverage"]["received_pages"] else "UNAVAILABLE"
        )
        if any(bucket["status"] == "CONFLICT" for bucket in buckets.values()) or unmapped["status"] == "CONFLICT":
            status = "CONFLICT"
        if status == "COMPLETE" and (
            unmapped["status"] == "UNMAPPED"
            or any(
                bucket["status"] in {"MISSING", "PARTIAL", "UNMAPPED"}
                for key, bucket in buckets.items()
                if key != "CROSS_DOCKING"
            )
        ):
            status = "PARTIAL"

        output_buckets = {key: cls._public_bucket(value) for key, value in buckets.items()}
        if unmapped["status"] != "MISSING":
            output_buckets["UNMAPPED_ADDITIONAL_SERVICE"] = cls._public_bucket(unmapped)
        return {
            "error": False,
            "status": status,
            "identity": normalized["identity"],
            "source_window": normalized["source_window"],
            "source_revision": normalized["source_revision"],
            "source_complete": cls._snapshot_complete(normalized),
            "mapping_id": mapping["mapping_id"],
            "categories": output_buckets,
            "out_of_scope_component_count": out_of_scope_component_count,
            "invalid_component_count": invalid_component_count,
            "full_cost_coverage_confirmed": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _snapshot(cls, value):
        if (
            not isinstance(value, dict)
            or value.get("error") is not False
            or value.get("source") != "SELLER_FINANCE"
            or not cls._valid_identity(value.get("identity"))
            or not cls._valid_window(value.get("source_window"))
            or not isinstance(value.get("coverage"), dict)
            or type(value["coverage"].get("complete")) is not bool
            or type(value["coverage"].get("received_pages")) is not int
            or not isinstance(value.get("source_revision"), str)
            or re.fullmatch(r"[0-9a-f]{32}", value["source_revision"]) is None
            or not isinstance(value.get("components"), list)
            or len(value["components"]) > cls._MAX_COMPONENTS
            or any(not isinstance(row, dict) for row in value["components"])
            or value.get("completeness") not in {
                "COMPLETE", "CONFIRMED_ZERO", "PARTIAL", "UNAVAILABLE", "UNKNOWN", "CONFLICT",
            }
        ):
            return None
        return {
            "identity": dict(value["identity"]),
            "source_window": dict(value["source_window"]),
            "source_revision": value.get("source_revision"),
            "coverage": dict(value["coverage"]),
            "completeness": value["completeness"],
            "components": [dict(row) for row in value["components"]],
        }

    @classmethod
    def _mapping(cls, value):
        if value is None:
            return {"mapping_id": None, "by_component_key": {}, "service_keys": [], "component_keys": set()}
        required = {
            "error", "status", "schema_version", "mapping_id", "mapping_authorized",
            "financial_evidence_mapping_allowed", "automatic_activation_allowed",
            "profit_adjustment_allowed", "immutable_artifact", "components",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("error") is not False
            or value.get("status") != "UNIT_ECONOMICS_ADDITIONAL_SERVICE_MAPPING_READY"
            or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
            or not cls._safe_mapping_id(value.get("mapping_id"))
            or value.get("mapping_authorized") is not True
            or value.get("financial_evidence_mapping_allowed") is not True
            or value.get("automatic_activation_allowed") is not False
            or value.get("profit_adjustment_allowed") is not False
            or value.get("immutable_artifact") is not True
            or not isinstance(value.get("components"), list)
            or not 1 <= len(value["components"]) <= cls._MAX_COMPONENTS
        ):
            return None
        by_component_key = {}
        service_keys = set()
        for row in value["components"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"component_key", "category", "service_key"}
                or not cls._safe_key(row.get("component_key"))
                or row["component_key"] in cls._BUILTIN_COMPONENTS
                or row.get("category") != "OTHER_SERVICE"
                or not cls._safe_key(row.get("service_key"))
                or row["component_key"] in by_component_key
            ):
                return None
            by_component_key[row["component_key"]] = row["service_key"]
            service_keys.add(row["service_key"])
        canonical = json.dumps(
            {
                "error": False,
                "status": "UNIT_ECONOMICS_ADDITIONAL_SERVICE_MAPPING_READY",
                "schema_version": 1,
                "mapping_authorized": True,
                "financial_evidence_mapping_allowed": True,
                "automatic_activation_allowed": False,
                "profit_adjustment_allowed": False,
                "immutable_artifact": True,
                "components": [
                    {"component_key": key, "category": "OTHER_SERVICE", "service_key": service}
                    for key, service in sorted(by_component_key.items())
                ],
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        expected_mapping_id = "unit-economics-additional-service-map:" + hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
        if value["mapping_id"] != expected_mapping_id:
            return None
        return {
            "mapping_id": value["mapping_id"],
            "by_component_key": by_component_key,
            "service_keys": sorted(service_keys),
            "component_keys": set(by_component_key),
        }

    @classmethod
    def _record_component(cls, bucket, component, delegated=False):
        bucket["component_count"] += 1
        status = component.get("status")
        if status == "CONFIRMED_ZERO":
            bucket["exact_known"] = True
            bucket["window_known"] = True
            return
        if status != "PRESENT":
            bucket["status"] = cls._merge_status(
                bucket["status"], "CONFLICT" if status == "CONFLICT" else "PARTIAL"
            )
            bucket["reasons"].add(status or "COMPONENT_STATUS_UNKNOWN")
            return
        amount = cls._amount(component.get("normalized_expense_rub"))
        if amount is None:
            cls._add_invalid(bucket, "NORMALIZED_AMOUNT_INVALID")
            return
        bucket["observed"] += amount
        if delegated:
            bucket["delegated"] += amount
            bucket["reasons"].add("EXISTING_CROSS_DOCKING_MODEL_OWNS_CATEGORY")
            return
        ownership = component.get("ownership")
        attribution = component.get("attribution")
        origin = component.get("origin")
        recurrence = component.get("recurrence")
        correction_state = component.get("correction_state")
        metadata_known = (
            ownership in {"ADDITIONAL", "BASE_ALREADY_INCLUDED", "RECONCILIATION_ONLY", "UNATTRIBUTED", "UNKNOWN"}
            and attribution in {"EXACT_SKU", "EXACT_COHORT", "WINDOW_ALLOCATION", "UNATTRIBUTED"}
            and origin in {"OFFICIAL_SOURCE", "DETERMINISTIC_DERIVATION", "OWNER_ASSUMPTION", "UNVERIFIED_SOURCE"}
            and recurrence in {"RECURRING", "ONE_OFF", "UNKNOWN"}
            and correction_state in {"FINAL_AS_OF", "CORRECTED_AS_OF", "OPEN", "UNKNOWN"}
        )
        if not metadata_known:
            bucket["unknown"] += amount
            bucket["reasons"].add("OWNERSHIP_OR_PROVENANCE_UNKNOWN")
            bucket["status"] = cls._merge_status(bucket["status"], "PARTIAL")
            return
        if ownership == "BASE_ALREADY_INCLUDED":
            bucket["base"] += amount
            bucket["reasons"].add("ALREADY_INCLUDED_IN_BASE_COST")
            bucket["exact_known"] = bucket["exact_known"] or attribution == "EXACT_SKU"
            bucket["window_known"] = bucket["window_known"] or attribution == "WINDOW_ALLOCATION"
            return
        if ownership == "RECONCILIATION_ONLY":
            bucket["reconciliation"] += amount
            bucket["reasons"].add("RECONCILIATION_ONLY")
            bucket["exact_known"] = bucket["exact_known"] or attribution == "EXACT_SKU"
            bucket["window_known"] = bucket["window_known"] or attribution == "WINDOW_ALLOCATION"
            return
        if ownership == "UNATTRIBUTED" or attribution == "UNATTRIBUTED":
            bucket["account"] += amount
            bucket["reasons"].add("ACCOUNT_LEVEL_NOT_ALLOCATED")
            bucket["status"] = cls._merge_status(bucket["status"], "PARTIAL")
            return
        if ownership == "UNKNOWN" or origin not in cls._EXACT_ORIGINS:
            bucket["unknown"] += amount
            bucket["reasons"].add("OWNERSHIP_OR_PROVENANCE_UNKNOWN")
            bucket["status"] = cls._merge_status(bucket["status"], "PARTIAL")
            return
        if recurrence == "ONE_OFF":
            bucket["one_off"] += amount
            bucket["reasons"].add("ONE_OFF_NOT_A_RECURRING_UNIT_RATE")
            if amount < 0:
                bucket["reasons"].add("ONE_OFF_CREDIT_NOT_A_RECURRING_RATE")
            return
        if recurrence != "RECURRING" or correction_state not in cls._FINAL_CORRECTIONS:
            bucket["unknown"] += amount
            bucket["reasons"].add("RECURRENCE_OR_CORRECTION_UNCONFIRMED")
            bucket["status"] = cls._merge_status(bucket["status"], "PARTIAL")
            return
        if amount < 0:
            bucket["unknown"] += amount
            bucket["reasons"].add("NET_CREDIT_REQUIRES_REVIEW")
            bucket["status"] = cls._merge_status(bucket["status"], "PARTIAL")
            return
        if attribution == "EXACT_SKU":
            bucket["exact"] += amount
            bucket["exact_known"] = True
            return
        if attribution == "WINDOW_ALLOCATION":
            bucket["window"] += amount
            bucket["window_known"] = True
            bucket["reasons"].add("WINDOW_ALLOCATION_REQUIRES_EXPLICIT_MODEL")
            return
        bucket["unknown"] += amount
        bucket["reasons"].add("EXACT_SKU_ATTRIBUTION_REQUIRED")
        bucket["status"] = cls._merge_status(bucket["status"], "PARTIAL")

    @classmethod
    def _finalize_bucket(cls, bucket, source_complete):
        if bucket["status"] == "UNMAPPED":
            return
        if bucket["status"] == "CONFLICT":
            return
        if not source_complete or bucket["status"] == "PARTIAL":
            bucket["status"] = "PARTIAL"
        elif bucket["component_count"] == 0:
            bucket["status"] = "MISSING"
        elif bucket["category"] == "CROSS_DOCKING":
            bucket["status"] = "DELEGATED"
        elif bucket["observed"] == 0 and not any((
            bucket["exact"], bucket["window"], bucket["base"], bucket["account"],
            bucket["one_off"], bucket["reconciliation"], bucket["unknown"],
        )):
            bucket["status"] = "CONFIRMED_ZERO"
        else:
            bucket["status"] = "PRESENT"
        if bucket["status"] != "PRESENT" and bucket["status"] != "CONFIRMED_ZERO":
            if bucket["status"] == "MISSING":
                return
        if bucket["category"] == "CROSS_DOCKING":
            bucket["exact_result"] = None
            bucket["window_result"] = None
        elif bucket["status"] in {"PRESENT", "CONFIRMED_ZERO"}:
            bucket["exact_result"] = (
                cls._money(bucket["exact"]) if bucket["exact_known"] else None
            )
            bucket["window_result"] = (
                cls._money(bucket["window"]) if bucket["window_known"] else None
            )
        else:
            bucket["exact_result"] = None
            bucket["window_result"] = None

    @staticmethod
    def _empty_bucket(key):
        return {
            "category": key,
            "status": "MISSING",
            "component_count": 0,
            "observed": Decimal("0.00"),
            "exact": Decimal("0.00"),
            "window": Decimal("0.00"),
            "base": Decimal("0.00"),
            "account": Decimal("0.00"),
            "one_off": Decimal("0.00"),
            "reconciliation": Decimal("0.00"),
            "unknown": Decimal("0.00"),
            "delegated": Decimal("0.00"),
            "exact_known": False,
            "window_known": False,
            "reasons": set(),
            "exact_result": None,
            "window_result": None,
        }

    @classmethod
    def _add_invalid(cls, bucket, reason):
        bucket["status"] = "CONFLICT"
        bucket["reasons"].add(reason)

    @staticmethod
    def _public_bucket(bucket):
        is_missing = bucket["status"] == "MISSING"
        money = UnitEconomicsAdditionalExpenseEvidenceService._money
        return {
            "category": bucket["category"],
            "status": bucket["status"],
            "component_count": bucket["component_count"],
            "observed_expense_rub": None if is_missing else money(bucket["observed"]),
            "exact_sku_recurring_expense_rub": bucket["exact_result"],
            "window_allocation_candidate_rub": bucket["window_result"],
            "base_included_expense_rub": None if is_missing else money(bucket["base"]),
            "account_level_expense_rub": None if is_missing else money(bucket["account"]),
            "one_off_expense_rub": None if is_missing else money(bucket["one_off"]),
            "reconciliation_only_expense_rub": None if is_missing else money(bucket["reconciliation"]),
            "unclassified_expense_rub": None if is_missing else money(bucket["unknown"]),
            "delegated_to_existing_model_rub": (
                money(bucket["delegated"])
                if bucket["category"] == "CROSS_DOCKING" and not is_missing
                else None
            ),
            "unit_amount_rub": None,
            "denominator_units": None,
            "denominator_kind": None,
            "reasons": sorted(bucket["reasons"]),
        }

    @classmethod
    def _snapshot_complete(cls, snapshot):
        return (
            snapshot["coverage"]["complete"] is True
            and snapshot["completeness"] in {"COMPLETE", "CONFIRMED_ZERO"}
        )

    @classmethod
    def _amount(cls, value):
        if not isinstance(value, str) or len(value) > 32:
            return None
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
        if not amount.is_finite() or abs(amount) > cls._MAX_AMOUNT:
            return None
        try:
            return amount.quantize(cls._MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None

    @staticmethod
    def _valid_identity(value):
        keys = {"owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema"}
        return (
            isinstance(value, dict)
            and set(value) == keys
            and all(isinstance(value.get(key), str) and value[key].strip() for key in keys)
            and value.get("sale_schema") in {"FBO", "FBS"}
        )

    @staticmethod
    def _valid_window(value):
        if (
            not isinstance(value, dict)
            or set(value) != {"from_date", "to_date", "date_basis", "timezone"}
            or not all(isinstance(item, str) and item for item in value.values())
        ):
            return False
        try:
            start = date.fromisoformat(value["from_date"])
            end = date.fromisoformat(value["to_date"])
        except ValueError:
            return False
        return (
            start.isoformat() == value["from_date"]
            and end.isoformat() == value["to_date"]
            and start <= end
        )

    @classmethod
    def _safe_key(cls, value):
        return isinstance(value, str) and cls._SAFE_KEY_RE.fullmatch(value) is not None

    @classmethod
    def _safe_mapping_id(cls, value):
        return (
            isinstance(value, str)
            and cls._SAFE_MAPPING_ID_RE.fullmatch(value) is not None
        )

    @staticmethod
    def _merge_status(current, incoming):
        order = {"PRESENT": 0, "CONFIRMED_ZERO": 0, "MISSING": 0, "PARTIAL": 1, "CONFLICT": 2}
        return incoming if order.get(incoming, 0) > order.get(current, 0) else current

    @classmethod
    def _money(cls, value):
        amount = value.quantize(cls._MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        return format(abs(amount) if amount.is_zero() else amount, ".2f")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
