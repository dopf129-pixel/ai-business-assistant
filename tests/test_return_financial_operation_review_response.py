from return_financial_operation_review_response import build_return_financial_operation_review_response


def test_formats_unclassified_operations_for_manual_review():
    result = build_return_financial_operation_review_response({
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_READY",
        "operations": [
            {"type_id": 10, "name": "A", "description": "AA", "return_related": None},
            {"type_id": 20, "name": "B", "description": None, "return_related": None},
        ],
    })
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_REVIEW_RESPONSE_READY"
    assert "ID 10: A — AA" in result["text"]
    assert "ID 20: B" in result["text"]
    assert "не помечена как возвратная автоматически" in result["text"]
    assert result["mapping_activation_allowed"] is False
    assert result["returns_profit_adjustment_allowed"] is False


def test_invalid_report_blocks():
    result = build_return_financial_operation_review_response({"error": True})
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_REQUIRED"
