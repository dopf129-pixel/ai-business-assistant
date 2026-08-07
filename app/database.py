import sqlite3


DB_NAME = "ozon_assistant.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            offer_id TEXT,
            sku TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics (
            product_id TEXT,
            offer_id TEXT,
            has_fbo_stocks INTEGER,
            has_fbs_stocks INTEGER,
            archived INTEGER,
            is_discounted INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            risk_score INTEGER,
            risk_level TEXT,
            reasons TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            priority TEXT,
            action TEXT,
            reason TEXT,
            impact TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            health_score INTEGER,
            risk_score INTEGER,
            has_fbo_stocks INTEGER,
            is_discounted INTEGER,
            snapshot_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(product_id, snapshot_date)
        )
        """
    )

    conn.commit()
    conn.close()


def save_product(product):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO products (
            id,
            offer_id,
            sku
        )
        VALUES (?, ?, ?)
        """,
        (
            str(product["product_id"]),
            product.get("offer_id"),
            str(product.get("sku"))
        )
    )

    conn.commit()
    conn.close()


def get_products():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            offer_id,
            sku
        FROM products
        """
    )

    result = cursor.fetchall()

    conn.close()

    return result


def save_metric(metrics):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO metrics (
            product_id,
            offer_id,
            has_fbo_stocks,
            has_fbs_stocks,
            archived,
            is_discounted
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(metrics.get("product_id")),
            metrics.get("offer_id"),
            int(bool(metrics.get("has_fbo_stocks"))),
            int(bool(metrics.get("has_fbs_stocks"))),
            int(bool(metrics.get("archived"))),
            int(bool(metrics.get("is_discounted")))
        )
    )

    conn.commit()
    conn.close()


def save_risk(risk, product_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO risk_history (
            product_id,
            risk_score,
            risk_level,
            reasons
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            str(product_id),
            int(risk.get("risk_score", 0)),
            risk.get("risk_level", ""),
            "; ".join(risk.get("reasons", []))
        )
    )

    conn.commit()
    conn.close()


def save_action(product_id, decision):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO actions (
            product_id,
            priority,
            action,
            reason,
            impact,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(product_id),
            decision.get("priority"),
            decision.get("action"),
            decision.get("reason"),
            decision.get("impact"),
            "🟡 Новое"
        )
    )

    conn.commit()
    conn.close()


def get_actions(product_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            priority,
            action,
            reason,
            impact,
            status,
            created_at
        FROM actions
        WHERE product_id = ?
        ORDER BY id DESC
        """,
        (
            str(product_id),
        )
    )

    rows = cursor.fetchall()

    conn.close()

    return rows


def update_action_status(action_id, status):

    conn = get_connection()
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