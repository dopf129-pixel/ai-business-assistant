from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from telegram_app_layer.telegram_bot_service import TelegramBotService
from telegram_app_layer.telegram_command_service import TelegramCommandService


class _Profiles:
    def create_user(self, user_id):
        return {"error": False, "user": {"user_id": user_id}}


class _Assistant:
    def ask(self, text, user_id=None):
        return {"error": False, "message": "unused"}


def _production_wired_bot():
    keyboard = AssistantKeyboardService()
    handler = AssistantButtonHandlerService(
        _Assistant(),
        keyboard_service=keyboard,
    )
    adapter = AssistantTelegramAdapter(
        _Assistant(), keyboard, handler, _Profiles()
    )
    return TelegramBotService(adapter, TelegramCommandService(adapter))


def _callbacks(result):
    return [button["callback"] for button in result["keyboard"]["buttons"]]


def test_main_menu_makes_help_discoverable():
    keyboard = AssistantKeyboardService().build_main_keyboard()

    assert "help" in _callbacks({"keyboard": keyboard})


def test_help_callback_uses_production_telegram_path_and_existing_workflows():
    result = _production_wired_bot().on_callback("seller-a", "help")

    assert result["error"] is False
    assert result["read_only_ozon"] is True
    assert {"period_profit", "seller_cost", "memory"}.issubset(_callbacks(result))
    assert "help:commands" in _callbacks(result)
    assert "help:examples" in _callbacks(result)


def test_help_command_and_button_share_one_user_guide():
    bot = _production_wired_bot()

    command = bot.on_message("seller-a", "/help")
    callback = bot.on_callback("seller-a", "help")

    assert command == callback


def test_command_reference_lists_every_supported_slash_command_without_secrets():
    result = _production_wired_bot().on_callback("seller-a", "help:commands")

    for command in (
        "/start",
        "/help",
        "/memory",
        "/ozon_connect CLIENT_ID API_KEY",
        "/ozon_status",
        "/ozon_disconnect",
        "/costsku SKU СУММА",
    ):
        assert command in result["message"]
    assert "actual-secret" not in result["message"]
    assert result["executed_ozon"] is False


def test_phrase_reference_documents_hidden_inputs_and_financial_boundaries():
    result = _production_wired_bot().on_callback("seller-a", "help:examples")

    assert "запомни цена sky = 1290" in result["message"]
    assert "себестоимость 450 ₽ с 01.01.2026" in result["message"]
    assert "SKU 111 и SKU 222 — один товар" in result["message"]
    assert "не угадывает" in result["message"]


def test_help_returns_to_real_main_keyboard():
    result = _production_wired_bot().on_callback("seller-a", "help:main")

    assert result["error"] is False
    assert "period_profit" in _callbacks(result)
    assert "help" in _callbacks(result)
