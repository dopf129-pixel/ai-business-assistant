from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)


class Finance:
    def __init__(self, sku="3398133813"):
        self.sku = sku

    def _get_accruals_by_day(self, _day):
        return {
            "error": False,
            "accruals": [
                {
                    "accrued_category": "POSTING",
                    "posting": {"products": [{"sku": self.sku}]},
                }
            ],
        }


class Summary:
    tax_rate = 0.0

    def __init__(self, cost_service):
        self.cost_service = cost_service
        self.received = None

    def calculate(self, _date_from, _date_to, products):
        self.received = list(products)
        return {"error": False, "profit": 1.0}


class HistoricalCosts:
    def get_historical_cost_evidence(self, at_date, product_id=None, sku=None, offer_id=None):
        assert at_date == "2026-08-31"
        assert sku == "3398133813"
        return {
            "error": False,
            "historical_cost_confirmed": True,
            "product_id": "old-product-1",
            "sku": sku,
            "offer_id": "old-offer",
            "cost_price": 123.45,
            "currency": "RUB",
        }

    def get_all_costs(self):
        raise AssertionError("historical evidence must win")


class CurrentCostsOnly:
    def get_historical_cost_evidence(self, *args, **kwargs):
        return {
            "error": False,
            "historical_cost_confirmed": False,
            "cost_price": None,
        }

    def get_all_costs(self):
        return [
            ("old-product-2", "3398133813", "old-offer-2", 77.0, "RUB", "2026-09-01"),
        ]


class AmbiguousCosts(CurrentCostsOnly):
    def get_all_costs(self):
        return [
            ("p1", "3398133813", "o1", 77.0, "RUB", "2026-09-01"),
            ("p2", "3398133813", "o2", 88.0, "RUB", "2026-09-01"),
        ]


def _catalog_without_target():
    return [{"product_id": "current", "sku": "111", "offer_id": "current"}]


def test_v1411_missing_current_catalog_sku_uses_historical_cost_evidence():
    summary = Summary(HistoricalCosts())
    service = PeriodProfitFinanceSkuScopeService(summary, Finance())

    result = service.calculate("2026-08-31", "2026-08-31", _catalog_without_target())

    assert result["error"] is False
    assert result["historical_sku_recovery_count"] == 1
    assert summary.received == [
        {
            "product_id": "old-product-1",
            "sku": "3398133813",
            "offer_id": "old-offer",
            "cost_price": 123.45,
            "historical_cost_evidence": True,
        }
    ]


def test_v1412_missing_current_catalog_sku_can_use_unique_existing_cost_record():
    summary = Summary(CurrentCostsOnly())
    service = PeriodProfitFinanceSkuScopeService(summary, Finance())

    result = service.calculate("2026-08-31", "2026-08-31", _catalog_without_target())

    assert result["error"] is False
    assert summary.received[0]["product_id"] == "old-product-2"
    assert summary.received[0]["cost_price"] == 77.0


def test_v1413_ambiguous_cost_records_fail_closed():
    summary = Summary(AmbiguousCosts())
    service = PeriodProfitFinanceSkuScopeService(summary, Finance())

    result = service.calculate("2026-08-31", "2026-08-31", _catalog_without_target())

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
    assert "3398133813" in result["message"]


def test_v1414_non_rub_current_cost_does_not_get_inferred():
    class Costs(CurrentCostsOnly):
        def get_all_costs(self):
            return [("p", "3398133813", "o", 77.0, "USD", "2026-09-01")]

    summary = Summary(Costs())
    result = PeriodProfitFinanceSkuScopeService(summary, Finance()).calculate(
        "2026-08-31", "2026-08-31", _catalog_without_target()
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"


def test_v1415_current_catalog_product_still_wins_without_cost_recovery_lookup():
    class Costs:
        def get_historical_cost_evidence(self, *args, **kwargs):
            raise AssertionError("must not recover an SKU already present in catalog")

    summary = Summary(Costs())
    service = PeriodProfitFinanceSkuScopeService(summary, Finance("111"))

    result = service.calculate("2026-08-31", "2026-08-31", _catalog_without_target())

    assert result["error"] is False
    assert result["historical_sku_recovery_count"] == 0
    assert summary.received[0]["sku"] == "111"
