import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


def test_marketing_executor_requires_explicit_evidence():

    core = create_telegram_core()

    result = (
        core["action_router"]
        .execute(
            {
                "type": "marketing",
                "title": "Проверить рекламные каналы",
                "priority": "HIGH",
                "context": {
                    "reason": "Снизилась эффективность рекламы"
                }
            }
        )
    )

    assert result == {
        "error": True,
        "message": "Недостаточно данных для анализа маркетинга"
    }


def test_marketing_executor_formats_only_supplied_evidence():

    core = create_telegram_core()

    result = (
        core["action_router"]
        .execute(
            {
                "type": "marketing",
                "priority": "HIGH",
                "context": {
                    "evidence": [
                        "CTR снизился с 3.1% до 2.4%",
                        "Расходы выросли на 12%"
                    ],
                    "reason": "Проверить изменение эффективности"
                }
            }
        )
    )

    assert result["error"] is False
    assert result["result"]["type"] == "marketing"
    assert result["result"]["message"] == "Маркетинговые данные подготовлены"
    assert result["result"]["details"] == [
        "CTR снизился с 3.1% до 2.4%",
        "Расходы выросли на 12%",
        "Причина анализа: Проверить изменение эффективности"
    ]
