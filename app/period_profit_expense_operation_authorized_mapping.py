import hashlib
import json

ALLOWED_DECISIONS = {"AUTHORIZE", "REJECT"}


def build_period_profit_expense_operation_authorization(selection, decision):
    source = dict(selection or {})
    if source.get("status") != "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_REQUIRED", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZATION_UNAVAILABLE"}
    choice = str(decision or "").strip().upper()
    if choice not in ALLOWED_DECISIONS:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZATION_DECISION_INVALID", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZATION_UNAVAILABLE"}
    authorized = choice == "AUTHORIZE"
    return {
        "error": False,
        "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED" if authorized else "PERIOD_PROFIT_EXPENSE_OPERATION_REJECTED",
        "scope": source.get("scope"),
        "decision": choice,
        "selected_type_ids": list(source.get("selected_type_ids") or []),
        "selected_operations": [dict(row) for row in source.get("selected_operations") or [] if isinstance(row, dict)],
        "mapping_authorized": authorized,
        "financial_evidence_mapping_allowed": authorized,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }


def build_period_profit_expense_operation_authorized_mapping(authorization):
    source = dict(authorization or {})
    if (
        source.get("status") != "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED"
        or source.get("error") is not False
        or source.get("mapping_authorized") is not True
        or source.get("financial_evidence_mapping_allowed") is not True
    ):
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZATION_REQUIRED", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_UNAVAILABLE"}

    operations = [
        {"type_id": int(row.get("type_id")), "name": row.get("name"), "description": row.get("description"), "source": row.get("source")}
        for row in source.get("selected_operations") or []
        if isinstance(row, dict) and row.get("type_id") is not None and row.get("name")
    ]
    operations.sort(key=lambda row: (row["type_id"], str(row["name"])))
    if not operations:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_EMPTY", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_UNAVAILABLE"}

    scope = str(source.get("scope") or "").upper()
    canonical = json.dumps({"scope": scope, "operations": operations}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    mapping_id = f"period-profit-{scope.lower()}-mapping:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "error": False,
        "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_READY",
        "scope": scope,
        "mapping_id": mapping_id,
        "operations": operations,
        "type_ids": [row["type_id"] for row in operations],
        "operation_names": [row["name"] for row in operations],
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "immutable_artifact": True,
        "persistent": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }
