class ActionPlanner:



    def create_plan(
        self,
        recommendations
    ):


        plan = []



        for item in recommendations:


            priority = item.get(
                "priority"
            )



            if priority == "Высокий":

                urgency = "Срочно"

                impact = "Высокое"


            elif priority == "Средний":

                urgency = "Сегодня"

                impact = "Среднее"


            elif priority == "Низкий":

                urgency = "В течение недели"

                impact = "Низкое"


            else:

                urgency = "Не требуется"

                impact = "Нет"



            plan.append(
                {
                    "action": item.get("action"),

                    "reason": item.get("reason"),

                    "priority": priority,

                    "urgency": urgency,

                    "impact": impact
                }
            )



        return plan