class AssistantBusinessPlannerService:


    def __init__(
        self,
        recommendation_service,
        planning_service,
        executor_service,
        task_service=None
    ):

        self.recommendation_service = (
            recommendation_service
        )

        self.planning_service = (
            planning_service
        )

        self.executor_service = (
            executor_service
        )

        self.task_service = (
            task_service
        )


    @staticmethod
    def _error_result(
        message
    ):

        return {
            "error": True,
            "message": message,
            "actions": [],
            "count": 0
        }


    @staticmethod
    def _valid_error_flag(
        payload
    ):

        return (
            isinstance(
                payload,
                dict
            )
            and
            isinstance(
                payload.get(
                    "error"
                ),
                bool
            )
        )


    def build_plan(
        self,
        report,
        user_id=None
    ):

        recommendations = (
            self.recommendation_service
            .analyze(
                report
            )
        )

        if not self._valid_error_flag(
            recommendations
        ):

            return self._error_result(
                "INVALID_RECOMMENDATION_RESULT"
            )


        if recommendations["error"]:

            return recommendations


        recommendation_items = (
            recommendations.get(
                "recommendations"
            )
        )


        if not isinstance(
            recommendation_items,
            list
        ):

            return self._error_result(
                "INVALID_RECOMMENDATION_RESULT"
            )


        actionable_recommendations = [
            item
            for item in recommendation_items
            if isinstance(
                item,
                dict
            )
            and item.get(
                "type"
            ) != "general"
        ]


        if not actionable_recommendations:

            return {
                "error": False,
                "recommendations": recommendation_items,
                "actions": [],
                "count": 0
            }


        plan = (
            self.planning_service
            .build_plan(
                actionable_recommendations
            )
        )


        if not self._valid_error_flag(
            plan
        ):

            return self._error_result(
                "INVALID_PLANNING_RESULT"
            )


        if plan["error"]:

            return plan


        plan_items = (
            plan.get(
                "plan"
            )
        )


        if not isinstance(
            plan_items,
            list
        ):

            return self._error_result(
                "INVALID_PLANNING_RESULT"
            )


        result = (
            self.executor_service
            .execute_plan(
                plan_items
            )
        )


        if not self._valid_error_flag(
            result
        ):

            return self._error_result(
                "INVALID_PLAN_EXECUTION_RESULT"
            )


        if result["error"]:

            return result


        actions = (
            result.get(
                "actions"
            )
        )


        count = (
            result.get(
                "count"
            )
        )


        if (
            not isinstance(
                actions,
                list
            )
            or
            not all(
                isinstance(
                    item,
                    dict
                )
                for item in actions
            )
            or
            isinstance(
                count,
                bool
            )
            or
            not isinstance(
                count,
                int
            )
            or
            count < 0
            or
            count
            !=
            len(
                actions
            )
        ):

            return self._error_result(
                "INVALID_PLAN_EXECUTION_RESULT"
            )


        if (
            self.task_service
            and user_id
            and actions
        ):

            task_result = (
                self.task_service
                .create_task(
                    user_id,
                    "Создание плана действий",
                    actions
                )
            )


            if not self._valid_error_flag(
                task_result
            ):

                return self._error_result(
                    "INVALID_TASK_CREATION_RESULT"
                )


            if task_result["error"]:

                return task_result


        return {
            "error": False,
            "recommendations": recommendation_items,
            "actions": actions,
            "count": count
        }
