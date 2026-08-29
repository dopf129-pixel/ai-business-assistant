from return_financial_operation_selection_request import build_return_financial_operation_selection_request


def _report():
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_READY",
        "operations": [
            {"type_id": 2, "name": "A", "description": "AA", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 10, "name": "B", "description": "BB", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        ],
    }


def test_selection_uses_only_reported_ids_and_requires_authorization():
    result = build_return_financial_operation_selection_request(_report(), [10, 2, 10])
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_SELECTION_READY"
    assert result["selected_type_ids"] == [2, 10]
    assert result["human_selected"] is True
    assert result["authorization_required"] is True
    assert result["mapping_authorized"] is False
    assert result["returns_profit_adjustment_allowed"] is False
    assert result["executed"] is False


def test_unknown_id_blocks_selection():
    result = build_return_financial_operation_selection_request(_report(), [999])
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_SELECTION_NOT_IN_REPORT"


def test_empty_selection_blocks():
    result = build_return_financial_operation_selection_request(_report(), [])
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_SELECTION_REQUIRED"
