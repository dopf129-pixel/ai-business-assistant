from services.period_profit_finance_sku_scope_service import PeriodProfitFinanceSkuScopeService
from services.period_profit_summary_service import PeriodProfitSummaryService


class _Finance:
    def begin_read_session(self):
        pass

    def _get_accruals_by_day(self, day):
        return {
            "error": False,
            "accruals": [{
                "accrued_category": "POSTING",
                "posting": {"products": [{"sku": "989101156"}]},
            }],
        }

    def get_daily_finance(self, day, sku=None):
        return {
            "error": False,
            "sales_count": 1,
            "gross_sales": 100.0,
            "net_accrual": 80.0,
            "commission": 10.0,
            "logistics": 5.0,
            "acquiring": 1.0,
            "other_fees": 4.0,
            "fee_breakdown": {},
        }

    def get_daily_account_finance(self, day):
        return {
            "error": False,
            "gross_sales": 1000.0,
            "net_accrual": 800.0,
            "commission": 100.0,
            "logistics": 50.0,
            "acquiring": 10.0,
            "other_fees": 40.0,
            "fee_breakdown": {},
        }


class _Costs:
    def get_product_cost(self, product_id):
        return 20.0


def test_selected_scope_survives_finance_wrapper_and_skips_account_reconciliation():
    finance = _Finance()
    raw = PeriodProfitSummaryService(finance, _Costs(), tax_rate=0.0)
    scoped = PeriodProfitFinanceSkuScopeService(raw, finance)

    result = scoped.calculate(
        "2026-09-19",
        "2026-09-19",
        [{
            "product_id": "p1",
            "offer_id": "10002_white_01",
            "sku": "989101156",
            "cost_price": 20.0,
            "_period_profit_selected_scope": True,
        }],
    )

    assert result["error"] is False
    assert result["revenue"] == 100.0
    assert result["account_level_ozon_accruals_included"] is False
    assert result["product_revenue_reconciled"] is None
