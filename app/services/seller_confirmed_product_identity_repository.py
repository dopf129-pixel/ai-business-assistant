from services.cost_service import ProductCostService


class SellerConfirmedProductIdentityRepository:
    """Tenant-local seller authority for legacy finance SKU aliases.

    The mapping is identity evidence only. It never stores a cost and never writes
    to Ozon. Historical/effective cost services remain authoritative for the
    monetary value used by Period Profit.
    """

    TABLE = "seller_confirmed_product_identity_mapping"

    def __init__(self, cost_service=None):
        self.cost_service = cost_service or ProductCostService()

    def record_mapping(
        self,
        finance_sku,
        current_product_id,
        current_sku,
        current_offer_id=None,
        source="SELLER_CONFIRMED_BOT_TEXT",
    ):
        finance_key = self._text(finance_sku)
        product_key = self._text(current_product_id)
        current_sku_key = self._text(current_sku)
        offer_key = self._text(current_offer_id)
        source_key = self._text(source)
        if (
            not finance_key
            or not product_key
            or not current_sku_key
            or finance_key == current_sku_key
            or not source_key
        ):
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_INPUT_INVALID")

        conn = self._connection()
        if conn is None:
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_STORAGE_UNAVAILABLE")
        try:
            self._ensure_schema(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_product_id, current_sku, current_offer_id, source "
                f"FROM {self.TABLE} WHERE finance_sku = ?",
                (finance_key,),
            )
            row = cursor.fetchone()
            if row is not None:
                existing = (
                    self._text(row[0]),
                    self._text(row[1]),
                    self._text(row[2]),
                )
                requested = (product_key, current_sku_key, offer_key)
                conn.close()
                if existing == requested:
                    return {
                        "error": False,
                        "status": "SELLER_PRODUCT_IDENTITY_MAPPING_ALREADY_RECORDED",
                        "finance_sku": finance_key,
                        "current_product_id": product_key,
                        "current_sku": current_sku_key,
                        "current_offer_id": offer_key or None,
                        "seller_confirmed": True,
                        "read_only_ozon": True,
                        "executed": False,
                    }
                return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_CONFLICT")

            cursor.execute(
                f"""
                INSERT INTO {self.TABLE} (
                    finance_sku,
                    current_product_id,
                    current_sku,
                    current_offer_id,
                    source
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    finance_key,
                    product_key,
                    current_sku_key,
                    offer_key or None,
                    source_key,
                ),
            )
            mapping_id = cursor.lastrowid
            conn.commit()
            conn.close()
        except Exception:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_STORAGE_UNAVAILABLE")

        return {
            "error": False,
            "status": "SELLER_PRODUCT_IDENTITY_MAPPING_RECORDED",
            "mapping_id": mapping_id,
            "finance_sku": finance_key,
            "current_product_id": product_key,
            "current_sku": current_sku_key,
            "current_offer_id": offer_key or None,
            "source": source_key,
            "seller_confirmed": True,
            "read_only_ozon": True,
            "executed": True,
        }

    def get_mapping(self, finance_sku):
        finance_key = self._text(finance_sku)
        if not finance_key:
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_QUERY_INVALID")

        conn = self._connection()
        if conn is None:
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_STORAGE_UNAVAILABLE")
        try:
            self._ensure_schema(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, finance_sku, current_product_id, current_sku, "
                "current_offer_id, source, confirmed_at "
                f"FROM {self.TABLE} WHERE finance_sku = ?",
                (finance_key,),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_STORAGE_UNAVAILABLE")

        if not rows:
            return {
                "error": False,
                "status": "SELLER_PRODUCT_IDENTITY_MAPPING_MISSING",
                "mapping_confirmed": False,
                "finance_sku": finance_key,
                "read_only_ozon": True,
                "executed": False,
            }
        if len(rows) != 1:
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_AMBIGUOUS")

        row = rows[0]
        product_id = self._text(row[2])
        current_sku = self._text(row[3])
        offer_id = self._text(row[4])
        source = self._text(row[5])
        if (
            self._text(row[1]) != finance_key
            or not product_id
            or not current_sku
            or current_sku == finance_key
            or not source
        ):
            return self._error("SELLER_PRODUCT_IDENTITY_MAPPING_ROW_INVALID")

        return {
            "error": False,
            "status": "SELLER_PRODUCT_IDENTITY_MAPPING_READY",
            "mapping_id": row[0],
            "finance_sku": finance_key,
            "current_product_id": product_id,
            "current_sku": current_sku,
            "current_offer_id": offer_id or None,
            "source": source,
            "confirmed_at": row[6],
            "mapping_confirmed": True,
            "seller_confirmed": True,
            "read_only_ozon": True,
            "executed": False,
        }

    def _connection(self):
        getter = getattr(self.cost_service, "get_connection", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:
            return None

    @classmethod
    def _ensure_schema(cls, conn):
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finance_sku TEXT NOT NULL UNIQUE,
                current_product_id TEXT NOT NULL,
                current_sku TEXT NOT NULL,
                current_offer_id TEXT,
                source TEXT NOT NULL DEFAULT 'SELLER_CONFIRMED_BOT_TEXT',
                confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{cls.TABLE}_current_sku "
            f"ON {cls.TABLE} (current_sku)"
        )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{cls.TABLE}_product_id "
            f"ON {cls.TABLE} (current_product_id)"
        )
        conn.commit()

    @staticmethod
    def _text(value):
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": str(code),
            "status": "SELLER_PRODUCT_IDENTITY_MAPPING_UNAVAILABLE",
            "seller_confirmed": False,
            "read_only_ozon": True,
            "executed": False,
        }
