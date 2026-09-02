from services.assistant_sales_executor_service import (
    AssistantSalesExecutorService,
)
from services.business_analytics_service import (
    BusinessAnalyticsService,
)
from services.sales_intelligence_service import (
    SalesIntelligenceService,
)
from services.store_analytics_service import (
    StoreAnalyticsService,
)
from services.store_profit_service import StoreProfitService


def _profit(**overrides):
    result = {
        "error": False,
        "sales_count": 2,
        "gross_sales": 1000.0,
        "net_accrual": 700.0,
        "total_cost": 400.0,
        "gross_profit": 300.0,
    }
    result.update(overrides)
    return result


def test_v1121_non_list_store_profit_input_fails_closed():
    service = StoreProfitService()

    for value in (
        None,
        {},
        "bad",
    ):
        assert service.calculate(value) == {
            "error": True,
            "code": "STORE_PROFIT_DATA_INVALID",
            "message": "Некорректные данные о прибыли товаров",
        }


def test_v1122_non_mapping_profit_record_fails_closed():
    result = StoreProfitService().calculate(
        [
            _profit(),
            "bad-record",
        ]
    )

    assert result["error"] is True
    assert result["code"] == "STORE_PROFIT_DATA_INVALID"


def test_v1123_invalid_sales_count_never_truncates_or_subtracts():
    service = StoreProfitService()

    for value in (
        True,
        False,
        -1,
        1.5,
        "bad",
        float("nan"),
        float("inf"),
    ):
        result = service.calculate(
            [
                _profit(
                    sales_count=value
                )
            ]
        )

        assert result["error"] is True
        assert result["code"] == "STORE_PROFIT_DATA_INVALID"


def test_v1124_invalid_financial_value_fails_closed():
    service = StoreProfitService()

    for field in (
        "gross_sales",
        "net_accrual",
        "total_cost",
        "gross_profit",
    ):
        for value in (
            True,
            "bad",
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            result = service.calculate(
                [
                    _profit(
                        **{field: value}
                    )
                ]
            )

            assert result["error"] is True
            assert result["code"] == "STORE_PROFIT_DATA_INVALID"


def test_v1125_aggregate_overflow_never_returns_infinity():
    result = StoreProfitService().calculate(
        [
            _profit(
                gross_sales=1e308
            ),
            _profit(
                gross_sales=1e308
            ),
        ]
    )

    assert result == {
        "error": True,
        "code": "STORE_PROFIT_RESULT_INVALID",
        "message": "Некорректный итог прибыли магазина",
    }
    assert "inf" not in str(result).lower()
    assert "nan" not in str(result).lower()


def test_v1126_failed_product_rows_remain_skipped():
    result = StoreProfitService().calculate(
        [
            {
                "error": True,
                "sales_count": "broken",
                "gross_sales": float("nan"),
            },
            _profit(),
        ]
    )

    assert result == {
        "sales_count": 2,
        "gross_sales": 1000.0,
        "net_accrual": 700.0,
        "total_cost": 400.0,
        "gross_profit": 300.0,
        "margin_percent": 30.0,
        "profitable_products": 1,
        "loss_products": 0,
    }


def test_v1127_missing_numeric_fields_preserve_zero_defaults():
    result = StoreProfitService().calculate(
        [
            {
                "error": False,
            }
        ]
    )

    assert result == {
        "sales_count": 0,
        "gross_sales": 0.0,
        "net_accrual": 0.0,
        "total_cost": 0.0,
        "gross_profit": 0.0,
        "margin_percent": 0.0,
        "profitable_products": 1,
        "loss_products": 0,
    }


def test_v1128_valid_numeric_strings_and_losses_remain_compatible():
    result = StoreProfitService().calculate(
        [
            _profit(
                sales_count="2",
                gross_sales="1000",
                net_accrual="700",
                total_cost="400",
                gross_profit="-50",
            ),
            _profit(
                sales_count="3.0",
                gross_sales="500",
                net_accrual="350",
                total_cost="200",
                gross_profit="100",
            ),
        ]
    )

    assert result == {
        "sales_count": 5,
        "gross_sales": 1500.0,
        "net_accrual": 1050.0,
        "total_cost": 600.0,
        "gross_profit": 50.0,
        "margin_percent": 3.33,
        "profitable_products": 1,
        "loss_products": 1,
    }


class _ShouldNotCall:
    def calculate(self, *args, **kwargs):
        raise AssertionError("downstream calculation must not run")


def test_v1129_business_analytics_propagates_store_profit_failure_first():
    service = BusinessAnalyticsService(
        tax_mode="USN_INCOME",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=0,
        analysis_date="2026-09-02",
    )
    service.tax_service = _ShouldNotCall()
    service.advertising_service = _ShouldNotCall()
    service.expense_service = _ShouldNotCall()

    result = service.calculate(
        [
            _profit(
                gross_sales=float("nan")
            )
        ]
    )

    assert result["error"] is True
    assert result["code"] == "STORE_PROFIT_DATA_INVALID"
    assert result["message"] == (
        "Некорректные данные о прибыли товаров"
    )
    assert result["store_profit"]["error"] is True
    assert "tax" not in result
    assert "advertising" not in result
    assert "expenses" not in result
    assert "business_profit" not in result


def test_v1130_sales_intelligence_and_executor_preserve_failure():
    analytics = StoreAnalyticsService(
        tax_mode="USN_INCOME",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=0,
        analysis_date="2026-09-02",
    )
    intelligence = SalesIntelligenceService(
        analytics_service=analytics
    )
    executor = AssistantSalesExecutorService(
        sales_intelligence_service=intelligence
    )
    profits = [
        _profit(
            total_cost=float("inf")
        )
    ]

    analyzed = intelligence.analyze(
        profits
    )
    executed = executor.execute(
        {
            "context": {
                "profits": profits,
            }
        }
    )

    assert analyzed["error"] is True
    assert analyzed["code"] == "STORE_PROFIT_DATA_INVALID"
    assert executed["error"] is True
    assert executed["code"] == "STORE_PROFIT_DATA_INVALID"
    assert "result" not in executed
