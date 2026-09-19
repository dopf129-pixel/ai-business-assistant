from services.period_profit_sku_runtime_service import PeriodProfitSkuRuntimeService
from services.telegram_seller_cost_update_service import TelegramSellerCostUpdateService


class _Costs:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.recorded = []

    def get_all_costs(self):
        return list(self.rows)

    def record_cost_switch(self, **kwargs):
        self.recorded.append(kwargs)
        self.rows.append((kwargs["product_id"], kwargs["sku"], kwargs["offer_id"], kwargs["cost_price"], "RUB", "now"))
        return {"error": False}


class _Products:
    def load_products(self):
        return [("1", "ART-A", "SKU-A"), ("2", "ART-B", "SKU-B")]


class _Query:
    product_provider = staticmethod(lambda: [("1", "ART-A", "SKU-A"), ("2", "ART-B", "SKU-B")])


def test_sku_profit_menu_only_shows_products_with_configured_cost():
    costs = _Costs([("1", "SKU-A", "ART-A", 430.0, "RUB", "now")])
    service = PeriodProfitSkuRuntimeService(_Query(), cost_service=costs)
    result = service.open_sku_menu()
    assert result["error"] is False
    assert result["keyboard"]["buttons"] == [
        {"text": "ART-A · SKU SKU-A", "callback": "period_profit_sku:SKU-A"}
    ]


def test_seller_cost_save_offers_profit_for_just_saved_sku():
    costs = _Costs()
    service = TelegramSellerCostUpdateService(_Products(), costs)
    service.select_sku("user", "SKU-A")
    result = service.handle_text("user", "430")
    assert result["error"] is False
    assert result["keyboard"]["buttons"][0] == {
        "text": "📊 Прибыль по этому товару",
        "callback": "period_profit_sku:SKU-A",
    }
    assert "Осталось заполнить" not in result["message"]
