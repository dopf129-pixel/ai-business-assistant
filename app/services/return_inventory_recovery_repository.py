from datetime import date, datetime
import sqlite3


DB_NAME = "ozon_assistant.db"


class ReturnInventoryRecoveryRepository:

    STATES = {
        "SALEABLE_RESTORED",
        "NON_SALEABLE",
    }

    def __init__(self):

        self.create_table()

    def get_connection(self):

        return sqlite3.connect(DB_NAME)

    def create_table(self):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS return_inventory_recovery_history (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                return_id TEXT NOT NULL,

                posting_number TEXT NOT NULL,

                sku TEXT NOT NULL,

                quantity INTEGER NOT NULL,

                recovery_state TEXT NOT NULL,

                confirmed_on TEXT NOT NULL,

                source TEXT NOT NULL DEFAULT 'SELLER_CONFIRMED',

                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(return_id, confirmed_on)
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_return_inventory_recovery_identity

            ON return_inventory_recovery_history (
                return_id,
                posting_number,
                sku,
                confirmed_on
            )
            """
        )

        conn.commit()
        conn.close()

    def record_recovery(
        self,
        return_id,
        posting_number,
        sku,
        quantity,
        recovery_state,
        confirmed_on,
        source="SELLER_CONFIRMED",
    ):
        return_key = self._text(
            return_id
        )
        posting_key = self._text(
            posting_number
        )
        sku_key = self._text(
            sku
        )
        count = self._quantity(
            quantity
        )
        state = self._text(
            recovery_state
        ).upper()
        confirmation_date = self._date(
            confirmed_on
        )
        source_key = self._text(
            source
        )

        if (
            not return_key
            or not posting_key
            or not sku_key
            or count is None
            or state not in self.STATES
            or confirmation_date is None
            or not source_key
        ):
            return {
                "error": True,
                "code": (
                    "RETURN_INVENTORY_RECOVERY_INPUT_INVALID"
                ),
                "status": (
                    "RETURN_INVENTORY_RECOVERY_RECORD_UNAVAILABLE"
                ),
            }

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO return_inventory_recovery_history (

                    return_id,
                    posting_number,
                    sku,
                    quantity,
                    recovery_state,
                    confirmed_on,
                    source

                )

                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    return_key,
                    posting_key,
                    sku_key,
                    count,
                    state,
                    confirmation_date.isoformat(),
                    source_key,
                )
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            return {
                "error": True,
                "code": (
                    "RETURN_INVENTORY_RECOVERY_VERSION_CONFLICT"
                ),
                "status": (
                    "RETURN_INVENTORY_RECOVERY_RECORD_UNAVAILABLE"
                ),
                "return_id": return_key,
                "confirmed_on": (
                    confirmation_date.isoformat()
                ),
            }

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "error": False,
            "status": (
                "RETURN_INVENTORY_RECOVERY_RECORDED"
            ),
            "history_id": row_id,
            "return_id": return_key,
            "posting_number": posting_key,
            "sku": sku_key,
            "quantity": count,
            "recovery_state": state,
            "confirmed_on": (
                confirmation_date.isoformat()
            ),
            "source": source_key,
            "inventory_recovery_evidence": True,
        }

    def get_latest_recovery(
        self,
        return_id,
        posting_number,
        sku,
    ):
        return_key = self._text(
            return_id
        )
        posting_key = self._text(
            posting_number
        )
        sku_key = self._text(
            sku
        )

        if (
            not return_key
            or not posting_key
            or not sku_key
        ):
            return self._unavailable(
                "RETURN_INVENTORY_RECOVERY_QUERY_INVALID"
            )

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                return_id,
                posting_number,
                sku,
                quantity,
                recovery_state,
                confirmed_on,
                source,
                recorded_at

            FROM return_inventory_recovery_history

            WHERE return_id = ?

            ORDER BY
                confirmed_on DESC,
                id DESC
            """,
            (
                return_key,
            )
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "error": False,
                "status": (
                    "RETURN_INVENTORY_RECOVERY_MISSING"
                ),
                "return_id": return_key,
                "inventory_recovery_confirmed": False,
                "recovery_state": None,
                "quantity": None,
                "confirmed_on": None,
                "source": None,
            }

        if any(
            (
                str(row[2]) != posting_key
                or str(row[3]) != sku_key
            )
            for row in rows
        ):
            return {
                "error": False,
                "status": (
                    "RETURN_INVENTORY_RECOVERY_IDENTITY_CONFLICT"
                ),
                "return_id": return_key,
                "inventory_recovery_confirmed": False,
                "recovery_state": None,
                "quantity": None,
                "confirmed_on": None,
                "source": None,
            }

        row = rows[0]
        count = self._quantity(
            row[4]
        )
        state = self._text(
            row[5]
        ).upper()
        confirmation_date = self._date(
            row[6]
        )

        if (
            count is None
            or state not in self.STATES
            or confirmation_date is None
        ):
            return self._unavailable(
                "RETURN_INVENTORY_RECOVERY_ROW_INVALID"
            )

        return {
            "error": False,
            "status": (
                "RETURN_INVENTORY_RECOVERY_READY"
            ),
            "history_id": row[0],
            "return_id": str(
                row[1]
            ),
            "posting_number": str(
                row[2]
            ),
            "sku": str(
                row[3]
            ),
            "quantity": count,
            "recovery_state": state,
            "confirmed_on": (
                confirmation_date.isoformat()
            ),
            "source": str(
                row[7]
            ),
            "recorded_at": row[8],
            "inventory_recovery_confirmed": True,
        }

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
    def _quantity(value):
        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            number = int(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        if number <= 0:
            return None

        return number

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "RETURN_INVENTORY_RECOVERY_UNAVAILABLE"
            ),
            "inventory_recovery_confirmed": False,
            "recovery_state": None,
            "quantity": None,
            "confirmed_on": None,
            "source": None,
        }
