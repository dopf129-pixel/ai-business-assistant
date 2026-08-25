from services.returns_buyout_analytics_service import ReturnsBuyoutAnalyticsService


def _facts(**overrides):
    data = {
        "error": False,
        "sku": "hook-2",
        "since": "2026-08-01T00:00:00Z",
        "to": "2026-08-25T00:00:00Z",
        "delivered_units": 40,
        "cancelled_units": 10,
        "ambiguous_cancelled_units": 0,
        "customer_non_buyout_units": None,
        "customer_return_units": None,
        "customer_cancelled_units": 0,
        "delivery_failure_units": 0,
        "unknown_return_units": 0,
        "postings_complete": True,
        "returns_complete": True,
    }
    data.update(overrides)
    return data


def test_ambiguous_cancellations_do_not_become_non_buyouts():
    result = ReturnsBuyoutAnalyticsService().analyze(
        _facts(ambiguous_cancelled_units=10)
    )

    assert result["customer_non_buyout_units"] is None
    assert result["buyout_rate"] is None
    assert result["buyout_sample_size"] is None
    assert "customer_non_buyout_units" in result["missing_data"]
    assert "ambiguous_cancelled_units" in result["missing_data"]
    assert result["complete"] is False


def test_buyout_rate_is_calculated_only_from_known_customer_non_buyouts():
    result = ReturnsBuyoutAnalyticsService().analyze(
        _facts(
            delivered_units=45,
            customer_non_buyout_units=5,
            customer_return_units=2,
        )
    )

    assert result["buyout_rate"] == 90.0
    assert result["observed_buyout_rate"] == 90.0
    assert result["buyout_sample_size"] == 50
    assert result["missing_data"] == []
    assert result["classification_complete"] is True
    assert result["complete"] is True


def test_observed_buyout_rate_can_exist_while_classification_is_incomplete():
    result = ReturnsBuyoutAnalyticsService().analyze(
        _facts(
            delivered_units=5107,
            cancelled_units=253,
            ambiguous_cancelled_units=69,
            customer_non_buyout_units=85,
            customer_return_units=2,
            customer_cancelled_units=60,
            delivery_failure_units=39,
        )
    )

    assert result["observed_buyout_rate"] == 98.36
    assert result["buyout_rate"] == 98.36
    assert result["buyout_sample_size"] == 5192
    assert result["customer_cancelled_units"] == 60
    assert result["delivery_failure_units"] == 39
    assert "ambiguous_cancelled_units" in result["missing_data"]
    assert result["classification_complete"] is False
    assert result["complete"] is False


def test_known_buyout_with_unknown_returns_stays_partially_complete():
    result = ReturnsBuyoutAnalyticsService().analyze(
        _facts(
            delivered_units=36,
            customer_non_buyout_units=14,
            customer_return_units=None,
        )
    )

    assert result["buyout_rate"] == 72.0
    assert result["buyout_sample_size"] == 50
    assert result["customer_return_units"] is None
    assert result["missing_data"] == ["customer_return_units"]
    assert result["complete"] is False


def test_incomplete_postings_block_buyout_rate_even_with_known_returns():
    result = ReturnsBuyoutAnalyticsService().analyze(
        _facts(
            delivered_units=45,
            customer_non_buyout_units=5,
            customer_return_units=2,
            postings_complete=False,
        )
    )

    assert result["buyout_rate"] is None
    assert result["buyout_sample_size"] is None
    assert "postings_incomplete" in result["missing_data"]


def test_incomplete_returns_block_buyout_rate():
    result = ReturnsBuyoutAnalyticsService().analyze(
        _facts(
            delivered_units=45,
            customer_non_buyout_units=None,
            customer_return_units=None,
            returns_complete=False,
        )
    )

    assert result["buyout_rate"] is None
    assert "returns_incomplete" in result["missing_data"]


def test_zero_sample_does_not_create_fake_percentage():
    result = ReturnsBuyoutAnalyticsService().analyze(
        _facts(
            delivered_units=0,
            customer_non_buyout_units=0,
            customer_return_units=0,
        )
    )

    assert result["buyout_rate"] is None
    assert result["buyout_sample_size"] == 0


def test_source_error_is_propagated_as_structured_result():
    result = ReturnsBuyoutAnalyticsService().analyze(
        {
            "error": True,
            "code": "FBO_POSTINGS_UNAVAILABLE",
            "sku": "hook-2",
            "message": "FBO postings недоступны",
        }
    )

    assert result == {
        "error": True,
        "code": "FBO_POSTINGS_UNAVAILABLE",
        "sku": "hook-2",
        "message": "FBO postings недоступны",
    }
