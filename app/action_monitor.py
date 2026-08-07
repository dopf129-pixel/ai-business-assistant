import sqlite3


DB_NAME = "ozon_assistant.db"



class ActionMonitor:



    def update_actions(
        self,
        product_id,
        metrics
    ):


        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()



        cursor.execute(
            """
            SELECT id, action, status

            FROM actions

            WHERE product_id = ?

            """,

            (
                str(product_id),
            )
        )



        actions = cursor.fetchall()



        for action in actions:


            action_id = action[0]

            action_name = action[1]

            status = action[2]



            if status == "done":

                continue



            new_status = None



            # Проверка FBS

            if (
                "FBS" in action_name
                and metrics.get("has_fbs_stocks")
            ):

                new_status = "done"



            # Проверка акции

            if (
                "акции" in action_name.lower()
                and metrics.get("is_discounted")
            ):

                new_status = "done"



            if new_status:


                cursor.execute(
                    """
                    UPDATE actions

                    SET status = ?

                    WHERE id = ?

                    """,

                    (
                        new_status,
                        action_id
                    )
                )



        conn.commit()

        conn.close()