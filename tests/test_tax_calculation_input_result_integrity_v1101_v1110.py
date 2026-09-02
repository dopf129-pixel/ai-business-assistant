import math

from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider,
)
from services.tax_service import TaxService


def test_v1101_missing_mode_preserves_unconfigured_contract():
    result = TaxService().calculate(
        mode=None,
        revenue="broken",
        gross_profit=float("nan"),
    )

    assert result == {
        "error": False,
        "configured": False,
        "mode": None,
        "mode_name": "Не настроен",
        "tax_base": None,
        "tax_rate": None,
        "tax_amount": None,
    }


def test_v1102_unsupported_mode_is_rejected_before_numeric_conversion():
    result = TaxService().calculate(
        mode="UNSUPPORTED",
        revenue="broken",
        gross_profit=object(),
    )

    assert result == {
        "error": True,
        "message": "Неподдерживаемый налоговый режим",
    }


def test_v1103_non_numeric_tax_inputs_fail_closed():
    service = TaxService()

    for revenue, gross_profit in (
        ("broken", 100),
        (1000, "broken"),
        (object(), 100),
        (1000, object()),
    ):
        result = service.calculate(
            mode="USN_INCOME",
            revenue=revenue,
            gross_profit=gross_profit,
            tax_rate=6.0,
        )

        assert result == {
            "error": True,
            "message": "Некорректные данные для расчёта налога",
        }


def test_v1104_non_finite_tax_inputs_fail_closed():
    service = TaxService()

    for value in (
        float("nan"),
        float("inf"),
        float("-inf"),
    ):
        for kwargs in (
            {
                "revenue": value,
                "gross_profit": 100.0,
            },
            {
                "revenue": 1000.0,
                "gross_profit": value,
            },
        ):
            result = service.calculate(
                mode="USN_INCOME",
                tax_rate=6.0,
                **kwargs,
            )

            assert result["error"] is True
            assert result["message"] == (
                "Некорректные данные для расчёта налога"
            )


def test_v1105_boolean_tax_inputs_are_not_numeric_amounts():
    service = TaxService()

    for kwargs in (
        {
            "revenue": True,
            "gross_profit": 100.0,
        },
        {
            "revenue": 1000.0,
            "gross_profit": False,
        },
    ):
        result = service.calculate(
            mode="USN_INCOME",
            tax_rate=6.0,
            **kwargs,
        )

        assert result["error"] is True
        assert result["message"] == (
            "Некорректные данные для расчёта налога"
        )


def test_v1106_invalid_income_tax_rate_fails_closed():
    service = TaxService()

    for rate in (
        "bad",
        True,
        -0.01,
        100.01,
        float("nan"),
        float("inf"),
    ):
        result = service.calculate(
            mode="USN_INCOME",
            revenue=1000.0,
            gross_profit=400.0,
            tax_rate=rate,
        )

        assert result == {
            "error": True,
            "message": "Некорректная налоговая ставка",
        }


def test_v1107_invalid_minimum_tax_rate_fails_closed():
    service = TaxService()

    for rate in (
        "bad",
        False,
        -0.01,
        100.01,
        float("nan"),
        float("inf"),
    ):
        result = service.calculate(
            mode="USN_INCOME_MINUS_EXPENSES",
            revenue=1000.0,
            gross_profit=400.0,
            tax_rate=15.0,
            minimum_tax_rate=rate,
        )

        assert result == {
            "error": True,
            "message": (
                "Некорректная минимальная налоговая ставка"
            ),
        }


def test_v1108_overflow_tax_result_never_returns_infinity():
    result = TaxService().calculate(
        mode="USN_INCOME",
        revenue=1e308,
        gross_profit=1e308,
        tax_rate=100.0,
    )

    assert result == {
        "error": True,
        "message": "Некорректный результат расчёта налога",
    }
    assert "inf" not in str(result).lower()
    assert "nan" not in str(result).lower()


def test_v1109_valid_tax_formulas_and_numeric_string_compatibility_remain():
    service = TaxService()

    income = service.calculate(
        mode="USN_INCOME",
        revenue="1000",
        gross_profit="-10",
        tax_rate="6",
    )
    income_minus_expenses = service.calculate(
        mode="USN_INCOME_MINUS_EXPENSES",
        revenue="1000",
        gross_profit="400",
        tax_rate="15",
        minimum_tax_rate="1",
    )
    negative = service.calculate(
        mode="USN_INCOME_MINUS_EXPENSES",
        revenue=-100,
        gross_profit=-50,
        tax_rate=15,
        minimum_tax_rate=1,
    )

    assert income["error"] is False
    assert income["tax_base"] == 1000.0
    assert income["tax_amount"] == 60.0
    assert income_minus_expenses["error"] is False
    assert income_minus_expenses["regular_tax"] == 60.0
    assert income_minus_expenses["minimum_tax"] == 10.0
    assert income_minus_expenses["tax_amount"] == 60.0
    assert negative["tax_base"] == 0.0
    assert negative["minimum_tax"] == 0.0
    assert negative["tax_amount"] == 0.0


def test_v1110_unit_economics_treats_invalid_tax_result_as_unknown():
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=float("nan"),
    )

    result = provider.build(
        [
            {
                "error": False,
                "product_id": "101",
                "sku": "hook-2",
                "sales_count": 2,
                "gross_sales": 1000.0,
                "total_cost": 400.0,
                "net_accrual": 700.0,
                "gross_profit": 300.0,
            },
        ]
    )[0]

    assert result["tax"] is None
    assert result["net_profit"] is None
    assert result["profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert result["marketplace_fees"] == 300.0
    for key in (
        "revenue",
        "product_cost",
        "marketplace_fees",
    ):
        assert math.isfinite(result[key])
