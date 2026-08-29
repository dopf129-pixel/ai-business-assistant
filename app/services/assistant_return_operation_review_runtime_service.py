from return_financial_operation_review_response import (
    build_return_financial_operation_review_response,
)


class AssistantReturnOperationReviewRuntimeService:
    """Read-only direct route for explicit Ozon operation-type review requests."""

    TRIGGERS = (
        "типы начислений ozon",
        "финансовые типы ozon",
        "операции ozon для возвратов",
        "типы операций ozon",
        "ozon accrual types",
    )

    def __init__(self, report_service):
        self.report_service = report_service

    def handle_text(self, text):
        normalized = " ".join(str(text or "").strip().lower().split())
        if not normalized or not any(trigger in normalized for trigger in self.TRIGGERS):
            return None

        report = self.report_service.build()
        if not isinstance(report, dict) or report.get("error"):
            return report

        response = build_return_financial_operation_review_response(report)
        if response.get("error"):
            return response

        return {
            "error": False,
            "status": "ASSISTANT_RETURN_OPERATION_REVIEW_READY",
            "report": report,
            "text": response["text"],
            "read_only": True,
            "mapping_activation_allowed": False,
            "returns_profit_adjustment_allowed": False,
            "executed": False,
        }
