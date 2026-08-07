import sqlite3


DB_NAME = "ozon_assistant.db"



class ActionStatusService:



    def get_actions(
        self,
        product_id=None
    ):


        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()



        if product_id:


            cursor.execute(
                """
                SELECT *

                FROM actions

                WHERE product_id = ?

                ORDER BY id DESC

                """,

                (
                    str(product_id),
                )
            )


        else:


            cursor.execute(
                """
                SELECT *

                FROM actions

                ORDER BY id DESC

                """
            )



        result = cursor.fetchall()


        conn.close()


        return result




    def update_status(
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