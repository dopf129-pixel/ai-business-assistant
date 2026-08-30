from services.store_comparison_report_service import (
    StoreComparisonReportService
)


class StorePeriodReportService:

    def __init__(
        self,
        profit_service,
        comparison_report_service=None
    ):

        self.profit_service = (
            profit_service
        )

        self.comparison_report = (
            comparison_report_service
            or StoreComparisonReportService()
        )


    def build(
        self,
        current_period,
        previous_period,
        products
    ):

        if not current_period:

            return {
                "error": True,
                "message": (
                    "Нет текущего периода"
                )
            }


        if not previous_period:

            return {
                "error": True,
                "message": (
                    "Нет предыдущего периода"
                )
            }


        if self.profit_service is None:

            return {
                "error": True,
                "message": (
                    "Сервис расчёта прибыли периода недоступен"
                )
            }


        current = (
            self.profit_service
            .calculate_period_profit(
                current_period.get(
                    "date_from"
                ),
                current_period.get(
                    "date_to"
                ),
                products
            )
        )


        if current.get(
            "error"
        ):

            return current


        previous = (
            self.profit_service
            .calculate_period_profit(
                previous_period.get(
                    "date_from"
                ),
                previous_period.get(
                    "date_to"
                ),
                products
            )
        )


        if previous.get(
            "error"
        ):

            return previous


        report = (
            self.comparison_report
            .build_report(
                current_result=current,
                previous_result=previous,
                current_period=current_period,
                previous_period=previous_period
            )
        )


        return report