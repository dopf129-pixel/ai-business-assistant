import sqlite3
from datetime import datetime


DB_NAME = "ozon_assistant.db"



class ActionExecutorService:


    def __init__(self):
        pass



    def start_action(
        self,
        action_id
    ):


        conn = sqlite3.connect(
            DB_NAME
        )

        cursor = conn.cursor()



        cursor.execute(
            """
            UPDATE actions

            SET status = ?

            WHERE id = ?
            """,
            (
                "processing",
                action_id
            )
        )



        conn.commit()

        conn.close()



    def complete_action(
        self,
        action_id
    ):


        conn = sqlite3.connect(
            DB_NAME
        )


        cursor = conn.cursor()



        cursor.execute(
            """
            UPDATE actions

            SET status = ?

            WHERE id = ?
            """,
            (
                "done",
                action_id
            )
        )



        conn.commit()

        conn.close()



    def get_status(
        self,
        action_id
    ):


        conn = sqlite3.connect(
            DB_NAME
        )


        cursor = conn.cursor()



        cursor.execute(
            """
            SELECT status

            FROM actions

            WHERE id = ?
            """,
            (
                action_id,
            )
        )


        result = cursor.fetchone()



        conn.close()



        if result:

            return result[0]


        return None