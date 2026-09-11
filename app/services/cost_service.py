import sqlite3

from services.base_cost_service import ProductCostService as BaseProductCostService
from services.tenant_storage import ensure_storage_parent, tenant_storage_path


DB_NAME = "ozon_assistant.db"


class ProductCostService(BaseProductCostService):
    """Tenant-local cost storage while preserving the legacy service contract."""

    def get_connection(self):
        conn = sqlite3.connect(ensure_storage_parent(tenant_storage_path(DB_NAME)))
        self._ensure_schema(conn)
        return conn

    @staticmethod
    def _ensure_schema(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE,
                sku TEXT,
                offer_id TEXT,
                cost_price REAL NOT NULL,
                currency TEXT DEFAULT 'RUB',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_cost_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                sku TEXT,
                offer_id TEXT,
                cost_price REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'RUB',
                effective_from TEXT NOT NULL,
                effective_through TEXT,
                source TEXT NOT NULL DEFAULT 'SELLER_CONFIRMED',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, effective_from)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_cost_switch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                sku TEXT,
                offer_id TEXT,
                cost_price REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'RUB',
                effective_from TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'SELLER_CONFIRMED_BOT',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, effective_from)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_cost_history_sku_effective
            ON product_cost_history (sku, effective_from)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_cost_history_offer_effective
            ON product_cost_history (offer_id, effective_from)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_cost_switch_sku_effective
            ON product_cost_switch_history (sku, effective_from)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_cost_switch_offer_effective
            ON product_cost_switch_history (offer_id, effective_from)
            """
        )
        conn.commit()
