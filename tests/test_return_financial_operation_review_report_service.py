from services.return_financial_operation_review_report_service import ReturnFinancialOperationReviewReportService


class Catalog:
    def __init__(self, result): self.result = result
    def load(self): return self.result


def test_report_exposes_unclassified_real_operations_for_human_review():
    result = ReturnFinancialOperationReviewReportService(Catalog({
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
        "operations": [{"type_id": 10, "name": "A", "description": "AA", "source": "OZON_FINANCE_ACCRUAL_TYPES"}],
    })).build()
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_READY"
    assert result["operations"][0]["return_related"] is None
    assert result["operations"][0]["human_verification_required"] is True
    assert result["mapping_activation_allowed"] is False
    assert result["returns_profit_adjustment_allowed"] is False


def test_catalog_failure_blocks_report():
    result = ReturnFinancialOperationReviewReportService(Catalog({"error": True, "message": "fail"})).build()
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_UNAVAILABLE"
