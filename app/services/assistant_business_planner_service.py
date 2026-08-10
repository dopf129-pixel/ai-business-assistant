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



        actions = (
            result["actions"]
        )



        if (
            self.task_service
            and user_id
        ):

            self.task_service.create_task(
                user_id,

                "Создание плана действий",

                actions
            )



        return {

            "error": False,

            "recommendations":
                recommendations["recommendations"],

            "actions":
                actions,

            "count":
                result["count"]
        }