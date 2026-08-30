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

        try:

            generated = (
                self.action_generator_service
                .generate(
                    plan
                )
            )

        except Exception:

            return self._failure(
                "ACTION_GENERATION_FAILED"
            )


        if not isinstance(
            generated,
            dict
        ):

            return self._failure(
                "INVALID_GENERATOR_RESULT"
            )


        generator_error = generated.get(
            "error"
        )

        if generator_error is True:

            return generated

        if generator_error is not False:

            return self._failure(
                "INVALID_GENERATOR_RESULT"
            )


        actions = generated.get(
            "actions"
        )

        if not isinstance(
            actions,
            (list, tuple)
        ):

            return self._failure(
                "INVALID_GENERATOR_RESULT"
            )

        if not actions:

            return self._failure(
                "EMPTY_ACTION_PLAN"
            )


        prioritized = []


        for action in actions:

            if not isinstance(
                action,
                dict
            ):

                return self._failure(
                    "INVALID_GENERATED_ACTION"
                )


            try:

                result = (
                    self.priority_service
                    .resolve(
                        action
                    )
                )

            except Exception:

                return self._failure(
                    "PRIORITY_RESOLUTION_FAILED"
                )


            if not isinstance(
                result,
                dict
            ):

                return self._failure(
                    "INVALID_PRIORITY_RESULT"
                )


            priority_error = result.get(
                "error"
            )

            if priority_error is True:

                return result

            if priority_error is not False:

                return self._failure(
                    "INVALID_PRIORITY_RESULT"
                )


            prioritized_action = result.get(
                "action"
            )

            if not isinstance(
                prioritized_action,
                dict
            ):

                return self._failure(
                    "INVALID_PRIORITY_RESULT"
                )


            prioritized.append(
                prioritized_action
            )


        try:

            executed = (
                self.execution_service
                .execute(
                    prioritized
                )
            )

        except Exception:

            return self._failure(
                "PLAN_EXECUTION_FAILED"
            )


        if not isinstance(
            executed,
            dict
        ):

            return self._failure(
                "INVALID_EXECUTION_RESULT"
            )


        execution_error = executed.get(
            "error"
        )

        if execution_error is True:

            return executed

        if execution_error is not False:

            return self._failure(
                "INVALID_EXECUTION_RESULT"
            )


        executed_actions = executed.get(
            "executed"
        )
        count = executed.get(
            "count"
        )

        if not isinstance(
            executed_actions,
            list
        ):

            return self._failure(
                "INVALID_EXECUTION_RESULT"
            )

        if (
            isinstance(
                count,
                bool
            )
            or not isinstance(
                count,
                int
            )
            or count < 0
            or count != len(
                executed_actions
            )
        ):

            return self._failure(
                "INVALID_EXECUTION_RESULT"
            )

        if not all(
            isinstance(
                item,
                dict
            )
            for item in executed_actions
        ):

            return self._failure(
                "INVALID_EXECUTION_RESULT"
            )


        return {
            "error": False,
            "actions": executed_actions,
            "count": count
        }


    def _failure(
        self,
        code
    ):

        return {
            "error": True,
            "message": code,
            "actions": [],
            "count": 0
        }
