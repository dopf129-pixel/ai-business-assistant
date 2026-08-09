class AssistantResponseService:

    def build(
        self,
        report,
        dashboard
    ):

        return {
            "error": False,

            "report": report,

            "actions": dashboard,

            "message": self.build_message(
                dashboard
            )
        }


    def build_message(
        self,
        dashboard
    ):

        active = (
            dashboard.get(
                "active",
                0
            )
        )


        if active:

            return (
                f"Есть активных задач: {active}"
            )


        return (
            "Активных задач нет"
        )