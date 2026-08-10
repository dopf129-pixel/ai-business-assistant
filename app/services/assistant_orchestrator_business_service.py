class AssistantOrchestratorBusinessService:


    def __init__(
        self,
        business_flow_service,
        task_service=None,
        execution_service=None
    ):

        self.business_flow_service = (
            business_flow_service
        )

        self.task_service = (
            task_service
        )

        self.execution_service = (
            execution_service
        )



    def handle(
        self,
        text,
        report,
        context=None,
        user_id=None
    ):


        result = (
            self.business_flow_service
            .process(
                text,
                report,
                context,
                user_id
            )
        )



        if result.get(
            "error"
        ):

            return result



        command = (
            result.get(
                "intent",
                {}
            )
            .get(
                "command"
            )
        )



        if command == "confirm_execute":


            return result





        if command == "execute":


            return result





        if command == "continue":


            task = (
                result.get(
                    "continued_task",
                    ""
                )
            )



            if not task and context:


                if "context" in context:

                    task = (
                        context["context"]
                        .get(
                            "current_task",
                            ""
                        )
                    )

                else:

                    task = (
                        context
                        .get(
                            "current_task",
                            ""
                        )
                    )



            return {

                "error": False,

                "message":
                    "Продолжаем работу",

                "task":
                    task,

                "next_step":
                    result.get(
                        "next_action"
                    )
            }





        return {

            "error": False,

            "message":
                "Бизнес-план создан",

            "actions":
                result.get(
                    "plan",
                    []
                ),

            "count":
                result.get(
                    "count",
                    0
                )
        }