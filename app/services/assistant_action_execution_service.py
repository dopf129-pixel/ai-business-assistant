class AssistantActionExecutionService:


    def __init__(
        self,
        history_service,
        task_service=None,
        action_router=None
    ):

        self.history_service = (
            history_service
        )

        self.task_service = (
            task_service
        )

        self.action_router = (
            action_router
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


            if not result.get(
                "error"
            ):

                saved.append(
                    action
                )



        return {

            "error": False,

            "executed":
                saved,

            "count":
                len(saved)
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



        action = None



        pending = (
            self.task_service
            .get_pending_action(
                user_id
            )
        )


        action = (
            pending
            .get(
                "action"
            )
        )



        if not action:


            current = (
                self.task_service
                .get_current_action(
                    user_id
                )
            )


            action = (
                current
                .get(
                    "action"
                )
            )



        if not action:


            next_result = (
                self.task_service
                .get_next_action(
                    user_id
                )
            )


            action = (
                next_result
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



        self.task_service.clear_pending_action(
            user_id
        )



        start = (
            self.task_service
            .start_action(
                user_id,
                action["title"]
            )
        )



        if start.get(
            "error"
        ):

            return start



        execution_result = {

            "error": False,

            "message":
                "Действие выполнено"
        }



        if self.action_router:


            execution_result = (
                self.action_router
                .execute(
                    action
                )
            )


            if execution_result.get(
                "error"
            ):

                return execution_result



        history_result = (
            self.history_service
            .save_action(
                action
            )
        )


        if history_result.get(
            "error"
        ):

            return history_result



        complete = (
            self.task_service
            .complete_action(
                user_id,
                action["title"],
                execution_result
            )
        )



        if complete.get(
            "error"
        ):

            return complete



        next_result = (
            self.task_service
            .get_next_action(
                user_id
            )
        )


        next_action = (
            next_result
            .get(
                "action"
            )
        )



        if next_action:


            self.task_service.set_pending_action(
                user_id,
                next_action
            )



        return {

            "error": False,

            "message":
                "Действие выполнено",

            "action":
                complete.get(
                    "action",
                    action
                ),

            "execution":
                execution_result,

            "next_action":
                next_action
        }