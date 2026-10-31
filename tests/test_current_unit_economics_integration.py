from services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider
)
from services.product_unit_economics_query_service import (
    ProductUnitEconomicsQueryService
)
from services.tax_service import TaxService
from telegram_app_layer.telegram_progress_feedback import split_telegram_text


class FakeProductService:
    def load_products(self):
        return [
            {
                "product_id": "old-id",
                "sku": "hook-2"
            }
        ]


class FakeCurrentSource:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return dict(self.facts)


class FakeCostService:
    def __init__(self, costs):
        self.costs = costs
        self.calls = []

    def get_cost(self, product_id):
        self.calls.append(str(product_id))
        value = self.costs.get(str(product_id))
        if value is None:
            return None
        return (
            str(product_id),
            "hook-2",
            "hook",
            value,
            "RUB",
            "2026-08-25"
        )


class UnusedPeriodProfitService:
    def calculate_period_profit(self, *args, **kwargs):
        raise AssertionError("historical path must not be used")


class UnusedAnalyticsService:
    def get_period(self):
        raise AssertionError("historical path must not be used")


def _facts(**overrides):
    data = {
        "error": False,
        "product_id": "4108512640",
        "sku": "hook-2",
        "seller_price": 96.0,
        "buyer_price": 90.0,
        "ozon_discount_compensation": 6.0,
        "commission_rate": 14.0,
        "commission_amount": 13.44,
        "logistics": 19.32,
        "last_mile": 1.76,
        "acquiring_average": 1.27,
        "finance_sample_sales": 50,
        "finance_sample_days": 2,
        "as_of": "2026-08-25T07:00:00+00:00",
        "missing_data": []
    }
    data.update(overrides)
    return data


def _service(
    facts=None,
    tax_mode="USN_INCOME",
    tax_base_policy="SELLER_PRICE",
):
    source = FakeCurrentSource(
        facts or _facts()
    )
    costs = FakeCostService(
        {
            "4108512640": 21.0,
            "old-id": 99.0
        }
    )
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode=tax_mode,
        tax_rate=6.0
    )
    service = ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=UnusedPeriodProfitService(),
        analytics_service=UnusedAnalyticsService(),
        unit_economics_provider=provider,
        current_economics_source=source,
        cost_service=costs,
        current_finance_days=2,
        current_tax_base_policy=tax_base_policy
    )
    return service, source, costs


def test_current_query_uses_live_price_and_prepared_expenses():
    service, source, costs = _service()

    result = service.query("hook-2")

    assert result["source"] == "current"
    assert result["unit_price"] == 96.0
    assert result["cost"] == 21.0
    assert result["commission"] == 13.44
    assert result["logistics"] == 19.32
    assert result["last_mile"] == 1.76
    assert result["acquiring"] == 1.27
    assert result["marketplace_fees"] == 35.79
    assert result["tax"] == 5.76
    assert result["net_profit_per_unit"] == 33.45
    assert result["margin_percent"] == 34.84
    assert result["missing_fields"] == []
    projection = result["pre_ad_margin"]
    assert projection["schema_version"] == 1
    assert projection["basis"] == "CURRENT_MODEL"
    assert projection["tax_basis"] == "CURRENT_TAX_POLICY"
    assert projection["revenue_basis"] == "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS"
    assert projection["status"] == "AVAILABLE"
    assert projection["profit_per_unit_rub"] == result["net_profit_per_unit"]
    assert projection["margin_percent"] == result["margin_percent"]
    assert projection["tax_per_unit_rub"] == result["tax"]
    assert projection["as_of"] == "2026-08-25T07:00:00+00:00"
    assert projection["advertising_status"] == "UNKNOWN"
    assert projection["advertising_per_unit_rub"] is None
    assert projection["expense_scope"]["status"] == "PARTIAL"
    assert projection["expense_scope"]["known_non_ad_expenses_rub"] == {
        "ACQUIRING": 1.27,
        "COGS": 21.0,
        "LAST_MILE": 1.76,
        "LOGISTICS": 19.32,
        "OZON_COMMISSION": 13.44,
    }
    assert "STORAGE" in projection["expense_scope"]["unknown_non_ad_expense_keys"]
    assert "RETURNS_AND_CANCELLATIONS" in projection["expense_scope"]["unknown_non_ad_expense_keys"]
    finance_period = projection["source_periods"]["current_finance_averages"]
    assert finance_period["date_from"] == min(source.calls[0]["accrual_dates"])
    assert finance_period["date_to"] == max(source.calls[0]["accrual_dates"])
    assert finance_period["requested_days"] == 2
    assert finance_period["observed_sales_days"] == 2
    assert costs.calls == ["4108512640"]
    assert source.calls[0]["sku"] == "hook-2"
    assert len(source.calls[0]["accrual_dates"]) == 2


