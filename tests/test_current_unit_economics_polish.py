from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)


def test_current_unit_economics_output_is_user_friendly():
    service = ProductUnitEconomicsQueryService(
        product_service=None,
        period_profit_service=None,
        analytics_service=None,
        unit_economics_provider=None
    )

    result = {
        "error": False,
        "source": "current",
        "sku": "hook-2",
        "unit_price": 96.0,
        "commission": 13.44,
        "logistics": 17.85,
        "last_mile": 1.55,
        "acquiring": 1.30,
        "cost": 21.0,
        "tax": 5.76,
        "net_profit_per_unit": 35.10,
        "margin_percent": 36.56,
        "missing_fields": [],
        "finance_sample_sales": 236,
        "finance_sample_days": 2,
        "as_of": "2026-08-25T08:02:47+00:00",
        "note": (
            "Основано на последних финансовых начислениях "
            "Ozon: 236 продаж за 2 дн."
        )
    }

    response = service.format_response(result)

    assert "Логистика:\n17.85 ₽ — 18.6%" in response
    assert "Последняя миля:\n1.55 ₽ — 1.6%" in response
    assert "Эквайринг:\n1.30 ₽ — 1.4%" in response
    assert "Логистика, среднее" not in response
    assert "Эквайринг, среднее" not in response
    assert "Цена:\n96.00 ₽ — 100.0%" in response
    assert "Прибыль с 1 шт:\n35.10 ₽ — 36.6%" in response
    assert "Актуальная цена продавца" not in response
    assert "Основано на последних финансовых начислениях" not in response
    assert "Данные обновлены:" not in response
