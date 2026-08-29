def build_period_profit_expense_operation_selection(review, selected_type_ids):
    source = dict(review or {})
    if source.get("status") != "PERIOD_PROFIT_EXPENSE_OPERATION_REVIEW_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_REVIEW_REQUIRED", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_UNAVAILABLE"}

    requested = []
    for value in selected_type_ids or []:
        try:
            requested.append(int(value))
        except (TypeError, ValueError):
            return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_TYPE_ID_INVALID", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_UNAVAILABLE"}
    if not requested:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_REQUIRED", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_UNAVAILABLE"}

    by_id = {int(row.get("type_id")): dict(row) for row in source.get("operations", []) if isinstance(row, dict) and row.get("type_id") is not None}
    selected_ids = sorted(set(requested))
    missing = [value for value in selected_ids if value not in by_id]
    if missing:
        return {"error": True, "code": "PERIOD_PROFIT_EXPENSE_OPERATION_NOT_IN_REVIEW", "status": "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_UNAVAILABLE", "missing_type_ids": missing}

    selected = []
    for type_id in selected_ids:
        row = by_id[type_id]
        selected.append({"type_id": type_id, "name": row.get("name"), "description": row.get("description"), "source": row.get("source")})

    return {
        "error": False,
        "status": "PERIOD_PROFIT_EXPENSE_OPERATION_SELECTION_READY",
        "scope": source.get("scope"),
        "selected_type_ids": selected_ids,
        "selected_operations": selected,
        "selected_operation_names": [row.get("name") for row in selected if row.get("name")],
        "human_selected": True,
        "authorization_required": True,
        "mapping_authorized": False,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }
