from period_profit_response import build_period_profit_response


def _summary(**values):
    result = {"error": False, "status": "PERIOD_PROFIT_SUMMARY_READY", "date_from": "2026-08-01", "date_to": "2026-08-07", "revenue": 1000, "net_accrual": 800, "product_cost": 300, "tax": 60, "profit": 440, "margin_percent": 44, "returns_included": False, "advertising_included": False, "storage_included": False, "profit_scope": "V1"}
    result.update(values)
    return result


def test_formats_profit_and_scope_warning():
    result = build_period_profit_response(_summary())
    assert result["status"] == "PERIOD_PROFIT_RESPONSE_READY"
    assert "Прибыль: 440.00 ₽" in result["text"]
    assert "возвраты" in result["text"]
    assert "бухгалтерская чистая прибыль" in result["text"]


def test_formats_comparison():
    comparison = {"status": "PERIOD_PROFIT_COMPARISON_READY", "profit_direction": "UP", "profit_change": 40, "profit_change_percent": 10}
    text = build_period_profit_response(_summary(), comparison)["text"]
    assert "выросла на 40.00 ₽ (10.00%)" in text


def test_invalid_summary_blocks():
    assert build_period_profit_response({"error": True})["error"] is True
