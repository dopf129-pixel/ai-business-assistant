import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


DB_NAME = "ozon_assistant.db"
_STORAGE_ROOT_ENV = "AI_ASSISTANT_STORAGE_ROOT"
_STORE_SCOPE_SEPARATOR = "::ozon::"


def make_store_tenant_scope(user_id, client_id):
    user_key = str(user_id or "").strip()
    client_key = str(client_id or "").strip()
    if not user_key or not client_key:
        return user_key or None
    return user_key + _STORE_SCOPE_SEPARATOR + client_key


def split_store_tenant_scope(value):
    text = str(value or "").strip()
    if _STORE_SCOPE_SEPARATOR not in text:
        return text or None, None
    user_id, client_id = text.split(_STORE_SCOPE_SEPARATOR, 1)
    return (user_id or None), (client_id or None)


class OzonAccountRepository:
    def __init__(self, master_key=None, db_name=DB_NAME):
        self.db_name = db_name
        self.master_key = master_key or os.getenv("OZON_CREDENTIAL_MASTER_KEY")
        self._create_table()

    def _resolved_db_name(self):
        path = Path(str(self.db_name))
        if path.is_absolute() or str(self.db_name) != DB_NAME:
            return str(path)
        storage_root = str(os.getenv(_STORAGE_ROOT_ENV, "") or "").strip()
        if storage_root:
            return str(Path(storage_root) / path)
        return str(path)

    def _connection(self):
        db_path = Path(self._resolved_db_name())
        parent = db_path.parent
        if parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(db_path))

    def _fernet(self):
        key = str(self.master_key or "").strip().encode("utf-8")
        if not key:
            return None
        try:
            return Fernet(key)
        except Exception:
            return None

    def _create_table(self):
        conn = self._connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ozon_accounts (
                    telegram_user_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ozon_store_accounts (
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
            # Legacy rows are copied for a safe in-place upgrade. delete() also
            # removes the matching legacy row so a disconnected legacy account
            # cannot be resurrected by this migration on the next process start.
            conn.execute(
                """
                INSERT OR IGNORE INTO ozon_store_accounts (
                    telegram_user_id, client_id, api_key_encrypted, is_active,
                    connected_at, updated_at
                )
                SELECT telegram_user_id, client_id, api_key_encrypted, 1,
                       connected_at, updated_at
                FROM ozon_accounts
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save(self, user_id, client_id, api_key):
        user_key = str(user_id or "").strip()
        client_key = str(client_id or "").strip()
        secret = str(api_key or "").strip()
        fernet = self._fernet()
        if not user_key or not client_key or not secret or fernet is None:
            return {"error": True, "code": "OZON_ACCOUNT_STORAGE_UNAVAILABLE"}
        encrypted = fernet.encrypt(secret.encode("utf-8")).decode("utf-8")
        conn = self._connection()
        try:
            conn.execute(
                "UPDATE ozon_store_accounts SET is_active = 0 WHERE telegram_user_id = ?",
                (user_key,),
            )
            conn.execute(
                """
                INSERT INTO ozon_store_accounts (
                    telegram_user_id, client_id, api_key_encrypted, is_active
                ) VALUES (?, ?, ?, 1)
                ON CONFLICT(telegram_user_id, client_id) DO UPDATE SET
                    api_key_encrypted = excluded.api_key_encrypted,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_key, client_key, encrypted),
            )
            conn.commit()
        finally:
            conn.close()
        return {"error": False, "client_id": client_key, "active": True}

    def list_accounts(self, user_id):
        user_key, _ = split_store_tenant_scope(user_id)
        if not user_key:
            return []
        conn = self._connection()
        try:
            rows = conn.execute(
                """
                SELECT client_id, is_active
                FROM ozon_store_accounts
                WHERE telegram_user_id = ?
                ORDER BY is_active DESC, connected_at ASC, client_id ASC
                """,
                (user_key,),
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "client_id": str(row[0]),
                "client_id_masked": self._mask_client_id(row[0]),
                "active": bool(row[1]),
            }
            for row in rows
        ]

    def active_client_id(self, user_id):
        user_key, scoped_client = split_store_tenant_scope(user_id)
        if scoped_client:
            return scoped_client
        if not user_key:
            return None
        conn = self._connection()
        try:
            row = conn.execute(
                """
                SELECT client_id FROM ozon_store_accounts
                WHERE telegram_user_id = ? AND is_active = 1
                ORDER BY updated_at DESC LIMIT 1
                """,
                (user_key,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT client_id FROM ozon_store_accounts
                    WHERE telegram_user_id = ?
                    ORDER BY connected_at ASC LIMIT 1
                    """,
                    (user_key,),
                ).fetchone()
        finally:
            conn.close()
        return str(row[0]) if row else None

    def select(self, user_id, client_id):
        user_key, _ = split_store_tenant_scope(user_id)
        client_key = str(client_id or "").strip()
        if not user_key or not client_key:
            return {"error": True, "selected": False}
        conn = self._connection()
        try:
            exists = conn.execute(
                "SELECT 1 FROM ozon_store_accounts WHERE telegram_user_id = ? AND client_id = ?",
                (user_key, client_key),
            ).fetchone()
            if exists is None:
                return {"error": False, "selected": False}
            conn.execute(
                "UPDATE ozon_store_accounts SET is_active = 0 WHERE telegram_user_id = ?",
                (user_key,),
            )
            conn.execute(
                """
                UPDATE ozon_store_accounts
                SET is_active = 1, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ? AND client_id = ?
                """,
                (user_key, client_key),
            )
            conn.commit()
        finally:
            conn.close()
        return {"error": False, "selected": True, "client_id": client_key}

    def get(self, user_id, client_id=None):
        user_key, scoped_client = split_store_tenant_scope(user_id)
        client_key = str(client_id or scoped_client or self.active_client_id(user_key) or "").strip()
        fernet = self._fernet()
        if not user_key or not client_key or fernet is None:
            return None
        conn = self._connection()
        try:
            row = conn.execute(
                """
                SELECT client_id, api_key_encrypted
                FROM ozon_store_accounts
                WHERE telegram_user_id = ? AND client_id = ?
                """,
                (user_key, client_key),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            api_key = fernet.decrypt(str(row[1]).encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError):
            return None
        return {"client_id": str(row[0]), "api_key": api_key}

    def status(self, user_id):
        account = self.get(user_id)
        accounts = self.list_accounts(user_id)
        if not account:
            return {"connected": False, "client_id_masked": None, "account_count": len(accounts)}
        client_id = str(account.get("client_id") or "")
        return {
            "connected": True,
            "client_id_masked": self._mask_client_id(client_id),
            "client_id": client_id,
            "account_count": len(accounts),
        }

    def delete(self, user_id, client_id=None):
        user_key, scoped_client = split_store_tenant_scope(user_id)
        client_key = str(client_id or scoped_client or self.active_client_id(user_key) or "").strip()
        if not user_key or not client_key:
            return {"error": True, "deleted": False}
        conn = self._connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ozon_store_accounts WHERE telegram_user_id = ? AND client_id = ?",
                (user_key, client_key),
            )
            deleted = cursor.rowcount > 0
            if deleted:
                # A migrated legacy credential must be deleted at the source as
                # well, otherwise _create_table() would import it again later.
                conn.execute(
                    "DELETE FROM ozon_accounts WHERE telegram_user_id = ? AND client_id = ?",
                    (user_key, client_key),
                )
                row = conn.execute(
                    """
                    SELECT client_id FROM ozon_store_accounts
                    WHERE telegram_user_id = ?
                    ORDER BY connected_at ASC LIMIT 1
                    """,
                    (user_key,),
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE ozon_store_accounts SET is_active = (client_id = ?) WHERE telegram_user_id = ?",
                        (str(row[0]), user_key),
                    )
            conn.commit()
        finally:
            conn.close()
        return {"error": False, "deleted": deleted}

    @staticmethod
    def _mask_client_id(client_id):
        text = str(client_id or "").strip()
        if len(text) <= 3:
            return "***" if text else None
        return text[:3] + "***"
