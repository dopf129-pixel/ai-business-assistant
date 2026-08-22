from app.services.assistant_stock_executor_service import (
    AssistantStockExecutorService
)


class FakeStockIntelligenceService:

    def __init__(self):
        self.calls = []

    def analyze(
        self,
        stock_data,
        sales_data,
        period_days
    ):

        self.calls.append(
            {
                "stock_data": stock_data,
                "sales_data": sales_data,
                "period_days": period_days
            }
        )

        return {
            "error": False,
            "product_id": "101",
            "current_stock": 10,
            "sales_velocity": 2.0,
            "days_of_stock": 5.0,
            "priority": "HIGH"
        }


def test_stock_executor_passes_context_to_intelligence_service():

    intelligence_service = (
        FakeStockIntelligenceService()
    )

    executor = AssistantStockExecutorService(
        stock_intelligence_service=(
            intelligence_service
        )
    )

    action = {
        "type": "stock",
        "priority": "HIGH",
        "context": {
            "stock_data": {
                "product_id": "101",
                "current_stock": 10
            },
            "sales_data": {
                "product_id": "101",
                "sales_count": 20
            },
            "period_days": 10,
            "reason": "Low stock"
        }
    }

    executor.execute(action)

    assert intelligence_service.calls == [
        {
            "stock_data": {
                "product_id": "101",
                "current_stock": 10
            },
            "sales_data": {
                "product_id": "101",
                "sales_count": 20
            },
            "period_days": 10
        }
    ]


def test_stock_executor_preserves_response_contract():

    executor = AssistantStockExecutorService(
        stock_intelligence_service=(
            FakeStockIntelligenceService()
        )
    )

    result = executor.execute(
        {
            "type": "stock",
            "priority": "HIGH",
            "context": {
                "stock_data": {
                    "product_id": "101",
                    "current_stock": 10
                },
                "sales_data": {
                    "product_id": "101",
                    "sales_count": 20
                },
                "period_days": 10
            }
        }
    )

    assert result["error"] is False
    assert result["result"]["type"] == "stock"
    assert (
        result["result"]["message"]
        == "Проверка остатков выполнена"
    )
    assert result["result"]["priority"] == "HIGH"
    assert "Текущий остаток: 10" in (
        result["result"]["details"]
    )
    assert "Приоритет пополнения: HIGH" in (
        result["result"]["details"]
    )


def test_stock_executor_keeps_legacy_fallback_without_service():

    executor = AssistantStockExecutorService()

    result = executor.execute(
        {
            "type": "stock",
            "priority": "NORMAL",
            "context": {
                "reason": "Inventory check"
            }
        }
    )

    assert result == {
        "error": False,
        "result": {
            "type": "stock",
            "message": "Проверка остатков выполнена",
            "details": [
                "Проверены остатки товара",
                "Найдены позиции для контроля",
                "Причина анализа: Inventory check"
            ],
            "priority": "NORMAL"
        }
    }
