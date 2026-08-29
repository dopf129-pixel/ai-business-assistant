from return_financial_operation_review_candidate import build_return_financial_operation_review_candidate


def _catalog():
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
        "operations": [
            {"type_id": 2, "name": "A", "description": "AA", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 10, "name": "B", "description": "BB", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        ],
    }


def test_candidate_uses_only_catalog_rows_and_requires_review():
    result = build_return_financial_operation_review_candidate(_catalog(), [10, 2, 10])
    assert result["selected_type_ids"] == [2, 10]
    assert result["selected_operation_names"] == ["A", "B"]
    assert result["review_required"] is True
    assert result["mapping_authorized"] is False
    assert result["returns_profit_adjustment_allowed"] is False


def test_unknown_type_id_blocks_candidate():
    result = build_return_financial_operation_review_candidate(_catalog(), [999])
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_TYPE_ID_NOT_IN_CATALOG"


def test_invalid_type_id_blocks_candidate():
    result = build_return_financial_operation_review_candidate(_catalog(), ["x"])
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_TYPE_ID_INVALID"
