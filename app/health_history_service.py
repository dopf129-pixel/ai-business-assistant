import sqlite3


DB_NAME = "ozon_assistant.db"


class HealthHistoryService:


    def __init__(self):

        self.create_table()



    def create_table(self):

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()


        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS health_history (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                product_id TEXT NOT NULL,

                score INTEGER,

                status TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )
            """
        )


        conn.commit()

        conn.close()



    def save(
        self,
        product_id,
        health
    ):

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()


        cursor.execute(
            """
            INSERT INTO health_history
            (
                product_id,
                score,
                status
            )

            VALUES (?, ?, ?)
            """,
            (
                str(product_id),
                health.get("score", 0),
                health.get("status", "")
            )
        )


        conn.commit()

        conn.close()



    def get_history(
        self,
        product_id
    ):

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()


        cursor.execute(
            """
            SELECT
                score,
                status,
                created_at

            FROM health_history

            WHERE product_id = ?

            ORDER BY id DESC
            """,
            (
                str(product_id),
            )
        )


        result = cursor.fetchall()


        conn.close()


        return result