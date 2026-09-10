import os
import sqlite3

from cryptography.fernet import Fernet, InvalidToken


DB_NAME = "ozon_assistant.db"


class OzonAccountRepository:
    def __init__(self, master_key=None, db_name=DB_NAME):
        self.db_name = db_name
        self.master_key = master_key or os.getenv("OZON_CREDENTIAL_MASTER_KEY")
        self._create_table()

    def _connection(self):
        return sqlite3.connect(self.db_name)

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
            conn.commit()
        finally:
            conn.close()

    def save(self, user_id, client_id, api_key):
        user_key = str(user_id or "").strip()
        client_key = str(client_id or "").strip()
        secret = str(api_key or "").strip()
        fernet = self._fernet()
        if not user_key or not client_key or not secret or fernet is None:
            return {
                "error": True,
                "code": "OZON_ACCOUNT_STORAGE_UNAVAILABLE",
            }

        encrypted = fernet.encrypt(secret.encode("utf-8")).decode("utf-8")
        conn = self._connection()
        try:
            conn.execute(
                """
                INSERT INTO ozon_accounts (
                    telegram_user_id,
                    client_id,
                    api_key_encrypted
                ) VALUES (?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    client_id = excluded.client_id,
                    api_key_encrypted = excluded.api_key_encrypted,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_key, client_key, encrypted),
            )
            conn.commit()
        finally:
            conn.close()
        return {"error": False, "client_id": client_key}

    def get(self, user_id):
        user_key = str(user_id or "").strip()
        fernet = self._fernet()
        if not user_key or fernet is None:
            return None
        conn = self._connection()
        try:
            row = conn.execute(
                """
                SELECT client_id, api_key_encrypted
                FROM ozon_accounts
                WHERE telegram_user_id = ?
                """,
                (user_key,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            api_key = fernet.decrypt(str(row[1]).encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError):
            return None
        return {
            "client_id": str(row[0]),
            "api_key": api_key,
        }

    def status(self, user_id):
        account = self.get(user_id)
        if not account:
            return {
                "connected": False,
                "client_id_masked": None,
            }
        client_id = str(account.get("client_id") or "")
        masked = self._mask_client_id(client_id)
        return {
            "connected": True,
            "client_id_masked": masked,
        }

    def delete(self, user_id):
        user_key = str(user_id or "").strip()
        if not user_key:
            return {"error": True, "deleted": False}
        conn = self._connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ozon_accounts WHERE telegram_user_id = ?",
                (user_key,),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
        finally:
            conn.close()
        return {"error": False, "deleted": deleted}

    @staticmethod
    def _mask_client_id(client_id):
        text = str(client_id or "").strip()
        if len(text) <= 3:
            return "***" if text else None
        return text[:3] + "***"
