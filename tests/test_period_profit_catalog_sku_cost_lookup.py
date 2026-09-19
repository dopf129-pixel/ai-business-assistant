from services.period_profit_effective_cost_sale_quantity_summary_service import (
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)


class _Costs:
    def __init__(self):
        self.calls = []

    def get_effective_cost_evidence(self, at_date, **identity):
        self.calls.append((at_date, identity))
        if identity.get("sku") != "10012_gray_01":
            return {"error": True, "code": "PERIOD_PROFIT_COST_HISTORY_MISSING"}
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_price": 430.0,
            "effective_from": "0001-01-01",
            "source": "SELLER_CONFIRMED_INITIAL_HISTORY",
            "cost_basis": "SELLER_CONFIRMED_OPERATIONAL_SWITCH",
            "switch_id": 1,
        }


def test_effective_cost_lookup_prefers_catalog_sku_over_finance_sku():
    costs = _Costs()
    service = object.__new__(PeriodProfitEffectiveCostSaleQuantitySummaryService)
    service.cost_service = costs

    evidence = service._effective_cost_evidence(
        {
            "product_id": "1",
            "offer_id": "10012_gray_01",
            "catalog_sku": "10012_gray_01",
            "sku": "989101156",
        },
        "2026-09-19",
    )

    assert evidence["cost_price"] == 430.0
    assert costs.calls == [
        (
            "2026-09-19",
            {
                "product_id": "1",
                "sku": "10012_gray_01",
                "offer_id": "10012_gray_01",
            },
        )
    ]
