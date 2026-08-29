import hashlib
import json


def build_return_financial_operation_authorized_mapping(authorization):
    source = dict(authorization or {})
    if (
        source.get("status") != "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED"
        or source.get("error") is not False
        or source.get("mapping_authorized") is not True
        or source.get("financial_evidence_mapping_allowed") is not True
    ):
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_AUTHORIZATION_REQUIRED",
            "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_UNAVAILABLE",
        }

    operations = [
        {
            "type_id": int(row.get("type_id")),
            "name": row.get("name"),
            "description": row.get("description"),
            "source": row.get("source"),
        }
        for row in source.get("selected_operations") or []
        if isinstance(row, dict) and row.get("type_id") is not None and row.get("name")
    ]
    operations.sort(key=lambda row: (row["type_id"], str(row["name"])))
    if not operations:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_EMPTY",
            "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_UNAVAILABLE",
        }

    canonical = json.dumps(operations, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    mapping_id = "return-financial-mapping:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_READY",
        "mapping_id": mapping_id,
        "operations": operations,
        "type_ids": [row["type_id"] for row in operations],
        "operation_names": [row["name"] for row in operations],
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "immutable_artifact": True,
        "persistent": False,
        "returns_profit_adjustment_allowed": False,
        "automatic_activation_allowed": False,
        "read_only": True,
        "executed": False,
    }
