from services.analysis_period_service import (
    AnalysisPeriodService
)


from services.store_period_report_service import (
    StorePeriodReportService
)


class StorePeriodRunnerService:
    def __init__(
        self,
        report_service=None,
        profit_service=None
    ):

        self.period_service = (
            AnalysisPeriodService()
        )

        self.report_service = (
            report_service
            or StorePeriodReportService(
                profit_service=profit_service
            )
        )


    def build_store_period_report(
        self,
        period_code,
        date_to,
        products
    ):

        current_period = (
            self.period_service
            .get_period(
                period_code,
                date_to
            )
        )


        if current_period.get(
            "error"
        ):

            return current_period


        previous_period = (
            self.period_service
            .get_previous_period(
                period_code,
                date_to
            )
        )


        if previous_period.get(
            "error"
        ):

            return previous_period


        return (
            self.report_service
            .build(
                current_period=current_period,
                previous_period=previous_period,
                products=products
            )
        )
