import sqlite3

from cryptography.fernet import Fernet

from api.ozon_client import OzonClient
from database import create_tables, get_products, save_product
from services.cost_service import ProductCostService
from services.ozon_account_repository import OzonAccountRepository
from services.ozon_account_service import OzonAccountService
from services.ozon_credential_provider import OzonCredentialProvider
from services.tenant_context import (
    get_current_tenant_user_id,
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from services.tenant_storage import tenant_storage_path
from telegram_app_layer.telegram_bot_service import TelegramBotService
from telegram_app_layer.telegram_command_service import TelegramCommandService


class _FakeProbeClient:
    def get_products(self, limit=1):
        return {"result": {"items": []}}


class _FakeAdapter:
    def get_start_response(self, user_id=None):
        return {
            "error": False,
            "tenant_seen": get_current_tenant_user_id(),
        }

    def handle_text(self, text, user_id=None):
        return {
            "error": False,
            "tenant_seen": get_current_tenant_user_id(),
        }

    def handle_button(self, callback, user_id=None):
        return {
            "error": False,
            "tenant_seen": get_current_tenant_user_id(),
        }


class _FakeAccountService:
    def __init__(self):
        self.calls = []

    def connect(self, user_id, client_id, api_key):
        self.calls.append(("connect", user_id, client_id, api_key))
        return {"error": False, "status": "CONNECTED"}

    def status(self, user_id):
        self.calls.append(("status", user_id))
        return {"error": False, "status": "STATUS"}

    def disconnect(self, user_id):
        self.calls.append(("disconnect", user_id))
        return {"error": False, "status": "DISCONNECTED"}


def _tenant(user_id):
    return set_current_tenant_user_id(user_id)


def test_account_repository_encrypts_api_key_and_isolates_users(tmp_path):
    db_path = tmp_path / "accounts.db"
    key = Fernet.generate_key().decode("utf-8")
    repo = OzonAccountRepository(master_key=key, db_name=str(db_path))

    assert repo.save("user-a", "111111", "secret-a")["error"] is False
    assert repo.save("user-b", "222222", "secret-b")["error"] is False

    assert repo.get("user-a") == {"client_id": "111111", "api_key": "secret-a"}
    assert repo.get("user-b") == {"client_id": "222222", "api_key": "secret-b"}
    assert repo.status("user-a")["client_id_masked"] == "111***"

    raw = db_path.read_bytes()
    assert b"secret-a" not in raw
    assert b"secret-b" not in raw


def test_tenant_credential_provider_never_falls_back_to_other_account(tmp_path):
    key = Fernet.generate_key().decode("utf-8")
    repo = OzonAccountRepository(master_key=key, db_name=str(tmp_path / "accounts.db"))
    repo.save("user-a", "client-a", "key-a")
    provider = OzonCredentialProvider(repository=repo)

    token = _tenant("user-a")
    try:
        credentials = provider.get_credentials()
        assert credentials["client_id"] == "client-a"
        assert credentials["api_key"] == "key-a"
        assert credentials["source"] == "TENANT_ACCOUNT"
    finally:
        reset_current_tenant_user_id(token)

    token = _tenant("user-b")
    try:
        credentials = provider.get_credentials()
        assert credentials["client_id"] is None
        assert credentials["api_key"] is None
        assert credentials["source"] == "TENANT_ACCOUNT_MISSING"
    finally:
        reset_current_tenant_user_id(token)


def test_ozon_client_resolves_headers_from_current_tenant(tmp_path):
    key = Fernet.generate_key().decode("utf-8")
    repo = OzonAccountRepository(master_key=key, db_name=str(tmp_path / "accounts.db"))
    repo.save("user-a", "client-a", "key-a")
    repo.save("user-b", "client-b", "key-b")
    client = OzonClient(credential_provider=OzonCredentialProvider(repository=repo))

    token = _tenant("user-a")
    try:
        assert client.get_headers()["Client-Id"] == "client-a"
        assert client.get_headers()["Api-Key"] == "key-a"
    finally:
        reset_current_tenant_user_id(token)

    token = _tenant("user-b")
    try:
        assert client.get_headers()["Client-Id"] == "client-b"
        assert client.get_headers()["Api-Key"] == "key-b"
    finally:
        reset_current_tenant_user_id(token)


def test_core_database_isolated_between_telegram_tenants(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    token = _tenant("user-a")
    try:
        create_tables()
        save_product({"product_id": "1", "offer_id": "A", "sku": "SKU-A"})
        assert get_products() == [("1", "A", "SKU-A")]
    finally:
        reset_current_tenant_user_id(token)

    token = _tenant("user-b")
    try:
        create_tables()
        assert get_products() == []
        save_product({"product_id": "2", "offer_id": "B", "sku": "SKU-B"})
        assert get_products() == [("2", "B", "SKU-B")]
    finally:
        reset_current_tenant_user_id(token)

    token = _tenant("user-a")
    try:
        assert get_products() == [("1", "A", "SKU-A")]
    finally:
        reset_current_tenant_user_id(token)


def test_product_cost_storage_isolated_between_telegram_tenants(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    token = _tenant("user-a")
    try:
        service = ProductCostService()
        service.set_cost("p", "sku", "offer", 10.0, "RUB")
        path_a = tenant_storage_path("ozon_assistant.db")
    finally:
        reset_current_tenant_user_id(token)

    token = _tenant("user-b")
    try:
        ProductCostService()
        path_b = tenant_storage_path("ozon_assistant.db")
        conn = sqlite3.connect(path_b)
        try:
            count_b = conn.execute("SELECT COUNT(*) FROM product_costs").fetchone()[0]
        finally:
            conn.close()
        assert count_b == 0
    finally:
        reset_current_tenant_user_id(token)

    assert path_a != path_b
    conn = sqlite3.connect(path_a)
    try:
        assert conn.execute("SELECT cost_price FROM product_costs").fetchone()[0] == 10.0
    finally:
        conn.close()


def test_telegram_bot_sets_and_resets_tenant_context():
    bot = TelegramBotService(_FakeAdapter())
    result = bot.on_message("user-a", "hello")
    assert result["tenant_seen"] == "user-a"
    assert get_current_tenant_user_id() is None


def test_ozon_account_commands_are_bound_to_request_user():
    account_service = _FakeAccountService()
    service = TelegramCommandService(
        _FakeAdapter(),
        ozon_account_service=account_service,
    )

    result = service.handle("user-a", "/ozon_connect 123 api-secret")
    assert result["status"] == "CONNECTED"
    assert account_service.calls[-1] == ("connect", "user-a", "123", "api-secret")

    service.handle("user-b", "/ozon_status")
    assert account_service.calls[-1] == ("status", "user-b")

    service.handle("user-a", "/ozon_disconnect")
    assert account_service.calls[-1] == ("disconnect", "user-a")


def test_account_service_validates_before_persisting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    key = Fernet.generate_key().decode("utf-8")
    repo = OzonAccountRepository(master_key=key, db_name=str(tmp_path / "accounts.db"))
    service = OzonAccountService(
        repository=repo,
        client_factory=lambda client_id, api_key: _FakeProbeClient(),
    )

    token = _tenant("user-a")
    try:
        result = service.connect("user-a", "123456", "api-secret")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "OZON_ACCOUNT_CONNECTED"
    assert result["read_only_ozon"] is True
    assert result["executed_ozon"] is False
    assert "api-secret" not in result["message"]
    assert repo.get("user-a")["api_key"] == "api-secret"
