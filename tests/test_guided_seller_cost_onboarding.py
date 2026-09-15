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


def test_menu_prioritizes_only_products_without_cost():
    costs = _Costs()
    costs.current.append(("1", "SKU-A", "ART-A", 100.0, "RUB", "now"))
    service = TelegramSellerCostUpdateService(_Products(), costs)

    result = service.open_menu()

    assert result["cost_coverage"] == {"configured": 1, "total": 2, "missing": 1}
    assert result["keyboard"]["buttons"] == [{"text": "ART-B", "callback": "seller_cost:SKU-B"}]
    assert "всей доступной истории продаж" in result["message"]


def test_empty_local_catalog_is_refreshed_from_ozon_before_cost_setup():
    products = _InitiallyEmptyProducts()
    service = TelegramSellerCostUpdateService(products, _Costs())

    result = service.open_menu()

    assert result["error"] is False
    assert products.refresh_calls == 1
    assert result["cost_coverage"] == {"configured": 0, "total": 1, "missing": 1}
    assert result["keyboard"]["buttons"] == [{"text": "ART-A", "callback": "seller_cost:SKU-A"}]


def test_catalog_refresh_failure_has_actionable_message():
    products = _InitiallyEmptyProducts({"error": True, "code": "PERIOD_PROFIT_PRODUCT_CATALOG_API_UNAVAILABLE"})
    service = TelegramSellerCostUpdateService(products, _Costs())

    result = service.open_menu()

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_PRODUCT_CATALOG_API_UNAVAILABLE"
    assert "Ozon" in result["message"]


def test_first_cost_is_effective_for_full_history_and_flow_offers_next_missing_product():
    costs = _Costs()
    service = TelegramSellerCostUpdateService(_Products(), costs, date_provider=lambda: date(2026, 9, 15))

    selected = service.select_sku("user", "SKU-A")
    assert selected["seller_cost_input_pending"] is True
    assert "всей доступной истории продаж" in selected["message"]

    saved = service.handle_text("user", "430")

    assert saved["effective_from"] == "0001-01-01"
    assert saved["historical_default"] is True
    assert saved["cost_coverage"]["missing"] == 1
    assert saved["keyboard"]["buttons"] == [{"text": "ART-B", "callback": "seller_cost:SKU-B"}]
    assert costs.recorded[0]["cost_price"] == 430.0
    assert costs.recorded[0]["source"] == "SELLER_CONFIRMED_INITIAL_HISTORY"


def test_existing_cost_change_still_starts_tomorrow():
    costs = _Costs()
    costs.current.append(("1", "SKU-A", "ART-A", 100.0, "RUB", "now"))
    service = TelegramSellerCostUpdateService(_Products(), costs, date_provider=lambda: date(2026, 9, 15))

    service.select_sku("user", "SKU-A")
    saved = service.handle_text("user", "120")

    assert saved["effective_from"] == "2026-09-16"
    assert saved["historical_default"] is False
    assert costs.recorded[0]["source"] == "SELLER_CONFIRMED_BOT"
