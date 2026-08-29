from services.period_profit_summary_service import PeriodProfitSummaryService


class Finance:
    def __init__(self, rows): self.rows = rows
    def get_daily_finance(self, day, sku=None): return dict(self.rows[(day, sku)])


class Costs:
    def __init__(self, costs): self.costs = costs
    def get_cost(self, product_id): return self.costs.get(str(product_id))


def test_calculates_period_profit_with_explicit_scope():
    finance = Finance({
        ("2026-08-01", "100"): {
            "error": False,
            "sales_count": 2,
            "gross_sales": 200,
            "net_accrual": 150,
            "commission": -20,
            "logistics": -15,
            "acquiring": -3,
            "other_fees": -12,
        },
        ("2026-08-02", "100"): {
            "error": False,
            "sales_count": 1,
            "gross_sales": 100,
            "net_accrual": 75,
            "commission": -10,
            "logistics": -8,
            "acquiring": -2,
            "other_fees": -5,
        },
    })
    costs = Costs({"10": ("10", "100", "hook", 20.0, "RUB", None)})
    result = PeriodProfitSummaryService(finance, costs, tax_rate=0.06).calculate(
        "2026-08-01", "2026-08-02", [{"product_id": "10", "sku": "100", "offer_id": "hook"}]
    )
    assert result["status"] == "PERIOD_PROFIT_SUMMARY_READY"
    assert result["units_sold"] == 3
    assert result["revenue"] == 300
    assert result["net_accrual"] == 225
    assert result["commission"] == -30
    assert result["logistics"] == -23
    assert result["acquiring"] == -5
    assert result["other_fees"] == -17
    assert result["product_cost"] == 60
    assert result["tax"] == 18
    assert result["profit"] == 147
    assert result["fee_components_included"] is True
    assert result["returns_included"] is False
    assert result["advertising_included"] is False


def test_aggregates_multiple_products():
    rows = {
        ("2026-08-01", "100"): {"error": False, "sales_count": 1, "gross_sales": 100, "net_accrual": 80},
        ("2026-08-01", "200"): {"error": False, "sales_count": 2, "gross_sales": 300, "net_accrual": 240},
    }
    products = [
        {"product_id": "10", "sku": "100", "offer_id": "a"},
        {"product_id": "20", "sku": "200", "offer_id": "b"},
    ]
    costs = Costs({
        "10": ("10", "100", "a", 10.0, "RUB", None),
        "20": ("20", "200", "b", 30.0, "RUB", None),
    })
    result = PeriodProfitSummaryService(Finance(rows), costs).calculate("2026-08-01", "2026-08-01", products)
    assert result["product_count"] == 2
    assert result["revenue"] == 400
    assert result["profit"] == 226


def test_direct_cost_field_is_supported():
    finance = Finance({("2026-08-01", "100"): {"error": False, "sales_count": 1, "gross_sales": 100, "net_accrual": 80}})
    result = PeriodProfitSummaryService(finance, Costs({})).calculate(
        "2026-08-01", "2026-08-01", [{"sku": "100", "offer_id": "a", "cost": 10}]
    )
    assert result["profit"] == 64


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
    costs = Costs({"10": ("10", "100", "a", 10.0, "RUB", None)})
    result = PeriodProfitSummaryService(finance, costs).calculate(
        "2026-08-01", "2026-08-01", [{"product_id": "10", "sku": "100", "offer_id": "a"}]
    )
    assert result["code"] == "PERIOD_PROFIT_FINANCE_UNAVAILABLE"
