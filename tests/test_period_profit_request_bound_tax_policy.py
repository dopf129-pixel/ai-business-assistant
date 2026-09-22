from services.period_profit_tax_policy_summary_service import (
    PeriodProfitTaxPolicySummaryService,
)
from services.tax_service import TaxService
from services.tenant_context import (
    get_current_tenant_user_id,
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


class BaseSummary:
    def calculate(self, _date_from, _date_to, _products):
        row = {
            "error": False,
            "revenue": 1000.0,
            "net_accrual": 700.0,
            "product_cost": 200.0,
        }
        return {**row, "products": [dict(row)]}


class RequestBoundTaxConfiguration:
    def __init__(self):
        self.calls = []

    def get_policy(self):
        tenant = get_current_tenant_user_id()
        self.calls.append(tenant)
        rates = {
            "seller::ozon::store-a": 6.0,
            "seller::ozon::store-b": 15.0,
        }
        return {
            "error": False,
            "configured": True,
            "policy": {
                "mode": "USN_INCOME",
                "tax_rate": rates[tenant],
                "minimum_tax_rate": 1.0,
            },
        }


def _in_store(scope, callback):
    token = set_current_tenant_user_id(scope)
    try:
        return callback()
    finally:
        reset_current_tenant_user_id(token)


def test_long_lived_period_profit_reads_tax_policy_for_active_store_each_request():
    configuration = RequestBoundTaxConfiguration()
    service = PeriodProfitTaxPolicySummaryService(
        BaseSummary(), TaxService(), configuration
    )

    store_a = _in_store(
        "seller::ozon::store-a",
        lambda: service.calculate("2026-09-01", "2026-09-30", []),
    )
    store_b = _in_store(
        "seller::ozon::store-b",
        lambda: service.calculate("2026-09-01", "2026-09-30", []),
    )
    store_a_again = _in_store(
        "seller::ozon::store-a",
        lambda: service.calculate("2026-09-01", "2026-09-30", []),
    )

    assert [store_a["tax"], store_b["tax"], store_a_again["tax"]] == [
        60.0,
        150.0,
        60.0,
    ]
    assert configuration.calls == [
        "seller::ozon::store-a",
        "seller::ozon::store-b",
        "seller::ozon::store-a",
    ]
