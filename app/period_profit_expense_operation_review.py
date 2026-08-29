ALLOWED_SCOPES = {"ADVERTISING", "STORAGE"}


def build_period_profit_expense_operation_review(source_catalog, scope):
    source = dict(source_catalog or {})
    normalized_scope = str(scope or "").strip().upper()
    if normalized_scope not in ALLOWED_SCOPES:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_SCOPE_INVALID", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_REVIEW_UNAVAILABLE"}
    if source.get("status") != "RETURN_FINANCIAL_OPERATION_CATALOG_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_CATALOG_REQUIRED", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_REVIEW_UNAVAILABLE"}

    operations = []
    for row in source.get("operations", []):
        if not isinstance(row, dict) or row.get("type_id") is None:
            continue
        operations.append({
            "type_id": int(row.get("type_id")),
            "name": row.get("name"),
            "description": row.get("description"),
            "source": row.get("source"),
            "expense_related": None,
            "human_verification_required": True,
        })

    return {
        "error": False,
        "status": "PERIOD_PROFIT_EXPENSE_OPERATION_REVIEW_READY",
        "scope": normalized_scope,
        "operation_count": len(operations),
        "operations": operations,
        "human_verification_required": True,
        "automatic_classification_allowed": False,
        "mapping_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }
