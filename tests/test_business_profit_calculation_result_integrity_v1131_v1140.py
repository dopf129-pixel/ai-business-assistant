from services.assistant_sales_executor_service import (
    AssistantSalesExecutorService,
)
from services.business_analytics_service import (
    BusinessAnalyticsService,
)
from services.business_profit_service import BusinessProfitService
from services.sales_intelligence_service import (
    SalesIntelligenceService,
)
from services.store_analytics_service import StoreAnalyticsService


class _EmptyExpenseRepository:
    def get_expenses_by_date(self, expense_date):
        return []


def _store_profit(**overrides):
    result = {
        "gross_sales": 1000.0,
        "gross_profit": 400.0,
    }
    result.update(overrides)
    return result


def _tax(**overrides):
    result = {
        "error": False,
        "configured": True,
        "tax_amount": 60.0,
    }
    result.update(overrides)
    return result


def test_v1131_non_mapping_business_profit_inputs_fail_closed():
    service = BusinessProfitService()

    store = service.calculate(
        "bad",
        _tax(),
    )
    tax = service.calculate(
        _store_profit(),
        "bad",
    )

    assert store["error"] is True
    assert store["code"] == "BUSINESS_PROFIT_STORE_PROFIT_INVALID"
    assert tax["error"] is True
    assert tax["code"] == "BUSINESS_PROFIT_TAX_RESULT_INVALID"


def test_v1132_malformed_error_and_configured_markers_fail_closed():
    service = BusinessProfitService()

    store = service.calculate(
        _store_profit(
            error="false"
        ),
        _tax(),
    )
    tax_error = service.calculate(
        _store_profit(),
        _tax(
            error="false"
        ),
    )
    configured = service.calculate(
        _store_profit(),
        _tax(
            configured="true"
        ),
    )

    assert store["code"] == "BUSINESS_PROFIT_STORE_PROFIT_INVALID"
    assert tax_error["code"] == "BUSINESS_PROFIT_TAX_RESULT_INVALID"
    assert configured["code"] == "BUSINESS_PROFIT_TAX_RESULT_INVALID"


def test_v1133_store_profit_numeric_values_must_be_finite_non_boolean():
    service = BusinessProfitService()

    for field in (
        "gross_sales",
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
                _store_profit(
                    **{field: value}
                ),
                _tax(),
            )

            assert result["error"] is True
            assert result["code"] == (
                "BUSINESS_PROFIT_STORE_PROFIT_INVALID"
            )


def test_v1134_cost_inputs_must_be_finite_non_negative_non_boolean():
    service = BusinessProfitService()

    for value in (
        True,
        -1,
        "bad",
        float("nan"),
        float("inf"),
    ):
        advertising = service.calculate(
            _store_profit(),
            _tax(),
            advertising_cost=value,
        )
        expenses = service.calculate(
            _store_profit(),
            _tax(),
            other_expenses=value,
        )

        assert advertising["code"] == (
            "BUSINESS_PROFIT_COST_INPUT_INVALID"
        )
        assert expenses["code"] == (
            "BUSINESS_PROFIT_COST_INPUT_INVALID"
        )


def test_v1135_unknown_tax_contract_remains_unknown_not_zero():
    result = BusinessProfitService().calculate(
        _store_profit(),
        {
            "error": False,
            "configured": False,
            "tax_amount": None,
        },
        advertising_cost="25",
        other_expenses="10",
    )

    assert result == {
        "error": False,
        "configured": False,
        "gross_sales": 1000.0,
        "gross_profit": 400.0,
        "tax_amount": None,
        "advertising_cost": 25.0,
        "other_expenses": 10.0,
        "business_profit": None,
        "margin_percent": None,
    }


def test_v1136_tax_amount_must_be_finite_non_negative_non_boolean():
    service = BusinessProfitService()

    for value in (
        True,
        -1,
        "bad",
        float("nan"),
        float("inf"),
    ):
        result = service.calculate(
            _store_profit(),
            _tax(
                tax_amount=value
            ),
        )

        assert result == {
            "error": True,
            "code": "BUSINESS_PROFIT_TAX_RESULT_INVALID",
            "message": "Некорректный результат расчёта налога",
        }


def test_v1137_existing_tax_error_message_contract_is_preserved():
    result = BusinessProfitService().calculate(
        _store_profit(),
        {
            "error": True,
            "message": "Неподдерживаемый налоговый режим",
        },
    )

    assert result == {
        "error": True,
        "message": "Неподдерживаемый налоговый режим",
    }


def test_v1138_non_finite_business_profit_and_margin_fail_closed():
    service = BusinessProfitService()

    overflow_profit = service.calculate(
        _store_profit(
            gross_profit=-1e308
        ),
        {
            "error": False,
            "configured": True,
            "tax_amount": 0,
        },
        advertising_cost=1e308,
    )
    overflow_margin = service.calculate(
        _store_profit(
            gross_sales=1e-308,
            gross_profit=1e308,
        ),
        {
            "error": False,
            "configured": True,
            "tax_amount": 0,
        },
    )

    for result in (
        overflow_profit,
        overflow_margin,
    ):
        assert result == {
            "error": True,
            "code": "BUSINESS_PROFIT_RESULT_INVALID",
            "message": "Некорректный результат прибыли бизнеса",
        }
        assert "inf" not in str(result).lower()
        assert "nan" not in str(result).lower()


def test_v1139_valid_formula_and_numeric_string_compatibility_remain():
    service = BusinessProfitService()

    result = service.calculate(
        _store_profit(
            gross_sales="1000",
            gross_profit="400",
        ),
        {
            "error": False,
            "tax_amount": "60",
        },
        advertising_cost="25",
        other_expenses="15",
    )

    assert result == {
        "error": False,
        "configured": True,
        "gross_sales": 1000.0,
        "gross_profit": 400.0,
        "tax_amount": 60.0,
        "advertising_cost": 25.0,
        "other_expenses": 15.0,
        "business_profit": 300.0,
        "margin_percent": 30.0,
    }


def test_v1140_integrity_failure_is_preserved_to_sales_executor():
    profits = [
        {
            "error": False,
            "sales_count": 1,
            "gross_sales": 1000.0,
            "net_accrual": 0.0,
            "total_cost": 0.0,
            "gross_profit": -1e308,
        }
    ]
    analytics = StoreAnalyticsService(
        tax_mode="NONE",
        tax_rate=0,
        minimum_tax_rate=1,
        advertising_cost=1e308,
        analysis_date="2026-09-02",
        expense_repository=_EmptyExpenseRepository(),
    )
    intelligence = SalesIntelligenceService(
        analytics_service=analytics
    )
    executor = AssistantSalesExecutorService(
        sales_intelligence_service=intelligence
    )

    direct = analytics.business_analytics.calculate(
        profits
    )
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

    for result in (
        direct,
        analyzed,
        executed,
    ):
        assert result["error"] is True
        assert result["code"] == "BUSINESS_PROFIT_RESULT_INVALID"

    assert direct["business_profit"]["error"] is True
    assert "result" not in executed
