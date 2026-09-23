import sqlite3

from cryptography.fernet import Fernet

from services.ozon_account_repository import OzonAccountRepository
from services.ozon_account_service import OzonAccountService


class _Client:
    info_calls = []

    def __init__(self, client_id, api_key):
        self.client_id = client_id
        self.api_key = api_key

    def get_products(self, limit=1):
        return {"error": False, "items": []}

    def get_seller_info(self):
        type(self).info_calls.append(self.client_id)
        return {"error": False, "company": {"name": " Магазин  Ромашка "}}


def _repository(tmp_path):
    return OzonAccountRepository(
        master_key=Fernet.generate_key().decode("utf-8"),
        db_name=str(tmp_path / "accounts.db"),
    )


def test_new_store_saves_and_displays_ozon_company_name(tmp_path):
    repository = _repository(tmp_path)
    service = OzonAccountService(repository=repository, client_factory=_Client)
    _Client.info_calls = []

    connected = service.connect("user", "390123", "secret")
    stores = service.stores("user")

    assert connected["error"] is False
    assert stores["keyboard"]["buttons"] == [{
        "text": "✓ Магазин Ромашка",
        "callback": "ozon_store:390123",
    }]
    assert service.status("user")["display_name"] == "Магазин Ромашка"
    assert _Client.info_calls == ["390123"]


def test_existing_store_name_is_backfilled_once_and_then_cached(tmp_path):
    repository = _repository(tmp_path)
    repository.save("user", "115123", "secret")
    service = OzonAccountService(repository=repository, client_factory=_Client)
    _Client.info_calls = []

    first = service.stores("user")
    second = service.stores("user")

    assert first["keyboard"]["buttons"][0]["text"] == "✓ Магазин Ромашка"
    assert second["keyboard"]["buttons"][0]["text"] == "✓ Магазин Ромашка"
    assert _Client.info_calls == ["115123"]


def test_old_database_schema_is_migrated_without_losing_credentials(tmp_path):
    db = tmp_path / "old.db"
    key = Fernet.generate_key().decode("utf-8")
    encrypted = Fernet(key.encode("utf-8")).encrypt(b"secret").decode("utf-8")
    connection = sqlite3.connect(db)
    try:
        connection.execute(
            """
            CREATE TABLE ozon_store_accounts (
                telegram_user_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                api_key_encrypted TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_user_id, client_id)
            )
            """
        )
        connection.execute(
            "INSERT INTO ozon_store_accounts "
            "(telegram_user_id, client_id, api_key_encrypted, is_active) "
            "VALUES (?, ?, ?, 1)",
            ("user", "123", encrypted),
        )
        connection.commit()
    finally:
        connection.close()

    repository = OzonAccountRepository(master_key=key, db_name=str(db))

    assert repository.get("user") == {"client_id": "123", "api_key": "secret"}
    assert repository.list_accounts("user")[0]["display_name"] is None
