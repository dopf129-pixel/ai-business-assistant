class AssistantPlanCorrectionService:


    def __init__(
        self
    ):

        pass



    def correct(
        self,
        actions
    ):


        corrected_plan = []


        for action in actions:


            status = action.get(
                "status"
            )


            if status == "FAILED":


                corrected_plan.append(

                    {

                        "title":
                            action.get(
                                "title"
                            ),

                        "type":
                            action.get(
                                "type",
                                "recovery"
                            ),

                        "status":
                            "NEW",

                        "corrected":
                            True

                    }

                )


            else:


                corrected_plan.append(
                    action
                )



        return {

            "error":
                False,

            "plan":
                corrected_plan

        }