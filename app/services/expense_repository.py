import math
import sqlite3
from datetime import datetime
from pathlib import Path


class ExpenseRepository:

    def __init__(
        self,
        db_path="ozon_assistant.db"
    ):

        self.db_path = Path(
            db_path
        )

        self.create_table()

    def get_connection(
        self
    ):

        return sqlite3.connect(
            self.db_path
        )

    def create_table(
        self
    ):

        with self.get_connection() as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expense_date TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS expense_coverage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            connection.commit()

    def confirm_coverage(
        self,
        date_from,
        date_to,
        note=""
    ):

        start = self._date(
            date_from
        )
        end = self._date(
            date_to
        )

        if (
            start is None
            or end is None
            or start > end
        ):
            return {
                "error": True,
                "code": "EXPENSE_COVERAGE_PERIOD_INVALID",
                "message": (
                    "Некорректный период покрытия расходов"
                )
            }

        created_at = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        with self.get_connection() as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO expense_coverage (
                    date_from,
                    date_to,
                    note,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    start,
                    end,
                    str(note or ""),
                    created_at,
                )
            )

            connection.commit()

            coverage_id = cursor.lastrowid

        return {
            "error": False,
            "status": "EXPENSE_COVERAGE_CONFIRMED",
            "id": coverage_id,
            "date_from": start,
            "date_to": end,
            "note": str(note or ""),
            "created_at": created_at,
        }

    def get_coverage_by_period(
        self,
        date_from,
        date_to
    ):

        with self.get_connection() as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    date_from,
                    date_to,
                    note,
                    created_at
                FROM expense_coverage
                WHERE date_to >= ?
                  AND date_from <= ?
                ORDER BY date_from ASC, id ASC
                """,
                (
                    str(date_from),
                    str(date_to),
                )
            )

            rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "date_from": row[1],
                "date_to": row[2],
                "note": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]

    @staticmethod
    def _date(value):

        text = str(
            value or ""
        ).strip()

        try:
            parsed = datetime.strptime(
                text,
                "%Y-%m-%d"
            ).date()
        except (
            TypeError,
            ValueError
        ):
            return None

        return parsed.isoformat()

    def add_expense(
        self,
        expense_date,
        category,
        amount,
        description=""
    ):

        if isinstance(
            amount,
            bool
        ):

            return {
                "error": True,
                "message": (
                    "Некорректная сумма расхода"
                )
            }

        try:
            amount = float(
                amount
            )

        except (
            TypeError,
            ValueError
        ):

            return {
                "error": True,
                "message": (
                    "Некорректная сумма расхода"
                )
            }

        if not math.isfinite(
            amount
        ):

            return {
                "error": True,
                "message": (
                    "Некорректная сумма расхода"
                )
            }

        if amount < 0:

            return {
                "error": True,
                "message": (
                    "Сумма расхода не может "
                    "быть отрицательной"
                )
            }

        category = str(
            category or ""
        ).strip()

        if not category:

            return {
                "error": True,
                "message": (
                    "Категория расхода "
                    "не указана"
                )
            }

        expense_date = self._date(
            expense_date
        )

        if expense_date is None:

            return {
                "error": True,
                "code": "EXPENSE_DATE_INVALID",
                "message": (
                    "Некорректная дата расхода"
                )
            }

        created_at = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        with self.get_connection() as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO expenses (
                    expense_date,
                    category,
                    amount,
                    description,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    expense_date,
                    category,
                    amount,
                    str(
                        description or ""
                    ),
                    created_at
                )
            )

            connection.commit()

            expense_id = (
                cursor.lastrowid
            )

        return {
            "error": False,
            "id": expense_id,
            "expense_date": expense_date,
            "category": category,
            "amount": round(
                amount,
                2
            ),
            "description": str(
                description or ""
            ),
            "created_at": created_at
        }

    def get_expenses_by_date(
        self,
        expense_date
    ):

        with self.get_connection() as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    expense_date,
                    category,
                    amount,
                    description,
                    created_at
                FROM expenses
                WHERE expense_date = ?
                ORDER BY id ASC
                """,
                (
                    str(
                        expense_date
                    ),
                )
            )

            rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "expense_date": row[1],
                "category": row[2],
                "amount": row[3],
                "description": row[4],
                "created_at": row[5]
            }
            for row in rows
        ]

    def get_expenses_by_period(
        self,
        date_from,
        date_to
    ):

        with self.get_connection() as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    expense_date,
                    category,
                    amount,
                    description,
                    created_at
                FROM expenses
                WHERE expense_date >= ?
                  AND expense_date <= ?
                ORDER BY expense_date ASC, id ASC
                """,
                (
                    str(
                        date_from
                    ),
                    str(
                        date_to
                    )
                )
            )

            rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "expense_date": row[1],
                "category": row[2],
                "amount": row[3],
                "description": row[4],
                "created_at": row[5]
            }
            for row in rows
        ]

    def delete_expense(
        self,
        expense_id
    ):

        with self.get_connection() as connection:

            cursor = connection.cursor()

            cursor.execute(
                """
                DELETE FROM expenses
                WHERE id = ?
                """,
                (
                    int(
                        expense_id
                    ),
                )
            )

            connection.commit()

            deleted = (
                cursor.rowcount
            )

        return {
            "error": False,
            "deleted": deleted
        }