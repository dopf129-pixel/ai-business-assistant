from datetime import date
import math

from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)
from services.period_profit_query_service import PeriodProfitQueryService
from services.period_profit_summary_service import PeriodProfitSummaryService


class _Finance:
    def __init__(self, rows):
        self.rows = rows

    def get_daily_finance(self, day, sku=None):
        value = self.rows[(day, sku)]
        if isinstance(value, Exception):
            raise value
        return value


class _Costs:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error

    def get_cost(self, product_id):
        if self.error is not None:
            raise self.error
        return self.value


def _daily(**overrides):
    result = {
        "error": False,
        "sales_count": 1,
        "gross_sales": 100.0,
        "net_accrual": 80.0,
        "commission": -10.0,
        "logistics": -5.0,
        "acquiring": -2.0,
        "other_fees": -3.0,
        "fee_breakdown": {
            "commission": -10.0,
        },
    }
    result.update(overrides)
    return result


def _product(**overrides):
    result = {
        "product_id": "10",
        "sku": "100",
        "offer_id": "offer-100",
        "cost": 20.0,
    }
    result.update(overrides)
    return result


def _service(rows, *, cost_service=None, tax_rate=0.06):
    return PeriodProfitSummaryService(
        _Finance(rows),
        cost_service or _Costs(),
        tax_rate=tax_rate,
    )


