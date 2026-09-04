from datetime import date, datetime
from math import isfinite
import sqlite3


DB_NAME = "ozon_assistant.db"


class ReturnCogsProfitApplicationAuthorizationRepository:
    """Append-only accounting authorization for a recognized Return COGS application."""

    AUTHORIZED = "PROFIT_APPLICATION_AUTHORIZED"
    APPLIED = "PROFIT_APPLICATION_APPLIED"
    REVOKED = "PROFIT_APPLICATION_AUTHORIZATION_REVOKED"
    STATES = {AUTHORIZED, APPLIED, REVOKED}
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
            CREATE TABLE IF NOT EXISTS return_cogs_profit_application_authorization_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recognition_history_id INTEGER NOT NULL,
                return_id TEXT NOT NULL,
                posting_number TEXT NOT NULL,
                sku TEXT NOT NULL,
                recovery_accounting_date TEXT NOT NULL,
                application_state TEXT NOT NULL,
                authorized_amount REAL,
                currency TEXT,
                monetary_authority_treatment TEXT,
                compensation_non_overlap_confirmed INTEGER,
                confirmed_on TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'SELLER_ACCOUNTING_PROFIT_APPLICATION',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(recognition_history_id, confirmed_on)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_return_cogs_profit_application_recognition
            ON return_cogs_profit_application_authorization_history (
                recognition_history_id,
                confirmed_on
            )
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_return_cogs_profit_application_no_update
            BEFORE UPDATE ON return_cogs_profit_application_authorization_history
            BEGIN
                SELECT RAISE(ABORT, 'return_cogs_profit_application_authorization_history is append-only');
            END
            """
        )
        conn.commit()
        conn.close()

    def record_application_state(
        self,
        recognition_history_id,
        return_id,
        posting_number,
        sku,
        recovery_accounting_date,
        application_state,
        authorized_amount,
        currency,
        monetary_authority_treatment,
        compensation_non_overlap_confirmed,
        confirmed_on,
        source="SELLER_ACCOUNTING_PROFIT_APPLICATION",
    ):
        recognition_id = self._positive_int(recognition_history_id)
        return_key = self._text(return_id)
        posting_key = self._text(posting_number)
        sku_key = self._text(sku)
        accounting_date = self._date(recovery_accounting_date)
        state = self._text(application_state).upper()
        amount = self._money(authorized_amount)
        currency_key = self._text(currency).upper()
        authority_treatment = self._text(monetary_authority_treatment).upper()
        non_overlap = compensation_non_overlap_confirmed
        confirmation_date = self._date(confirmed_on)
        source_key = self._text(source)

        if (
            recognition_id is None
            or not return_key
            or not posting_key
            or not sku_key
            or accounting_date is None
            or state not in self.STATES
            or confirmation_date is None
            or not source_key
        ):
            return self._input_invalid()

        if state in {self.AUTHORIZED, self.APPLIED}:
            if (
                amount is None
                or currency_key != "RUB"
                or authority_treatment != self.MONETARY_AUTHORITY_EXCLUDED
                or non_overlap is not True
            ):
                return self._input_invalid()
        else:
            if (
                authorized_amount is not None
                or self._text(currency)
                or self._text(monetary_authority_treatment)
                or compensation_non_overlap_confirmed is not None
            ):
                return self._input_invalid()
            amount = None
            currency_key = None
            authority_treatment = None
            non_overlap = None

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO return_cogs_profit_application_authorization_history (
                    recognition_history_id,
                    return_id,
                    posting_number,
                    sku,
                    recovery_accounting_date,
                    application_state,
                    authorized_amount,
                    currency,
                    monetary_authority_treatment,
                    compensation_non_overlap_confirmed,
                    confirmed_on,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recognition_id,
                    return_key,
                    posting_key,
                    sku_key,
                    accounting_date.isoformat(),
                    state,
                    amount,
                    currency_key,
                    authority_treatment,
                    1 if non_overlap is True else None,
                    confirmation_date.isoformat(),
                    source_key,
                ),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            return {
                "error": True,
                "code": "RETURN_COGS_PROFIT_APPLICATION_VERSION_CONFLICT",
                "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_UNAVAILABLE",
                "recognition_history_id": recognition_id,
                "confirmed_on": confirmation_date.isoformat(),
            }

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {
            "error": False,
            "status": "RETURN_COGS_PROFIT_APPLICATION_STATE_RECORDED",
            "history_id": row_id,
            "recognition_history_id": recognition_id,
            "return_id": return_key,
            "posting_number": posting_key,
            "sku": sku_key,
            "recovery_accounting_date": accounting_date.isoformat(),
            "application_state": state,
            "authorized_amount": amount,
            "currency": currency_key,
            "monetary_authority_treatment": authority_treatment,
            "compensation_non_overlap_confirmed": non_overlap,
            "confirmed_on": confirmation_date.isoformat(),
            "source": source_key,
            "application_authorization_evidence": state == self.AUTHORIZED,
        }

    def get_application_authorization(
        self,
        recognition_history_id,
        return_id,
        posting_number,
        sku,
    ):
        recognition_id = self._positive_int(recognition_history_id)
        return_key = self._text(return_id)
        posting_key = self._text(posting_number)
        sku_key = self._text(sku)
        if recognition_id is None or not return_key or not posting_key or not sku_key:
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_QUERY_INVALID")

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                recognition_history_id,
                return_id,
                posting_number,
                sku,
                recovery_accounting_date,
                application_state,
                authorized_amount,
                currency,
                monetary_authority_treatment,
                compensation_non_overlap_confirmed,
                confirmed_on,
                source,
                recorded_at
            FROM return_cogs_profit_application_authorization_history
            WHERE recognition_history_id = ?
            ORDER BY confirmed_on DESC, id DESC
            """,
            (recognition_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return self._state_result(
                status="RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_MISSING",
                recognition_history_id=recognition_id,
                return_id=return_key,
                posting_number=posting_key,
                sku=sku_key,
            )

        if any(
            str(row[2]) != return_key
            or str(row[3]) != posting_key
            or str(row[4]) != sku_key
            for row in rows
        ):
            return self._state_result(
                status="RETURN_COGS_PROFIT_APPLICATION_IDENTITY_CONFLICT",
                recognition_history_id=recognition_id,
                return_id=return_key,
                posting_number=posting_key,
                sku=sku_key,
            )

        if any(self._text(row[6]).upper() == self.APPLIED for row in rows):
            return self._state_result(
                status="RETURN_COGS_PROFIT_APPLICATION_ALREADY_APPLIED",
                recognition_history_id=recognition_id,
                return_id=return_key,
                posting_number=posting_key,
                sku=sku_key,
                already_applied=True,
            )

        row = rows[0]
        accounting_date = self._date(row[5])
        state = self._text(row[6]).upper()
        amount = self._money(row[7])
        currency_key = self._text(row[8]).upper()
        authority_treatment = self._text(row[9]).upper()
        non_overlap = row[10] == 1
        confirmation_date = self._date(row[11])
        source_key = self._text(row[12])

        if (
            accounting_date is None
            or state not in self.STATES
            or confirmation_date is None
            or not source_key
        ):
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_ROW_INVALID")

        if state == self.REVOKED:
            if any(value is not None for value in (row[7], row[8], row[9], row[10])):
                return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_ROW_INVALID")
            return self._state_result(
                status="RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_REVOKED",
                recognition_history_id=recognition_id,
                return_id=return_key,
                posting_number=posting_key,
                sku=sku_key,
            )

        if (
            amount is None
            or currency_key != "RUB"
            or authority_treatment != self.MONETARY_AUTHORITY_EXCLUDED
            or non_overlap is not True
        ):
            return self._unavailable("RETURN_COGS_PROFIT_APPLICATION_ROW_INVALID")

        return {
            "error": False,
            "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY",
            "history_id": row[0],
            "recognition_history_id": recognition_id,
            "return_id": str(row[2]),
            "posting_number": str(row[3]),
            "sku": str(row[4]),
            "recovery_accounting_date": accounting_date.isoformat(),
            "application_state": state,
            "authorized_amount": amount,
            "currency": currency_key,
            "monetary_authority_treatment": authority_treatment,
            "monetary_authority_non_overlap_confirmed": True,
            "compensation_non_overlap_confirmed": True,
            "confirmed_on": confirmation_date.isoformat(),
            "source": source_key,
            "recorded_at": row[13],
            "application_authorization_confirmed": state == self.AUTHORIZED,
            "application_already_applied": False,
        }

    @staticmethod
    def _state_result(
        status,
        recognition_history_id,
        return_id,
        posting_number,
        sku,
        already_applied=False,
    ):
        return {
            "error": False,
            "status": status,
            "recognition_history_id": recognition_history_id,
            "return_id": return_id,
            "posting_number": posting_number,
            "sku": sku,
            "application_authorization_confirmed": False,
            "application_already_applied": already_applied,
            "recovery_accounting_date": None,
            "application_state": None,
            "authorized_amount": None,
            "currency": None,
            "monetary_authority_treatment": None,
            "monetary_authority_non_overlap_confirmed": False,
            "compensation_non_overlap_confirmed": False,
            "confirmed_on": None,
            "source": None,
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
            "code": "RETURN_COGS_PROFIT_APPLICATION_INPUT_INVALID",
            "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_UNAVAILABLE",
        }

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_UNAVAILABLE",
            "application_authorization_confirmed": False,
            "application_already_applied": False,
            "authorized_amount": None,
            "currency": None,
            "monetary_authority_treatment": None,
            "monetary_authority_non_overlap_confirmed": False,
            "compensation_non_overlap_confirmed": False,
        }
