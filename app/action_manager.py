import sqlite3


DB_NAME = "ozon_assistant.db"



class ActionManager:


    def set_status(
        self,
        action_id,
        status
    ):


        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()


        cursor.execute(
            """
            UPDATE actions

            SET status = ?

            WHERE id = ?

            """,

            (
                status,
                action_id
            )
        )


        conn.commit()

        conn.close()



    def get_status_name(
        self,
        status
    ):


        names = {

            "new": "🟡 Новое",

            "in_progress": "🔵 В работе",

            "done": "🟢 Выполнено"

        }


        return names.get(
            status,
            status
        )