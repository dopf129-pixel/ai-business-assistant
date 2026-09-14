import period_profit_factory
from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)


class _NoCost:
    def get_historical_cost_evidence(self, *args, **kwargs):
        return {"error": True, "code": "PRODUCT_COST_HISTORY_MISSING"}

    def get_all_costs(self):
        return []


class _Summary:
    def __init__(self):
        self.cost_service = _NoCost()
        self.tax_rate = 0.0
        self.received_products = None

    def calculate(self, date_from, date_to, products):
        self.received_products = products
        return {"error": False, "profit": 0.0}


class _Finance:
    def __init__(self, posting_records):
        self.prefetch_calls = []
        self.day_reads = []
        self.posting_reads = []
        self.posting_records = list(posting_records)
        self._daily_accrual_cache = {}

    def prefetch_daily_accruals(self, date_from, date_to):
        self.prefetch_calls.append((str(date_from), str(date_to)))
        self._daily_accrual_cache[str(date_from)] = {
            "error": False,
            "accruals": [{
                "accrued_category": "POSTING",
                "unit_number": "posting-1",
                "posting": {"products": [{"sku": "legacy-sku"}]},
            }],
        }
        return {"error": False, "complete": True}

    def _get_accruals_by_day(self, accrual_date):
        self.day_reads.append(str(accrual_date))
        return self._daily_accrual_cache[str(accrual_date)]

    def get_sale_posting_quantity_evidence(self, posting_numbers):
        self.posting_reads.append(tuple(posting_numbers))
        return {
            "error": False,
            "complete": True,
            "records": list(self.posting_records),
        }


def test_production_factory_uses_finance_posting_identity_scope():
    assert period_profit_factory.PeriodProfitFinanceSkuScopeService is (
        PeriodProfitFinancePostingIdentityScopeService
    )


def test_scope_reuses_prefetched_finance_and_bridges_legacy_sku_without_fbo():
    summary = _Summary()
    finance = _Finance([{
        "posting_number": "posting-1",
        "sku": "current-sku",
        "quantity": 3,
    }])
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary,
        finance,
        sku_ozon_client=None,
    )

    result = service.calculate(
        "2026-09-14",
        "2026-09-14",
        [{
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "current-sku",
        }],
    )

    assert result["error"] is False
    assert finance.prefetch_calls == [("2026-09-14", "2026-09-14")]
    assert finance.day_reads == ["2026-09-14"]
    assert finance.posting_reads == [("posting-1",)]
    assert summary.received_products[0]["sku"] == "legacy-sku"
    assert summary.received_products[0]["catalog_sku"] == "current-sku"
    assert summary.received_products[0]["product_id"] == "product-1"
    assert summary.received_products[0]["historical_sku_identity_source"] == (
        "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_SKU"
    )


def test_scope_fails_closed_on_ambiguous_current_catalog_sku():
    summary = _Summary()
    finance = _Finance([
        {"posting_number": "posting-1", "sku": "current-a", "quantity": 1},
        {"posting_number": "posting-1", "sku": "current-b", "quantity": 1},
    ])
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary,
        finance,
        sku_ozon_client=None,
    )

    result = service.calculate(
        "2026-09-14",
        "2026-09-14",
        [
            {"product_id": "p-a", "offer_id": "o-a", "sku": "current-a"},
            {"product_id": "p-b", "offer_id": "o-b", "sku": "current-b"},
        ],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
    assert summary.received_products is None
