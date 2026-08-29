from return_financial_operation_authorization import build_return_financial_operation_authorization


def _candidate():
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_REVIEW_CANDIDATE_READY",
        "selected_type_ids": [2, 10],
        "selected_operation_names": ["A", "B"],
    }


def test_authorize_allows_mapping_only():
    result = build_return_financial_operation_authorization(_candidate(), "AUTHORIZE")
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_AUTHORIZED"
    assert result["mapping_authorized"] is True
    assert result["financial_evidence_mapping_allowed"] is True
    assert result["returns_profit_adjustment_allowed"] is False
    assert result["automatic_activation_allowed"] is False
    assert result["executed"] is False


def test_reject_keeps_mapping_blocked():
    result = build_return_financial_operation_authorization(_candidate(), "REJECT")
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_REJECTED"
    assert result["mapping_authorized"] is False
    assert result["financial_evidence_mapping_allowed"] is False


def test_invalid_decision_blocks():
    result = build_return_financial_operation_authorization(_candidate(), "MAYBE")
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_AUTHORIZATION_DECISION_INVALID"
