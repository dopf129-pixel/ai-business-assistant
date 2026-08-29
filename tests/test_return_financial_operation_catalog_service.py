from services.return_financial_operation_catalog_service import ReturnFinancialOperationCatalogService


class Finance:
    def __init__(self, result=None):
        self.result = result or {"error": False}
        self.accrual_types = {
            10: {"name": "Type B", "description": "Description B"},
            2: {"name": "Type A", "description": "Description A"},
        }

    def load_accrual_types(self):
        return self.result


def test_catalog_exposes_real_source_types_without_classification():
    result = ReturnFinancialOperationCatalogService(Finance()).load()
    assert result["status"] == "RETURN_FINANCIAL_OPERATION_CATALOG_READY"
    assert [row["type_id"] for row in result["operations"]] == [2, 10]
    assert result["operations"][0]["name"] == "Type A"
    assert result["return_classification_applied"] is False
    assert result["mapping_activation_allowed"] is False
    assert result["executed"] is False


def test_source_failure_blocks_catalog():
    result = ReturnFinancialOperationCatalogService(Finance({"error": True, "message": "fail"})).load()
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_CATALOG_UNAVAILABLE"
