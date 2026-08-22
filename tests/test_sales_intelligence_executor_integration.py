import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_sales_executor_service import (
    AssistantSalesExecutorService
)


class FakeSalesIntelligenceService:

    def __init__(
        self,
        result
    ):

        self.result = result
        self.calls = []


    def analyze(
        self,
        profits,
        previous_result=None
    ):

        self.calls.append(
            {
                "profits": profits,
                "previous_result": previous_result
            }
        )

        return self.result


def test_sales_executor_uses_injected_sales_intelligence_service():

    intelligence = (
        FakeSalesIntelligenceService(
            {
                "error": False,
                "metrics": {
                    "revenue": 875,
                    "gross_profit": 250,
                    "business_profit": 150,
                    "margin_percent": 17.14
                },
                "insights": [
                    {
                        "type": "sales_decline",
                        "message": (
                            "Продажи снизились относительно предыдущего периода"
                        )
                    }
                ]
            }
        )
    )

    executor = (
        AssistantSalesExecutorService(
            sales_intelligence_service=(
                intelligence
            )
        )
    )

    profits = [
        {
            "sku": "SKU-1",
            "profit": 150
        }
    ]

    previous_result = {
        "store_profit": {
            "gross_sales": 1000
        }
    }

    result = executor.execute(
        {
            "type": "sales",
            "priority": "HIGH",
            "context": {
                "profits": profits,
                "previous_result": previous_result,
                "reason": "Продажи снизились"
            }
        }
    )

    assert intelligence.calls == [
        {
            "profits": profits,
            "previous_result": previous_result
        }
    ]

    assert result["error"] is False
    assert result["result"]["type"] == "sales"
    assert result["result"]["priority"] == "HIGH"
    assert result["result"]["message"] == (
        "Анализ продаж выполнен"
    )

    assert result["result"]["details"] == [
        "Выручка: 875",
        "Валовая прибыль: 250",
        "Прибыль после расходов: 150",
        "Маржинальность: 17.14%",
        "Продажи снизились относительно предыдущего периода",
        "Причина анализа: Продажи снизились"
    ]


def test_sales_executor_propagates_sales_intelligence_error():

    intelligence = (
        FakeSalesIntelligenceService(
            {
                "error": True,
                "message": "Нет данных для анализа"
            }
        )
    )

    executor = (
        AssistantSalesExecutorService(
            sales_intelligence_service=(
                intelligence
            )
        )
    )

    result = executor.execute(
        {
            "type": "sales",
            "context": {
                "profits": []
            }
        }
    )

    assert result == {
        "error": True,
        "message": "Нет данных для анализа"
    }


def test_sales_executor_keeps_legacy_contract_without_intelligence_service():

    executor = (
        AssistantSalesExecutorService()
    )

    result = executor.execute(
        {
            "type": "sales",
            "priority": "NORMAL",
            "context": {
                "reason": "Проверка совместимости"
            }
        }
    )

    assert result == {
        "error": False,
        "result": {
            "type": "sales",
            "message": "Анализ продаж выполнен",
            "details": [
                "Проверено падение продаж",
                "Найдены возможные причины",
                "Причина анализа: Проверка совместимости"
            ],
            "priority": "NORMAL"
        }
    }
