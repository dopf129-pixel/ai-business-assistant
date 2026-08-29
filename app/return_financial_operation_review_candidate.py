def build_return_financial_operation_review_candidate(catalog, selected_type_ids):
    source = dict(catalog or {})
    if source.get("status") != "RETURN_FINANCIAL_OPERATION_CATALOG_READY" or source.get("error") is not False:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_CATALOG_REQUIRED",
            "status": "RETURN_FINANCIAL_OPERATION_REVIEW_CANDIDATE_UNAVAILABLE",
        }

    selected = []
    requested_ids = []
    for value in selected_type_ids or []:
        try:
            requested_ids.append(int(value))
        except (TypeError, ValueError):
            return {
                "error": True,
                "code": "RETURN_FINANCIAL_OPERATION_TYPE_ID_INVALID",
                "status": "RETURN_FINANCIAL_OPERATION_REVIEW_CANDIDATE_UNAVAILABLE",
            }

    by_id = {int(row.get("type_id")): dict(row) for row in source.get("operations", []) if isinstance(row, dict) and row.get("type_id") is not None}
    missing = sorted(set(requested_ids) - set(by_id))
    if missing:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_TYPE_ID_NOT_IN_CATALOG",
            "status": "RETURN_FINANCIAL_OPERATION_REVIEW_CANDIDATE_UNAVAILABLE",
            "missing_type_ids": missing,
        }

    for type_id in sorted(set(requested_ids)):
        row = by_id[type_id]
        selected.append({
            "type_id": type_id,
            "name": row.get("name"),
            "description": row.get("description"),
            "source": row.get("source"),
        })

    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_REVIEW_CANDIDATE_READY",
        "selected_operations": selected,
        "selected_type_ids": [row["type_id"] for row in selected],
        "selected_operation_names": [row.get("name") for row in selected if row.get("name")],
        "review_required": True,
        "mapping_authorized": False,
        "returns_profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }
