from period_profit_response import build_period_profit_response


def _summary(**values):
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-06-06",
        "date_to": "2026-09-03",
        "revenue": 1348371.10,
        "net_accrual": 752971.82,
        "commission": -190333.00,
        "logistics": -369353.19,
        "acquiring": -15778.95,
        "other_fees": -19934.14,
        "fee_components_included": True,
        "product_cost": 361368.00,
        "tax": 80902.27,
        "profit": 310701.55,
        "margin_percent": 23.04,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "profit_scope": "V1",
    }
    result.update(values)
    return result


def _text(**values):
    return build_period_profit_response(
        _summary(**values)
    )["text"]


def test_v1221_revenue_is_shown_as_one_hundred_percent():
    assert (
        "Выручка: 1 348 371.10 ₽ (100.00%)"
        in _text()
    )


def test_v1222_net_ozon_accrual_shows_revenue_share():
    assert (
        "Начисления Ozon после комиссий/услуг: "
        "752 971.82 ₽ (55.84%)"
        in _text()
    )


def test_v1223_fee_lines_show_absolute_revenue_shares():
    text = _text()

    assert "Комиссия: 190 333.00 ₽ (14.12%)" in text
    assert "Логистика: 369 353.19 ₽ (27.39%)" in text
    assert "Эквайринг: 15 778.95 ₽ (1.17%)" in text
    assert (
        "Прочие начисления/удержания: "
        "19 934.14 ₽ (1.48%)"
        in text
    )


def test_v1224_product_cost_shows_revenue_share():
    assert (
        "Себестоимость: 361 368.00 ₽ (26.80%)"
        in _text()
    )


def test_v1225_tax_shows_revenue_share():
    assert (
        "Налог: 80 902.27 ₽ (6.00%)"
        in _text()
    )


def test_v1226_profit_shows_revenue_share():
    text = _text()

    assert "Прибыль: 310 701.55 ₽ (23.04%)" in text
    assert "Маржа: 23.04%" in text


def test_v1227_negative_profit_keeps_negative_revenue_share():
    text = _text(
        profit=-100.0,
        margin_percent=-10.0,
        revenue=1000.0,
    )

    assert "Прибыль: -100.00 ₽ (-10.00%)" in text
    assert "Маржа: -10.00%" in text


def test_v1228_zero_revenue_suppresses_all_revenue_share_percentages():
    text = _text(
        revenue=0.0,
        net_accrual=0.0,
        commission=0.0,
        logistics=0.0,
        acquiring=0.0,
        other_fees=0.0,
        product_cost=0.0,
        tax=0.0,
        profit=0.0,
        margin_percent=0.0,
    )

    assert "Выручка: 0.00 ₽\n" in text
    assert "Начисления Ozon после комиссий/услуг: 0.00 ₽" in text
    assert "Себестоимость: 0.00 ₽" in text
    assert "Налог: 0.00 ₽" in text
    assert "Прибыль: 0.00 ₽" in text
    assert "(100.00%)" not in text


def test_v1229_existing_comparison_percentage_keeps_its_own_meaning():
    comparison = {
        "status": "PERIOD_PROFIT_COMPARISON_READY",
        "profit_direction": "UP",
        "profit_change": 40000.0,
        "profit_change_percent": 10.0,
    }

    text = build_period_profit_response(
        _summary(),
        comparison=comparison,
    )["text"]

    assert (
        "прибыль выросла на 40 000.00 ₽ (10.00%)"
        in text
    )


def test_v1230_amounts_and_scope_warning_are_preserved():
    text = _text()

    assert "1 348 371.10 ₽" in text
    assert "752 971.82 ₽" in text
    assert "361 368.00 ₽" in text
    assert "80 902.27 ₽" in text
    assert "310 701.55 ₽" in text
    assert "возвраты" in text
    assert "реклама" in text
    assert "хранение" in text
    assert "бухгалтерская чистая прибыль" in text
