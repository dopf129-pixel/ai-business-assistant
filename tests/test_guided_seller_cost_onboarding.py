from datetime import date

from services.telegram_seller_cost_update_service import TelegramSellerCostUpdateService


class _Products:
    def load_products(self):
        return [("1", "ART-A", "SKU-A"), ("2", "ART-B", "SKU-B")]


class _InitiallyEmptyProducts:
    def __init__(self, refresh_result=None):
        self.rows = []
        self.refresh_calls = 0
        self.refresh_result = refresh_result or {"error": False, "status": "PERIOD_PROFIT_PRODUCT_CATALOG_REFRESHED"}

    def load_products(self):
        return list(self.rows)

    def refresh_products_for_period_profit(self):
        self.refresh_calls += 1
        if self.refresh_result.get("error") is False:
            self.rows = [("1", "ART-A", "SKU-A")]
        return dict(self.refresh_result)


class _Costs:
    def __init__(self):
        self.current = []
        self.recorded = []

    def get_all_costs(self):
        return list(self.current)

    def record_cost_switch(self, **kwargs):
        self.recorded.append(kwargs)
        self.current = [row for row in self.current if row[0] != kwargs["product_id"]]
        self.current.append((kwargs["product_id"], kwargs["sku"], kwargs["offer_id"], kwargs["cost_price"], "RUB", "now"))
        return {"error": False, "status": "PRODUCT_COST_SWITCH_RECORDED"}


def _table_button():
    return {"text": "📥 Заполнить таблицей", "callback": "seller_cost_table"}


def test_menu_prioritizes_only_products_without_cost():
    costs = _Costs()
    costs.current.append(("1", "SKU-A", "ART-A", 100.0, "RUB", "now"))
    service = TelegramSellerCostUpdateService(_Products(), costs)
    result = service.open_menu()
    assert result["cost_coverage"] == {"configured": 1, "total": 2, "missing": 1}
    assert result["keyboard"]["buttons"] == [_table_button(), {"text": "ART-B", "callback": "seller_cost:SKU-B"}]
    assert "применение ко всей истории потребует отдельного подтверждения" in result["message"]


def test_empty_local_catalog_is_refreshed_from_ozon_before_cost_setup():
    products = _InitiallyEmptyProducts()
    service = TelegramSellerCostUpdateService(products, _Costs())
    result = service.open_menu()
    assert result["error"] is False
    assert products.refresh_calls == 1
    assert result["cost_coverage"] == {"configured": 0, "total": 1, "missing": 1}
    assert result["keyboard"]["buttons"] == [_table_button(), {"text": "ART-A", "callback": "seller_cost:SKU-A"}]


def test_catalog_refresh_failure_has_actionable_message():
    products = _InitiallyEmptyProducts({"error": True, "code": "PERIOD_PROFIT_PRODUCT_CATALOG_API_UNAVAILABLE"})
    service = TelegramSellerCostUpdateService(products, _Costs())
    result = service.open_menu()
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCT_CATALOG_API_UNAVAILABLE"
    assert "Ozon" in result["message"]


def test_first_cost_proposes_date_and_requires_confirmation_before_writing():
    costs = _Costs()
    service = TelegramSellerCostUpdateService(_Products(), costs, date_provider=lambda: date(2026, 9, 15))
    selected = service.select_sku("user", "SKU-A")
    assert selected["seller_cost_input_pending"] is True
    assert "предложу дату начала действия" in selected["message"]
    preview = service.handle_text("user", "430")
    assert preview["seller_cost_confirmation_pending"] is True
    assert preview["effective_from"] == "2026-09-15"
    assert "Магазин: активный магазин" in preview["message"]
    assert "SKU SKU-A" in preview["message"]
    assert costs.recorded == []
    callbacks = [button["callback"] for button in preview["keyboard"]["buttons"]]
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)
    assert [callback.split(":", 1)[0] for callback in callbacks] == [
        service.CONFIRM_DATE_CALLBACK,
        service.SELECT_ALL_HISTORY_CALLBACK,
        service.CANCEL_CALLBACK,
    ]

    saved = service.handle_button("user", callbacks[0])
    assert saved["effective_from"] == "2026-09-15"
    assert saved["historical_default"] is False
    assert saved["cost_coverage"]["missing"] == 1
    assert saved["keyboard"]["buttons"] == [
        {"text": "📊 Прибыль по этому товару", "callback": "period_profit_sku:SKU-A"},
        _table_button(),
        {"text": "ART-B", "callback": "seller_cost:SKU-B"},
    ]
    assert costs.recorded[0]["cost_price"] == 430.0
    assert costs.recorded[0]["source"] == "SELLER_CONFIRMED_FIRST_EFFECTIVE_DATE"


def test_whole_history_requires_a_second_explicit_confirmation():
    costs = _Costs()
    service = TelegramSellerCostUpdateService(_Products(), costs, date_provider=lambda: date(2026, 9, 15))
    service.select_sku("user", "SKU-A")
    preview = service.handle_text("user", "430")
    selected = service.handle_button(
        "user", preview["keyboard"]["buttons"][1]["callback"]
    )
    assert selected["error"] is False
    assert "ко всей доступной истории" in selected["message"]
    assert costs.recorded == []

    saved = service.handle_button(
        "user", selected["keyboard"]["buttons"][0]["callback"]
    )
    assert saved["error"] is False
    assert saved["effective_from"] == "0001-01-01"
    assert saved["historical_default"] is True
    assert costs.recorded[0]["source"] == "SELLER_CONFIRMED_INITIAL_HISTORY"


def test_existing_cost_change_still_starts_tomorrow():
    costs = _Costs()
    costs.current.append(("1", "SKU-A", "ART-A", 100.0, "RUB", "now"))
    service = TelegramSellerCostUpdateService(_Products(), costs, date_provider=lambda: date(2026, 9, 15))
    service.select_sku("user", "SKU-A")
    preview = service.handle_text("user", "120")
    assert costs.recorded == []
    saved = service.handle_button(
        "user", preview["keyboard"]["buttons"][0]["callback"]
    )
    assert saved["effective_from"] == "2026-09-16"
    assert saved["historical_default"] is False
    assert costs.recorded[0]["source"] == "SELLER_CONFIRMED_BOT"
