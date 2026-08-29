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
