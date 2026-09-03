from period_profit_response import build_period_profit_response
from services.period_profit_return_evidence_service import (
    PeriodProfitReturnEvidenceService,
)
from services.period_profit_summary_service import (
    PeriodProfitSummaryService,
)


class Finance:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_daily_finance(self, day, sku=None):
        self.calls.append((day, sku))
        return dict(self.rows[(day, sku)])


class Costs:
    def __init__(self, values):
        self.values = values

    def get_cost(self, product_id):
        return self.values.get(str(product_id))


def test_v1201_sqlite_product_tuple_is_normalized_for_period_profit():
    finance = Finance({
        ("2026-09-03", "100"): {
            "error": False,
            "sales_count": 2,
            "gross_sales": 200.0,
            "net_accrual": 150.0,
            "commission": -20.0,
            "logistics": -15.0,
            "acquiring": -3.0,
            "other_fees": -12.0,
            "fee_breakdown": {},
        }
    })
    costs = Costs({
        "10": ("10", "hook-2", "100", 21.0, "RUB", None),
    })

    result = PeriodProfitSummaryService(
        finance,
        costs,
        tax_rate=0.06,
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [("10", "hook-2", "100")],
    )

    assert result["error"] is False
    assert result["product_count"] == 1
    assert result["units_sold"] == 2
    assert result["revenue"] == 200.0
    assert result["product_cost"] == 42.0
    assert result["tax"] == 12.0
    assert result["profit"] == 96.0
    assert finance.calls == [("2026-09-03", "100")]


def test_v1202_empty_product_list_fails_instead_of_returning_zero_profit():
    result = PeriodProfitSummaryService(
        Finance({}),
        Costs({}),
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE"


def test_v1203_malformed_products_fail_instead_of_zero_success():
    result = PeriodProfitSummaryService(
        Finance({}),
        Costs({}),
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [None, (), ("only", "two"), {"bad": "row"}],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE"


def test_v1204_existing_dict_product_contract_remains_supported():
    finance = Finance({
        ("2026-09-03", "100"): {
            "error": False,
            "sales_count": 1,
            "gross_sales": 100.0,
            "net_accrual": 80.0,
            "fee_breakdown": {},
        }
    })

    result = PeriodProfitSummaryService(
        finance,
        Costs({}),
    ).calculate(
        "2026-09-03",
        "2026-09-03",
        [{
            "product_id": "10",
            "offer_id": "hook-2",
            "sku": "100",
            "cost": 20.0,
        }],
    )

    assert result["error"] is False
    assert result["product_count"] == 1
    assert result["profit"] == 54.0
