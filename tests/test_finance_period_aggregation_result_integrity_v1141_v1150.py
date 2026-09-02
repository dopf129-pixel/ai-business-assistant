import math

from services.finance_analytics_service import (
    FinanceAnalyticsService,
)
from services.store_analytics_service import StoreAnalyticsService


class _Finance:
    def __init__(self, rows):
        self.rows = rows

    def get_daily_finance(self, day, sku=None):
        value = self.rows[day]

        if isinstance(
            value,
            Exception
        ):
            raise value

        return value


def _daily(**overrides):
    result = {
        "error": False,
        "operations": 2,
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


def _service(rows):
    return FinanceAnalyticsService(
        _Finance(rows)
    )


def test_v1141_daily_source_exception_is_contained_as_failed_day():
    result = _service({
        "2026-09-01": OSError("private transport failure"),
    }).get_period_finance(
        "2026-09-01",
        "2026-09-01",
        "sku-1",
    )

    assert result["error"] is True
    assert result["days_loaded"] == 0
    assert result["days_failed"] == 1
    assert result["errors"] == [{
        "date": "2026-09-01",
        "message": "Финансовые данные дня недоступны",
    }]
    assert "private transport failure" not in str(result)


def test_v1142_non_mapping_daily_result_is_failed_not_exception():
    result = _service({
        "2026-09-01": ["bad"],
    }).get_period_finance(
        "2026-09-01",
        "2026-09-01",
    )

    assert result["error"] is True
    assert result["days_failed"] == 1
    assert result["errors"][0]["message"] == (
        "Некорректные финансовые данные дня"
    )


def test_v1143_malformed_error_marker_is_failed_day():
    result = _service({
        "2026-09-01": _daily(
            error="false"
        ),
    }).get_period_finance(
        "2026-09-01",
        "2026-09-01",
    )

    assert result["error"] is True
    assert result["days_loaded"] == 0
    assert result["days_failed"] == 1


def test_v1144_invalid_counters_do_not_enter_period_totals():
    for field in (
        "operations",
        "sales_count",
    ):
        for value in (
            True,
            -1,
            1.5,
            "bad",
            float("nan"),
            float("inf"),
        ):
            result = _service({
                "2026-09-01": _daily(
                    **{field: value}
                ),
            }).get_period_finance(
                "2026-09-01",
                "2026-09-01",
            )

            assert result["error"] is True
            assert result["days_loaded"] == 0
            assert result["operations"] == 0
            assert result["sales_count"] == 0


def test_v1145_invalid_amount_field_does_not_partially_commit_day():
    for field in FinanceAnalyticsService.AMOUNT_FIELDS:
        for value in (
            True,
            "bad",
            float("nan"),
            float("inf"),
        ):
            result = _service({
                "2026-09-01": _daily(
                    **{field: value}
                ),
            }).get_period_finance(
                "2026-09-01",
                "2026-09-01",
            )

            assert result["error"] is True
            assert result["days_loaded"] == 0
            assert result["gross_sales"] == 0.0
            assert result["net_accrual"] == 0.0


def test_v1146_malformed_fee_breakdown_fails_whole_day():
    malformed = _service({
        "2026-09-01": _daily(
            fee_breakdown=["bad"]
        ),
    }).get_period_finance(
        "2026-09-01",
        "2026-09-01",
    )
    invalid_amount = _service({
        "2026-09-01": _daily(
            fee_breakdown={
                "commission": float("nan"),
            }
        ),
    }).get_period_finance(
        "2026-09-01",
        "2026-09-01",
    )

    for result in (
        malformed,
        invalid_amount,
    ):
        assert result["error"] is True
        assert result["days_loaded"] == 0
        assert result["fee_breakdown"] == {}


def test_v1147_partial_period_keeps_only_fully_valid_days():
    result = _service({
        "2026-09-01": _daily(),
        "2026-09-02": _daily(
            gross_sales=float("nan")
        ),
    }).get_period_finance(
        "2026-09-01",
        "2026-09-02",
        "sku-1",
    )

    assert result["error"] is False
    assert result["days_requested"] == 2
    assert result["days_loaded"] == 1
    assert result["days_failed"] == 1
    assert result["operations"] == 2
    assert result["sales_count"] == 1
    assert result["gross_sales"] == 100.0
    assert result["net_accrual"] == 80.0
    assert result["fee_breakdown"] == {
        "commission": -10.0,
    }


def test_v1148_aggregate_overflow_fails_closed_without_inf_output():
    result = _service({
        "2026-09-01": _daily(
            gross_sales=1e308
        ),
        "2026-09-02": _daily(
            gross_sales=1e308
        ),
    }).get_period_finance(
        "2026-09-01",
        "2026-09-02",
    )

    assert result["error"] is True
    assert result["code"] == (
        "FINANCE_PERIOD_AGGREGATE_INVALID"
    )
    assert result["days_loaded"] == 1
    assert result["days_failed"] == 1
    for field in FinanceAnalyticsService.AMOUNT_FIELDS:
        assert math.isfinite(
            result[field]
        )

    assert all(
        math.isfinite(amount)
        for amount in result["fee_breakdown"].values()
    )


def test_v1149_valid_numeric_strings_and_signed_fees_remain_compatible():
    result = _service({
        "2026-09-01": _daily(
            operations="2",
            sales_count="1.0",
            gross_sales="100",
            net_accrual="80",
            commission="-10",
            logistics="-5",
            acquiring="-2",
            other_fees="-3",
            fee_breakdown={
                "commission": "-10",
                "storage": "4.5",
            },
        ),
    }).get_period_finance(
        "2026-09-01",
        "2026-09-01",
    )

    assert result["error"] is False
    assert result["operations"] == 2
    assert result["sales_count"] == 1
    assert result["gross_sales"] == 100.0
    assert result["commission"] == -10.0
    assert result["fee_breakdown"] == {
        "commission": -10.0,
        "storage": 4.5,
    }


def test_v1150_store_analytics_finance_path_contains_source_exception():
    finance = _Finance({
        "2026-09-02": RuntimeError(
            "private daily failure"
        ),
    })
    analytics = StoreAnalyticsService(
        tax_mode="NONE",
        tax_rate=0,
        minimum_tax_rate=1,
        advertising_cost=0,
        analysis_date="2026-09-02",
        finance_service=finance,
    )

    result = analytics.analyze_finance(
        sku="sku-1"
    )

    assert result["error"] is True
    assert result["days_requested"] == 1
    assert result["days_loaded"] == 0
    assert result["days_failed"] == 1
    assert "private daily failure" not in str(result)
