from period_profit_compact_response import compact_period_profit_result
from period_profit_response import build_period_profit_response
from services.finance_service import FinanceService
from services.period_profit_summary_service import PeriodProfitSummaryService
from services.period_profit_tax_policy_summary_service import (
    PeriodProfitTaxPolicySummaryService,
)
from services.tax_service import TaxService


def _money(amount):
    return {"amount": str(amount), "currency": "RUB"}


def _finance_service():
    finance = FinanceService.__new__(FinanceService)
    finance.accrual_types = {1: {"name": "fixture", "description": "fixture"}}
    finance._daily_accrual_cache = {}
    finance._get_accruals_by_day = lambda _day: {
        "error": False,
        "accruals": [
            {
                "accrued_category": "POSTING",
                "total_amount": _money(800),
                "posting": {
                    "products": [
                        {
                            "sku": "SKU-1",
                            "commission": {
                                "sale_amount": _money(1000),
                                "sale_price": _money(900),
                                "bonus": _money(100),
                                "sale_commission": _money(0),
                            },
                        },
                    ],
                },
            },
        ],
    }
    return finance


def _summary(selected=False):
    finance = _finance_service()
    base = PeriodProfitSummaryService(
        finance,
        cost_service=None,
        tax_rate=0.0,
    )
    tax = PeriodProfitTaxPolicySummaryService(
        base,
        TaxService(),
        {
            "error": False,
            "configured": True,
            "policy": {
                "mode": "USN_INCOME",
                "tax_rate": 6.0,
                "minimum_tax_rate": 1.0,
            },
        },
    )
    product = {
        "product_id": "product-1",
        "offer_id": "offer-1",
        "sku": "SKU-1",
        "cost": 300.0,
    }
    if selected:
        product["_period_profit_selected_scope"] = True
    return tax.calculate(
        "2026-08-01",
        "2026-08-01",
        [product],
    )


def test_all_products_finance_to_telegram_uses_discount_adjusted_tax():
    summary = _summary()

    assert summary["error"] is False
    assert summary["revenue"] == 1000.0
    assert summary["discount_points"] == 100.0
    assert summary["revenue_tax_base"] == 900.0
    assert summary["tax"] == 54.0
    assert summary["profit"] == 446.0

    response = build_period_profit_response(summary)
    compact = compact_period_profit_result({
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "summary": summary,
        "text": response["text"],
    })

    assert "Баллы за скидки: 100.00 ₽" in response["text"]
    assert "Выручка для расчёта налога: 900.00 ₽ (90.00%)" in response["text"]
    assert "Налог: 54.00 ₽ (5.40%)" in response["text"]
    assert "Баллы за скидки: 100 ₽" in compact["text"]
    assert "Выручка для расчёта налога: 900 ₽" in compact["text"]
    assert "Налог: 54 ₽" in compact["text"]


def test_selected_products_finance_keeps_points_without_account_fallback():
    summary = _summary(selected=True)

    assert summary["error"] is False
    assert summary["account_level_ozon_accruals_included"] is False
    assert summary["discount_points"] == 100.0
    assert summary["revenue_tax_base"] == 900.0
    assert summary["tax"] == 54.0
