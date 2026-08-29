from services.period_profit_summary_service import PeriodProfitSummaryService


class Finance:
    def __init__(self, rows): self.rows = rows
    def get_daily_finance(self, day, sku=None): return dict(self.rows[(day, sku)])


class Costs:
    def __init__(self, costs): self.costs = costs
    def get_cost(self, sku): return self.costs.get(sku)


def test_calculates_period_profit_with_explicit_scope():
    finance = Finance({
        ("2026-08-01", "100"): {"error": False, "sales_count": 2, "gross_sales": 200, "net_accrual": 150},
        ("2026-08-02", "100"): {"error": False, "sales_count": 1, "gross_sales": 100, "net_accrual": 75},
    })
    result = PeriodProfitSummaryService(finance, Costs({"hook": 20}), tax_rate=0.06).calculate(
        "2026-08-01", "2026-08-02", [{"sku": "100", "offer_id": "hook"}]
    )
    assert result["status"] == "PERIOD_PROFIT_SUMMARY_READY"
    assert result["units_sold"] == 3
    assert result["revenue"] == 300
    assert result["net_accrual"] == 225
    assert result["product_cost"] == 60
    assert result["tax"] == 18
    assert result["profit"] == 147
    assert result["returns_included"] is False
    assert result["advertising_included"] is False


def test_aggregates_multiple_products():
    rows = {
        ("2026-08-01", "100"): {"error": False, "sales_count": 1, "gross_sales": 100, "net_accrual": 80},
        ("2026-08-01", "200"): {"error": False, "sales_count": 2, "gross_sales": 300, "net_accrual": 240},
    }
    result = PeriodProfitSummaryService(Finance(rows), Costs({"a": 10, "b": 30})).calculate(
        "2026-08-01", "2026-08-01", [{"sku": "100", "offer_id": "a"}, {"sku": "200", "offer_id": "b"}]
    )
    assert result["product_count"] == 2
    assert result["revenue"] == 400
    assert result["profit"] == 226


def test_invalid_period_blocks():
    result = PeriodProfitSummaryService(Finance({}), Costs({})).calculate("2026-08-02", "2026-08-01", [])
    assert result["code"] == "PERIOD_PROFIT_PERIOD_INVALID"


def test_missing_cost_blocks_instead_of_inventing_it():
    result = PeriodProfitSummaryService(Finance({}), Costs({})).calculate(
        "2026-08-01", "2026-08-01", [{"sku": "100", "offer_id": "a"}]
    )
    assert result["code"] == "PERIOD_PROFIT_COST_UNAVAILABLE"


def test_finance_failure_blocks_whole_summary():
    finance = Finance({("2026-08-01", "100"): {"error": True}})
    result = PeriodProfitSummaryService(finance, Costs({"a": 10})).calculate(
        "2026-08-01", "2026-08-01", [{"sku": "100", "offer_id": "a"}]
    )
    assert result["code"] == "PERIOD_PROFIT_FINANCE_UNAVAILABLE"
