from datetime import date, datetime
from math import isfinite
import sqlite3


DB_NAME = "ozon_assistant.db"


class ReturnCogsProfitApplicationCommitRepository:
    """Append-only exact-once commitment ledger for Return COGS profit application."""

    COMMITTED = "PROFIT_APPLICATION_COMMITTED"
    RECOGNIZED = "COGS_RECOVERY_RECOGNIZED"
    AUTHORIZED = "PROFIT_APPLICATION_AUTHORIZED"
    MONETARY_AUTHORITY_EXCLUDED = "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL"

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
            CREATE INDEX IF NOT EXISTS idx_return_cogs_profit_application_commit_authorization
            ON return_cogs_profit_application_commit_history (authorization_history_id)
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
        """Low-level exact-once append with strict semantic replay matching."""
        prepared = self._prepare_commit(
            recognition_history_id,
            authorization_history_id,
            return_id,
            posting_number,
            sku,
            recovery_accounting_date,
            committed_amount,
            currency,
            committed_on,
            source,
        )
        if prepared is None:
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_INPUT_INVALID")
        conn = self.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            return self._append_prepared(conn, prepared)
        except sqlite3.Error:
            conn.rollback()
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_STORAGE_ERROR")
        finally:
            conn.close()

    def commit_current_authorization(
        self,
        recognition_history_id,
        authorization_history_id,
        return_id,
        posting_number,
        sku,
        committed_on,
        source="ACCOUNTING_CONTROLLED_COMMIT",
    ):
        """Atomically append only from the latest still-authorized recognition chain."""
        recognition_id = self._positive_int(recognition_history_id)
        authorization_id = self._positive_int(authorization_history_id)
        identity = self._identity(return_id, posting_number, sku)
        commit_date = self._date(committed_on)
        source_key = self._text(source)
        if (
            recognition_id is None
            or authorization_id is None
            or identity is None
            or commit_date is None
            or not source_key
        ):
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_INPUT_INVALID")

        conn = self.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            recognition = self._current_recognition(conn, recognition_id, identity)
            if recognition.get("error") is True:
                conn.rollback()
                return recognition
            authorization = self._current_authorization(
                conn, recognition_id, authorization_id, identity
            )
            if authorization.get("error") is True:
                conn.rollback()
                return authorization
            if recognition["recovery_accounting_date"] != authorization["recovery_accounting_date"]:
                conn.rollback()
                return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_ACCOUNTING_DATE_MISMATCH")
            if abs(recognition["amount"] - authorization["amount"]) > 0.01:
                conn.rollback()
                return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_AMOUNT_MISMATCH")

            prepared = {
                "recognition_history_id": recognition_id,
                "authorization_history_id": authorization_id,
                "return_id": identity[0],
                "posting_number": identity[1],
                "sku": identity[2],
                "recovery_accounting_date": recognition["recovery_accounting_date"],
                "committed_amount": recognition["amount"],
                "currency": "RUB",
                "committed_on": commit_date.isoformat(),
                "source": source_key,
            }
            result = self._append_prepared(conn, prepared)
            if result.get("error") is False:
                result["controlled_commit_authorization_revalidated"] = True
                result["controlled_commit_recognition_revalidated"] = True
                result["controlled_commit_transaction_basis"] = (
                    "BEGIN_IMMEDIATE_CURRENT_RECOGNITION_AND_AUTHORIZATION"
                )
            return result
        except sqlite3.Error:
            conn.rollback()
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_STORAGE_ERROR")
        finally:
            conn.close()

    def list_commits(self):
        """Return the append-only ledger for read-only integrity auditing."""
        conn = self.get_connection()
        try:
            rows = conn.execute(
                """
                SELECT id, recognition_history_id, return_id, posting_number, sku,
                       recovery_accounting_date, committed_amount, currency,
                       authorization_history_id, committed_on, source, recorded_at
                FROM return_cogs_profit_application_commit_history
                ORDER BY id ASC
                """
            ).fetchall()
        except sqlite3.Error:
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_STORAGE_ERROR")
        finally:
            conn.close()
        records = []
        for row in rows:
            record = self._ledger_row(row)
            if record is None:
                return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_ROW_INVALID")
            records.append(record)
        return {
            "error": False,
            "status": "RETURN_COGS_PROFIT_APPLICATION_COMMIT_LEDGER_READY",
            "records": records,
            "count": len(records),
            "read_only": True,
            "executed": False,
        }

    def get_application_commit(self, recognition_history_id):
        recognition_id = self._positive_int(recognition_history_id)
        if recognition_id is None:
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_QUERY_INVALID")
        conn = self.get_connection()
        try:
            row = self._select_commit_by_recognition(conn, recognition_id)
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

    def _append_prepared(self, conn, prepared):
        recognition_id = prepared["recognition_history_id"]
        authorization_id = prepared["authorization_history_id"]
        existing = self._select_commit_by_recognition(conn, recognition_id)
        if existing is not None:
            if self._same_commit(prepared, existing):
                conn.rollback()
                result = self._existing_result(recognition_id, existing)
                result["idempotent_replay"] = True
                return result
            conn.rollback()
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_REPLAY_CONFLICT")

        authorization_use = self._select_commit_by_authorization(conn, authorization_id)
        if authorization_use is not None:
            conn.rollback()
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_ALREADY_COMMITTED")

        try:
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
                    prepared["return_id"],
                    prepared["posting_number"],
                    prepared["sku"],
                    prepared["recovery_accounting_date"],
                    prepared["committed_amount"],
                    prepared["currency"],
                    authorization_id,
                    prepared["committed_on"],
                    prepared["source"],
                ),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            existing = self._select_commit_by_recognition(conn, recognition_id)
            if existing is not None and self._same_commit(prepared, existing):
                result = self._existing_result(recognition_id, existing)
                result["idempotent_replay"] = True
                return result
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_CONFLICT")
        conn.commit()
        return {
            "error": False,
            "status": "RETURN_COGS_PROFIT_APPLICATION_COMMIT_RECORDED",
            "history_id": cursor.lastrowid,
            **prepared,
            "application_commit_confirmed": True,
            "application_already_committed": False,
            "idempotent_replay": False,
        }

    def _current_recognition(self, conn, recognition_id, identity):
        rows = conn.execute(
            """
            SELECT id, return_id, posting_number, sku, recovery_accounting_date,
                   recognition_state, recognized_amount, currency
            FROM return_cogs_accounting_recognition_history
            WHERE return_id = ?
            ORDER BY confirmed_on DESC, id DESC
            """,
            (identity[0],),
        ).fetchall()
        if not rows:
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_RECOGNITION_MISSING")
        if any((str(row[1]), str(row[2]), str(row[3])) != identity for row in rows):
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_RECOGNITION_IDENTITY_CONFLICT")
        row = rows[0]
        amount = self._money(row[6])
        accounting_date = self._date(row[4])
        if row[0] != recognition_id:
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_RECOGNITION_STALE")
        if self._text(row[5]).upper() != self.RECOGNIZED:
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_RECOGNITION_NOT_ACTIVE")
        if amount is None or self._text(row[7]).upper() != "RUB" or accounting_date is None:
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_RECOGNITION_INVALID")
        return {"error": False, "amount": amount, "recovery_accounting_date": accounting_date.isoformat()}

    def _current_authorization(self, conn, recognition_id, authorization_id, identity):
        rows = conn.execute(
            """
            SELECT id, return_id, posting_number, sku, recovery_accounting_date,
                   application_state, authorized_amount, currency,
                   monetary_authority_treatment, compensation_non_overlap_confirmed
            FROM return_cogs_profit_application_authorization_history
            WHERE recognition_history_id = ?
            ORDER BY confirmed_on DESC, id DESC
            """,
            (recognition_id,),
        ).fetchall()
        if not rows:
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_AUTHORIZATION_MISSING")
        if any((str(row[1]), str(row[2]), str(row[3])) != identity for row in rows):
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_AUTHORIZATION_IDENTITY_CONFLICT")
        if any(self._text(row[5]).upper() == "PROFIT_APPLICATION_APPLIED" for row in rows):
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_ALREADY_APPLIED")
        row = rows[0]
        amount = self._money(row[6])
        accounting_date = self._date(row[4])
        if row[0] != authorization_id:
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_AUTHORIZATION_STALE")
        if self._text(row[5]).upper() != self.AUTHORIZED:
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_AUTHORIZATION_NOT_ACTIVE")
        if (
            amount is None or self._text(row[7]).upper() != "RUB" or accounting_date is None
            or self._text(row[8]).upper() != self.MONETARY_AUTHORITY_EXCLUDED or row[9] != 1
        ):
            return self._unavailable("RETURN_COGS_CONTROLLED_COMMIT_AUTHORIZATION_INVALID")
        return {"error": False, "amount": amount, "recovery_accounting_date": accounting_date.isoformat()}

    @classmethod
    def _prepare_commit(
        cls, recognition_history_id, authorization_history_id, return_id, posting_number, sku,
        recovery_accounting_date, committed_amount, currency, committed_on, source,
    ):
        recognition_id = cls._positive_int(recognition_history_id)
        authorization_id = cls._positive_int(authorization_history_id)
        identity = cls._identity(return_id, posting_number, sku)
        accounting_date = cls._date(recovery_accounting_date)
        amount = cls._money(committed_amount)
        currency_key = cls._text(currency).upper()
        commit_date = cls._date(committed_on)
        source_key = cls._text(source)
        if (
            recognition_id is None or authorization_id is None or identity is None
            or accounting_date is None or amount is None or currency_key != "RUB"
            or commit_date is None or not source_key
        ):
            return None
        return {
            "recognition_history_id": recognition_id,
            "authorization_history_id": authorization_id,
            "return_id": identity[0], "posting_number": identity[1], "sku": identity[2],
            "recovery_accounting_date": accounting_date.isoformat(),
            "committed_amount": amount, "currency": currency_key,
            "committed_on": commit_date.isoformat(), "source": source_key,
        }

    @staticmethod
    def _select_commit_by_recognition(conn, recognition_id):
        return conn.execute(
            """
            SELECT id, return_id, posting_number, sku, recovery_accounting_date,
                   committed_amount, currency, authorization_history_id, committed_on, source, recorded_at
            FROM return_cogs_profit_application_commit_history WHERE recognition_history_id = ?
            """,
            (recognition_id,),
        ).fetchone()

    @staticmethod
    def _select_commit_by_authorization(conn, authorization_id):
        return conn.execute(
            "SELECT id, recognition_history_id FROM return_cogs_profit_application_commit_history WHERE authorization_history_id = ? LIMIT 1",
            (authorization_id,),
        ).fetchone()

    @classmethod
    def _same_commit(cls, prepared, row):
        row_date = cls._date(row[4])
        return (
            cls._text(row[1]) == prepared["return_id"]
            and cls._text(row[2]) == prepared["posting_number"]
            and cls._text(row[3]) == prepared["sku"]
            and row_date is not None and row_date.isoformat() == prepared["recovery_accounting_date"]
            and cls._money(row[5]) == prepared["committed_amount"]
            and cls._text(row[6]).upper() == prepared["currency"]
            and cls._positive_int(row[7]) == prepared["authorization_history_id"]
            and cls._text(row[9]) == prepared["source"]
        )

    @classmethod
    def _existing_result(cls, recognition_id, row):
        amount = cls._money(row[5])
        authorization_id = cls._positive_int(row[7])
        accounting_date = cls._date(row[4])
        committed_on = cls._date(row[8])
        if (
            amount is None or cls._text(row[6]).upper() != "RUB" or authorization_id is None
            or accounting_date is None or committed_on is None or not cls._text(row[9])
        ):
            return cls._unavailable("RETURN_COGS_PROFIT_APPLICATION_COMMIT_ROW_INVALID")
        return {
            "error": False, "status": "RETURN_COGS_PROFIT_APPLICATION_ALREADY_COMMITTED",
            "history_id": row[0], "recognition_history_id": recognition_id,
            "return_id": str(row[1]), "posting_number": str(row[2]), "sku": str(row[3]),
            "recovery_accounting_date": accounting_date.isoformat(), "committed_amount": amount,
            "currency": "RUB", "authorization_history_id": authorization_id,
            "committed_on": committed_on.isoformat(), "source": cls._text(row[9]),
            "recorded_at": row[10], "application_commit_confirmed": True,
            "application_already_committed": True,
        }

    @classmethod
    def _ledger_row(cls, row):
        recognition_id = cls._positive_int(row[1]); authorization_id = cls._positive_int(row[8])
        identity = cls._identity(row[2], row[3], row[4]); accounting_date = cls._date(row[5])
        amount = cls._money(row[6]); committed_on = cls._date(row[9]); source = cls._text(row[10])
        if (
            recognition_id is None or authorization_id is None or identity is None or accounting_date is None
            or amount is None or cls._text(row[7]).upper() != "RUB" or committed_on is None or not source
        ):
            return None
        return {
            "history_id": row[0], "recognition_history_id": recognition_id,
            "authorization_history_id": authorization_id, "return_id": identity[0],
            "posting_number": identity[1], "sku": identity[2],
            "recovery_accounting_date": accounting_date.isoformat(), "committed_amount": amount,
            "currency": "RUB", "committed_on": committed_on.isoformat(), "source": source,
            "recorded_at": row[11], "application_commit_confirmed": True,
        }

    @staticmethod
    def _positive_int(value):
        if isinstance(value, bool): return None
        try: value = int(value)
        except (TypeError, ValueError): return None
        return value if value > 0 else None

    @classmethod
    def _identity(cls, return_id, posting_number, sku):
        values = (cls._text(return_id), cls._text(posting_number), cls._text(sku))
        return values if all(values) else None

    @staticmethod
    def _text(value): return "" if value is None else str(value).strip()

    @staticmethod
    def _date(value):
        if isinstance(value, datetime): return value.date()
        if isinstance(value, date): return value
        try: return date.fromisoformat(str(value))
        except (TypeError, ValueError): return None

    @staticmethod
    def _money(value):
        if value is None or isinstance(value, bool): return None
        try: number = float(value)
        except (TypeError, ValueError): return None
        if not isfinite(number) or number < 0.0: return None
        return round(number, 2)

    @staticmethod
    def _unavailable(code):
        return {
            "error": True, "code": code,
            "status": "RETURN_COGS_PROFIT_APPLICATION_COMMIT_UNAVAILABLE",
            "application_commit_confirmed": False, "application_already_committed": False,
            "committed_amount": None, "currency": None,
        }
