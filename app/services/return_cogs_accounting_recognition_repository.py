from datetime import date, datetime
from math import isfinite
import sqlite3


DB_NAME = "ozon_assistant.db"


class ReturnCogsAccountingRecognitionRepository:
    """Append-only seller accounting evidence that Return COGS was booked."""

    RECOGNIZED = "COGS_RECOVERY_RECOGNIZED"
    REVOKED = "COGS_RECOVERY_RECOGNITION_REVOKED"
    STATES = {RECOGNIZED, REVOKED}

    def __init__(self):
        self.create_table()

    def get_connection(self):
        return sqlite3.connect(DB_NAME)

    def create_table(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS return_cogs_accounting_recognition_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                return_id TEXT NOT NULL,
                posting_number TEXT NOT NULL,
                sku TEXT NOT NULL,
                recovery_accounting_date TEXT NOT NULL,
                recognition_state TEXT NOT NULL,
                recognized_amount REAL,
                currency TEXT,
                confirmed_on TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'SELLER_ACCOUNTING_BOOKED',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(return_id, posting_number, sku, confirmed_on)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_return_cogs_recognition_identity
            ON return_cogs_accounting_recognition_history (
                return_id,
                posting_number,
                sku,
                confirmed_on
            )
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_return_cogs_recognition_no_update
            BEFORE UPDATE ON return_cogs_accounting_recognition_history
            BEGIN
                SELECT RAISE(ABORT, 'return_cogs_accounting_recognition_history is append-only');
            END
            """
        )
        conn.commit()
        conn.close()

    def record_recognition(
        self,
        return_id,
        posting_number,
        sku,
        recovery_accounting_date,
        recognition_state,
        recognized_amount,
        currency,
        confirmed_on,
        source="SELLER_ACCOUNTING_BOOKED",
    ):
        return_key = self._text(return_id)
        posting_key = self._text(posting_number)
        sku_key = self._text(sku)
        accounting_date = self._date(recovery_accounting_date)
        state = self._text(recognition_state).upper()
        amount = self._money(recognized_amount)
        currency_key = self._text(currency).upper()
        confirmation_date = self._date(confirmed_on)
        source_key = self._text(source)

        if (
            not return_key
            or not posting_key
            or not sku_key
            or accounting_date is None
            or state not in self.STATES
            or confirmation_date is None
            or not source_key
        ):
            return self._input_invalid()

        if state == self.RECOGNIZED:
            if amount is None or currency_key != "RUB":
                return self._input_invalid()
        else:
            if recognized_amount is not None or self._text(currency):
                return self._input_invalid()
            amount = None
            currency_key = None

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO return_cogs_accounting_recognition_history (
                    return_id,
                    posting_number,
                    sku,
                    recovery_accounting_date,
                    recognition_state,
                    recognized_amount,
                    currency,
                    confirmed_on,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    return_key,
                    posting_key,
                    sku_key,
                    accounting_date.isoformat(),
                    state,
                    amount,
                    currency_key,
                    confirmation_date.isoformat(),
                    source_key,
                ),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            return {
                "error": True,
                "code": "RETURN_COGS_ACCOUNTING_RECOGNITION_VERSION_CONFLICT",
                "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_RECORD_UNAVAILABLE",
                "return_id": return_key,
                "posting_number": posting_key,
                "sku": sku_key,
                "confirmed_on": confirmation_date.isoformat(),
            }

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {
            "error": False,
            "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_RECORDED",
            "history_id": row_id,
            "return_id": return_key,
            "posting_number": posting_key,
            "sku": sku_key,
            "recovery_accounting_date": accounting_date.isoformat(),
            "recognition_state": state,
            "recognized_amount": amount,
            "currency": currency_key,
            "confirmed_on": confirmation_date.isoformat(),
            "source": source_key,
            "accounting_recognition_evidence": True,
        }

    def get_latest_recognition(self, return_id, posting_number, sku):
        return_key = self._text(return_id)
        posting_key = self._text(posting_number)
        sku_key = self._text(sku)
        if not return_key or not posting_key or not sku_key:
            return self._unavailable(
                "RETURN_COGS_ACCOUNTING_RECOGNITION_QUERY_INVALID"
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
                recognition_state,
                recognized_amount,
                currency,
                confirmed_on,
                source,
                recorded_at
            FROM return_cogs_accounting_recognition_history
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
                "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_MISSING",
                "return_id": return_key,
                "posting_number": posting_key,
                "sku": sku_key,
                "accounting_recognition_confirmed": False,
                "recovery_accounting_date": None,
                "recognition_state": None,
                "recognized_amount": None,
                "currency": None,
                "confirmed_on": None,
                "source": None,
            }

        if any(
            str(row[2]) != posting_key or str(row[3]) != sku_key
            for row in rows
        ):
            return {
                "error": False,
                "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_IDENTITY_CONFLICT",
                "return_id": return_key,
                "posting_number": posting_key,
                "sku": sku_key,
                "accounting_recognition_confirmed": False,
                "recovery_accounting_date": None,
                "recognition_state": None,
                "recognized_amount": None,
                "currency": None,
                "confirmed_on": None,
                "source": None,
            }

        row = rows[0]
        accounting_date = self._date(row[4])
        state = self._text(row[5]).upper()
        amount = self._money(row[6])
        currency_key = self._text(row[7]).upper()
        confirmation_date = self._date(row[8])
        source_key = self._text(row[9])

        if (
            accounting_date is None
            or state not in self.STATES
            or confirmation_date is None
            or not source_key
        ):
            return self._unavailable(
                "RETURN_COGS_ACCOUNTING_RECOGNITION_ROW_INVALID"
            )

        confirmed = state == self.RECOGNIZED
        if confirmed and (amount is None or currency_key != "RUB"):
            return self._unavailable(
                "RETURN_COGS_ACCOUNTING_RECOGNITION_ROW_INVALID"
            )
        if state == self.REVOKED and (row[6] is not None or row[7] is not None):
            return self._unavailable(
                "RETURN_COGS_ACCOUNTING_RECOGNITION_ROW_INVALID"
            )

        return {
            "error": False,
            "status": (
                "RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
                if confirmed
                else "RETURN_COGS_ACCOUNTING_RECOGNITION_REVOKED"
            ),
            "history_id": row[0],
            "return_id": str(row[1]),
            "posting_number": str(row[2]),
            "sku": str(row[3]),
            "recovery_accounting_date": accounting_date.isoformat(),
            "recognition_state": state,
            "recognized_amount": amount if confirmed else None,
            "currency": currency_key if confirmed else None,
            "confirmed_on": confirmation_date.isoformat(),
            "source": source_key,
            "recorded_at": row[10],
            "accounting_recognition_confirmed": confirmed,
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
    def _money(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not isfinite(number) or number < 0.0:
            return None
        return round(number, 2)

    @staticmethod
    def _input_invalid():
        return {
            "error": True,
            "code": "RETURN_COGS_ACCOUNTING_RECOGNITION_INPUT_INVALID",
            "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_RECORD_UNAVAILABLE",
        }

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_UNAVAILABLE",
            "accounting_recognition_confirmed": False,
            "recovery_accounting_date": None,
            "recognition_state": None,
            "recognized_amount": None,
            "currency": None,
            "confirmed_on": None,
            "source": None,
        }
