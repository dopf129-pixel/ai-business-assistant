from services.telegram_onboarding_service import TelegramOnboardingService
from services.tenant_context import get_current_tenant_user_id
from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from telegram_app_layer.telegram_bot_service import TelegramBotService


class Assistant:
    def ask(self, text, user_id=None): return {"error": False, "message": text}


class Keyboard:
    def build_main_keyboard(self): return {"error": False, "type": "inline_keyboard", "buttons": []}


class Buttons:
    def handle(self, callback, user_id=None): return {"error": False, "message": callback}


class Profiles:
    def create_user(self, user_id): return {"error": False, "user": {"user_id": str(user_id)}}


class Accounts:
    def __init__(self, connected=()):
        self.connected, self.connect_calls = set(connected), []

    def status(self, user_id):
        assert get_current_tenant_user_id() == str(user_id)
        return {"error": False, "connected": user_id in self.connected}

    def connect(self, user_id, client_id, api_key):
        assert get_current_tenant_user_id() == str(user_id)
        self.connect_calls.append((user_id, client_id, api_key))
        self.connected.add(user_id)
        return {"error": False, "status": "OZON_ACCOUNT_CONNECTED"}


class Tax:
    def __init__(self, configured=False): self.configured, self.saved = configured, []
    def get_policy(self): return {"error": False, "configured": self.configured, "policy": None}
    def save_policy(self, mode, tax_rate=None, minimum_tax_rate=1.0):
        self.saved.append((mode, tax_rate))
        self.configured = True
        return {"error": False, "saved": True}


def make_bot(accounts, tax):
    service = TelegramOnboardingService(accounts, tax)
    adapter = AssistantTelegramAdapter(Assistant(), Keyboard(), Buttons(), Profiles(), onboarding_service=service)
    return TelegramBotService(adapter)


def test_production_callback_path_resumes_without_echoing_secret():
    accounts, tax = Accounts(), Tax()
    bot = make_bot(accounts, tax)
    assert bot.on_start("seller-a")["required_step"] == "OZON_CREDENTIALS"
    connected = bot.on_message("seller-a", "client-123 api-secret")
    assert connected["required_step"] == "TAX_CONFIGURATION"
    assert "api-secret" not in str(connected)
    completed = bot.on_callback("seller-a", "onboarding_tax:NONE")
    assert completed["onboarding_complete"] is True
    assert tax.saved == [("NONE", None)]


def test_existing_settings_are_skipped_and_complete_user_gets_menu():
    accounts, tax = Accounts({"seller-a"}), Tax()
    bot = make_bot(accounts, tax)
    assert bot.on_start("seller-a")["required_step"] == "TAX_CONFIGURATION"
    tax.configured = True
    assert bot.on_start("seller-a")["onboarding_complete"] is True


def test_pending_input_is_tenant_scoped():
    accounts, tax = Accounts({"seller-b"}), Tax()
    bot = make_bot(accounts, tax)
    bot.on_start("seller-a")
    bot.on_start("seller-b")
    assert bot.on_message("seller-b", "ordinary message")["message"] == "ordinary message"


def test_factory_wires_onboarding(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    from telegram_assistant_factory import create_telegram_assistant
    runner = create_telegram_assistant()
    assert isinstance(runner.onboarding_service, TelegramOnboardingService)
    assert runner.bot_service.on_start("new-seller")["required_step"] == "OZON_CREDENTIALS"


def test_failed_ozon_probe_does_not_advance_to_tax_setup():
    class RejectedAccounts(Accounts):
        def connect(self, user_id, client_id, api_key):
            return {
                "error": False,
                "status": "OZON_ACCOUNT_CONNECTION_FAILED",
                "message": "Ozon не подтвердил доступ с этими реквизитами.",
            }

    bot = make_bot(RejectedAccounts(), Tax())
    bot.on_start("seller-a")

    result = bot.on_message("seller-a", "client invalid-key")

    assert result["handled"] is True
    assert "не подтвердил" in result["message"]
    assert result.get("required_step") != "TAX_CONFIGURATION"


def test_storage_failure_is_shown_without_secret_or_false_success():
    class FailedStorageAccounts(Accounts):
        def connect(self, user_id, client_id, api_key):
            return {
                "error": True,
                "status": "OZON_ACCOUNT_STORAGE_UNAVAILABLE",
                "message": "Проверьте OZON_CREDENTIAL_MASTER_KEY и хранилище.",
            }

    bot = make_bot(FailedStorageAccounts(), Tax())
    bot.on_start("seller-a")

    result = bot.on_message("seller-a", "client api-secret")

    assert result["handled"] is True
    assert "OZON_CREDENTIAL_MASTER_KEY" in result["message"]
    assert "api-secret" not in str(result)


def test_existing_unreadable_credentials_do_not_prompt_for_reconnection():
    class UnreadableAccounts(Accounts):
        def status(self, user_id):
            return {
                "error": True,
                "code": "OZON_ACCOUNT_MASTER_KEY_MISMATCH",
                "message": (
                    "Подключение уже сохранено. Восстановите прежний "
                    "OZON_CREDENTIAL_MASTER_KEY; не подключайте магазин повторно."
                ),
            }

    result = make_bot(UnreadableAccounts(), Tax()).on_start("seller-a")

    assert result["error"] is True
    assert result["code"] == "OZON_ACCOUNT_MASTER_KEY_MISMATCH"
    assert result.get("required_step") != "OZON_CREDENTIALS"
    assert "не подключайте магазин повторно" in result["text"]
