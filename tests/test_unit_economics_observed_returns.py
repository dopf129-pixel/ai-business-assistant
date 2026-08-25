from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService,
)


class StubReturnsImpactQuery:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def query(self, sku):
        self.calls.append(sku)
        return dict(self.result)


def _impact(complete=False, delivered_units=None):
    return {
        "error": False,
        "complete": complete,
        "delivered_units": delivered_units,
        "categories": {
            "customer_non_buyout": {
                "label": "Невыкуп",
                "event_posting_count": 93,
                "finance_coverage_percent": 88.17,
                "observed_cost_total": 4668.60,
                "observed_cost_average": 56.93,
            },
            "customer_return": {
                "label": "Возврат покупателя",
                "event_posting_count": 2,
                "finance_coverage_percent": 100.0,
                "observed_cost_total": 108.73,
                "observed_cost_average": 54.36,
            },
        },
    }


def _service(impact):
    return ProductUnitEconomicsQueryService(
        product_service=None,
        period_profit_service=None,
        analytics_service=None,
        unit_economics_provider=None,
        returns_finance_impact_query=(
            StubReturnsImpactQuery(impact)
        ),
    )


def _economics():
    return {
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
        "missing_fields": ["returns"],
    }


def test_observed_returns_are_attached_without_changing_base_profit():
    service = _service(_impact(complete=False))
    original = _economics()

    result = service._attach_returns_impact(
        "hook-2",
        original,
    )

    assert service.returns_finance_impact_query.calls == [
        "hook-2"
    ]
    assert result["net_profit_per_unit"] == 35.10
    assert result["returns_observed_cost_total"] == 4777.33
    assert result["returns_observed_event_count"] == 95
    assert result["returns_finance_complete"] is False
    assert result["risk_adjusted_profit_per_unit"] is None
    assert original.get("returns_finance_impact") is None


def test_current_card_shows_observed_cost_and_unknown_adjusted_profit():
    service = _service(_impact(complete=False))
    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    response = service.format_response(result)

    assert "Невыкуп:" in response
    assert "Покрытие: 88.17%" in response
    assert "Наблюдаемые расходы: 4668.60 ₽" in response
    assert "Всего наблюдаемых расходов:\n4777.33 ₽" in response
    assert "Скорректированная прибыль с 1 шт:\n—" in response
    assert "экстраполяция не выполнялась" in response


def test_complete_attribution_allocates_cost_over_same_period_deliveries():
    service = _service(_impact(
        complete=True,
        delivered_units=1000,
    ))
    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    response = service.format_response(result)

    assert result["returns_finance_complete"] is True
    assert result["returns_delivered_units"] == 1000
    assert result["returns_cost_per_delivered_unit"] == 4.78
    assert result["risk_adjusted_profit_per_unit"] == 30.32
    assert result["risk_adjusted_margin_percent"] == 31.58
    assert "returns" not in result["missing_fields"]
    assert "Расход на доставленную единицу:\n4.78 ₽" in response
    assert "Скорректированная прибыль с 1 шт:\n30.32 ₽" in response
    assert "Скорректированная маржа:\n31.58%" in response
    assert "экстраполяция не выполнялась" not in response


def test_complete_attribution_without_denominator_keeps_adjustment_unknown():
    service = _service(_impact(
        complete=True,
        delivered_units=None,
    ))
    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    response = service.format_response(result)

    assert result["returns_cost_per_delivered_unit"] is None
    assert result["risk_adjusted_profit_per_unit"] is None
    assert "returns" in result["missing_fields"]
    assert "Скорректированная прибыль с 1 шт:\n—" in response
    assert "не хватает полных данных" in response


def test_unavailable_returns_data_keeps_unit_economics_available():
    service = _service({
        "error": True,
        "message": "Ozon API недоступен",
    })

    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )
    response = service.format_response(result)

    assert result["error"] is False
    assert result["net_profit_per_unit"] == 35.10
    assert result["returns_observed_cost_total"] is None
    assert result["risk_adjusted_profit_per_unit"] is None
    assert "Наблюдаемые расходы:\n—" in response
    assert "Скорректированная прибыль с 1 шт:\n—" in response
