class AssistantActionRouterService:


    def __init__(
        self,
        executors=None
    ):

        self.executors = (
            executors
            or {}
        )



    def execute(
        self,
        action
    ):


        action_type = (
            action.get(
                "type"
            )
        )


        executor = (
            self.executors
            .get(
                action_type
            )
        )


        if not executor:


            return {

                "error": True,

                "message":
                    f"Исполнитель для типа {action_type} не найден"

            }


        return (
            executor.execute(
                action
            )
        )



    def run(
        self,
        action
    ):

        return (
            self.execute(
                action
            )
        )