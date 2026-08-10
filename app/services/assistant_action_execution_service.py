class AssistantActionExecutionService:


    def __init__(
        self,
        history_service,
        task_service=None
    ):

        self.history_service = (
            history_service
        )

        self.task_service = (
            task_service
        )



    def execute(
        self,
        actions
    ):


        saved = []


        for action in actions:


            result = (
                self.history_service
                .save_action(
                    action
                )
            )


            if not result["error"]:

                saved.append(
                    action
                )



        return {

            "error": False,

            "executed":
                saved,

            "count":
                len(
                    saved
                )
        }



    def execute_current_action(
        self,
        user_id
    ):


        if (
            not self.task_service
            or not user_id
        ):

            return {

                "error": True,

                "message":
                    "Task service не подключён"
            }



        current = (
            self.task_service
            .get_current_action(
                user_id
            )
        )


        action = (
            current.get(
                "action"
            )
        )



        if not action:


            next_action = (
                self.task_service
                .get_next_action(
                    user_id
                )
            )


            action = (
                next_action
                .get(
                    "action"
                )
            )



        if not action:

            return {

                "error": False,

                "message":
                    "Нет действий для выполнения"
            }



        start = (
            self.task_service
            .start_action(
                user_id,

                action["title"]
            )
        )


        if start["error"]:

            return start



        history_result = (
            self.history_service
            .save_action(
                action
            )
        )



        if history_result["error"]:

            return history_result



        complete = (
            self.task_service
            .complete_action(
                user_id,

                action["title"]
            )
        )



        return {

            "error": False,

            "message":
                "Действие выполнено",

            "action":
                action,

            "completed":
                complete
        }