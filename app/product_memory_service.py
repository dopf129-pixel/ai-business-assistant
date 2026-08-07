import sqlite3
from datetime import date


DB_NAME = "ozon_assistant.db"


class ProductMemoryService:

    def __init__(self):
        self.create_table()

    def get_connection(self):
        return sqlite3.connect(DB_NAME)

    def format_number(self, value):

        try:
            return f"{int(value):,}".replace(",", " ")
        except (TypeError, ValueError):
            return "0"

    def format_days(self, value):

        days = int(value)

        last_two = days % 100
        last_one = days % 10

        if 11 <= last_two <= 14:
            word = "дней"
        elif last_one == 1:
            word = "день"
        elif 2 <= last_one <= 4:
            word = "дня"
        else:
            word = "дней"

        return f"{days} {word}"

    def create_table(self):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                health_score INTEGER,
                risk_score INTEGER,
                has_fbo_stocks INTEGER,
                is_discounted INTEGER,
                fbo_present INTEGER DEFAULT 0,
                fbo_reserved INTEGER DEFAULT 0,
                fbo_available INTEGER DEFAULT 0,
                snapshot_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, snapshot_date)
            )
            """
        )

        cursor.execute(
            """
            PRAGMA table_info(product_memory)
            """
        )

        existing_columns = {
            row[1]
            for row in cursor.fetchall()
        }

        new_columns = {
            "fbo_present": "INTEGER DEFAULT 0",
            "fbo_reserved": "INTEGER DEFAULT 0",
            "fbo_available": "INTEGER DEFAULT 0"
        }

        for column_name, column_type in new_columns.items():

            if column_name not in existing_columns:

                cursor.execute(
                    f"""
                    ALTER TABLE product_memory
                    ADD COLUMN {column_name} {column_type}
                    """
                )

        conn.commit()
        conn.close()

    def save_snapshot(
        self,
        product_id,
        metrics,
        health,
        risk
    ):

        snapshot_date = date.today().isoformat()

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO product_memory (
                product_id,
                health_score,
                risk_score,
                has_fbo_stocks,
                is_discounted,
                fbo_present,
                fbo_reserved,
                fbo_available,
                snapshot_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(product_id, snapshot_date)

            DO UPDATE SET
                health_score = excluded.health_score,
                risk_score = excluded.risk_score,
                has_fbo_stocks = excluded.has_fbo_stocks,
                is_discounted = excluded.is_discounted,
                fbo_present = excluded.fbo_present,
                fbo_reserved = excluded.fbo_reserved,
                fbo_available = excluded.fbo_available,
                created_at = CURRENT_TIMESTAMP
            """,
            (
                str(product_id),
                int(health.get("score", 0)),
                int(risk.get("risk_score", 0)),
                int(bool(metrics.get("has_fbo_stocks"))),
                int(bool(metrics.get("is_discounted"))),
                int(metrics.get("fbo_present", 0) or 0),
                int(metrics.get("fbo_reserved", 0) or 0),
                int(metrics.get("fbo_available", 0) or 0),
                snapshot_date
            )
        )

        conn.commit()
        conn.close()

    def get_history(
        self,
        product_id,
        limit=7
    ):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                health_score,
                risk_score,
                has_fbo_stocks,
                is_discounted,
                fbo_present,
                fbo_reserved,
                fbo_available,
                snapshot_date

            FROM product_memory

            WHERE product_id = ?

            ORDER BY snapshot_date DESC

            LIMIT ?
            """,
            (
                str(product_id),
                int(limit)
            )
        )

        rows = cursor.fetchall()

        conn.close()

        return rows

    def analyze(
        self,
        product_id,
        limit=7
    ):

        history = self.get_history(
            product_id,
            limit
        )

        if not history:

            return {
                "records": 0,
                "health_change": 0,
                "risk_change": 0,
                "stock_change": 0,
                "current_fbo_present": 0,
                "current_fbo_reserved": 0,
                "current_fbo_available": 0,
                "days_without_discount": 0,
                "fbo_stable": False,
                "summary": "Истории пока недостаточно"
            }

        current = history[0]
        oldest = history[-1]

        health_change = current[0] - oldest[0]
        risk_change = current[1] - oldest[1]
        stock_change = current[6] - oldest[6]

        current_fbo_present = current[4]
        current_fbo_reserved = current[5]
        current_fbo_available = current[6]

        days_without_discount = 0

        for row in history:

            if row[3] == 0:
                days_without_discount += 1
            else:
                break

        fbo_stable = all(
            row[2] == 1
            and row[6] > 0
            for row in history
        )

        if health_change > 0:

            health_text = (
                f"Здоровье выросло на "
                f"{health_change} баллов"
            )

        elif health_change < 0:

            health_text = (
                f"Здоровье снизилось на "
                f"{abs(health_change)} баллов"
            )

        else:

            health_text = "Здоровье не изменилось"

        if risk_change < 0:

            risk_text = (
                f"Риск снизился на "
                f"{abs(risk_change)} баллов"
            )

        elif risk_change > 0:

            risk_text = (
                f"Риск вырос на "
                f"{risk_change} баллов"
            )

        else:

            risk_text = "Риск не изменился"

        if len(history) < 2:

            stock_text = (
                "Доступный остаток FBO: "
                f"{self.format_number(current_fbo_available)} шт"
            )

        elif stock_change > 0:

            stock_text = (
                "Доступный остаток FBO вырос на "
                f"{self.format_number(stock_change)} шт"
            )

        elif stock_change < 0:

            stock_text = (
                "Доступный остаток FBO снизился на "
                f"{self.format_number(abs(stock_change))} шт"
            )

        else:

            stock_text = (
                "Доступный остаток FBO не изменился"
            )

        summary_parts = [
            health_text,
            risk_text,
            stock_text
        ]

        if fbo_stable:

            summary_parts.append(
                "FBO остатки есть во всех сохранённых снимках"
            )

        if days_without_discount > 0:

            summary_parts.append(
                "Без скидки: "
                f"{self.format_days(days_without_discount)} подряд"
            )

        return {
            "records": len(history),
            "health_change": health_change,
            "risk_change": risk_change,
            "stock_change": stock_change,
            "current_fbo_present": current_fbo_present,
            "current_fbo_reserved": current_fbo_reserved,
            "current_fbo_available": current_fbo_available,
            "days_without_discount": days_without_discount,
            "fbo_stable": fbo_stable,
            "summary": ". ".join(summary_parts)
        }