def test_v1151_daily_finance_source_exception_is_contained():
    service = _service({
        ("2026-09-02", "100"): RuntimeError(
            "private finance transport failure"
        ),
    })

    result = service.calculate(
        "2026-09-02",
        "2026-09-02",
        [_product()],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_UNAVAILABLE"
    assert "private finance transport failure" not in str(result)


def test_v1152_malformed_daily_result_and_error_marker_fail_closed():
    malformed = _service({
        ("2026-09-02", "100"): ["bad"],
    }).calculate(
        "2026-09-02",
        "2026-09-02",
        [_product()],
    )

    marker = _service({
        ("2026-09-02", "100"): _daily(error="false"),
    }).calculate(
        "2026-09-02",
        "2026-09-02",
        [_product()],
    )

    for result in (malformed, marker):
        assert result["error"] is True
        assert result["code"] == "PERIOD_PROFIT_FINANCE_INVALID"


def test_v1153_sales_count_requires_non_negative_exact_integer():
    for value in (
        True,
        -1,
        1.5,
        "bad",
        float("nan"),
        float("inf"),
    ):
        result = _service({
            ("2026-09-02", "100"): _daily(
                sales_count=value
            ),
        }).calculate(
            "2026-09-02",
            "2026-09-02",
            [_product()],
        )

        assert result["error"] is True
        assert result["code"] == "PERIOD_PROFIT_FINANCE_INVALID"


def test_v1154_daily_amounts_reject_bool_non_numeric_and_non_finite():
    fields = (
        "gross_sales",
        "net_accrual",
        "commission",
        "logistics",
        "acquiring",
        "other_fees",
    )

    for field in fields:
        for value in (
            True,
            "bad",
            float("nan"),
            float("inf"),
        ):
            result = _service({
                ("2026-09-02", "100"): _daily(
                    **{field: value}
                ),
            }).calculate(
                "2026-09-02",
                "2026-09-02",
                [_product()],
            )

            assert result["error"] is True
            assert result["code"] == "PERIOD_PROFIT_FINANCE_INVALID"


def test_v1155_fee_breakdown_must_be_mapping_with_finite_amounts():
    malformed = _service({
        ("2026-09-02", "100"): _daily(
            fee_breakdown=["bad"]
        ),
    }).calculate(
        "2026-09-02",
        "2026-09-02",
        [_product()],
    )

    invalid_amount = _service({
        ("2026-09-02", "100"): _daily(
            fee_breakdown={
                "commission": float("nan"),
            }
        ),
    }).calculate(
        "2026-09-02",
        "2026-09-02",
        [_product()],
    )

    for result in (malformed, invalid_amount):
        assert result["error"] is True
        assert result["code"] == "PERIOD_PROFIT_FINANCE_INVALID"


def test_v1156_cost_failures_are_invalid_or_unavailable_not_exceptions():
    for value in (
        True,
        -1,
        "bad",
        float("nan"),
        float("inf"),
    ):
        result = _service({
            ("2026-09-02", "100"): _daily(),
        }).calculate(
            "2026-09-02",
            "2026-09-02",
            [_product(cost=value)],
        )

        assert result["error"] is True
        assert result["code"] == "PERIOD_PROFIT_COST_INVALID"

    unavailable = _service(
        {
            ("2026-09-02", "100"): _daily(),
        },
        cost_service=_Costs(
            error=RuntimeError("private cost storage failure")
        ),
    ).calculate(
        "2026-09-02",
        "2026-09-02",
        [_product(cost=None)],
    )

    assert unavailable["error"] is True
    assert unavailable["code"] == "PERIOD_PROFIT_COST_UNAVAILABLE"
    assert "private cost storage failure" not in str(unavailable)


def test_v1157_invalid_tax_rate_fails_closed_without_startup_exception():
    for tax_rate in (
        True,
        -0.01,
        "bad",
        float("nan"),
        float("inf"),
    ):
        service = _service(
            {
                ("2026-09-02", "100"): _daily(),
            },
            tax_rate=tax_rate,
        )

        result = service.calculate(
            "2026-09-02",
            "2026-09-02",
            [_product()],
        )

        assert result["error"] is True
        assert result["code"] == "PERIOD_PROFIT_TAX_RATE_INVALID"


def test_v1158_amount_and_fee_aggregate_overflow_fail_closed():
    amount_overflow = _service(
        {
            ("2026-09-01", "100"): _daily(
                gross_sales=1e308,
                net_accrual=1e308,
            ),
            ("2026-09-02", "100"): _daily(
                gross_sales=1e308,
                net_accrual=1e308,
            ),
        },
        tax_rate=0,
    ).calculate(
        "2026-09-01",
        "2026-09-02",
        [_product(cost=0)],
    )

    fee_overflow = _service(
        {
            ("2026-09-01", "100"): _daily(
                fee_breakdown={"x": 1e308}
            ),
            ("2026-09-02", "100"): _daily(
                fee_breakdown={"x": 1e308}
            ),
        },
        tax_rate=0,
    ).calculate(
        "2026-09-01",
        "2026-09-02",
        [_product(cost=0)],
    )

    for result in (amount_overflow, fee_overflow):
        assert result["error"] is True
        assert result["code"] == "PERIOD_PROFIT_AGGREGATE_INVALID"
        assert all(
            not (
                isinstance(value, float)
                and not math.isfinite(value)
            )
            for value in result.values()
        )


def test_v1159_valid_numeric_strings_and_existing_formula_remain_compatible():
    result = _service(
        {
            ("2026-09-02", "100"): _daily(
                sales_count="2.0",
                gross_sales="200",
                net_accrual="150",
                commission="-20",
                logistics="-15",
                acquiring="-3",
                other_fees="-12",
                fee_breakdown={
                    "commission": "-20",
                    "storage": "4.5",
                },
            ),
        },
        tax_rate="0.06",
    ).calculate(
        "2026-09-02",
        "2026-09-02",
        [_product(cost="20")],
    )

    assert result["error"] is False
    assert result["units_sold"] == 2
    assert result["revenue"] == 200.0
    assert result["net_accrual"] == 150.0
    assert result["product_cost"] == 40.0
    assert result["tax"] == 12.0
    assert result["profit"] == 98.0
    assert result["margin_percent"] == 49.0
    assert result["fee_breakdown"] == {
        "commission": -20.0,
        "storage": 4.5,
    }


def test_v1160_runtime_query_preserves_period_profit_integrity_failure():
    summary = _service({
        ("2026-09-02", "100"): _daily(
            gross_sales=float("nan")
        ),
    })
    query = PeriodProfitQueryService(
        summary_service=summary,
        product_provider=lambda: [_product()],
    )
    runtime = AssistantPeriodProfitRuntimeService(query)

    result = runtime.handle_text(
        "прибыль сегодня",
        today=date(2026, 9, 2),
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_INVALID"
    assert result["status"] == "PERIOD_PROFIT_SUMMARY_UNAVAILABLE"