def test_current_response_shows_rubles_and_percentages():
    service, _, _ = _service()

    response = service.format_response(
        service.query("hook-2")
    )

    assert "Цена:\n96.00 ₽ — 100.0%" in response
    assert "Комиссия Ozon:\n13.44 ₽ — 14.0%" in response
    assert "Логистика:\n19.32 ₽ — 20.1%" in response
    assert "Последняя миля:\n1.76 ₽ — 1.8%" in response
    assert "Эквайринг:\n1.27 ₽ — 1.3%" in response
    assert "Себестоимость:\n21.00 ₽ — 21.9%" in response
    assert "Налог:\n5.76 ₽ — 6.0%" in response
    assert (
        "Маржа до рекламы (после налога):\n"
        "33.45 ₽ / шт. · 34.84% от цены продавца"
    ) in response
    assert "Налог: УСН Доходы · 5.76 ₽ / шт." in response
    assert "Полнота расходов без рекламы: частичная" in response
    assert "Не подтверждены: кросс-докинг, размещение, возвраты и отмены, хранение, прочие расходы" in response
    assert "После рекламы: не рассчитана — расход рекламы неизвестен" in response
    assert "Начисления Ozon:" in response
    assert "Цена продавца актуальна на 25.08.2026 07:00 UTC" in response
    telegram_chunks = split_telegram_text(response)
    assert "".join(telegram_chunks) == response
    assert all(len(chunk) <= 3800 for chunk in telegram_chunks)
    assert "Прибыль с 1 шт:\n33.45 ₽ — 34.8%" in response
    assert "Основано на последних финансовых начислениях Ozon: 50 продаж за 2 дн." in response
    assert "Маржа до рекламы рассчитана по учтённым расходам" in response
    assert "Реклама" not in response
    assert "Хранение" not in response


def test_current_economics_includes_sku_cross_docking_cost_and_explains_basis():
    facts = _facts(
        cross_docking_per_unit=10.0,
        cross_docking={
            "status": "SKU_SUPPLY_PERIOD_AVERAGE",
            "reason": None,
            "evidence_complete": True,
            "applicable_to_sku": True,
            "method": "sku_accrual_cost_per_delivered_crossdock_unit",
            "date_from": "2026-08-24",
            "date_to": "2026-10-18",
            "expense_by_sku": "400.00",
            "supplied_units_sku": 40,
            "days_complete": 56,
            "days_expected": 56,
            "sku": "must-not-be-exposed",
            "supply_id": "must-not-be-exposed",
        },
    )
    service, _, _ = _service(facts)

    result = service.query("hook-2")
    response = service.format_response(result)

    assert result["cross_docking_per_unit"] == 10.0
    assert result["cross_docking_included"] is True
    assert result["net_profit_per_unit"] == 23.45
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == 23.45
    assert result["pre_ad_margin"]["expense_scope"]["known_non_ad_expenses_rub"]["CROSS_DOCKING"] == 10.0
    assert "CROSS_DOCKING" not in result["pre_ad_margin"]["expense_scope"]["unknown_non_ad_expense_keys"]
    assert result["pre_ad_margin"]["source_periods"]["cross_docking"] == {
        "date_from": "2026-08-24",
        "date_to": "2026-10-18",
        "days_complete": 56,
        "days_expected": 56,
    }
    assert "Кросс-докинг — на фактически поставленную единицу за 2026-08-24 — 2026-10-18" in response
    assert "10.00 ₽ — 10.4%" in response
    assert "начисления 400.00 ₽ / фактически принято 40 шт." in response
    assert "покрытие 56/56 дней" in response
    assert "must-not-be-exposed" not in response
    assert "фактически поставленные единицы" in result["note"]
    assert "Основано на последних финансовых начислениях Ozon: 50 продаж за 2 дн." in response
    assert "среднее начислений кросс-докинга за 56 завершённых дней" in response


