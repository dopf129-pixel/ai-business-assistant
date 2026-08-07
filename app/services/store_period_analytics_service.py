from services.analysis_period_service import (
    AnalysisPeriodService
)

from services.period_comparison_service import (
    PeriodComparisonService
)


class StorePeriodAnalyticsService:

    def __init__(
        self,
        store_analytics_factory
    ):

        self.period_service = (
            AnalysisPeriodService()
        )

        self.comparison_service = (
            PeriodComparisonService()
        )

        self.store_analytics_factory = (
            store_analytics_factory
        )


    def analyze_periods(
        self,
        period_code,
        date_to,
        current_profits,
        previous_profits=None
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


        current_service = (
            self.store_analytics_factory(
                current_period
            )
        )


        current_result = (
            current_service
            .analyze(
                current_profits
            )
        )


        result = {
            "error": False,
            "current_period": current_period,
            "current": current_result,
            "previous_period": previous_period
        }


        if previous_profits is None:

            result[
                "comparison"
            ] = {
                "error": True,
                "message": (
                    "Нет данных "
                    "предыдущего периода"
                )
            }

            return result


        previous_service = (
            self.store_analytics_factory(
                previous_period
            )
        )


        previous_result = (
            previous_service
            .analyze(
                previous_profits
            )
        )


        result[
            "previous"
        ] = previous_result


        result[
            "comparison"
        ] = (
            self.comparison_service
            .compare(
                current_result,
                previous_result
            )
        )


        return result


    def print_result(
        self,
        result
    ):

        if result.get(
            "error"
        ):

            print(
                result.get(
                    "message",
                    "Ошибка анализа"
                )
            )

            return


        current_period = result.get(
            "current_period",
            {}
        )

        previous_period = result.get(
            "previous_period",
            {}
        )


        print()

        print(
            "========================="
        )

        print(
            "Периоды анализа"
        )

        print(
            "========================="
        )

        print()


        print(
            "Текущий период:"
        )

        print(
            current_period.get(
                "label"
            )
        )

        print(
            current_period.get(
                "date_from"
            ),
            "→",
            current_period.get(
                "date_to"
            )
        )


        print()

        print(
            "Предыдущий период:"
        )

        print(
            previous_period.get(
                "date_from"
            ),
            "→",
            previous_period.get(
                "date_to"
            )
        )


        comparison = result.get(
            "comparison"
        )


        if comparison:

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
                    ),
                    ":",
                    item.get(
                        "change_percent"
                    ),
                    "%"
                )