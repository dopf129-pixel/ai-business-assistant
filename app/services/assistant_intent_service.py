class AssistantIntentService:


    def detect(
        self,
        text,
        context=None
    ):


        text = (
            text.lower()
            .strip()
        )



        if (
            text == "да"
            or
            text == "давай"
            or
            "подтверждаю" in text
            or
            "выполняй" in text
            or
            "запускай" in text
        ):

            return {

                "error": False,

                "intent": "confirm_execute",

                "command": "confirm_execute"

            }



        if (
            "пропусти" in text
            or
            "пропустить" in text
            or
            "пропусти этот шаг" in text
            or
            "не делать" in text
        ):

            return {

                "error": False,

                "intent": "skip_action",

                "command": "skip_action"

            }



        if (
            "отмени" in text
            or
            "отменить" in text
            or
            "отмена задачи" in text
            or
            "закрой задачу" in text
            or
            "удали задачу" in text
        ):

            return {

                "error": False,

                "intent": "cancel_task",

                "command": "cancel_task"

            }



        if (
            "поставь на паузу" in text
            or
            "поставь задачу на паузу" in text
            or
            "пауза" in text
            or
            "приостанови задачу" in text
            or
            "останови задачу" in text
        ):

            return {

                "error": False,

                "intent": "pause_task",

                "command": "pause_task"

            }



        if (
            "продолжи задачу" in text
            or
            "возобнови задачу" in text
            or
            "сними с паузы" in text
            or
            "возобновить" in text
        ):

            return {

                "error": False,

                "intent": "resume_task",

                "command": "resume_task"

            }



        if (
            "выполни" in text
            or
            "выполнить" in text
            or
            "сделай" in text
            or
            "запусти" in text
        ):

            return {

                "error": False,

                "intent": "execute",

                "command": "execute"

            }



        if (
            "что дальше" in text
            or
            "следующий шаг" in text
            or
            "что делать дальше" in text
            or
            text == "дальше"
        ):

            return {

                "error": False,

                "intent": "task_next",

                "command": "task_next"

            }



        if (
            "статус" in text
            or
            "прогресс" in text
            or
            "состояние задачи" in text
            or
            "что по задаче" in text
            or
            "покажи задачу" in text
        ):

            return {

                "error": False,

                "intent": "task_status",

                "command": "task_status"

            }



        if (
            "детал" in text
            or
            "подробност" in text
            or
            "результат" in text
            or
            "что получилось" in text
        ):

            return {

                "error": False,

                "intent": "task_details",

                "command": "task_details"

            }



        if (
            "истори" in text
            or
            "что было сделано" in text
            or
            "покажи выполненное" in text
        ):

            return {

                "error": False,

                "intent": "task_history",

                "command": "task_history"

            }



        if (
            "отчёт" in text
            or
            "отчет" in text
            or
            "магазин" in text
            or
            "продажи" in text
        ):

            return {

                "error": False,

                "intent": "report",

                "command": "report"

            }



        if (
            "задач" in text
            or
            "действ" in text
            or
            "сделать" in text
            or
            "план" in text
        ):

            return {

                "error": False,

                "intent": "actions",

                "command": "actions"

            }



        if (
            "продолж" in text
            or
            "далее" in text
            or
            "дальше" in text
        ):


            current_task = ""


            if context:


                if "context" in context:


                    current_task = (
                        context["context"]
                        .get(
                            "current_task",
                            ""
                        )
                    )

                else:


                    current_task = (
                        context
                        .get(
                            "current_task",
                            ""
                        )
                    )



            return {

                "error": False,

                "intent": "continue",

                "command": "continue",

                "task": current_task

            }



        return {

            "error": True,

            "message": "Не удалось определить намерение"

        }