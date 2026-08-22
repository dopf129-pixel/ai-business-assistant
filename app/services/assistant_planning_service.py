class AssistantPlanningService:


    def __init__(
        self,
        memory_service=None
    ):

        self.memory_service = (
            memory_service
        )



    def create_plan(
        self,
        request
    ):


        recommendations = [

            {

                "message":
                    request,

                "type":
                    "task"

            }

        ]


        return (
            self.build_plan(
                recommendations
            )
        )



    def build_plan(
        self,
        recommendations
    ):


        plan = []


        memory_context = []


        for item in recommendations:


            action = (
                item.get(
                    "message"
                )
            )


            plan.append(

                {

                    "step":
                        len(plan) + 1,

                    "action":
                        action,

                    "type":
                        item.get(
                            "type"
                        ),

                    "context":
                        dict(
                            item.get(
                                "context"
                            )
                            or
                            {}
                        )

                }

            )


            if self.memory_service:


                memories = (
                    self.memory_service
                    .recall(
                        action
                    )
                )


                if memories:

                    memory_context.extend(
                        memories
                    )



        return {

            "error":
                False,

            "plan":
                plan,

            "memory":
                memory_context,

            "count":
                len(
                    plan
                )

        }