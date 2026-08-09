class AssistantCommandService:

    def __init__(
        self,
        orchestrator_service
    ):

        self.orchestrator_service = (
            orchestrator_service
        )


    def execute(
        self,
        command,
        params
    ):

        if command == "report":

            return (
                self.orchestrator_service
                .build_response(
                    period_code=(
                        params.get(
                            "period_code"
                        )
                    ),
                    date_to=(
                        params.get(
                            "date_to"
                        )
                    ),
                    products=(
                        params.get(
                            "products",
                            []
                        )
                    ),
                    actions=(
                        params.get(
                            "actions",
                            []
                        )
                    )
                )
            )


        return {
            "error": True,
            "message": "Неизвестная команда"
        }