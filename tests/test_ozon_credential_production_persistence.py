import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from services.ozon_account_repository import OzonAccountRepository


MASTER_KEY = Fernet.generate_key().decode("utf-8")
WRONG_KEY = Fernet.generate_key().decode("utf-8")


def _ciphertext(db_path, user_id="42", client_id="client-123"):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """SELECT api_key_encrypted FROM ozon_store_accounts
               WHERE telegram_user_id = ? AND client_id = ?""",
            (user_id, client_id),
        ).fetchone()
    finally:
        conn.close()
    return None if row is None else str(row[0])


def test_default_credential_db_uses_persistent_runtime_root(monkeypatch, tmp_path):
    storage_root = tmp_path / "persistent"
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", MASTER_KEY)

    repository = OzonAccountRepository()
    saved = repository.save("42", "client-123", "api-secret")

    db_path = storage_root / "ozon_assistant.db"
    assert saved["error"] is False
    assert db_path.exists()
    assert repository._resolved_db_name() == str(db_path)
    assert "api-secret" not in db_path.read_bytes().decode("utf-8", errors="ignore")

    restarted = OzonAccountRepository()
    assert restarted.get("42") == {
        "client_id": "client-123",
        "api_key": "api-secret",
    }


def test_wrong_master_key_cannot_decrypt_or_mutate_persisted_credentials(monkeypatch, tmp_path):
    storage_root = tmp_path / "persistent"
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(storage_root))

    original = OzonAccountRepository(master_key=MASTER_KEY)
    assert original.save("42", "client-123", "api-secret")["error"] is False
    db_path = storage_root / "ozon_assistant.db"
    ciphertext_before = _ciphertext(db_path)

    wrong_key_repository = OzonAccountRepository(master_key=WRONG_KEY)
    assert wrong_key_repository.get("42") is None
    assert wrong_key_repository.status("42") == {
        "error": True,
        "code": "OZON_ACCOUNT_MASTER_KEY_MISMATCH",
        "connected": False,
        "account_count": 1,
    }
    assert _ciphertext(db_path) == ciphertext_before

    restored = OzonAccountRepository(master_key=MASTER_KEY)
    assert restored.get("42")["api_key"] == "api-secret"


def test_explicit_database_path_is_not_rebased_by_runtime_root(monkeypatch, tmp_path):
    storage_root = tmp_path / "persistent"
    explicit_db = tmp_path / "explicit" / "credentials.db"
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(storage_root))

    repository = OzonAccountRepository(master_key=MASTER_KEY, db_name=str(explicit_db))
    assert repository.save("42", "client-123", "api-secret")["error"] is False

    assert explicit_db.exists()
    assert repository._resolved_db_name() == str(explicit_db)
    assert not (storage_root / "credentials.db").exists()


def test_no_storage_root_preserves_legacy_default_path(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_ASSISTANT_STORAGE_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    repository = OzonAccountRepository(master_key=MASTER_KEY)
    assert repository.save("42", "client-123", "api-secret")["error"] is False

    assert (tmp_path / "ozon_assistant.db").exists()


def test_missing_master_key_only_errors_when_an_encrypted_store_exists(tmp_path):
    db_path = tmp_path / "credentials.db"
    repository = OzonAccountRepository(master_key=MASTER_KEY, db_name=str(db_path))
    assert repository.save("42", "client-123", "api-secret")["error"] is False

    missing_key = OzonAccountRepository(master_key=" ", db_name=str(db_path))

    assert missing_key.status("42") == {
        "error": True,
        "code": "OZON_ACCOUNT_MASTER_KEY_UNAVAILABLE",
        "connected": False,
        "account_count": 1,
    }
    assert missing_key.status("new-user") == {
        "error": False,
        "connected": False,
        "client_id_masked": None,
        "account_count": 0,
    }
