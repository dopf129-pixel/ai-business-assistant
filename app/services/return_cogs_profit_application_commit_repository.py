from datetime import date, datetime
from math import isfinite
import sqlite3


DB_NAME = "ozon_assistant.db"


class ReturnCogsProfitApplicationCommitRepository:
    """Append-only exact-once commitment ledger for Return COGS profit application."""

    COMMITTED = "PROFIT_APPLICATION_COMMITTED"

    def __init__(self):
        self.create_table()

    def get_connection(self):
        return sqlite3.connect(DB_NAME)

    def create_table(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS return_cogs_profit_application_commit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recognition_history_id INTEGER NOT NULL UNIQUE,
                return_id TEXT NOT NULL,
                posting_number TEXT NOT NULL,
                sku TEXT NOT NULL,
                recovery_accounting_date TEXT NOT NULL,
                committed_amount REAL NOT NULL,
                currency TEXT NOT NULL,
                authorization_history_id INTEGER NOT NULL,
                committed_on TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'SELLER_ACCOUNTING_PROFIT_APPLICATION_COMMIT',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_return_cogs_profit_application_commit_no_update
            BEFORE UPDATE ON return_cogs_profit_application_commit_history
            BEGIN
                SELECT RAISE(ABORT, 'return_cogs_profit_application_commit_history is append-only');
            END
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_return_cogs_profit_application_commit_no_delete
            BEFORE DELETE ON return_cogs_profit_application_commit_history
            BEGIN
                SELECT RAISE(ABORT, 'return_cogs_profit_application_commit_history is append-only');
            END
            """
        )
        conn.commit()
        conn.close()

    def commit_application(
        self,
        recognition_history_id,
        return_id,
        posting_number,
        sku,
        recovery_accounting_date,
        committed_amount,
        currency,
        authorization_history_id,
        committed_on,
        source="SELLER_ACCOUNTING_PROFIT_APPLICATION_COMMIT",
    ):
        recognition_id = self._positive_int(recognition_history_id)
        authorization_id = self._positive_int(authorization_history_id)
        return_key = self._text(return_id)
        posting_key = self._text(posting_number)
        sku_key = self._text(sku)
        accounting_date = self._date(recovery_accounting_date)
        amount = self._money(committed_amount)
        currency_key = self._text(currency).upper()
        commit_date = self._date(committed_on)
        source_key = self._text(source)
        if (
            recognition_id is None
            or authorization_id is None
            or not return_key
            or not posting_key
            or not sku_key
            or accounting_date is None
            or amount is None
            or currency_key != "RUB"
            or commit_date is None
            or not source_key
        ):
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_INPUT_INVALID")

        conn = self.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT id, return_id, posting_number, sku, recovery_accounting_date,
                       committed_amount, currency, authorization_history_id, committed_on, source, recorded_at
                FROM return_cogs_profit_application_commit_history
                WHERE recognition_history_id = ?
                """,
                (recognition_id,),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return self._existing_result(recognition_id, existing)

            cursor = conn.execute(
                """
                INSERT INTO return_cogs_profit_application_commit_history (
                    recognition_history_id, return_id, posting_number, sku,
                    recovery_accounting_date, committed_amount, currency,
                    authorization_history_id, committed_on, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recognition_id,
                    return_key,
                    posting_key,
                    sku_key,
                    accounting_date.isoformat(),
                    amount,
                    currency_key,
                    authorization_id,
                    commit_date.isoformat(),
                    source_key,
                ),
            )
            row_id = cursor.lastrowid
            conn.commit()
            return {
                "error": False,
                "status": "RETURN_COGS_PROFIT_APPLICATION_COMMIT_RECORDED",
                "history_id": row_id,
                "recognition_history_id": recognition_id,
                "return_id": return_key,
                "posting_number": posting_key,
                "sku": sku_key,
                "recovery_accounting_date": accounting_date.isoformat(),
                "committed_amount": amount,
                "currency": currency_key,
                "authorization_history_id": authorization_id,
                "committed_on": commit_date.isoformat(),
                "source": source_key,
                "application_commit_confirmed": True,
                "application_already_committed": False,
            }
        except sqlite3.IntegrityError:
            conn.rollback()
            existing = conn.execute(
                """
                SELECT id, return_id, posting_number, sku, recovery_accounting_date,
                       committed_amount, currency, authorization_history_id, committed_on, source, recorded_at
                FROM return_cogs_profit_application_commit_history
                WHERE recognition_history_id = ?
                """,
                (recognition_id,),
            ).fetchone()
            if existing is not None:
                return self._existing_result(recognition_id, existing)
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_CONFLICT")
        except sqlite3.Error:
            conn.rollback()
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_STORAGE_ERROR")
        finally:
            conn.close()

    def get_application_commit(self, recognition_history_id):
        recognition_id = self._positive_int(recognition_history_id)
        if recognition_id is None:
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_QUERY_INVALID")
        conn = self.get_connection()
        try:
            row = conn.execute(
                """
                SELECT id, return_id, posting_number, sku, recovery_accounting_date,
                       committed_amount, currency, authorization_history_id, committed_on, source, recorded_at
                FROM return_cogs_profit_application_commit_history
                WHERE recognition_history_id = ?
                """,
                (recognition_id,),
            ).fetchone()
        except sqlite3.Error:
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_STORAGE_ERROR")
        finally:
            conn.close()
        if row is None:
            return {
                "error": False,
                "status": "RETURN_COGS_PROFIT_APPLICATION_COMMIT_MISSING",
                "recognition_history_id": recognition_id,
                "application_commit_confirmed": False,
                "application_already_committed": False,
                "committed_amount": None,
                "currency": None,
            }
        return self._existing_result(recognition_id, row)

    @classmethod
    def _existing_result(cls, recognition_id, row):
        amount = cls._money(row[5])
        authorization_id = cls._positive_int(row[7])
        accounting_date = cls._date(row[4])
        committed_on = cls._date(row[8])
        if (
            amount is None
            or cls._text(row[6]).upper() != "RUB"
            or authorization_id is None
            or accounting_date is None
            or committed_on is None
        ):
            return cls._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_ROW_INVALID")
        return {
            "error": False,
            "status": "RETURN_COGS_PROFIT_APPLICATION_ALREADY_COMMITTED",
            "history_id": row[0],
            "recognition_history_id": recognition_id,
            "return_id": str(row[1]),
            "posting_number": str(row[2]),
            "sku": str(row[3]),
            "recovery_accounting_date": accounting_date.isoformat(),
            "committed_amount": amount,
            "currency": "RUB",
            "authorization_history_id": authorization_id,
            "committed_on": committed_on.isoformat(),
            "source": cls._text(row[9]),
            "recorded_at": row[10],
            "application_commit_confirmed": True,
            "application_already_committed": True,
        }

    @staticmethod
    def _positive_int(value):
        if isinstance(value, bool):
            return None
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _text(value):
        return "" if value is None else str(value).strip()

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
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "RETURN_COGS_PROFIT_APPLICATION_COMMIT_UNAVAILABLE",
            "application_commit_confirmed": False,
            "application_already_committed": False,
            "committed_amount": None,
            "currency": None,
        }
