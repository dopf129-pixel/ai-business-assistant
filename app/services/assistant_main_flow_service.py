class AssistantMainFlowService:


    def __init__(
        self,
        business_service,
        response_service=None
    ):

        self.business_service = (
            business_service
        )

        self.response_service = (
            response_service
        )



    def process(
        self,
        text,
        report,
        context=None
    ):


        result = (
            self.business_service
            .handle(
                text,
                report,
                context
            )
        )



        if result["error"]:

            return result



        if self.response_service:

            return (
                self.response_service
                .build(
                    result
                )
            )



        return {
            "error": False,
            "response": result
        }