from database import (
    get_actions,
    update_action_status
)


class ActionAutomationService:

    def __init__(self):
        pass

    def execute(self, product_id):
        """
        Выполняет все новые действия для товара.
        """
        actions = get_actions(product_id)

        if not actions:
            return []

        results = []

        for action in actions:

            action_id = action[0]
            action_name = action[2]
            status = action[5]

            # выполняем только новые действия
            if status != "🟡 Новое":
                continue

            result = self.execute_action(action_name)

            update_action_status(
                action_id,
                "🟢 Выполнено"
            )

            results.append(result)

        return results

    def execute_action(self, action):

        if "FBS" in action:
            return "Выполнено: Требуется ручная проверка FBS"

        if "акции" in action:
            return "Выполнено: Подготовлена рекомендация акции"

        if "анализ" in action:
            return "Выполнено: Создан запрос глубокого анализа"

        return "Выполнено: Требуется ручная проверка"