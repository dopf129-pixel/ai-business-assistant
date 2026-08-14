class AssistantResponseService:


    def build(
        self,
        result
    ):


        if (
            "message" in result
            and
            result.get("message")
        ):


            return {

                "error":
                    result.get(
                        "error",
                        False
                    ),

                "message":
                    result.get(
                        "message"
                    ),

                "status":
                    result.get(
                        "status"
                    ),

                "intent":
                    result.get(
                        "intent"
                    )

            }



        report = (
            result.get(
                "report",
                result
            )
        )


        dashboard = (
            result.get(
                "dashboard",
                {}
            )
        )



        return {

            "error": False,

            "report":
                report,

            "actions":
                dashboard,

            "message":
                self.build_message(
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