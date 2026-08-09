class AssistantIntentService:


    def detect(
        self,
        text
    ):

        text = (
            text.lower()
            .strip()
        )


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
        ):

            return {
                "error": False,
                "intent": "actions",
                "command": "actions"
            }


        return {
            "error": True,
            "message": "Не удалось определить намерение"
        }