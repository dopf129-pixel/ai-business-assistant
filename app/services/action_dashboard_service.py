class ActionDashboardService:

    def __init__(
        self,
        query_service
    ):

        self.query_service = (
            query_service
        )


    def build(
        self,
        actions
    ):

        active = (
            self.query_service
            .get_active(
                actions
            )
        )


        completed = (
            self.query_service
            .filter_by_status(
                actions,
                "DONE"
            )
        )


        return {
            "error": False,
            "total": len(
                actions
            ),
            "active": active["count"],
            "completed": completed["count"],
            "actions": actions
        }