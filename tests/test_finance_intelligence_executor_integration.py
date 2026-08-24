import sys

sys.path.insert(0, "app")

from services.assistant_finance_executor_service import (
    AssistantFinanceExecutorService
)


class FakeFinanceIntelligenceService:

    def __init__(self):
        self.finance_data = None
        self.previous_data = None

    def analyze(
        self,
        finance_data,
        previous_data=None
    ):
        self.finance_data = finance_data
        self.previous_data = previous_data
        return {
            "error": False,
            "metrics": {
                "revenue": 1000.0,
                "expenses": 600.0,
                "profit": 400.0,
                "margin": 40.0
            },
            "insights": [
                {
                    "message": "Бизнес работает с положительной прибылью"
                }
            ]
        }


def test_finance_action_calls_intelligence_with_context_data():
    intelligence = FakeFinanceIntelligenceService()
    executor = AssistantFinanceExecutorService(
        finance_intelligence_service=intelligence
    )

    finance_data = {
        "revenue": 1000,
        "expenses": 600
    }
    previous_data = {
        "revenue": 900,
        "expenses": 550
    }

    result = executor.execute(
        {
            "type": "finance",
            "priority": "HIGH",
            "context": {
                "finance_data": finance_data,
                "previous_data": previous_data
            }
        }
    )

    assert intelligence.finance_data == finance_data
    assert intelligence.previous_data == previous_data
    assert result["error"] is False
    assert result["result"]["type"] == "finance"
    assert result["result"]["priority"] == "HIGH"
    assert "Выручка: 1000.0" in result["result"]["details"]
    assert "Прибыль: 400.0" in result["result"]["details"]


def test_finance_executor_preserves_response_contract():
    executor = AssistantFinanceExecutorService(
        finance_intelligence_service=(
            FakeFinanceIntelligenceService()
        )
    )

    result = executor.execute(
        {
            "type": "finance",
            "context": {
                "finance_data": {
                    "revenue": 1000,
                    "expenses": 600
                }
            }
        }
    )

    assert set(result.keys()) == {"error", "result"}
    assert set(result["result"].keys()) == {
        "type",
        "message",
        "details",
        "priority"
    }


def test_finance_executor_falls_back_without_intelligence_service():
    executor = AssistantFinanceExecutorService()

    result = executor.execute(
        {
            "type": "finance",
            "context": {}
        }
    )

    assert result == {
        "error": False,
        "result": {
            "type": "finance",
            "message": "Финансовый анализ выполнен",
            "details": [
                "Проверены финансовые показатели",
                "Финансовый анализ подготовлен"
            ],
            "priority": "NORMAL"
        }
    }
