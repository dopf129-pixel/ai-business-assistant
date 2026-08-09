class AssistantOrchestratorService:

    def __init__(
        self,
        report_service,
        action_dashboard_service,
        response_service
    ):

        self.report_service = (
            report_service
        )

        self.action_dashboard_service = (
            action_dashboard_service
        )

        self.response_service = (
            response_service
        )


    def build_response(
        self,
        period_code,
        date_to,
        products,
        actions
    ):

        report = (
            self.report_service
            .build(
                period_code=period_code,
                date_to=date_to,
                products=products
            )
        )


        if report.get(
            "error"
        ):

            return report


        dashboard = (
            self.action_dashboard_service
            .build(
                actions
            )
        )


        return (
            self.response_service
            .build(
                report,
                dashboard
            )
        )