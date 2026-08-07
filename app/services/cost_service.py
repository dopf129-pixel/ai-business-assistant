import sqlite3


DB_NAME = "ozon_assistant.db"


class ProductCostService:

    def __init__(self):

        self.create_table()

    def get_connection(self):

        return sqlite3.connect(DB_NAME)

    def create_table(self):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_costs (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                product_id TEXT UNIQUE,

                sku TEXT,

                offer_id TEXT,

                cost_price REAL NOT NULL,

                currency TEXT DEFAULT 'RUB',

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()
        conn.close()

    def set_cost(
        self,
        product_id,
        sku,
        offer_id,
        cost_price,
        currency="RUB"
    ):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO product_costs (

                product_id,
                sku,
                offer_id,
                cost_price,
                currency

            )

            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(product_id)

            DO UPDATE SET

                sku = excluded.sku,
                offer_id = excluded.offer_id,
                cost_price = excluded.cost_price,
                currency = excluded.currency,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(product_id),
                str(sku),
                str(offer_id),
                float(cost_price),
                currency
            )
        )

        conn.commit()
        conn.close()

    def get_cost(
        self,
        product_id
    ):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT

                product_id,
                sku,
                offer_id,
                cost_price,
                currency,
                updated_at

            FROM product_costs

            WHERE product_id = ?
            """,
            (
                str(product_id),
            )
        )

        row = cursor.fetchone()

        conn.close()

        return row

    def get_all_costs(self):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT

                product_id,
                sku,
                offer_id,
                cost_price,
                currency,
                updated_at

            FROM product_costs

            ORDER BY offer_id
            """
        )

        rows = cursor.fetchall()

        conn.close()

        return rows

    def delete_cost(
        self,
        product_id
    ):

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM product_costs
            WHERE product_id = ?
            """,
            (
                str(product_id),
            )
        )

        conn.commit()
        conn.close()