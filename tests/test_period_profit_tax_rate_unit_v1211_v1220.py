from period_profit_factory import (
    _period_profit_tax_fraction,
    create_period_profit_query,
)
from services.period_profit_summary_service import (
    PeriodProfitSummaryService,
)


class Finance:
    def __init__(self, row):
        self.row = row

    def get_daily_finance(self, day, sku=None):
        return dict(self.row)


class Costs:
    def __init__(self, cost):
        self.cost = cost

    def get_cost(self, product_id):
        return (
            str(product_id),
            "hook-2",
            "100",
            self.cost,
            "RUB",
            None,
        )


def _policy(mode="USN_INCOME", rate=6.0):
    return {
        "error": False,
        "configured": True,
        "policy": {
            "mode": mode,
            "tax_rate": rate,
            "minimum_tax_rate": 1.0,
        },
    }


def test_v1211_usn_income_percent_converts_to_fraction():
    assert _period_profit_tax_fraction(
        _policy(rate=6.0)
    ) == 0.06


def test_v1212_none_tax_mode_converts_to_zero_fraction():
    assert _period_profit_tax_fraction(
        _policy(mode="NONE", rate=0.0)
    ) == 0.0


def test_v1213_unconfigured_policy_fails_closed():
    assert _period_profit_tax_fraction({
        "error": False,
        "configured": False,
        "policy": None,
    }) is None


def test_v1214_income_minus_expenses_is_not_silently_miscomputed():
    assert _period_profit_tax_fraction(
        _policy(
            mode="USN_INCOME_MINUS_EXPENSES",
            rate=15.0,
        )
    ) is None


def test_v1215_invalid_percent_rates_fail_closed():
    for rate in (
        True,
        -1,
        101,
        "bad",
        float("nan"),
        float("inf"),
    ):
        assert _period_profit_tax_fraction(
            _policy(rate=rate)
        ) is None


def test_v1216_summary_rejects_percent_scale_rate_instead_of_600_percent_tax():
    service = PeriodProfitSummaryService(
        Finance({
            "error": False,
            "sales_count": 1,
            "gross_sales": 100.0,
            "net_accrual": 80.0,
            "fee_breakdown": {},
        }),
        Costs(20.0),
        tax_rate=6.0,
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        [{
            "product_id": "10",
            "offer_id": "hook-2",
            "sku": "100",
        }],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_TAX_RATE_INVALID"


def test_v1217_summary_accepts_six_percent_as_fraction():
    service = PeriodProfitSummaryService(
        Finance({
            "error": False,
            "sales_count": 1,
            "gross_sales": 100.0,
            "net_accrual": 80.0,
            "fee_breakdown": {},
        }),
        Costs(20.0),
        tax_rate=0.06,
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        [{
            "product_id": "10",
            "offer_id": "hook-2",
            "sku": "100",
        }],
    )

    assert result["error"] is False
    assert result["tax"] == 6.0
    assert result["profit"] == 54.0
    assert result["margin_percent"] == 54.0


def test_v1218_live_period_numbers_use_six_percent_not_six_times_revenue():
    service = PeriodProfitSummaryService(
        Finance({
            "error": False,
            "sales_count": 1,
            "gross_sales": 1348371.10,
            "net_accrual": 752971.82,
            "commission": -190333.00,
            "logistics": -369353.19,
            "acquiring": -15778.95,
            "other_fees": -19934.14,
            "fee_breakdown": {},
        }),
        Costs(361368.00),
        tax_rate=0.06,
    )

    result = service.calculate(
        "2026-09-03",
        "2026-09-03",
        [{
            "product_id": "10",
            "offer_id": "hook-2",
            "sku": "100",
        }],
    )

    assert result["error"] is False
    assert result["revenue"] == 1348371.10
    assert result["tax"] == 80902.27
    assert result["profit"] == 310701.55
    assert result["margin_percent"] == 23.04


def test_v1219_production_factory_uses_repository_tax_policy_fraction():
    query = create_period_profit_query()

    assert query.summary_service.tax_rate == 0.06


def test_v1220_period_profit_tax_path_remains_read_only_configuration_only():
    query = create_period_profit_query()

    assert query.summary_service.tax_rate == 0.06
    assert query.return_evidence_service is not None
    assert not hasattr(query.summary_service, "execute")
    assert not hasattr(query.summary_service, "mutate")
