class RecommendationEngine:


    def generate(self, metrics, risk):

        recommendations = []


        if not metrics.get("has_fbs_stocks"):

            recommendations.append(
                {
                    "priority": "Средний",
                    "action": "Проверить подключение FBS",
                    "reason": "Нет FBS остатков"
                }
            )


        if not metrics.get("is_discounted"):

            recommendations.append(
                {
                    "priority": "Низкий",
                    "action": "Рассмотреть запуск акции",
                    "reason": "Нет активной скидки"
                }
            )


        if metrics.get("archived"):

            recommendations.append(
                {
                    "priority": "Высокий",
                    "action": "Проверить статус товара",
                    "reason": "Товар находится в архиве"
                }
            )


        if risk.get("risk_score", 0) >= 50:

            recommendations.append(
                {
                    "priority": "Высокий",
                    "action": "Требуется срочная проверка",
                    "reason": "Высокий уровень риска"
                }
            )


        if not recommendations:

            recommendations.append(
                {
                    "priority": "Нет",
                    "action": "Изменений не требуется",
                    "reason": "Показатели товара стабильны"
                }
            )


        return recommendations