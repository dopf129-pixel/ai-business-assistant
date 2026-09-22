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
        return {"error": False}


class Tax:
    def __init__(self, configured=False): self.configured, self.saved = configured, []
    def get_policy(self): return {"error": False, "configured": self.configured, "policy": None}
    def save_policy(self, mode, tax_rate=None, minimum_tax_rate=1.0):
        self.saved.append((mode, tax_rate))
        self.configured = True
        return {"error": False, "saved": True}


class SellerCosts:
    def __init__(self, configured, total=2):
        self.configured = configured
        self.total = total
        self.calls = 0

    def open_menu(self):
        self.calls += 1
        missing = self.total - self.configured
        return {
            "error": False,
            "cost_coverage": {
                "configured": self.configured,
                "total": self.total,
                "missing": missing,
            },
        }


def make_bot(accounts, tax, seller_costs=None):
    service = TelegramOnboardingService(
        accounts, tax, seller_cost_service=seller_costs
    )
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


def test_start_skips_seller_cost_prompt_when_catalog_coverage_is_complete():
    accounts, tax = Accounts({"seller-a"}), Tax(configured=True)
    costs = SellerCosts(configured=2, total=2)
    bot = make_bot(accounts, tax, costs)

    result = bot.on_start("seller-a")

    assert result["onboarding_complete"] is True
    assert result["cost_coverage"]["missing"] == 0
    assert "Шаг 3 из 3" not in result.get("text", "")
    assert "Себестоимость заполнена" in result["message"]
    assert costs.calls == 1


def test_start_keeps_seller_cost_step_when_catalog_has_missing_costs():
    accounts, tax = Accounts({"seller-a"}), Tax(configured=True)
    costs = SellerCosts(configured=1, total=2)
    bot = make_bot(accounts, tax, costs)

    result = bot.on_start("seller-a")

    assert result["onboarding_complete"] is True
    assert "Шаг 3 из 3" in result["text"]
    assert result["keyboard"]["buttons"][0]["callback"] == "seller_cost"


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