def test_current_economics_leaves_profit_unchanged_and_labels_incomplete_cross_docking():
    facts = _facts(
        cross_docking_per_unit=None,
        cross_docking={
            "status": "UNAVAILABLE",
            "reason": "CROSSDOCK_WINDOW_INCOMPLETE",
            "evidence_complete": False,
            "applicable_to_sku": False,
        },
    )
    service, _, _ = _service(facts)

    result = service.query("hook-2")
    response = service.format_response(result)

    assert result["net_profit_per_unit"] == 33.45
    assert result["cross_docking_included"] is False
    assert "Кросс-докинг — на фактически поставленную единицу:" in response
    assert "не учтён: нет подтверждённой применимой ставки" in response
    assert "без кросс-докинга: CROSSDOCK_WINDOW_INCOMPLETE" in result["note"]


def test_current_unit_economics_subtracts_points_and_shows_effective_tax_percent():
    service, _, _ = _service(
        _facts(discount_points_per_unit=10.0)
    )

    result = service.query("hook-2")
    response = service.format_response(result)

    assert result["revenue_tax_base"] == 86.0
    assert result["tax"] == 5.16
    assert result["tax_effective_percent"] == 5.38
    assert "Баллы за скидки:\n10.00 ₽ — 10.4%" in response
    assert "Выручка для расчёта налога:\n86.00 ₽ — 89.6%" in response
    assert "Налог:\n5.16 ₽ — 5.4%" in response


