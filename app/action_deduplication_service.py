import sqlite3


DB_NAME = "ozon_assistant.db"



class ActionDeduplicationService:


    def __init__(self):

        pass



    def exists(
        self,
        product_id,
        action
    ):


        conn = sqlite3.connect(
            DB_NAME
        )

        cursor = conn.cursor()


        cursor.execute(
            """
            SELECT id

            FROM actions

            WHERE product_id = ?

            AND action = ?

            AND status != 'done'

            LIMIT 1
            """,
            (
                str(product_id),
                action
            )
        )


        result = cursor.fetchone()


        conn.close()


        return result is not None




    def filter_new_actions(
        self,
        product_id,
        decisions
    ):


        new_actions = []



        for decision in decisions:


            if not self.exists(
                product_id,
                decision["action"]
            ):


                new_actions.append(
                    decision
                )



        return new_actions