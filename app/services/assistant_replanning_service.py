class AssistantReplanningService:


    def __init__(
        self
    ):

        pass



    def replan(
        self,
        failed_action
    ):


        error = failed_action.get(
            "error",
            ""
        )


        new_plan = []



        if "API" in str(error):


            new_plan = [

                {

                    "title":
                        "Повторить запрос через альтернативный источник",

                    "type":
                        "recovery",

                    "status":
                        "NEW"

                }

            ]


        else:


            new_plan = [

                {

                    "title":
                        "Повторить выполнение действия",

                    "type":
                        failed_action.get(
                            "type",
                            "unknown"
                        ),

                    "status":
                        "NEW"

                }

            ]



        return {

            "error":
                False,

            "plan":
                new_plan

        }