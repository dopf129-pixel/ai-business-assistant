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


def _impact(
    complete=False,
    delivered_units=4653,
    classification_complete=True,
    observed_non_buyouts=None,
):
    observed = (
        90
        if complete
        else (
            82
            if observed_non_buyouts is None
            else observed_non_buyouts
        )
    )
    non_buyout_total = (
        5124.07
        if complete
        else round(56.93414634 * observed, 2)
    )
    return {
        "error": False,
        "complete": complete,
        "period_days": 30,
        "classification_complete": classification_complete,
        "finance_complete": complete,
        "delivered_units": delivered_units,
        "missing_data": (
            []
            if complete
            else ["finance_postings_unmatched"]
        ),
        "categories": {
            "customer_non_buyout": {
                "label": "Невыкуп",
                "event_posting_count": 90,
                "finance_matched_posting_count": observed,
                "observed_posting_count": observed,
                "finance_coverage_percent": round(
                    observed / 90 * 100,
                    2,
                ),
                "observed_cost_total": non_buyout_total,
                "observed_cost_average": 56.93,
                "complete": complete,
            },
            "customer_return": {
                "label": "Возврат покупателя",
                "event_posting_count": 2,
                "finance_matched_posting_count": 2,
                "observed_posting_count": 2,
                "finance_coverage_percent": 100.0,
                "observed_cost_total": 108.73,
                "observed_cost_average": 54.36,
                "complete": True,
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


def test_covered_sample_estimates_returns_adjusted_profit():
    service = _service(_impact())
    original = _economics()

    result = service._attach_returns_impact(
        "hook-2",
        original,
    )

    assert service.returns_finance_impact_query.calls == [
        "hook-2"
    ]
    assert result["net_profit_per_unit"] == 35.10
    assert result["returns_finance_complete"] is False
    assert result["returns_estimate_available"] is True
    assert result["estimated_returns_cost_total"] == 5232.80
    assert result["estimated_returns_cost_per_unit"] == 1.12
    assert result["estimated_profit_per_unit"] == 33.98
    assert result["estimated_margin_percent"] == 35.40
    assert result["returns_estimate_coverage_percent"] == 91.11
    assert result["risk_adjusted_profit_per_unit"] is None
    assert original.get("returns_finance_impact") is None


def test_card_shows_only_estimated_profit_and_coverage_warning():
    service = _service(_impact())
    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    response = service.format_response(result)

    assert "Возвраты и невыкупы:\n1.12 ₽ — 1.2%" in response
    assert "Оценочная прибыль с 1 шт:\n33.98 ₽ — 35.4%" in response
    assert "за 30 полных дней" in response
    assert "покрытие 91.11%" in response
    assert "Прибыль до учёта возвратов:" not in response
    assert "Расходы на возвраты с 1 шт:" not in response
    assert "Итоговая оценочная маржа:" not in response
    assert "Невыкуп:" not in response
    assert "Наблюдаемые расходы:" not in response


def test_complete_attribution_shows_confirmed_profit():
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
    assert result["returns_cost_per_delivered_unit"] == 5.23
    assert result["risk_adjusted_profit_per_unit"] == 29.87
    assert result["risk_adjusted_margin_percent"] == 31.11
    assert "returns" not in result["missing_fields"]
    assert "Возвраты и невыкупы:\n5.23 ₽ — 5.4%" in response
    assert "Прибыль с 1 шт:\n29.87 ₽ — 31.1%" in response
    assert "Оценочная прибыль" not in response
    assert "⚠️" not in response


def test_below_eighty_percent_coverage_keeps_estimate_unknown():
    service = _service(_impact(
        observed_non_buyouts=70,
    ))
    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    response = service.format_response(result)

    assert result["returns_estimate_available"] is False
    assert result["estimated_profit_per_unit"] is None
    assert "Возвраты и невыкупы:\n—" in response
    assert "Оценочная прибыль с 1 шт:\n—" in response
    assert "недостаточно данных" in response


def test_incomplete_small_sample_is_not_extrapolated():
    impact = _impact()
    category = impact["categories"]["customer_non_buyout"]
    category.update({
        "event_posting_count": 20,
        "observed_posting_count": 18,
        "finance_matched_posting_count": 18,
        "observed_cost_total": 1024.81,
    })
    service = _service(impact)

    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    assert result["returns_estimate_available"] is False
    assert result["estimated_profit_per_unit"] is None


def test_historical_sample_ignores_unclassified_events():
    service = _service(_impact(
        classification_complete=False,
    ))

    result = service._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    assert result["returns_estimate_available"] is True
    assert result["estimated_returns_cost_per_unit"] == 1.12
    assert result["estimated_profit_per_unit"] == 33.98


def test_unavailable_returns_keeps_profit_unknown():
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
    assert result["estimated_profit_per_unit"] is None
    assert "Возвраты и невыкупы:\n—" in response
    assert "Оценочная прибыль с 1 шт:\n—" in response
    assert "Данные возвратов недоступны" in response
