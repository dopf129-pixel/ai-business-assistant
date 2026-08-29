def build_return_financial_operation_selection_request(review_report, selected_type_ids):
    source = dict(review_report or {})
    if source.get("status") != "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_READY" or source.get("error") is not False:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_REQUIRED",
            "status": "RETURN_FINANCIAL_OPERATION_SELECTION_UNAVAILABLE",
        }

    requested = []
    for value in selected_type_ids or []:
        try:
            requested.append(int(value))
        except (TypeError, ValueError):
            return {
                "error": True,
                "code": "RETURN_FINANCIAL_OPERATION_SELECTION_TYPE_ID_INVALID",
                "status": "RETURN_FINANCIAL_OPERATION_SELECTION_UNAVAILABLE",
            }

    if not requested:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_SELECTION_REQUIRED",
            "status": "RETURN_FINANCIAL_OPERATION_SELECTION_UNAVAILABLE",
        }

    by_id = {
        int(row.get("type_id")): dict(row)
        for row in source.get("operations", [])
        if isinstance(row, dict) and row.get("type_id") is not None
    }
    selected_ids = sorted(set(requested))
    missing = [type_id for type_id in selected_ids if type_id not in by_id]
    if missing:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_SELECTION_NOT_IN_REPORT",
            "status": "RETURN_FINANCIAL_OPERATION_SELECTION_UNAVAILABLE",
            "missing_type_ids": missing,
        }

    selected = []
    for type_id in selected_ids:
        row = by_id[type_id]
        selected.append({
            "type_id": type_id,
            "name": row.get("name"),
            "description": row.get("description"),
            "source": row.get("source"),
        })

    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_SELECTION_READY",
        "selected_type_ids": selected_ids,
        "selected_operations": selected,
        "selected_operation_names": [row.get("name") for row in selected if row.get("name")],
        "human_selected": True,
        "authorization_required": True,
        "mapping_authorized": False,
        "returns_profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }
