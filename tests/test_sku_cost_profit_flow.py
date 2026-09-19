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


class _EffectiveCosts(_Costs):
    def get_effective_cost_evidence(self, **kwargs):
        assert kwargs["product_id"] == "1"
        assert kwargs["sku"] == "SKU-A"
        assert kwargs["offer_id"] == "ART-A"
        return {
            "error": False,
            "effective_cost_confirmed": True,
            "cost_price": 430.0,
        }


def test_sku_profit_uses_selected_seller_cost_even_if_canonical_row_cost_is_missing():
    costs = _EffectiveCosts([("1", "SKU-A", "ART-A", 430.0, "RUB", "now")])

    class Query(_Query):
        def query(self, **kwargs):
            summary = {
                "date_from": "2026-09-13",
                "date_to": "2026-09-19",
                "tax_mode": "NONE",
                "tax_rate_percent": 0,
                "minimum_tax_rate_percent": 0,
                "products": [{
                    "product_id": "1",
                    "catalog_sku": "SKU-A",
                    "sku": "989101156",
                    "units_sold": 2,
                    "revenue": 2000.0,
                    "net_accrual": 1500.0,
                    "commission": 200.0,
                    "logistics": 250.0,
                    "acquiring": 50.0,
                    "other_fees": 0.0,
                    "product_cost": 0.0,
                    "tax": 0.0,
                    "profit": 1500.0,
                }],
            }
            return {"error": False, "summary": summary}

    service = PeriodProfitSkuRuntimeService(Query(), cost_service=costs)
    result = service.handle_callback("period_profit_sku:SKU-A:7D")
    assert result["error"] is False
    assert result["summary"]["product_cost"] == 860.0
    assert result["summary"]["profit"] == 640.0
