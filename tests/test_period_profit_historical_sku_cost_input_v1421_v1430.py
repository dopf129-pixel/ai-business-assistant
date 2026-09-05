from telegram_app_layer.telegram_command_service import TelegramCommandService
from services.period_profit_finance_sku_scope_service import (
    PeriodProfitFinanceSkuScopeService,
)


class Adapter:
    pass


class CostStorage:
    def __init__(self):
        self.calls = []

    def set_cost(self, product_id, sku, offer_id, cost_price, currency):
        self.calls.append((product_id, sku, offer_id, cost_price, currency))


class UnavailableCostStorage:
    pass


class Summary:
    def __init__(self, cost_service):
        self.cost_service = cost_service
        self.products = None

    def calculate(self, date_from, date_to, products):
        self.products = list(products)
        return {"error": False, "status": "PERIOD_PROFIT_SUMMARY_READY"}


class Finance:
    def _get_accruals_by_day(self, day):
        return {
            "error": False,
            "accruals": [
                {
                    "accrued_category": "POSTING",
                    "posting": {"products": [{"sku": "3398133813"}]},
                }
            ],
        }


class RecoverableCostStorage(CostStorage):
    def get_historical_cost_evidence(self, at_date, **kwargs):
        return {
            "error": False,
            "historical_cost_confirmed": False,
            "cost_price": None,
        }

    def get_all_costs(self):
        return [
            (
                "finance-sku:3398133813",
                "3398133813",
                "3398133813",
                450.0,
                "RUB",
                "2026-09-05T00:00:00",
            )
        ]


def test_v1421_costsku_saves_seller_confirmed_local_cost():
    storage = CostStorage()
    service = TelegramCommandService(Adapter(), cost_service=storage)

    result = service.handle(1, "/costsku 3398133813 450")

    assert result["error"] is False
    assert result["seller_confirmed"] is True
    assert result["local_only"] is True
    assert result["read_only_ozon"] is True
    assert result["executed_ozon"] is False
    assert storage.calls == [
        (
            "finance-sku:3398133813",
            "3398133813",
            "3398133813",
            450.0,
            "RUB",
        )
    ]


def test_v1422_costsku_accepts_decimal_comma():
    storage = CostStorage()
    service = TelegramCommandService(Adapter(), cost_service=storage)

    result = service.handle(1, "/costsku 3398133813 450,25")

    assert result["error"] is False
    assert result["cost_price"] == 450.25
    assert storage.calls[0][3] == 450.25


def test_v1423_costsku_rejects_invalid_or_negative_cost_without_write():
    storage = CostStorage()
    service = TelegramCommandService(Adapter(), cost_service=storage)

    invalid = service.handle(1, "/costsku 3398133813 nope")
    negative = service.handle(1, "/costsku 3398133813 -1")

    assert invalid["error"] is False
    assert negative["error"] is False
    assert storage.calls == []


def test_v1424_unavailable_cost_storage_fails_closed():
    service = TelegramCommandService(
        Adapter(),
        cost_service=UnavailableCostStorage(),
    )

    result = service.handle(1, "/costsku 3398133813 450")

    assert result["error"] is True
    assert "недоступно" in result["message"]


def test_v1425_local_sku_cost_is_recoverable_for_period_profit():
    storage = RecoverableCostStorage()
    summary = Summary(storage)
    service = PeriodProfitFinanceSkuScopeService(summary, Finance())

    result = service.calculate(
        "2026-09-01",
        "2026-09-01",
        [("1", "current", "OTHER")],
    )

    assert result["error"] is False
    assert summary.products == [
        {
            "product_id": "finance-sku:3398133813",
            "sku": "3398133813",
            "offer_id": "3398133813",
            "cost_price": 450.0,
            "historical_cost_evidence": False,
        }
    ]
    assert result["historical_sku_recovery_count"] == 1


def test_v1426_help_documents_costsku_command():
    service = TelegramCommandService(Adapter(), cost_service=CostStorage())

    result = service.handle(1, "/help")

    assert result["error"] is False
    assert "/costsku" in result["message"]
