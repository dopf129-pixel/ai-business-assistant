class AssistantOrchestratorBusinessService:


    def __init__(
        self,
        business_flow_service
    ):

        self.business_flow_service = (
            business_flow_service
        )


    def handle(
        self,
        text,
        report
    ):

        result = (
            self.business_flow_service
            .process(
                text,
                report
            )
        )


        if result["error"]:

            return result


        return {
            "error": False,
            "message": "Бизнес-план создан",
            "actions": result["plan"],
            "count": result["count"]
        }