from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)


class _Summary:
    cost_service = None
    tax_rate = 0.0


class _Finance:
    pass


def test_production_scope_does_not_require_fbo_client():
    service = PeriodProfitFinancePostingIdentityScopeService(
        _Summary(),
        _Finance(),
        sku_ozon_client=None,
    )
    assert service.sku_ozon_client is None
