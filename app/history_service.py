import sqlite3



DB_NAME = "ozon_assistant.db"



class HistoryService:



    def get_last_risk(self, product_id):


        conn = sqlite3.connect(DB_NAME)

        cursor = conn.cursor()



        cursor.execute(
            """
            SELECT
                risk_score,
                risk_level,
                reasons,
                created_at

            FROM risk_history

            WHERE product_id = ?

            ORDER BY id DESC

            LIMIT 2
            """,

            (
                str(product_id),
            )
        )



        result = cursor.fetchall()


        conn.close()



        return result





    def compare_risk(self, product_id):


        history = self.get_last_risk(
            product_id
        )



        if len(history) < 2:

            return {

                "status": "first_check",

                "message": "Недостаточно данных для сравнения"

            }



        current = history[0]

        previous = history[1]



        current_score = current[0]

        previous_score = previous[0]



        difference = (
            current_score - previous_score
        )



        if difference < 0:

            message = "Риск снизился"

        elif difference > 0:

            message = "Риск вырос"

        else:

            message = "Изменений нет"



        return {

            "status": "ok",

            "previous": previous,

            "current": current,

            "difference": difference,

            "message": message

        }