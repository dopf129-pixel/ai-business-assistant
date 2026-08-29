from services.period_profit_summary_service import PeriodProfitSummaryService


class Finance:
    def get_daily_finance(self, day, sku=None):
        return {
            "error": False,
            "sales_count": 1,
            "gross_sales": 100,
            "net_accrual": 80,
            "commission": -10,
            "logistics": -5,
            "acquiring": -1,
            "other_fees": -4,
            "fee_breakdown": {
                "Возвратная логистика": -3,
                "Обычная услуга": -1,
            },
        }


class Costs:
    def get_cost(self, product_id):
        return (str(product_id), "100", "offer", 20.0, "RUB", None)


def test_aggregates_fee_breakdown_across_days_without_changing_profit_formula():
    result = PeriodProfitSummaryService(Finance(), Costs()).calculate(
        "2026-08-01",
        "2026-08-02",
        [{"product_id": "10", "sku": "100", "offer_id": "offer"}],
    )
    assert result["fee_breakdown"] == {
        "Возвратная логистика": -6.0,
        "Обычная услуга": -2.0,
    }
    assert result["products"][0]["fee_breakdown"]["Возвратная логистика"] == -6.0
    assert result["profit"] == 108.0
    assert result["returns_included"] is False
