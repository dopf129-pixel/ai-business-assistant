ALLOWED_DECISIONS = {"AUTHORIZE", "REJECT"}


def build_return_financial_operation_selection_authorization(selection, decision):
    source = dict(selection or {})
    if source.get("status") != "RETURN_FINANCIAL_OPERATION_SELECTION_READY" or source.get("error") is not False:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_SELECTION_REQUIRED",
            "status": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZATION_UNAVAILABLE",
        }

    choice = str(decision or "").strip().upper()
    if choice not in ALLOWED_DECISIONS:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZATION_DECISION_INVALID",
            "status": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZATION_UNAVAILABLE",
        }

    authorized = choice == "AUTHORIZE"
    return {
        "error": False,
        "status": (
            "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED"
            if authorized else
            "RETURN_FINANCIAL_OPERATION_SELECTION_REJECTED"
        ),
        "decision": choice,
        "selected_type_ids": list(source.get("selected_type_ids") or []),
        "selected_operations": [dict(row) for row in source.get("selected_operations") or [] if isinstance(row, dict)],
        "selected_operation_names": list(source.get("selected_operation_names") or []),
        "human_selected": source.get("human_selected") is True,
        "mapping_authorized": authorized,
        "financial_evidence_mapping_allowed": authorized,
        "returns_profit_adjustment_allowed": False,
        "automatic_activation_allowed": False,
        "read_only": True,
        "executed": False,
    }
