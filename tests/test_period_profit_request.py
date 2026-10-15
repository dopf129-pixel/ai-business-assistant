from period_profit_request import build_period_profit_request, build_previous_period_profit_request


def test_preset_7d():
    result = build_period_profit_request("7D", today="2026-08-29")
    assert result["date_from"] == "2026-08-23"
    assert result["date_to"] == "2026-08-29"


def test_custom_dates():
    result = build_period_profit_request(date_from="2026-08-01", date_to="2026-08-20")
    assert result["mode"] == "CUSTOM"


def test_previous_comparable_period():
    current = build_period_profit_request("7D", today="2026-08-29")
    previous = build_previous_period_profit_request(current)
    assert previous["date_from"] == "2026-08-16"
    assert previous["date_to"] == "2026-08-22"


def test_invalid_custom_period_blocks():
    result = build_period_profit_request(date_from="2026-08-20", date_to="2026-08-01")
    assert result["code"] == "PERIOD_PROFIT_REQUEST_PERIOD_INVALID"


def test_invalid_preset_blocks():
    assert build_period_profit_request("MONTH")["error"] is True


def test_previous_period_crosses_year_boundary_with_equal_inclusive_length():
    current = build_period_profit_request(
        date_from="2026-01-01",
        date_to="2026-01-07",
    )

    previous = build_previous_period_profit_request(current)

    assert previous["date_from"] == "2025-12-25"
    assert previous["date_to"] == "2025-12-31"


def test_previous_period_handles_leap_day_without_changing_duration():
    current = build_period_profit_request(
        date_from="2024-02-26",
        date_to="2024-03-03",
    )

    previous = build_previous_period_profit_request(current)

    assert previous["date_from"] == "2024-02-19"
    assert previous["date_to"] == "2024-02-25"


def test_date_underflow_is_a_controlled_invalid_period():
    current = build_period_profit_request(
        date_from="0001-01-01",
        date_to="0001-01-01",
    )

    previous = build_previous_period_profit_request(current)
    preset = build_period_profit_request("7D", today="0001-01-01")

    assert previous["error"] is True
    assert previous["code"] == "PERIOD_PROFIT_REQUEST_PERIOD_INVALID"
    assert preset["error"] is True
    assert preset["code"] == "PERIOD_PROFIT_REQUEST_PERIOD_INVALID"
