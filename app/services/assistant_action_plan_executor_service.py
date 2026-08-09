class AssistantActionPlanExecutorService:


    def __init__(
        self,
        priority_service,
        action_generator_service,
        execution_service
    ):

        self.priority_service = priority_service
        self.action_generator_service = action_generator_service
        self.execution_service = execution_service



    def execute_plan(
        self,
        plan
    ):

        generated = (
            self.action_generator_service
            .generate(
                plan
            )
        )


        if generated["error"]:

            return generated


        prioritized = []


        for action in generated["actions"]:

            result = (
                self.priority_service
                .resolve(
                    action
                )
            )

            prioritized.append(
                result["action"]
            )


        executed = (
            self.execution_service
            .execute(
                prioritized
            )
        )


        return {
            "error": False,
            "actions": executed["executed"],
            "count": executed["count"]
        }