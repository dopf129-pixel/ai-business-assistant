class ActionService:

    def build(
        self,
        recommendations
    ):

        if not recommendations:

            return {
                "error": False,
                "actions": []
            }


        actions = []


        for item in recommendations:

            actions.append(
                {
                    "title": item.get(
                        "title"
                    ),
                    "type": "GENERAL",
                    "status": "NEW"
                }
            )


        return {
            "error": False,
            "actions": actions
        }