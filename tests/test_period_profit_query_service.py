from services.period_profit_query_service import PeriodProfitQueryService


class Summary:
    def __init__(self, profits): self.profits = iter(profits)
    def calculate(self, date_from, date_to, products):
        profit = next(self.profits)
        return {"error": False, "status": "PERIOD_PROFIT_SUMMARY_READY", "date_from": date_from, "date_to": date_to, "revenue": 1000, "net_accrual": 800, "product_cost": 300, "tax": 60, "profit": profit, "margin_percent": profit / 10, "products": [], "fee_components_included": True, "returns_included": False, "advertising_included": False, "storage_included": False, "profit_scope": "V1"}


def test_query_returns_user_text_and_coverage():
    result = PeriodProfitQueryService(Summary([440]), lambda: [{"sku": "1"}]).query("7D", today="2026-08-29")
    assert result["status"] == "PERIOD_PROFIT_QUERY_READY"
    assert "Прибыль: 440.00 ₽" in result["text"]
    assert result["coverage"]["coverage_status"] == "PARTIAL"
    assert result["coverage"]["missing_components"] == ["returns", "advertising", "storage"]
    assert result["coverage"]["accounting_net_profit_claim_allowed"] is False
    assert result["read_only"] is True
    assert result["executed"] is False


def test_query_with_previous_comparison():
    result = PeriodProfitQueryService(Summary([440, 400]), lambda: [{"sku": "1"}]).query("7D", compare_previous=True, today="2026-08-29")
    assert result["comparison"]["profit_direction"] == "UP"
    assert "выросла" in result["text"]


def test_product_provider_failure_blocks():
    result = PeriodProfitQueryService(Summary([]), lambda: None).query("7D", today="2026-08-29")
    assert result["code"] == "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE"
