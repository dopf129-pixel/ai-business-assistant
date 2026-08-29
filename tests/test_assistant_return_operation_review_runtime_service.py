from services.assistant_return_operation_review_runtime_service import (
    AssistantReturnOperationReviewRuntimeService,
)


class ReportService:
    def build(self):
        return {
            "error": False,
            "status": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_READY",
            "operations": [
                {"type_id": 10, "name": "A", "description": "AA"},
            ],
        }


def test_explicit_review_query_is_handled_read_only():
    service = AssistantReturnOperationReviewRuntimeService(ReportService())
    result = service.handle_text("покажи типы начислений Ozon")
    assert result["status"] == "ASSISTANT_RETURN_OPERATION_REVIEW_READY"
    assert "ID 10: A — AA" in result["text"]
    assert result["mapping_activation_allowed"] is False
    assert result["returns_profit_adjustment_allowed"] is False
    assert result["read_only"] is True
    assert result["executed"] is False


def test_unrelated_text_is_not_intercepted():
    service = AssistantReturnOperationReviewRuntimeService(ReportService())
    assert service.handle_text("сколько я заработал за 7 дней") is None
