class AssistantActionGeneratorService:


    def generate(
        self,
        recommendations
    ):

        actions = []


        for item in recommendations:

            actions.append(
                {
                    "title": (
                        item.get(
                            "message"
                        )
                    ),
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