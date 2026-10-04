from telegram_app_layer.telegram_response_formatter import TelegramResponseFormatter


def test_error_without_user_message_never_exposes_raw_result_context():
    result = {
        "error": True,
        "code": "PERIOD_PROFIT_SKU_ADVERTISING_MAPPING_REQUIRED",
        "status": "PERIOD_PROFIT_SKU_UNAVAILABLE",
        "context": {
            "last_message": "private-date-range",
            "memory": {
                "name": "private-name",
                "credential": "private-token-fixture",
            },
        },
    }

    formatted = TelegramResponseFormatter().format(result)

    assert formatted == "Не удалось обработать запрос."
    assert "private-date-range" not in formatted
    assert "private-name" not in formatted
    assert "private-token-fixture" not in formatted
    assert "PERIOD_PROFIT_SKU_ADVERTISING_MAPPING_REQUIRED" not in formatted


def test_error_with_safe_user_message_uses_message_without_context():
    result = {
        "error": True,
        "message": "Сверка не завершена. Код диагностики: SAFE_CODE",
        "context": {"private": "private-context-fixture"},
    }

    formatted = TelegramResponseFormatter().format(result)

    assert formatted == "Сверка не завершена. Код диагностики: SAFE_CODE"
    assert "private-context-fixture" not in formatted
