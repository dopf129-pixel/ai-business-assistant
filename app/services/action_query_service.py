class ActionQueryService:

    def filter_by_status(
        self,
        actions,
        status
    ):

        result = []


        for action in actions:

            if (
                action.get(
                    "status"
                )
                ==
                status
            ):

                result.append(
                    action
                )


        return {
            "error": False,
            "actions": result,
            "count": len(
                result
            )
        }


    def get_active(
        self,
        actions
    ):

        result = []


        for action in actions:

            if (
                action.get(
                    "status"
                )
                !=
                "DONE"
            ):

                result.append(
                    action
                )


        return {
            "error": False,
            "actions": result,
            "count": len(
                result
            )
        }