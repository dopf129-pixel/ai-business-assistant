import math

from services.advertising_service import AdvertisingService
from services.business_analytics_service import (
    BusinessAnalyticsService,
)
from services.expense_service import ExpenseService


class _EmptyExpenseRepository:
    def get_expenses_by_date(self, expense_date):
        return []


class _OverflowExpenseRepository:
    def get_expenses_by_date(self, expense_date):
        return [
            {
                "category": "a",
                "amount": 1e308,
            },
            {
                "category": "b",
                "amount": 1e308,
            },
        ]


def _profits():
    return [
        {
            "error": False,
            "sales_count": 10,
            "gross_sales": 10000.0,
            "net_accrual": 7000.0,
            "total_cost": 2000.0,
            "gross_profit": 5000.0,
        }
    ]


def test_v1111_advertising_calculate_rejects_non_finite_values():
    service = AdvertisingService()

    for value in (
        float("nan"),
        float("inf"),
        float("-inf"),
    ):
        result = service.calculate(value)

        assert result == {
            "error": True,
            "message": "Некорректная сумма расходов на рекламу",
        }


def test_v1112_advertising_calculate_rejects_boolean_values():
    service = AdvertisingService()

    for value in (
        True,
        False,
    ):
        result = service.calculate(value)

        assert result == {
            "error": True,
            "message": "Некорректная сумма расходов на рекламу",
        }


def test_v1113_advertising_negative_contract_remains_explicit():
    result = AdvertisingService().calculate(-1)

    assert result == {
        "error": True,
        "message": "Расходы на рекламу не могут быть отрицательными",
    }


def test_v1114_advertising_total_ignores_invalid_campaign_rows():
    result = AdvertisingService().total(
        [
            {"cost": 100},
            {"cost": "25.5"},
            {"cost": float("nan")},
            {"cost": float("inf")},
            {"cost": -5},
            {"cost": True},
            {"cost": "bad"},
            "not-a-campaign",
        ]
    )

    assert result == {
        "error": False,
        "campaigns": 8,
        "advertising_cost": 125.5,
    }
    assert math.isfinite(result["advertising_cost"])


def test_v1115_advertising_total_overflow_fails_closed():
    result = AdvertisingService().total(
        [
            {"cost": 1e308},
            {"cost": 1e308},
        ]
    )

    assert result == {
        "error": True,
        "message": "Некорректный итог расходов на рекламу",
    }
    assert "inf" not in str(result).lower()
    assert "nan" not in str(result).lower()


def test_v1116_expense_calculate_ignores_invalid_rows_and_stays_finite():
    result = ExpenseService().calculate(
        [
            {"name": "a", "amount": 100},
            {"name": "b", "amount": "25.5"},
            {"name": "nan", "amount": float("nan")},
            {"name": "inf", "amount": float("inf")},
            {"name": "negative", "amount": -5},
            {"name": "bool", "amount": True},
            {"name": "bad", "amount": "bad"},
            "not-an-expense",
        ]
    )

    assert result == {
        "error": False,
        "expenses_count": 2,
        "expenses": [
            {"name": "a", "amount": 100.0},
            {"name": "b", "amount": 25.5},
        ],
        "other_expenses": 125.5,
    }
    assert math.isfinite(result["other_expenses"])


def test_v1117_expense_total_overflow_fails_closed():
    result = ExpenseService().calculate(
        [
            {"name": "a", "amount": 1e308},
            {"name": "b", "amount": 1e308},
        ]
    )

    assert result == {
        "error": True,
        "message": "Некорректный итог прочих расходов",
    }


def test_v1118_expense_single_rejects_boolean_and_non_finite_values():
    service = ExpenseService()

    for value in (
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
    ):
        result = service.calculate_single(value)

        assert result == {
            "error": True,
            "message": "Некорректная сумма расхода",
        }


def test_v1119_valid_financial_input_compatibility_remains():
    advertising = AdvertisingService().calculate("100.50")
    expense = ExpenseService().calculate_single(
        "25.25",
        name="Упаковка",
    )

    assert advertising == {
        "error": False,
        "configured": True,
        "advertising_cost": 100.5,
    }
    assert expense == {
        "error": False,
        "expenses_count": 1,
        "expenses": [
            {
                "name": "Упаковка",
                "amount": 25.25,
            }
        ],
        "other_expenses": 25.25,
    }


def test_v1120_business_analytics_does_not_emit_profit_for_invalid_costs():
    invalid_advertising = BusinessAnalyticsService(
        tax_mode="USN_INCOME",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=float("nan"),
        analysis_date="2026-09-02",
        expense_repository=_EmptyExpenseRepository(),
    ).calculate(_profits())

    assert invalid_advertising["error"] is True
    assert invalid_advertising["advertising"]["error"] is True
    assert "business_profit" not in invalid_advertising

    overflow_expense = BusinessAnalyticsService(
        tax_mode="USN_INCOME",
        tax_rate=6,
        minimum_tax_rate=1,
        advertising_cost=0,
        analysis_date="2026-09-02",
        expense_repository=_OverflowExpenseRepository(),
    ).calculate(_profits())

    assert overflow_expense["error"] is True
    assert overflow_expense["expenses"] == {
        "error": True,
        "message": "Некорректный итог прочих расходов",
    }
    assert "business_profit" not in overflow_expense
