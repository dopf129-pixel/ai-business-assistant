from period_profit_compact_response import compact_period_profit_result


def _result():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "summary": {
            "date_from": "2026-08-09",
            "date_to": "2026-08-31",
            "revenue": 374325.0,
            "units_sold": 4811,
            "net_accrual": 141707.0,
            "commission": -50000.0,
            "logistics": -100000.0,
            "acquiring": -5000.0,
            "other_fees": -77618.0,
            "product_cost": 101031.0,
            "tax": 22459.5,
            "profit": 18216.5,
            "margin_percent": 4.87,
        },
        "text": "verbose",
        "read_only": True,
        "executed": False,
    }


def test_compact_report_shows_account_level_ozon_breakdown():
    compact = compact_period_profit_result(_result())
    text = compact["text"]

    assert "🧾 Разложение начислений Ozon:" in text
    assert "Выручка: +374 325 ₽" in text
    assert "Комиссия: −50 000 ₽" in text
    assert "Логистика: −100 000 ₽" in text
    assert "Эквайринг: −5 000 ₽" in text
    assert "Прочие операции: −77 618 ₽" in text
    assert "= Начисления Ozon: 141 707 ₽" in text
    assert "Контроль: сходится" in text


def test_breakdown_does_not_invent_missing_money():
    result = _result()
    result["summary"]["other_fees"] = None

    compact = compact_period_profit_result(result)

    assert "🧾 Разложение начислений Ozon:" not in compact["text"]
