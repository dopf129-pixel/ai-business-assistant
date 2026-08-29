ALLOWED_DECISIONS = {"AUTHORIZE", "REJECT"}


def build_return_financial_operation_authorization(candidate, decision):
    source = dict(candidate or {})
    if source.get("status") != "RETURN_FINANCIAL_OPERATION_REVIEW_CANDIDATE_READY" or source.get("error") is not False:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_REVIEW_CANDIDATE_REQUIRED",
            "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZATION_UNAVAILABLE",
        }

    choice = str(decision or "").strip().upper()
    if choice not in ALLOWED_DECISIONS:
        return {
            "error": True,
            "code": "RETURN_FINANCIAL_OPERATION_AUTHORIZATION_DECISION_INVALID",
            "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZATION_UNAVAILABLE",
        }

    authorized = choice == "AUTHORIZE"
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZED" if authorized else "RETURN_FINANCIAL_OPERATION_REJECTED",
        "decision": choice,
        "selected_type_ids": list(source.get("selected_type_ids") or []),
        "selected_operation_names": list(source.get("selected_operation_names") or []),
        "mapping_authorized": authorized,
        "financial_evidence_mapping_allowed": authorized,
        "returns_profit_adjustment_allowed": False,
        "automatic_activation_allowed": False,
        "read_only": True,
        "executed": False,
    }
