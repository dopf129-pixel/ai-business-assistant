from services.period_comparison_service import (
    PeriodComparisonService
)


class StoreComparisonReportService:

    def __init__(
        self,
        comparison_service=None
    ):

        self.comparison_service = (
            comparison_service
            or PeriodComparisonService()
        )


    def build_report(
        self,
        current_result,
        previous_result,
        current_period=None,
        previous_period=None
    ):

        if not current_result:

            return {
                "error": True,
                "message": (
                    "Нет текущего результата"
                )
            }


        if not previous_result:

            return {
                "error": True,
                "message": (
                    "Нет предыдущего результата"
                ),
                "current": current_result
            }


        comparison = (
            self.comparison_service
            .compare(
                current_result,
                previous_result
            )
        )


        return {
            "error": False,

            "current_period": (
                current_period
            ),

            "previous_period": (
                previous_period
            ),

            "current": (
                current_result
            ),

            "previous": (
                previous_result
            ),

            "comparison": comparison
        }


    def print_report(
        self,
        report
    ):

        if report.get(
            "error"
        ):

            print(
                report.get(
                    "message",
                    "Ошибка отчёта"
                )
            )

            return


        comparison = report.get(
            "comparison",
            {}
        )


        print()

        print(
            "========================="
        )

        print(
            "Сравнение периодов"
        )

        print(
            "========================="
        )

        print()


        print(
            comparison.get(
                "status",
                ""
            )
        )


        for item in comparison.get(
            "comparison",
            {}
        ).values():

            print()

            print(
                item.get(
                    "name"
                )
            )

            print(
                item.get(
                    "trend"
                ),
                item.get(
                    "change_percent"
                ),
                "%"
            )