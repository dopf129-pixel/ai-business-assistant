from datetime import date, datetime
from math import isfinite
import sqlite3


DB_NAME = "ozon_assistant.db"


class ProductCostService:

    def __init__(self):

        self.create_table()

    def get_connection(self):

        return sqlite3.connect(DB_NAME)

    def create_table(self):

        conn = self.get_connection()
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

                source TEXT NOT NULL DEFAULT 'SELLER_CONFIRMED',

                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(product_id, effective_from)
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_product_cost_history_sku_effective

            ON product_cost_history (
                sku,
                effective_from
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_product_cost_history_offer_effective

            ON product_cost_history (
                offer_id,
                effective_from
            )
            """
        )

        conn.commit()
        conn.close()

    def set_cost(
        self,
        product_id,
        sku,
        offer_id,
        cost_price,
        currency="RUB"
    ):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO product_costs (

                product_id,
                sku,
                offer_id,
                cost_price,
                currency

            )

            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(product_id)

            DO UPDATE SET

                sku = excluded.sku,
                offer_id = excluded.offer_id,
                cost_price = excluded.cost_price,
                currency = excluded.currency,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(product_id),
                str(sku),
                str(offer_id),
                float(cost_price),
                currency
            )
        )

        conn.commit()
        conn.close()

    def record_historical_cost(
        self,
        product_id,
        sku,
        offer_id,
        cost_price,
        effective_from,
        currency="RUB",
        source="SELLER_CONFIRMED",
    ):
        product_key = self._text(
            product_id
        )
        sku_key = self._text(
            sku
        )
        offer_key = self._text(
            offer_id
        )
        cost = self._cost_number(
            cost_price
        )
        effective_date = self._date(
            effective_from
        )
        currency_key = self._text(
            currency
        )
        source_key = self._text(
            source
        )

        if (
            not product_key
            or (
                not sku_key
                and not offer_key
            )
            or cost is None
            or effective_date is None
            or not currency_key
            or not source_key
        ):
            return {
                "error": True,
                "code": (
                    "PRODUCT_COST_HISTORY_INPUT_INVALID"
                ),
                "status": (
                    "PRODUCT_COST_HISTORY_RECORD_UNAVAILABLE"
                ),
            }

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO product_cost_history (

                    product_id,
                    sku,
                    offer_id,
                    cost_price,
                    currency,
                    effective_from,
                    source

                )

                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_key,
                    sku_key or None,
                    offer_key or None,
                    cost,
                    currency_key,
                    effective_date.isoformat(),
                    source_key,
                )
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            return {
                "error": True,
                "code": (
                    "PRODUCT_COST_HISTORY_VERSION_CONFLICT"
                ),
                "status": (
                    "PRODUCT_COST_HISTORY_RECORD_UNAVAILABLE"
                ),
                "product_id": product_key,
                "effective_from": (
                    effective_date.isoformat()
                ),
            }

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "error": False,
            "status": (
                "PRODUCT_COST_HISTORY_RECORDED"
            ),
            "history_id": row_id,
            "product_id": product_key,
            "sku": sku_key or None,
            "offer_id": offer_key or None,
            "cost_price": round(
                cost,
                2,
            ),
            "currency": currency_key,
            "effective_from": (
                effective_date.isoformat()
            ),
            "source": source_key,
            "historical_evidence": True,
        }

    def get_historical_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        effective_date = self._date(
            at_date
        )
        product_key = self._text(
            product_id
        )
        sku_key = self._text(
            sku
        )
        offer_key = self._text(
            offer_id
        )

        if (
            effective_date is None
            or not (
                product_key
                or sku_key
                or offer_key
            )
        ):
            return self._historical_unavailable(
                "PRODUCT_COST_HISTORY_QUERY_INVALID"
            )

        clauses = []
        values = []

        if product_key:
            clauses.append(
                "product_id = ?"
            )
            values.append(
                product_key
            )
        else:
            if sku_key:
                clauses.append(
                    "sku = ?"
                )
                values.append(
                    sku_key
                )
            if offer_key:
                clauses.append(
                    "offer_id = ?"
                )
                values.append(
                    offer_key
                )

        where_identifiers = (
            " OR ".join(
                clauses
            )
        )

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT
                id,
                product_id,
                sku,
                offer_id,
                cost_price,
                currency,
                effective_from,
                source,
                recorded_at

            FROM product_cost_history

            WHERE
                effective_from <= ?
                AND (
                    {where_identifiers}
                )

            ORDER BY
                effective_from DESC,
                id DESC
            """,
            (
                effective_date.isoformat(),
                *values,
            )
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "error": False,
                "status": (
                    "PRODUCT_COST_HISTORY_MISSING"
                ),
                "at_date": (
                    effective_date.isoformat()
                ),
                "historical_cost_confirmed": False,
                "cost_price": None,
                "effective_from": None,
                "source": None,
            }

        latest_by_product = {}
        for row in rows:
            row_product_id = str(
                row[1]
            )
            if (
                row_product_id
                not in latest_by_product
            ):
                latest_by_product[
                    row_product_id
                ] = row

        if len(
            latest_by_product
        ) != 1:
            return {
                "error": False,
                "status": (
                    "PRODUCT_COST_HISTORY_AMBIGUOUS"
                ),
                "at_date": (
                    effective_date.isoformat()
                ),
                "historical_cost_confirmed": False,
                "cost_price": None,
                "effective_from": None,
                "source": None,
                "candidate_product_ids": sorted(
                    latest_by_product
                ),
            }

        row = next(
            iter(
                latest_by_product.values()
            )
        )
        cost = self._cost_number(
            row[4]
        )
        row_effective = self._date(
            row[6]
        )

        if (
            cost is None
            or row_effective is None
            or row_effective
            > effective_date
        ):
            return self._historical_unavailable(
                "PRODUCT_COST_HISTORY_ROW_INVALID"
            )

        return {
            "error": False,
            "status": (
                "PRODUCT_COST_HISTORY_READY"
            ),
            "history_id": row[0],
            "product_id": str(
                row[1]
            ),
            "sku": (
                str(row[2])
                if row[2] is not None
                else None
            ),
            "offer_id": (
                str(row[3])
                if row[3] is not None
                else None
            ),
            "cost_price": round(
                cost,
                2,
            ),
            "currency": str(
                row[5]
            ),
            "effective_from": (
                row_effective.isoformat()
            ),
            "source": str(
                row[7]
            ),
            "recorded_at": row[8],
            "at_date": (
                effective_date.isoformat()
            ),
            "historical_cost_confirmed": True,
        }

    def get_cost(
        self,
        product_id
    ):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT

                product_id,
                sku,
                offer_id,
                cost_price,
                currency,
                updated_at

            FROM product_costs

            WHERE product_id = ?
            """,
            (
                str(product_id),
            )
        )

        row = cursor.fetchone()

        conn.close()

        return row

    def get_all_costs(self):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT

                product_id,
                sku,
                offer_id,
                cost_price,
                currency,
                updated_at

            FROM product_costs

            ORDER BY offer_id
            """
        )

        rows = cursor.fetchall()

        conn.close()

        return rows

    def delete_cost(
        self,
        product_id
    ):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM product_costs
            WHERE product_id = ?
            """,
            (
                str(product_id),
            )
        )

        conn.commit()
        conn.close()

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        return str(
            value
        ).strip()

    @staticmethod
    def _date(value):
        if isinstance(
            value,
            datetime,
        ):
            return value.date()
        if isinstance(
            value,
            date,
        ):
            return value

        try:
            return date.fromisoformat(
                str(value)
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _cost_number(value):
        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if (
            not isfinite(
                number
            )
            or number < 0
        ):
            return None

        return number

    @staticmethod
    def _historical_unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "PRODUCT_COST_HISTORY_UNAVAILABLE"
            ),
            "historical_cost_confirmed": False,
            "cost_price": None,
            "effective_from": None,
            "source": None,
        }
