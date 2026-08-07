import sqlite3
from datetime import datetime


DB_NAME = "ozon_assistant.db"



class ChangeLogService:


    def __init__(self):

        self.create_table()



    def create_table(self):

        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()


        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS change_log (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                product_id TEXT,

                change TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )
            """
        )


        conn.commit()

        conn.close()



    def add_change(
        self,
        product_id,
        change
    ):


        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()


        cursor.execute(
            """
            INSERT INTO change_log
            (
                product_id,
                change
            )

            VALUES (?, ?)

            """,

            (
                str(product_id),
                change
            )
        )


        conn.commit()

        conn.close()



    def get_changes(
        self,
        product_id
    ):


        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()


        cursor.execute(
            """
            SELECT change, created_at

            FROM change_log

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