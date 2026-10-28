"""Normalize bounded expense evidence without persisting source identifiers."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UnitEconomicsExpenseNormalizer:
    """Pure, fail-closed normalization for one exact source window and SKU."""

    SCHEMA_VERSION = 1
    MAX_OPERATIONS = 10_000
    MAX_COMPONENTS = 20_000
    MAX_COMPONENTS_PER_OPERATION = 100
    MAX_COMPONENT_GROUPS = 64
    MAX_MAP_FIELDS = 128
    MAX_TEXT_LENGTH = 128
    MAX_AMOUNT = Decimal("999999999999.99")
    MONEY_QUANTUM = Decimal("0.01")

    IDENTITY_KEYS = frozenset({
        "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
    })
    CATEGORY_VALUES = frozenset({
        "COMMISSION", "ACQUIRING", "LOGISTICS", "ADVERTISING_CPC",
        "ADVERTISING_CPO", "ADVERTISING_OTHER", "STORAGE", "PLACEMENT", "CROSS_DOCKING",
        "RETURN_NONBUYOUT", "RETURN_INVENTORY_LOSS", "OTHER_SERVICE",
    })
    OWNERSHIP_VALUES = frozenset({
        "BASE_ALREADY_INCLUDED", "ADDITIONAL", "RECONCILIATION_ONLY",
        "UNATTRIBUTED", "UNKNOWN",
    })
    ATTRIBUTION_VALUES = frozenset({
        "EXACT_SKU", "EXACT_COHORT", "WINDOW_ALLOCATION", "UNATTRIBUTED",
    })
    ORIGIN_VALUES = frozenset({
        "OFFICIAL_SOURCE", "DETERMINISTIC_DERIVATION", "OWNER_ASSUMPTION",
        "UNVERIFIED_SOURCE",
    })
    RECURRENCE_VALUES = frozenset({"RECURRING", "ONE_OFF", "UNKNOWN"})
    CORRECTION_VALUES = frozenset({"FINAL_AS_OF", "CORRECTED_AS_OF", "OPEN", "UNKNOWN"})
    ALLOWED_STOP_REASONS = frozenset({"END_OF_DATA", "CONFIRMED_EMPTY"})
    _SAFE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    _SAFE_METHOD_RE = re.compile(r"^[A-Za-z0-9_./-]{1,96}$")
    _SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
    _SAFE_COHORT_REF_RE = re.compile(r"^[0-9a-f]{64}$")

    @classmethod
    def normalize(cls, evidence):
        """Return only allowlisted aggregates; raw operation/part IDs stay transient."""
        if (
            not isinstance(evidence, dict)
            or type(evidence.get("schema_version")) is not int
            or evidence.get("schema_version") != cls.SCHEMA_VERSION
            or len(evidence) > cls.MAX_MAP_FIELDS
        ):
            return cls._error("UNIT_ECONOMICS_EVIDENCE_SCHEMA_UNSUPPORTED")

        identity = cls._identity(evidence.get("identity"))
        source = evidence.get("source")
        source_method = evidence.get("source_method")
        source_contract = evidence.get("source_contract_version")
        cohort_ref = evidence.get("cohort_ref")
        window = cls._window(evidence.get("source_window"))
        received_at = cls._timestamp(evidence.get("received_at"))
        as_of = cls._timestamp(evidence.get("as_of"), allow_unknown=True)
        coverage = cls._coverage(evidence.get("coverage"))
        operations = evidence.get("operations")
        expected = cls._expected_keys(evidence.get("expected_component_keys", []))
        if (
            identity is None or not isinstance(source, str) or source not in {
                "SELLER_FINANCE", "PERFORMANCE", "SUPPLY_ACT", "DERIVED", "OWNER_INPUT",
            }
            or not cls._safe_method(source_method)
            or not isinstance(source_contract, str)
            or cls._SAFE_VERSION_RE.fullmatch(source_contract) is None
            or window is None or received_at is None or as_of is None or coverage is None
            or not isinstance(operations, list) or len(operations) > cls.MAX_OPERATIONS
            or expected is None
            or cohort_ref is not None and not cls._safe_cohort_ref(cohort_ref)
        ):
            return cls._error("UNIT_ECONOMICS_EVIDENCE_INVALID")

        unique_parts = {}
        conflicts = set()
        duplicate_count = 0
        invalid_rows = 0
        missing_identity_rows = 0
        identity_mismatch_rows = 0
        component_count = 0
        unknown_field_count = cls._unknown_fields(
            evidence,
            {"schema_version", "identity", "source", "source_method", "source_contract_version",
             "source_window", "received_at", "as_of", "coverage", "operations",
             "expected_component_keys", "cohort_ref"},
        )

        for operation in operations:
            if not isinstance(operation, dict):
                invalid_rows += 1
                continue
            if len(operation) > 32:
                invalid_rows += 1
                continue
            unknown_field_count += cls._unknown_fields(
                operation, {"operation_id", "identity", "components"},
            )
            operation_id = cls._bounded_text(operation.get("operation_id"), 128)
            row_identity = cls._identity(operation.get("identity"))
            parts = operation.get("components")
            if (
                operation_id is None or not isinstance(parts, list)
                or len(parts) > cls.MAX_COMPONENTS_PER_OPERATION
            ):
                invalid_rows += 1
                continue
            if row_identity is None:
                missing_identity_rows += len(parts)
                continue
            if row_identity != identity:
                identity_mismatch_rows += len(parts)
                continue

            for part in parts:
                component_count += 1
                if component_count > cls.MAX_COMPONENTS:
                    return cls._error("UNIT_ECONOMICS_COMPONENT_LIMIT_EXCEEDED")
                if isinstance(part, dict) and len(part) > 32:
                    invalid_rows += 1
                    continue
                normalized = cls._component(part)
                if normalized is None:
                    invalid_rows += 1
                    if isinstance(part, dict):
                        unknown_field_count += cls._unknown_fields(
                            part, cls._component_input_fields(),
                        )
                    continue
                if isinstance(part, dict):
                    unknown_field_count += cls._unknown_fields(
                        part, cls._component_input_fields(),
                    )
                part_id = cls._bounded_text(part.get("component_id"), 128)
                dedup_key = (operation_id, part_id)
                previous = unique_parts.get(dedup_key)
                if previous is None:
                    unique_parts[dedup_key] = normalized
                elif previous == normalized:
                    duplicate_count += 1
                else:
                    conflicts.add(dedup_key)

        component_groups = {}
        group_metadata_conflicts = set()
        for dedup_key, component in unique_parts.items():
            key = component["component_key"]
            group = component_groups.setdefault(key, {
                "category": component["category"],
                "ownership": component["ownership"],
                "attribution": component["attribution"],
                "origin": component["origin"],
                "recurrence": component["recurrence"],
                "correction_state": component["correction_state"],
                "signed_amount": Decimal("0.00"),
                "count": 0,
                "conflicted": False,
            })
            group["count"] += 1
            if dedup_key in conflicts:
                group["conflicted"] = True
                continue
            if any(group[field] != component[field] for field in (
                "category", "ownership", "attribution", "origin", "recurrence", "correction_state",
            )):
                group["conflicted"] = True
                group_metadata_conflicts.add(key)
                continue
            group["signed_amount"] += Decimal(component["signed_source_amount_rub"])

        if len(set(expected) | set(component_groups)) > cls.MAX_COMPONENT_GROUPS:
            return cls._error("UNIT_ECONOMICS_COMPONENT_GROUP_LIMIT_EXCEEDED")

        normalized_components = []
        for key in sorted(set(expected) | set(component_groups)):
            group = component_groups.get(key)
            if group is None:
                status = (
                    "CONFIRMED_ZERO"
                    if coverage["complete"] and not invalid_rows
                    and not missing_identity_rows and not identity_mismatch_rows
                    else "PARTIAL"
                )
                normalized_components.append({
                    "component_key": key,
                    "category": None,
                    "status": status,
                    "signed_source_amount_rub": "0.00" if status == "CONFIRMED_ZERO" else None,
                    "normalized_expense_rub": "0.00" if status == "CONFIRMED_ZERO" else None,
                    "ownership": "UNKNOWN",
                    "attribution": "UNATTRIBUTED",
                    "origin": None,
                    "recurrence": "UNKNOWN",
                    "correction_state": "UNKNOWN",
                    "component_count": 0,
                })
                continue
            status = "CONFLICT" if group["conflicted"] else "PRESENT"
            signed = group["signed_amount"].quantize(cls.MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            normalized_components.append({
                "component_key": key,
                "category": group["category"],
                "status": status,
                "signed_source_amount_rub": None if status == "CONFLICT" else cls._money_text(signed),
                "normalized_expense_rub": None if status == "CONFLICT" else cls._money_text(-signed),
                "ownership": group["ownership"] if not group["conflicted"] else "UNKNOWN",
                "attribution": group["attribution"] if not group["conflicted"] else "UNATTRIBUTED",
                "origin": group["origin"] if not group["conflicted"] else None,
                "recurrence": group["recurrence"] if not group["conflicted"] else "UNKNOWN",
                "correction_state": group["correction_state"] if not group["conflicted"] else "UNKNOWN",
                "component_count": group["count"],
            })

        unique_count = len(unique_parts)
        part_conflict_keys = {
            unique_parts[key]["component_key"] for key in conflicts if key in unique_parts
        }
        conflict_count = len(conflicts) + len(group_metadata_conflicts - part_conflict_keys)
        coverage_complete = (
            coverage["complete"] and invalid_rows == 0 and missing_identity_rows == 0
            and identity_mismatch_rows == 0 and conflict_count == 0
        )
        coverage_status = (
            "CONFLICT" if conflict_count or identity_mismatch_rows
            else "PARTIAL" if not coverage_complete and (coverage["received_pages"] or operations)
            else "UNAVAILABLE" if not coverage["received_pages"] and not coverage["source_complete"]
            else "CONFIRMED_ZERO" if coverage_complete and not unique_parts
            else "COMPLETE" if coverage_complete
            else "UNKNOWN"
        )
        ownership_ledger = cls._ownership_ledger(normalized_components)
        result = {
            "error": False,
            "schema_version": cls.SCHEMA_VERSION,
            "identity": identity,
            "source": source,
            "source_method": source_method,
            "source_contract_version": source_contract,
            "source_window": window,
            "received_at": received_at,
            "as_of": as_of,
            "completeness": coverage_status,
            "components": normalized_components,
            "ownership_ledger": ownership_ledger,
            "coverage": {
                **coverage,
                "status": coverage_status,
                "complete": coverage_complete,
                "input_operation_count": len(operations),
                "accepted_component_rows": unique_count,
                "duplicate_rows_ignored": duplicate_count,
                "conflict_count": conflict_count,
                "invalid_rows": invalid_rows,
                "missing_identity_rows": missing_identity_rows,
                "identity_mismatch_rows": identity_mismatch_rows,
                "unknown_field_count": unknown_field_count,
            },
        }
        if cohort_ref is not None:
            result["cohort_ref"] = cohort_ref
        result["source_revision"] = cls._fingerprint(result)
        return result

    @classmethod
    def _component(cls, value):
        if not isinstance(value, dict):
            return None
        component_id = cls._bounded_text(value.get("component_id"), 128)
        key = value.get("component_key")
        category = value.get("category")
        ownership = value.get("ownership")
        attribution = value.get("attribution")
        origin = value.get("origin")
        recurrence = value.get("recurrence")
        correction_state = value.get("correction_state")
        signed_amount = cls._amount(value.get("signed_source_amount_rub"))
        if (
            component_id is None or not cls._safe_key(key)
            or category not in cls.CATEGORY_VALUES
            or ownership not in cls.OWNERSHIP_VALUES
            or attribution not in cls.ATTRIBUTION_VALUES
            or origin not in cls.ORIGIN_VALUES
            or recurrence not in cls.RECURRENCE_VALUES
            or correction_state not in cls.CORRECTION_VALUES
            or signed_amount is None
            or (attribution == "UNATTRIBUTED" and ownership == "ADDITIONAL")
        ):
            return None
        return {
            "component_id": component_id,
            "component_key": key,
            "category": category,
            "signed_source_amount_rub": cls._money_text(signed_amount),
            "ownership": ownership,
            "attribution": attribution,
            "origin": origin,
            "recurrence": recurrence,
            "correction_state": correction_state,
        }

    @classmethod
    def _identity(cls, value):
        if not isinstance(value, dict) or set(value) != cls.IDENTITY_KEYS:
            return None
        result = {}
        for key in sorted(cls.IDENTITY_KEYS):
            item = cls._bounded_text(value.get(key), 128)
            if item is None:
                return None
            result[key] = item
        if result["sale_schema"] not in {"FBO", "FBS"}:
            return None
        return result

    @classmethod
    def _window(cls, value):
        if not isinstance(value, dict) or set(value) != {"from_date", "to_date", "date_basis", "timezone"}:
            return None
        start = cls._date(value.get("from_date"))
        end = cls._date(value.get("to_date"))
        basis = cls._bounded_text(value.get("date_basis"), 64)
        zone = cls._bounded_text(value.get("timezone"), 64)
        if start is None or end is None or start > end or not cls._safe_key(basis) or zone is None:
            return None
        if zone != "UNKNOWN":
            try:
                ZoneInfo(zone)
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                return None
        return {
            "from_date": start.isoformat(), "to_date": end.isoformat(),
            "date_basis": basis, "timezone": zone,
        }

    @classmethod
    def _coverage(cls, value):
        required = {"requested_pages", "received_pages", "has_more", "stop_reason", "source_complete"}
        if not isinstance(value, dict) or set(value) != required:
            return None
        requested = value.get("requested_pages")
        received = value.get("received_pages")
        has_more = value.get("has_more")
        source_complete = value.get("source_complete")
        stop_reason = value.get("stop_reason")
        if (
            type(requested) is not int or not 0 <= requested <= 10_000
            or type(received) is not int or not 0 <= received <= requested
            or type(has_more) is not bool or type(source_complete) is not bool
            or not cls._safe_key(stop_reason) or len(stop_reason) > 48
        ):
            return None
        complete = (
            source_complete and requested > 0 and received == requested and has_more is False
            and stop_reason in cls.ALLOWED_STOP_REASONS
        )
        return {
            "requested_pages": requested, "received_pages": received,
            "has_more": has_more, "stop_reason": stop_reason,
            "source_complete": source_complete, "complete": complete,
        }

    @classmethod
    def _expected_keys(cls, values):
        if not isinstance(values, list) or len(values) > cls.MAX_COMPONENTS:
            return None
        result = []
        for value in values:
            if not cls._safe_key(value) or value in result:
                return None
            result.append(value)
        return result

    @classmethod
    def _amount(cls, value):
        if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int, Decimal)):
            return None
        text = str(value).strip()
        if not text or len(text) > 64:
            return None
        try:
            amount = Decimal(text)
            if not amount.is_finite() or abs(amount) > cls.MAX_AMOUNT:
                return None
            return amount.quantize(cls.MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, OverflowError):
            return None

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
    def _timestamp(value, allow_unknown=False):
        if allow_unknown and value == "UNKNOWN":
            return "UNKNOWN"
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @classmethod
    def _bounded_text(cls, value, maximum=None):
        if (
            not isinstance(value, str) or not value.strip()
            or len(value) > (maximum or cls.MAX_TEXT_LENGTH)
        ):
            return None
        if any(ord(char) < 32 for char in value):
            return None
        return value.strip()

    @classmethod
    def _safe_method(cls, value):
        return isinstance(value, str) and cls._SAFE_METHOD_RE.fullmatch(value) is not None

    @classmethod
    def _safe_key(cls, value):
        return isinstance(value, str) and cls._SAFE_KEY_RE.fullmatch(value) is not None

    @classmethod
    def _safe_cohort_ref(cls, value):
        return (
            isinstance(value, str)
            and cls._SAFE_COHORT_REF_RE.fullmatch(value) is not None
        )

    @classmethod
    def _ownership_ledger(cls, components):
        ledger = {
            key: {"component_count": 0, "signed_source_amount_rub": "0.00", "normalized_expense_rub": "0.00"}
            for key in sorted(cls.OWNERSHIP_VALUES)
        }
        totals = {key: Decimal("0.00") for key in ledger}
        for component in components:
            ownership = component["ownership"]
            if component["status"] == "CONFLICT":
                continue
            signed = component["signed_source_amount_rub"]
            normalized = component["normalized_expense_rub"]
            if signed is None or normalized is None:
                continue
            ledger[ownership]["component_count"] += component["component_count"]
            totals[ownership] += Decimal(signed)
        for ownership in ledger:
            ledger[ownership]["signed_source_amount_rub"] = cls._money_text(totals[ownership])
            ledger[ownership]["normalized_expense_rub"] = cls._money_text(-totals[ownership])
        return ledger

    @classmethod
    def _fingerprint(cls, result):
        encoded = json.dumps(
            result, ensure_ascii=True, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _money_text(value):
        rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if rounded.is_zero():
            rounded = abs(rounded)
        return format(rounded, ".2f")

    @staticmethod
    def _unknown_fields(value, allowed):
        return sum(1 for key in value if key not in allowed)

    @staticmethod
    def _component_input_fields():
        return {
            "component_id", "component_key", "category", "signed_source_amount_rub",
            "ownership", "attribution", "origin", "recurrence", "correction_state",
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
