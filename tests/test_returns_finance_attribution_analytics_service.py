from services.returns_finance_attribution_analytics_service import (
    ReturnsFinanceAttributionAnalyticsService,
)


def _category(
    events,
    matched,
    observed,
    total,
    average,
    unmatched=None,
):
    return {
        "event_posting_count": events,
        "event_units": events,
        "finance_matched_posting_count": matched,
        "finance_unmatched_posting_numbers": list(
            unmatched or []
        ),
        "non_attributable_posting_numbers": [],
        "observed_posting_count": observed,
        "observed_net_amount_total": total,
        "observed_net_amount_average": average,
        "fees": {
            "59": {
                "posting_count": observed,
                "observed_total": -100.0,
                "observed_average_per_posting": -10.0,
            }
        },
    }


def test_builds_observed_costs_without_extrapolation():
    facts = {
        "error": False,
        "sku": "hook-2",
        "finance_sku": "42",
        "since": "2026-08-01",
        "to": "2026-08-25",
        "classification_complete": True,
        "finance_complete": False,
        "complete": False,
        "missing_data": ["finance_postings_unmatched"],
        "categories": {
            "customer_non_buyout": _category(
                events=12,
                matched=10,
                observed=10,
                total=-567.0,
                average=-56.7,
                unmatched=["p-11", "p-12"],
            ),
            "customer_return": _category(
                events=2,
                matched=2,
                observed=2,
                total=-108.72,
                average=-54.36,
            ),
        },
    }

    result = (
        ReturnsFinanceAttributionAnalyticsService()
        .analyze(facts)
    )

    assert result["error"] is False
    non_buyout = result["categories"]["customer_non_buyout"]
    assert non_buyout["finance_coverage_percent"] == 83.33
    assert non_buyout["observed_cost_total"] == 567.0
    assert non_buyout["observed_cost_average"] == 56.7
    assert non_buyout["complete"] is False
    assert "экстраполяция не выполнялась" in non_buyout["note"]

    customer_return = result["categories"]["customer_return"]
    assert customer_return["finance_coverage_percent"] == 100.0
    assert customer_return["observed_cost_total"] == 108.72
    assert customer_return["observed_cost_average"] == 54.36
    assert customer_return["fees"]["59"] == {
        "posting_count": 2,
        "observed_net_amount_total": -100.0,
        "observed_net_amount_average": -10.0,
        "observed_cost_total": 100.0,
        "observed_cost_average": 10.0,
    }
    assert result["complete"] is False


def test_preserves_positive_compensation_as_negative_cost():
    facts = {
        "error": False,
        "classification_complete": True,
        "finance_complete": True,
        "complete": True,
        "categories": {
            "customer_non_buyout": _category(
                events=1,
                matched=1,
                observed=1,
                total=5.0,
                average=5.0,
            ),
            "customer_return": _category(
                events=0,
                matched=0,
                observed=0,
                total=None,
                average=None,
            ),
        },
    }

    result = (
        ReturnsFinanceAttributionAnalyticsService()
        .analyze(facts)
    )

    category = result["categories"]["customer_non_buyout"]
    assert category["observed_net_amount_total"] == 5.0
    assert category["observed_cost_total"] == -5.0
    assert result["complete"] is True

    empty = result["categories"]["customer_return"]
    assert empty["observed_cost_total"] is None


def test_keeps_empty_category_unknown_instead_of_zero_cost():
    facts = {
        "error": False,
        "classification_complete": True,
        "finance_complete": True,
        "complete": True,
        "categories": {
            "customer_non_buyout": _category(
                events=0,
                matched=0,
                observed=0,
                total=None,
                average=None,
            ),
            "customer_return": _category(
                events=0,
                matched=0,
                observed=0,
                total=None,
                average=None,
            ),
        },
    }

    result = (
        ReturnsFinanceAttributionAnalyticsService()
        .analyze(facts)
    )

    category = result["categories"]["customer_return"]
    assert category["finance_coverage_percent"] is None
    assert category["observed_cost_total"] is None
    assert category["observed_cost_average"] is None


def test_preserves_structured_error():
    result = (
        ReturnsFinanceAttributionAnalyticsService()
        .analyze({
            "error": True,
            "code": "FINANCE_UNAVAILABLE",
            "sku": "hook-2",
            "message": "Нет данных",
        })
    )

    assert result == {
        "error": True,
        "code": "FINANCE_UNAVAILABLE",
        "sku": "hook-2",
        "message": "Нет данных",
    }
