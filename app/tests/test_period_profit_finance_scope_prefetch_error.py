from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)


class _Summary:
    cost_service = None
    tax_rate = 0.0


class _Finance:
    def prefetch_daily_accruals(self, date_from, date_to):
        return {"error": True, "code": "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE"}


def test_prefetch_failure_fails_closed_before_scope_reads():
    service = PeriodProfitFinancePostingIdentityScopeService(
        _Summary(),
        _Finance(),
        sku_ozon_client=None,
    )
    result = service._scope_products(
        "2026-06-01",
        "2026-06-30",
        [{"product_id": "p", "offer_id": "o", "sku": "s"}],
    )
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE"
    assert result["read_only"] is True
    assert result["executed"] is False
