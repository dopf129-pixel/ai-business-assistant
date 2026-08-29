from period_profit_telegram_contract import build_period_profit_telegram_menu, parse_period_profit_callback


def test_menu_exposes_safe_period_buttons():
    result = build_period_profit_telegram_menu()
    assert [item["callback_data"] for item in result["buttons"]] == [
        "period_profit:TODAY", "period_profit:7D", "period_profit:28D", "period_profit:56D", "period_profit:90D"
    ]
    assert result["read_only"] is True
    assert result["executed"] is False


def test_callback_enables_previous_comparison():
    result = parse_period_profit_callback("period_profit:28D")
    assert result["period_code"] == "28D"
    assert result["compare_previous"] is True
    assert result["executed"] is False


def test_invalid_callback_blocks():
    assert parse_period_profit_callback("product:28D")["error"] is True
    assert parse_period_profit_callback("period_profit:ALL")["error"] is True
