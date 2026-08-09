class AssistantBusinessPlannerService:


    def __init__(
        self,
        recommendation_service,
        planning_service,
        executor_service
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


    def build_plan(
        self,
        report
    ):

        recommendations = (
            self.recommendation_service
            .analyze(
                report
            )
        )


        if recommendations["error"]:

            return recommendations


        plan = (
            self.planning_service
            .build_plan(
                recommendations["recommendations"]
            )
        )


        if plan["error"]:

            return plan


        result = (
            self.executor_service
            .execute_plan(
                plan["plan"]
            )
        )


        return {
            "error": False,
            "recommendations": (
                recommendations["recommendations"]
            ),
            "actions": (
                result["actions"]
            ),
            "count": (
                result["count"]
            )
        }