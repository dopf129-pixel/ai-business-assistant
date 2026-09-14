import period_profit_factory
from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)


def test_factory_uses_finance_posting_identity_scope():
    assert period_profit_factory.PeriodProfitFinanceSkuScopeService is (
        PeriodProfitFinancePostingIdentityScopeService
    )
