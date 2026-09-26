from services.period_profit_cost_exclusion_context import activate_cost_exclusion, reset_cost_exclusion
from services.period_profit_finance_sku_scope_service import PeriodProfitFinanceSkuScopeService


class _Summary:
    cost_service = object()

    def calculate(self, date_from, date_to, products):
        return {"error": False, "products": products}


def test_pre_cogs_keeps_unresolved_finance_skus_without_confirmed_cost():
    service = PeriodProfitFinanceSkuScopeService(_Summary(), object())
    service._load_period_skus = lambda *_: {
        "error": False,
        "skus": ["3398133813", "3921245627"],
    }
    service._recover_missing_product = lambda *_: None
    token = activate_cost_exclusion()
    try:
        result = service.calculate("2026-05-03", "2026-09-23", [
            {"product_id": "catalog", "sku": "unrelated", "offer_id": "unrelated"}
        ])
    finally:
        reset_cost_exclusion(token)

    assert result["error"] is False
    assert [row["sku"] for row in result["products"]] == [
        "3398133813", "3921245627"
    ]
    assert all(row["cost_price"] == 0.0 for row in result["products"])


def test_normal_profit_still_fails_closed_for_unresolved_cost_skus():
    service = PeriodProfitFinanceSkuScopeService(_Summary(), object())
    service._load_period_skus = lambda *_: {"error": False, "skus": ["3398133813"]}
    service._recover_missing_product = lambda *_: None
    result = service.calculate("2026-05-03", "2026-09-23", [
        {"product_id": "catalog", "sku": "unrelated", "offer_id": "unrelated"}
    ])
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
