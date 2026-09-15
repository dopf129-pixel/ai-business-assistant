from cryptography.fernet import Fernet

from services.ozon_account_repository import (
    OzonAccountRepository,
    make_store_tenant_scope,
    split_store_tenant_scope,
)
from services.ozon_credential_provider import OzonCredentialProvider
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


def _repo(tmp_path):
    return OzonAccountRepository(
        master_key=Fernet.generate_key().decode("utf-8"),
        db_name=str(tmp_path / "ozon.db"),
    )


def test_repository_keeps_multiple_stores_and_switches_active_store(tmp_path):
    repo = _repo(tmp_path)

    assert repo.save("42", "111111", "key-a")["error"] is False
    assert repo.save("42", "222222", "key-b")["error"] is False

    stores = repo.list_accounts("42")
    assert {item["client_id"] for item in stores} == {"111111", "222222"}
    assert repo.active_client_id("42") == "222222"
    assert repo.get("42") == {"client_id": "222222", "api_key": "key-b"}

    selected = repo.select("42", "111111")
    assert selected["selected"] is True
    assert repo.active_client_id("42") == "111111"
    assert repo.get("42") == {"client_id": "111111", "api_key": "key-a"}


def test_store_tenant_scope_selects_exact_credentials(tmp_path):
    repo = _repo(tmp_path)
    repo.save("42", "111111", "key-a")
    repo.save("42", "222222", "key-b")
    provider = OzonCredentialProvider(repository=repo)

    scope = make_store_tenant_scope("42", "111111")
    assert split_store_tenant_scope(scope) == ("42", "111111")

    token = set_current_tenant_user_id(scope)
    try:
        credentials = provider.get_credentials()
    finally:
        reset_current_tenant_user_id(token)

    assert credentials["client_id"] == "111111"
    assert credentials["api_key"] == "key-a"


def test_disconnect_only_removes_selected_store(tmp_path):
    repo = _repo(tmp_path)
    repo.save("42", "111111", "key-a")
    repo.save("42", "222222", "key-b")
    repo.select("42", "111111")

    result = repo.delete("42")

    assert result == {"error": False, "deleted": True}
    assert repo.get("42", "111111") is None
    assert repo.get("42", "222222") == {"client_id": "222222", "api_key": "key-b"}
    assert repo.active_client_id("42") == "222222"


def test_deleted_legacy_store_is_not_resurrected_by_migration(tmp_path):
    db_name = str(tmp_path / "ozon.db")
    key = Fernet.generate_key().decode("utf-8")
    repo = OzonAccountRepository(master_key=key, db_name=db_name)
    encrypted = repo._fernet().encrypt(b"legacy-key").decode("utf-8")

    conn = repo._connection()
    try:
        conn.execute(
            "INSERT INTO ozon_accounts (telegram_user_id, client_id, api_key_encrypted) VALUES (?, ?, ?)",
            ("42", "legacy", encrypted),
        )
        conn.commit()
    finally:
        conn.close()

    migrated = OzonAccountRepository(master_key=key, db_name=db_name)
    assert migrated.get("42", "legacy") == {"client_id": "legacy", "api_key": "legacy-key"}
    assert migrated.delete("42", "legacy")["deleted"] is True

    restarted = OzonAccountRepository(master_key=key, db_name=db_name)
    assert restarted.get("42", "legacy") is None
    assert restarted.list_accounts("42") == []
