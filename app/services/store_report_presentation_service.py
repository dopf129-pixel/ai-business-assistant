class StoreReportPresentationService:

    def __init__(
        self,
        dashboard_service
    ):

        self.dashboard_service = (
            dashboard_service
        )


    def build(
        self,
        report
    ):

        return (
            self.dashboard_service
            .build(
                report
            )
        )