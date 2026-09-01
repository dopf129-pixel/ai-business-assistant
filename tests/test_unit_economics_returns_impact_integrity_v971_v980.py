from copy import deepcopy

from app.services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService,
)


class _ImpactQuery:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def query(self, sku):
        self.calls.append(sku)
        if self.error is not None:
            raise self.error
        return deepcopy(self.result)


def _category(
    events,
    observed,
    cost,
    complete,
    matched=None,
):
    if matched is None:
        matched = observed
    return {
        "label": "category",
        "event_posting_count": events,
        "finance_matched_posting_count": matched,
        "observed_posting_count": observed,
        "observed_cost_total": cost,
        "complete": complete,
    }


def _impact(
    complete=False,
    delivered_units=4653,
    classification_complete=True,
    finance_complete=None,
):
    if finance_complete is None:
        finance_complete = complete
    non_buyout_observed = 90 if complete else 82
    return {
        "error": False,
        "complete": complete,
        "classification_complete": classification_complete,
        "finance_complete": finance_complete,
        "delivered_units": delivered_units,
        "missing_data": (
            []
            if complete
            else ["finance_postings_unmatched"]
        ),
        "categories": {
            "customer_non_buyout": _category(
                90,
                non_buyout_observed,
                (
                    5124.07
                    if complete
                    else round(56.93414634 * non_buyout_observed, 2)
                ),
                complete,
                matched=non_buyout_observed,
            ),
            "customer_return": _category(
                2,
                2,
                108.73,
                True,
                matched=2,
            ),
        },
    }


def _economics():
    return {
        "error": False,
        "source": "current",
        "sku": "hook-2",
        "unit_price": 96.0,
        "net_profit_per_unit": 35.10,
        "margin_percent": 36.56,
        "missing_fields": ["returns"],
    }


def _service(result=None, error=None):
    return ProductUnitEconomicsQueryService(
        product_service=None,
        period_profit_service=None,
        analytics_service=None,
        unit_economics_provider=None,
        returns_finance_impact_query=_ImpactQuery(
            result=result,
            error=error,
        ),
    )


def _assert_unknown(result):
    assert result["error"] is False
    assert result["net_profit_per_unit"] == 35.10
    assert result["returns_finance_complete"] is False
    assert result["returns_observed_cost_total"] is None
    assert result["returns_observed_event_count"] is None
    assert result["returns_cost_per_delivered_unit"] is None
    assert result["risk_adjusted_profit_per_unit"] is None
    assert result["risk_adjusted_margin_percent"] is None
    assert result["returns_estimate_available"] is False
    assert result["estimated_returns_cost_total"] is None
    assert result["estimated_returns_cost_per_unit"] is None
    assert result["estimated_profit_per_unit"] is None
    assert result["estimated_margin_percent"] is None
    assert "returns" in result["missing_fields"]
    assert result["returns_finance_impact"]["error"] is True
    assert result["returns_finance_impact"]["code"] == (
        "RETURNS_FINANCE_IMPACT_RESULT_INVALID"
    )


def test_v971_non_mapping_returns_impact_is_unknown_not_zero():
    result = _service(result=["bad"])._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)


def test_v972_returns_impact_exception_is_sanitized():
    result = _service(
        error=ValueError("secret finance detail")
    )._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)
    assert "secret finance detail" not in str(result)


def test_v973_missing_explicit_error_marker_is_invalid():
    impact = _impact()
    impact.pop("error")

    result = _service(impact)._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)


def test_v974_string_complete_false_cannot_become_confirmed_zero():
    impact = _impact()
    impact["complete"] = "false"
    impact["categories"] = {
        "customer_non_buyout": _category(0, 0, None, True, matched=0),
        "customer_return": _category(0, 0, None, True, matched=0),
    }
    impact["finance_complete"] = True

    result = _service(impact)._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)
    assert result["returns_observed_cost_total"] is not 0.0


def test_v975_categories_must_be_mapping():
    impact = _impact()
    impact["categories"] = []

    result = _service(impact)._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)


def test_v976_each_required_category_must_be_mapping():
    impact = _impact()
    impact["categories"]["customer_return"] = ["bad"]

    result = _service(impact)._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)


def test_v977_event_counts_are_exact_integers_not_coerced():
    impact = _impact()
    impact["categories"]["customer_non_buyout"][
        "event_posting_count"
    ] = "90"

    result = _service(impact)._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)


def test_v978_observed_count_cannot_exceed_matched_or_events():
    impact = _impact()
    impact["categories"]["customer_non_buyout"].update({
        "event_posting_count": 10,
        "finance_matched_posting_count": 9,
        "observed_posting_count": 10,
    })

    result = _service(impact)._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)


def test_v979_complete_requires_complete_finance_and_categories():
    impact = _impact(complete=True, delivered_units=1000)
    impact["finance_complete"] = False

    result = _service(impact)._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    _assert_unknown(result)


def test_v980_valid_estimated_and_confirmed_paths_remain_exact():
    estimated_source = _impact()
    estimated_before = deepcopy(estimated_source)
    estimated = _service(
        estimated_source
    )._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    assert estimated["returns_finance_complete"] is False
    assert estimated["returns_estimate_available"] is True
    assert estimated["estimated_returns_cost_total"] == 5232.80
    assert estimated["estimated_returns_cost_per_unit"] == 1.12
    assert estimated["estimated_profit_per_unit"] == 33.98
    assert estimated["returns_estimate_coverage_percent"] == 91.11
    assert estimated_source == estimated_before

    confirmed_source = _impact(
        complete=True,
        delivered_units=1000,
    )
    confirmed = _service(
        confirmed_source
    )._attach_returns_impact(
        "hook-2",
        _economics(),
    )

    assert confirmed["returns_finance_complete"] is True
    assert confirmed["returns_observed_cost_total"] == 5232.80
    assert confirmed["returns_cost_per_delivered_unit"] == 5.23
    assert confirmed["risk_adjusted_profit_per_unit"] == 29.87
    assert confirmed["risk_adjusted_margin_percent"] == 31.11
    assert "returns" not in confirmed["missing_fields"]
