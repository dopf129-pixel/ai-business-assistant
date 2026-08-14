class AssistantActionGeneratorService:


    def __init__(
        self,
        memory_service=None
    ):

        self.memory_service = (
            memory_service
        )



    def generate(
        self,
        request
    ):


        memory_context = []


        if self.memory_service:

            memory_context = (
                self.memory_service
                .recall(
                    request
                )
            )



        if isinstance(
            request,
            list
        ):

            actions = request


        elif isinstance(
            request,
            dict
        ):

            actions = [
                request
            ]


        else:

            actions = [

                {

                    "message":
                        request,

                    "type":
                        "task"

                }

            ]



        normalized_actions = []



        for item in actions:


            action = dict(
                item
            )


            action.setdefault(
                "title",
                action.get(
                    "message",
                    "task"
                )
            )


            action.setdefault(
                "message",
                action["title"]
            )


            action.setdefault(
                "type",
                "task"
            )


            action.setdefault(
                "priority",
                "NORMAL"
            )


            action.setdefault(
                "reason",
                "Generated action"
            )


            action.setdefault(
                "context",
                {}
            )


            action["context"]["reason"] = (
                action["reason"]
            )


            action["memory_context"] = (
                memory_context
            )


            normalized_actions.append(
                action
            )



        return {

            "error":
                False,

            "action":
                normalized_actions[0],

            "actions":
                normalized_actions,

            "memory":
                memory_context

        }