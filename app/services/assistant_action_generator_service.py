class AssistantActionGeneratorService:


    def generate(
        self,
        recommendations
    ):

        actions = []


        for item in recommendations:

            title = (
                item.get(
                    "message"
                )
                or
                item.get(
                    "action"
                )
            )


            actions.append(
                {
                    "title": title,
                    "type": (
                        item.get(
                            "type"
                        )
                    ),
                    "status": "NEW"
                }
            )


        return {
            "error": False,
            "actions": actions,
            "count": len(
                actions
            )
        }