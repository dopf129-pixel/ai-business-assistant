from return_financial_operation_selection_authorization import (
    build_return_financial_operation_selection_authorization,
)


def _selection():
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_SELECTION_READY",
        "selected_type_ids": [2, 10],
        "selected_operations": [
            {"type_id": 2, "name": "A"},
            {"type_id": 10, "name": "B"},
        ],
        "selected_operation_names": ["A", "B"],
        "human_selected": True,
    }


def test_authorize_allows_only_financial_evidence_mapping():
    result = build_return_financial_operation_selection_authorization(_selection(), "AUTHORIZE")
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED"
    assert result["mapping_authorized"] is True
    assert result["financial_evidence_mapping_allowed"] is True
    assert result["returns_profit_adjustment_allowed"] is False
    assert result["automatic_activation_allowed"] is False
    assert result["executed"] is False


def test_reject_keeps_mapping_blocked():
    result = build_return_financial_operation_selection_authorization(_selection(), "REJECT")
    assert result["mapping_authorized"] is False


def test_invalid_decision_blocks():
    result = build_return_financial_operation_selection_authorization(_selection(), "MAYBE")
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZATION_DECISION_INVALID"
