from datetime import date
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

    def get_historical_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        """Recover pre-timeline seller costs without inventing retroactive history.

        Older installations stored an explicitly seller-entered cost only in the
        mutable ``product_costs`` row.  Its ``updated_at`` value is still trustworthy
        evidence that the value was present from that date forward.  We may therefore
        use the current row for dates on/after ``updated_at`` and no later than today,
        but never for an earlier sale.  Explicit history always wins.
        """
        historical = super().get_historical_cost_evidence(
            at_date,
            product_id=product_id,
            sku=sku,
            offer_id=offer_id,
        )
        if (
            not isinstance(historical, dict)
            or historical.get("error") is True
            or historical.get("status") != "PRODUCT_COST_HISTORY_MISSING"
        ):
            return historical

        target = self._date(at_date)
        if target is None or target > date.today():
            return historical

        product_key = self._text(product_id)
        sku_key = self._text(sku)
        offer_key = self._text(offer_id)
        clauses = []
        values = []
        if product_key:
            clauses.append("product_id = ?")
            values.append(product_key)
        else:
            if sku_key:
                clauses.append("sku = ?")
                values.append(sku_key)
            if offer_key:
                clauses.append("offer_id = ?")
                values.append(offer_key)
        if not clauses:
            return historical

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, product_id, sku, offer_id, cost_price, currency, updated_at
                FROM product_costs
                WHERE """ + " OR ".join(clauses) + " ORDER BY id ASC",
                tuple(values),
            )
            rows = cursor.fetchall()
        except Exception:
            return historical
        finally:
            conn.close()

        by_product = {}
        for row in rows:
            if isinstance(row, (tuple, list)) and len(row) >= 7:
                by_product.setdefault(str(row[1]), row)
        if len(by_product) != 1:
            if by_product:
                return {
                    "error": False,
                    "status": "PRODUCT_COST_HISTORY_AMBIGUOUS",
                    "at_date": target.isoformat(),
                    "historical_cost_confirmed": False,
                    "cost_price": None,
                    "effective_from": None,
                    "effective_through": None,
                    "source": None,
                    "candidate_product_ids": sorted(by_product),
                }
            return historical

        row = next(iter(by_product.values()))
        cost = self._cost_number(row[4])
        updated = self._stored_timestamp_date(row[6])
        if cost is None or updated is None or target < updated:
            return historical

        return {
            "error": False,
            "status": "PRODUCT_COST_HISTORY_READY",
            "history_id": "legacy-current:" + str(row[0]),
            "product_id": str(row[1]),
            "sku": str(row[2]) if row[2] is not None else None,
            "offer_id": str(row[3]) if row[3] is not None else None,
            "cost_price": round(cost, 2),
            "currency": str(row[5]),
            "effective_from": updated.isoformat(),
            "effective_through": date.today().isoformat(),
            "source": "SELLER_CONFIRMED_LEGACY_CURRENT_TIMESTAMP",
            "recorded_at": row[6],
            "at_date": target.isoformat(),
            "historical_cost_confirmed": True,
            "legacy_current_cost_evidence": True,
        }

    @staticmethod
    def _stored_timestamp_date(value):
        text = str(value or "").strip()
        if len(text) < 10:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
