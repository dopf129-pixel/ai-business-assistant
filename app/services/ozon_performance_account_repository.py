from services.ozon_account_repository import OzonAccountRepository, split_store_tenant_scope


class OzonPerformanceAccountRepository(OzonAccountRepository):
    """Encrypted Performance API credentials scoped to one seller store."""

    def _create_table(self):
        super()._create_table()
        conn = self._connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ozon_performance_accounts (
                    telegram_user_id TEXT NOT NULL,
                    seller_client_id TEXT NOT NULL,
                    performance_client_id TEXT NOT NULL,
                    client_secret_encrypted TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_user_id, seller_client_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_performance(self, user_id, performance_client_id, client_secret):
        user_key, seller_client = split_store_tenant_scope(user_id)
        seller_client = seller_client or self.active_client_id(user_key)
        performance_client = str(performance_client_id or "").strip()
        secret = str(client_secret or "").strip()
        fernet = self._fernet()
        if not user_key or not seller_client or not performance_client or not secret or fernet is None:
            return {"error": True, "code": "OZON_PERFORMANCE_STORAGE_UNAVAILABLE"}
        encrypted = fernet.encrypt(secret.encode("utf-8")).decode("utf-8")
        conn = self._connection()
        try:
            conn.execute(
                """
                INSERT INTO ozon_performance_accounts (
                    telegram_user_id, seller_client_id, performance_client_id,
                    client_secret_encrypted
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id, seller_client_id) DO UPDATE SET
                    performance_client_id = excluded.performance_client_id,
                    client_secret_encrypted = excluded.client_secret_encrypted,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_key, seller_client, performance_client, encrypted),
            )
            conn.commit()
        finally:
            conn.close()
        return {"error": False, "performance_client_id": performance_client}

    def get_performance(self, user_id):
        user_key, seller_client = split_store_tenant_scope(user_id)
        seller_client = seller_client or self.active_client_id(user_key)
        fernet = self._fernet()
        if not user_key or not seller_client or fernet is None:
            return None
        conn = self._connection()
        try:
            row = conn.execute(
                """
                SELECT performance_client_id, client_secret_encrypted
                FROM ozon_performance_accounts
                WHERE telegram_user_id = ? AND seller_client_id = ?
                """,
                (user_key, seller_client),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            secret = fernet.decrypt(str(row[1]).encode("utf-8")).decode("utf-8")
        except Exception:
            return None
        return {"client_id": str(row[0]), "client_secret": secret}
