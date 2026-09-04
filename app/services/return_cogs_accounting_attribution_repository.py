from datetime import date, datetime
import sqlite3


DB_NAME = "ozon_assistant.db"


class ReturnCogsAccountingAttributionRepository:
    """Append-only seller accounting evidence for return COGS attribution."""

    COMPENSATION_STATES = {
        "NO_COMPENSATION_CONFIRMED",
        "COMPENSATION_PRESENT",
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
            CREATE TABLE IF NOT EXISTS return_cogs_accounting_attribution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                return_id TEXT NOT NULL,
                posting_number TEXT NOT NULL,
                sku TEXT NOT NULL,
                recovery_accounting_date TEXT NOT NULL,
                compensation_state TEXT NOT NULL,
                compensation_double_count_clear INTEGER NOT NULL,
                confirmed_on TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'SELLER_ACCOUNTING_CONFIRMED',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(return_id, confirmed_on)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_return_cogs_accounting_identity
            ON return_cogs_accounting_attribution_history (
                return_id,
                posting_number,
                sku,
                confirmed_on
            )
            """
        )
        conn.commit()
        conn.close()

    def record_attribution(
        self,
        return_id,
        posting_number,
        sku,
        recovery_accounting_date,
        compensation_state,
        compensation_double_count_clear,
        confirmed_on,
        source="SELLER_ACCOUNTING_CONFIRMED",
    ):
        return_key = self._text(return_id)
        posting_key = self._text(posting_number)
        sku_key = self._text(sku)
        accounting_date = self._date(recovery_accounting_date)
        state = self._text(compensation_state).upper()
        clear = self._bool(compensation_double_count_clear)
        confirmation_date = self._date(confirmed_on)
        source_key = self._text(source)

        if (
            not return_key
            or not posting_key
            or not sku_key
            or accounting_date is None
            or state not in self.COMPENSATION_STATES
            or clear is None
            or confirmation_date is None
            or not source_key
        ):
            return {
                "error": True,
                "code": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_INPUT_INVALID",
                "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_RECORD_UNAVAILABLE",
            }

        # Explicit no-compensation evidence is itself the no-double-count proof.
        # A contradictory false marker is rejected rather than normalized.
        if state == "NO_COMPENSATION_CONFIRMED" and clear is not True:
            return {
                "error": True,
                "code": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_INPUT_INVALID",
                "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_RECORD_UNAVAILABLE",
            }

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO return_cogs_accounting_attribution_history (
                    return_id,
                    posting_number,
                    sku,
                    recovery_accounting_date,
                    compensation_state,
                    compensation_double_count_clear,
                    confirmed_on,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    return_key,
                    posting_key,
                    sku_key,
                    accounting_date.isoformat(),
                    state,
                    1 if clear else 0,
                    confirmation_date.isoformat(),
                    source_key,
                ),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            return {
                "error": True,
                "code": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_VERSION_CONFLICT",
                "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_RECORD_UNAVAILABLE",
                "return_id": return_key,
                "confirmed_on": confirmation_date.isoformat(),
            }

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {
            "error": False,
            "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_RECORDED",
            "history_id": row_id,
            "return_id": return_key,
            "posting_number": posting_key,
            "sku": sku_key,
            "recovery_accounting_date": accounting_date.isoformat(),
            "compensation_state": state,
            "compensation_double_count_clear": clear,
            "confirmed_on": confirmation_date.isoformat(),
            "source": source_key,
            "accounting_attribution_evidence": True,
        }

    def get_latest_attribution(self, return_id, posting_number, sku):
        return_key = self._text(return_id)
        posting_key = self._text(posting_number)
        sku_key = self._text(sku)
        if not return_key or not posting_key or not sku_key:
            return self._unavailable(
                "RETURN_COGS_ACCOUNTING_ATTRIBUTION_QUERY_INVALID"
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
                recovery_accounting_date,
                compensation_state,
                compensation_double_count_clear,
                confirmed_on,
                source,
                recorded_at
            FROM return_cogs_accounting_attribution_history
            WHERE return_id = ?
            ORDER BY confirmed_on DESC, id DESC
            """,
            (return_key,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "error": False,
                "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_MISSING",
                "return_id": return_key,
                "accounting_attribution_confirmed": False,
                "recovery_accounting_date": None,
                "compensation_state": None,
                "compensation_double_count_clear": None,
                "confirmed_on": None,
                "source": None,
            }

        if any(
            str(row[2]) != posting_key or str(row[3]) != sku_key
            for row in rows
        ):
            return {
                "error": False,
                "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_IDENTITY_CONFLICT",
                "return_id": return_key,
                "accounting_attribution_confirmed": False,
                "recovery_accounting_date": None,
                "compensation_state": None,
                "compensation_double_count_clear": None,
                "confirmed_on": None,
                "source": None,
            }

        row = rows[0]
        accounting_date = self._date(row[4])
        state = self._text(row[5]).upper()
        clear = self._db_bool(row[6])
        confirmation_date = self._date(row[7])
        source_key = self._text(row[8])
        if (
            accounting_date is None
            or state not in self.COMPENSATION_STATES
            or clear is None
            or confirmation_date is None
            or not source_key
            or (state == "NO_COMPENSATION_CONFIRMED" and clear is not True)
        ):
            return self._unavailable(
                "RETURN_COGS_ACCOUNTING_ATTRIBUTION_ROW_INVALID"
            )

        return {
            "error": False,
            "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
            "history_id": row[0],
            "return_id": str(row[1]),
            "posting_number": str(row[2]),
            "sku": str(row[3]),
            "recovery_accounting_date": accounting_date.isoformat(),
            "compensation_state": state,
            "compensation_double_count_clear": clear,
            "confirmed_on": confirmation_date.isoformat(),
            "source": source_key,
            "recorded_at": row[9],
            "accounting_attribution_confirmed": True,
        }

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bool(value):
        return value if isinstance(value, bool) else None

    @staticmethod
    def _db_bool(value):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_UNAVAILABLE",
            "accounting_attribution_confirmed": False,
            "recovery_accounting_date": None,
            "compensation_state": None,
            "compensation_double_count_clear": None,
            "confirmed_on": None,
            "source": None,
        }
