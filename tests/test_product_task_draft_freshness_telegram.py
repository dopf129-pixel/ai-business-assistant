from app.telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)


class _ButtonHandler:
    def __init__(self, result):
        self.result = result

    def handle(self, callback, user_id=None):
        return self.result


class _KeyboardService:
    def build_main_keyboard(self):
        return []


def _adapter(result):
    return AssistantTelegramAdapter(
        assistant=None,
        keyboard_service=_KeyboardService(),
        button_handler=_ButtonHandler(result),
    )


def test_task_draft_list_shows_freshness_counts():
    result = {
        "error": False,
        "message": "Черновики задач",
        "readiness_summary": {
            "freshness_counts": {
                "FRESH": 2,
                "STALE": 1,
                "UNKNOWN": 3,
            }
        },
        "executed": False,
    }

    response = _adapter(result).handle_button(
        "product_action_task_drafts"
    )

    assert "Свежесть данных:" in response["message"]
    assert "Свежие: 2" in response["message"]
    assert "Устарели: 1" in response["message"]
    assert "Неизвестно: 3" in response["message"]
    assert response["executed"] is False


def test_task_draft_detail_shows_status_age_and_reasons():
    result = {
        "error": False,
        "message": "Черновик задачи",
        "readiness": {
            "freshness": {
                "status": "UNKNOWN",
                "decision_snapshot": {
                    "age_seconds": 1800.0,
                },
                "reasons": [
                    "SALES_TIMESTAMP_UNKNOWN",
                    "STOCK_TIMESTAMP_UNKNOWN",
                ],
            },
            "execution_ready": False,
            "executed": False,
        },
        "executed": False,
    }

    response = _adapter(result).handle_button(
        "product_task_draft:view:d1"
    )

    assert "Свежесть данных:" in response["message"]
    assert "свежесть неизвестна" in response["message"]
    assert "Возраст снимка решения: 30 мин." in response["message"]
    assert "время данных продаж неизвестно" in response["message"]
    assert "время данных остатков неизвестно" in response["message"]
    assert response["executed"] is False


def test_non_draft_callback_is_not_modified():
    result = {
        "error": False,
        "message": "Без изменений",
    }

    response = _adapter(result).handle_button("history")

    assert response == result