def test_missing_logistics_keeps_profit_unknown():
    service, _, _ = _service(
        _facts(
            logistics=None,
            missing_data=["logistics"]
        )
    )

    result = service.query("hook-2")

    assert result["logistics"] is None
    assert result["net_profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert "logistics" in result["missing_fields"]

    response = service.format_response(result)
    assert "Логистика:\n—" in response
    assert "Прибыль с 1 шт:\n—" in response


def test_missing_tax_keeps_profit_unknown():
    service, _, _ = _service(tax_mode=None)

    result = service.query("hook-2")

    assert result["tax"] is None
    assert result["net_profit_per_unit"] is None
    assert result["margin_percent"] is None
    assert "tax" in result["missing_fields"]


def test_current_pre_ad_projection_is_unavailable_when_seller_price_is_missing():
    service, _, _ = _service(
        _facts(seller_price=None, missing_data=["current_price"])
    )

    result = service.query("hook-2")

    projection = result["pre_ad_margin"]
    assert result["available"] is False
    assert projection["schema_version"] == 1
    assert projection["status"] == "UNAVAILABLE"
    assert projection["price_per_unit_rub"] is None
    assert projection["profit_per_unit_rub"] is None
    assert projection["margin_percent"] is None
    assert projection["advertising_status"] == "UNKNOWN"

    response = service.format_response(result)

    assert "Маржа до рекламы (после налога):\nне рассчитана" in response
    assert "После рекламы: не рассчитана — расход рекламы неизвестен" in response
    assert "0.00 ₽ / шт." not in response


def test_current_pre_ad_source_periods_are_allowlisted_and_bounded():
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6,
    )
    facts = _facts(
        cross_docking_per_unit=10,
        cross_docking={
            "status": "SKU_SUPPLY_PERIOD_AVERAGE",
            "evidence_complete": True,
            "applicable_to_sku": True,
            "date_from": "2026-08-01",
            "date_to": "2026-09-25",
            "days_complete": 56,
            "days_expected": 56,
            "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        },
        pre_ad_source_periods={
            "seller_price": {"as_of": "token-secret"},
            "current_finance_averages": {
                "date_from": "2026-08-01",
                "date_to": "yesterday!!",
                "requested_days": True,
                "observed_sales_days": 2,
                "raw_response": "private",
            },
            "unexpected": {"sku": "private"},
        },
    )

    projection = provider.build_current(facts, product_cost=21)["pre_ad_margin"]

    assert projection["source_periods"] == {
        "current_finance_averages": {
            "date_from": "2026-08-01",
            "observed_sales_days": 2,
        },
        "cross_docking": {
            "date_from": "2026-08-01",
            "date_to": "2026-09-25",
            "days_complete": 56,
            "days_expected": 56,
            "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        },
    }
    assert projection["as_of"] is None


def test_current_product_id_is_preferred_for_cost_lookup():
    service, _, costs = _service()

    result = service.query("hook-2")

    assert result["cost"] == 21.0
    assert costs.calls == ["4108512640"]


def test_missing_current_product_cost_falls_back_to_catalog_id():
    source = FakeCurrentSource(_facts())
    costs = FakeCostService({"old-id": 21.0})
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_mode="USN_INCOME",
        tax_rate=6.0
    )
    service = ProductUnitEconomicsQueryService(
        product_service=FakeProductService(),
        period_profit_service=UnusedPeriodProfitService(),
        analytics_service=UnusedAnalyticsService(),
        unit_economics_provider=provider,
        current_economics_source=source,
        cost_service=costs
    )

    result = service.query("hook-2")

    assert result["cost"] == 21.0
    assert costs.calls == ["4108512640", "old-id"]


def test_ozon_buyer_price_policy_uses_dynamic_tax_base():
    service, _, _ = _service(
        tax_base_policy="OZON_BUYER_PRICE"
    )

    result = service.query("hook-2")

    assert result["unit_price"] == 96.0
    assert result["buyer_price"] == 90.0
    assert result["ozon_discount_compensation"] == 6.0
    assert result["tax_base_policy"] == "OZON_BUYER_PRICE"
    assert result["tax_base"] == 90.0
    assert result["tax_rate"] == 6.0
    assert result["tax"] == 5.4
    assert result["tax_effective_percent"] == 5.62
    assert result["net_profit_per_unit"] == 33.81
    assert result["margin_percent"] == 35.22
    assert result["pre_ad_margin"]["profit_per_unit_rub"] == 33.81
    assert result["pre_ad_margin"]["margin_percent"] == 35.22
    assert result["pre_ad_margin"]["tax_per_unit_rub"] == 5.4
    assert result["pre_ad_margin"]["price_per_unit_rub"] == 96.0


def test_ozon_buyer_price_policy_is_explicit_in_response():
    service, _, _ = _service(
        tax_base_policy="OZON_BUYER_PRICE"
    )

    response = service.format_response(
        service.query("hook-2")
    )

    assert "Цена:\n96.00 ₽ — 100.0%" in response
    assert "Налог:\n5.40 ₽ — 5.6%" in response
    assert "Цена покупателя Ozon:" not in response
    assert "Компенсация скидки Ozon:" not in response
    assert "Налоговая база:" not in response
    assert "Ставка налога:" not in response
    assert "Эффективный налог от цены продавца:" not in response
    assert "управленческого расчёта" not in response


def test_missing_ozon_buyer_price_keeps_tax_and_profit_unknown():
    service, _, _ = _service(
        facts=_facts(
            buyer_price=None,
            ozon_discount_compensation=None,
        ),
        tax_base_policy="OZON_BUYER_PRICE",
    )

    result = service.query("hook-2")

    assert result["tax"] is None
    assert result["net_profit_per_unit"] is None
    assert "buyer_price" in result["missing_fields"]
