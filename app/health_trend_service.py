import sqlite3


DB_NAME = "ozon_assistant.db"


class HealthTrendService:


    def __init__(self):

        pass



    def calculate(self, product_id):


        conn = sqlite3.connect(
            DB_NAME
        )


        cursor = conn.cursor()


        cursor.execute(
            """
            SELECT
                score

            FROM health_history

            WHERE product_id = ?

            ORDER BY id DESC

            LIMIT 2
            """,
            (
                str(product_id),
            )
        )


        rows = cursor.fetchall()


        conn.close()



        if len(rows) == 0:


            return {

                "current": 0,

                "previous": 0,

                "change": 0,

                "status": "Нет данных"

            }



        current = rows[0][0]


        if len(rows) > 1:

            previous = rows[1][0]

        else:

            previous = current



        change = current - previous



        if change > 0:


            status = "🔴 Ухудшается"



        elif change < 0:


            status = "🟢 Улучшается"



        else:


            status = "🟡 Стабильно"




        return {


            "current": current,


            "previous": previous,


            "change": change,


            "status": status


        }