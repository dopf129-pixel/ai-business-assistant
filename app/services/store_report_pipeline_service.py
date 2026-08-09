class StoreReportPipelineService:

    def __init__(
        self,
        report_manager,
        history_service
    ):

        self.report_manager = (
            report_manager
        )

        self.history_service = (
            history_service
        )


    def build_and_save(
        self,
        period_code,
        date_to,
        products
    ):

        report = (
            self.report_manager
            .build_store_report(
                period_code=period_code,
                date_to=date_to,
                products=products
            )
        )


        if report.get(
            "error"
        ):

            return report


        self.history_service.save_report(
            report
        )


        return report