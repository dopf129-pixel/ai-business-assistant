from services.period_profit_cost_exclusion_context import activate_cost_exclusion, reset_cost_exclusion
from services.period_profit_effective_cost_sale_quantity_summary_service import PeriodProfitEffectiveCostSaleQuantitySummaryService


class _Finance:
    def get_daily_sale_posting_evidence(self, *_):
        raise AssertionError("pre-COGS must not request sale quantity evidence")


class _Service(PeriodProfitEffectiveCostSaleQuantitySummaryService):
    pass


def test_pre_cogs_does_not_require_sale_quantity(monkeypatch):
    service = _Service(_Finance(), object(), sale_quantity_ozon_client=object())
    base = {
        "error": False,
        "products": [],
        "revenue": 100.0,
        "net_accrual": 80.0,
        "tax": 6.0,
        "profit": 74.0,
        "margin_percent": 74.0,
    }
    monkeypatch.setattr(
        "services.period_profit_effective_cost_sale_quantity_summary_service.PeriodProfitCriticalFinanceSummaryService.calculate",
        lambda *args, **kwargs: dict(base),
    )
    token = activate_cost_exclusion()
    try:
        result = service.calculate("2026-05-03", "2026-09-23", [])
    finally:
        reset_cost_exclusion(token)

    assert result["error"] is False
    assert result["profit"] == 74.0
    assert result["product_cost"] == 0.0
    assert result["sale_quantity_required"] is False
    assert result["sale_quantity_reconciled"] is False
