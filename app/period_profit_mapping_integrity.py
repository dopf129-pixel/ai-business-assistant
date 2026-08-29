import hashlib
import json


SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}


def verify_period_profit_mapping_integrity(scope, mapping):
    normalized = str(scope or "").strip().upper()
    source = dict(mapping or {})
    if normalized not in SCOPES:
        return _result(False, "PERIOD_PROFIT_MAPPING_INTEGRITY_SCOPE_INVALID")

    operations = []
    for row in source.get("operations") or []:
        if not isinstance(row, dict) or row.get("type_id") is None or not row.get("name"):
            return _result(False, "PERIOD_PROFIT_MAPPING_INTEGRITY_OPERATIONS_INVALID")
        operations.append({
            "type_id": int(row.get("type_id")),
            "name": row.get("name"),
            "description": row.get("description"),
            "source": row.get("source"),
        })
    operations.sort(key=lambda row: (row["type_id"], str(row["name"])))
    if not operations:
        return _result(False, "PERIOD_PROFIT_MAPPING_INTEGRITY_OPERATIONS_EMPTY")

    if normalized == "RETURN":
        canonical_payload = operations
        prefix = "return-financial-mapping:"
    else:
        canonical_payload = {"scope": normalized, "operations": operations}
        prefix = f"period-profit-{normalized.lower()}-mapping:"

    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    expected_mapping_id = prefix + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    actual_mapping_id = source.get("mapping_id")
    valid = actual_mapping_id == expected_mapping_id
    return {
        "error": not valid,
        "status": "PERIOD_PROFIT_MAPPING_INTEGRITY_VALID" if valid else "PERIOD_PROFIT_MAPPING_INTEGRITY_INVALID",
        "code": None if valid else "PERIOD_PROFIT_MAPPING_ID_MISMATCH",
        "scope": normalized,
        "mapping_id": actual_mapping_id,
        "expected_mapping_id": expected_mapping_id,
        "integrity_valid": valid,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }


def _result(valid, code):
    return {
        "error": not valid,
        "status": "PERIOD_PROFIT_MAPPING_INTEGRITY_VALID" if valid else "PERIOD_PROFIT_MAPPING_INTEGRITY_INVALID",
        "code": None if valid else code,
        "integrity_valid": valid,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
