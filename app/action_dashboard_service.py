import sqlite3


DB_NAME = "ozon_assistant.db"


class ActionDashboardService:

    def __init__(self, limit=10):
        self.limit = limit

    def get_active_actions(
        self,
        product_id
    ):

        conn = sqlite3.connect(
            DB_NAME
        )

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                action,
                priority,
                impact,
                reason,
                status,
                created_at

            FROM actions

            WHERE product_id = ?
              AND status != '🟢 Выполнено'

            ORDER BY
                CASE priority
                    WHEN 'Высокий' THEN 1
                    WHEN 'Средний' THEN 2
                    WHEN 'Низкий' THEN 3
                    ELSE 4
                END,
                id DESC

            LIMIT ?
            """,
            (
                str(product_id),
                self.limit
            )
        )

        result = cursor.fetchall()

        conn.close()

        return result

    def get_recent_actions(
        self,
        product_id
    ):

        conn = sqlite3.connect(
            DB_NAME
        )

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                action,
                priority,
                impact,
                reason,
                status,
                created_at

            FROM actions

            WHERE product_id = ?

            ORDER BY id DESC

            LIMIT ?
            """,
            (
                str(product_id),
                self.limit
            )
        )

        result = cursor.fetchall()

        conn.close()

        return result

    def format_status(
        self,
        status
    ):

        statuses = {
            "new": "🟡 Новое",
            "done": "🟢 Выполнено",
            "cancelled": "🔴 Отменено"
        }

        return statuses.get(
            status,
            status
        )

    def print_action(
        self,
        action
    ):

        print()
        print(
            "ID:",
            action[0]
        )
        print(
            "🔥 Приоритет:",
            action[2]
        )
        print(
            "Действие:",
            action[1]
        )
        print(
            "Причина:",
            action[4]
        )
        print(
            "Влияние:",
            action[3]
        )
        print(
            "Статус:",
            self.format_status(
                action[5]
            )
        )
        print(
            "Создано:",
            action[6]
        )

    def print_dashboard(
        self,
        product_id
    ):

        active_actions = self.get_active_actions(
            product_id
        )

        recent_actions = self.get_recent_actions(
            product_id
        )

        print()
        print("=========================")
        print("AI Action Dashboard")
        print("=========================")

        print()
        print("Активные задачи:")

        if active_actions:

            for action in active_actions:
                self.print_action(action)

        else:

            print("Активных задач нет")

        print()
        print(
            f"Последние {self.limit} действий:"
        )

        if recent_actions:

            for action in recent_actions:
                self.print_action(action)

        else:

            print("Истории действий нет")