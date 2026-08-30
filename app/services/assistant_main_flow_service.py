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
        context=None,
        user_id=None
    ):


        result = (
            self.business_service
            .handle(
                text,
                report,
                context,
                user_id
            )
        )


        if not self._valid_result(
            result
        ):

            return {
                "error": True,
                "message":
                    "INVALID_BUSINESS_SERVICE_RESULT"
            }


        if result["error"]:

            return result



        if self.response_service:

            response = (
                self.response_service
                .build(
                    result
                )
            )

            if not self._valid_result(
                response
            ):

                return {
                    "error": True,
                    "message":
                        "INVALID_RESPONSE_RESULT"
                }

            return response



        return {
            "error": False,
            "response": result
        }


    @staticmethod
    def _valid_result(
        result
    ):

        return (
            isinstance(
                result,
                dict
            )
            and
            type(
                result.get(
                    "error"
                )
            )
            is bool
        )
