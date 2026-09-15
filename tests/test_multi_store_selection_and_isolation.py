from cryptography.fernet import Fernet

from services.ozon_account_repository import OzonAccountRepository
from services.ozon_account_service import OzonAccountService
from services.tenant_context import get_current_tenant_store_id
from services.tenant_storage import tenant_storage_path
from telegram_app_layer.store_selection_telegram_adapter import StoreSelectionTelegramAdapter
from telegram_app_layer.telegram_bot_service import TelegramBotService


class Probe:
    def get_products(self, limit=1): return {"error": False, "items": []}


class Base:
    def get_start_response(self, user_id=None): return {"error": False}
    def handle_text(self, text, user_id=None): return {"error": False, "message": text}
    def handle_button(self, callback, user_id=None): return {"error": False, "message": callback}


def service(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = OzonAccountRepository(master_key=Fernet.generate_key().decode(), db_name=str(tmp_path / "accounts.db"))
    return OzonAccountService(repository=repo, client_factory=lambda *_: Probe())


def test_one_telegram_user_can_store_and_select_two_accounts(tmp_path, monkeypatch):
    accounts = service(tmp_path, monkeypatch)
    assert accounts.connect("user", "store-a", "key-a")["error"] is False
    assert accounts.connect("user", "store-b", "key-b")["error"] is False
    assert accounts.repository.get("user")["client_id"] == "store-b"

    assert accounts.select("user", "store-a")["error"] is False
    assert accounts.repository.get("user")["api_key"] == "key-a"
    rows = accounts.list_accounts("user")["accounts"]
    assert len(rows) == 2
    assert [row["client_id"] for row in rows if row["active"]] == ["store-a"]


def test_store_scope_changes_tenant_storage_path_without_guessing_legacy_data(tmp_path, monkeypatch):
    accounts = service(tmp_path, monkeypatch)
    accounts.connect("user", "store-a", "key-a")
    accounts.connect("user", "store-b", "key-b")

    class Adapter(Base):
        def handle_button(self, callback, user_id=None):
            return {"error": False, "store": get_current_tenant_store_id(), "path": tenant_storage_path("ozon_assistant.db")}

    bot = TelegramBotService(Adapter(), store_resolver=accounts.repository.active_client_id)
    path_b = bot.on_callback("user", "x")
    accounts.select("user", "store-a")
    path_a = bot.on_callback("user", "x")

    assert path_a["store"] == "store-a"
    assert path_b["store"] == "store-b"
    assert path_a["path"] != path_b["path"]
    assert get_current_tenant_store_id() is None


def test_store_adapter_exposes_picker_and_adds_account_through_existing_chain(tmp_path, monkeypatch):
    accounts = service(tmp_path, monkeypatch)
    accounts.connect("user", "store-a", "key-a")
    adapter = StoreSelectionTelegramAdapter.__new__(StoreSelectionTelegramAdapter)
    adapter.account_service = accounts
    adapter._pending_store_add = set()

    menu = adapter.handle_button("stores", "user")
    assert [b["callback"] for b in menu["keyboard"]["buttons"]] == ["store_select:store-a", "store_add"]
    adapter.handle_button("store_add", "user")
    added = adapter.handle_text("store-b key-b", "user")
    assert added["status"] == "OZON_ACCOUNT_CONNECTED"
    assert len(accounts.list_accounts("user")["accounts"]) == 2


def test_store_selection_is_tenant_scoped(tmp_path, monkeypatch):
    accounts = service(tmp_path, monkeypatch)
    accounts.connect("user-a", "store-a", "key-a")
    accounts.connect("user-b", "store-b", "key-b")

    assert accounts.select("user-a", "store-b")["error"] is True
    assert accounts.repository.get("user-a")["client_id"] == "store-a"
    assert accounts.repository.get("user-b")["client_id"] == "store-b"
