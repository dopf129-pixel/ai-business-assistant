from decimal import Decimal
from math import inf, nan

from period_profit_comparison import build_period_profit_comparison


def _summary(profit, start="2026-08-01", end="2026-08-07", **values):
    result = {"error": False, "status": "PERIOD_PROFIT_SUMMARY_READY", "date_from": start, "date_to": end, "profit": profit, "profit_scope": "V1", "returns_included": False, "advertising_included": False, "storage_included": False}
    result.update(values)
    return result


def test_profit_growth():
    result = build_period_profit_comparison(_summary(120), _summary(100, "2026-07-25", "2026-07-31"))
    assert result["profit_direction"] == "UP"
    assert result["profit_change"] == 20
    assert result["profit_change_percent"] == 20


def test_profit_decline():
    result = build_period_profit_comparison(_summary(80), _summary(100))
    assert result["profit_direction"] == "DOWN"
    assert result["profit_change_percent"] == -20


def test_zero_previous_has_no_percent():
    assert build_period_profit_comparison(_summary(10), _summary(0))["profit_change_percent"] is None


def test_scope_mismatch_blocks():
    result = build_period_profit_comparison(_summary(10), _summary(10, profit_scope="V2"))
    assert result["code"] == "PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH"


def test_finite_decimal_profit_is_supported():
    result = build_period_profit_comparison(
        _summary(Decimal("12.34")),
        _summary(Decimal("10.00")),
    )

    assert result["error"] is False
    assert result["profit_change"] == 2.34


def test_negative_profit_and_confirmed_zero_are_valid():
    result = build_period_profit_comparison(_summary(0), _summary(-100))

    assert result["error"] is False
    assert result["profit_change"] == 100
    assert result["profit_change_percent"] == 100


def test_invalid_profit_never_produces_ready_comparison():
    for invalid in (None, True, False, "", "not-money", nan, inf, -inf):
        result = build_period_profit_comparison(_summary(invalid), _summary(100))

        assert result["error"] is True
        assert result["code"] == "PERIOD_PROFIT_COMPARISON_PROFIT_INVALID"
        assert result["status"] == "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
        assert "profit_change" not in result


def test_truthy_strings_are_not_accepted_as_scope_flags():
    current = _summary(120, returns_included="false")
    previous = _summary(100, returns_included=False)

    result = build_period_profit_comparison(current, previous)

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_COMPARISON_SUMMARY_INVALID"


def test_invalid_previous_profit_never_produces_ready_comparison():
    result = build_period_profit_comparison(_summary(100), _summary(nan))

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_COMPARISON_PROFIT_INVALID"


def test_overflowing_profit_delta_is_rejected():
    result = build_period_profit_comparison(
        _summary(1.7e308),
        _summary(-1.7e308),
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_COMPARISON_PROFIT_INVALID"
