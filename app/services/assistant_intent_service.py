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
            "да" == text
            or
            "давай" == text
            or
            "подтверждаю" in text
            or
            "выполняй" in text
            or
            "запускай" in text
        ):


            return {

                "error": False,

                "intent":
                    "confirm_execute",

                "command":
                    "confirm_execute"
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

                "intent":
                    "execute",

                "command":
                    "execute"
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

                "intent":
                    "report",

                "command":
                    "report"
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

                "intent":
                    "actions",

                "command":
                    "actions"
            }



        if (
            "продолж" in text
            or
            "дальше" in text
            or
            "далее" in text
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



            if current_task:


                return {

                    "error": False,

                    "intent":
                        "continue",

                    "command":
                        "continue",

                    "task":
                        current_task
                }



        return {

            "error": True,

            "message":
                "Не удалось определить намерение"
        }