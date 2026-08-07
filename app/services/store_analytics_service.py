from services.analysis_period_service import (
    AnalysisPeriodService
)

from services.business_analytics_service import (
    BusinessAnalyticsService
)

from services.finance_analytics_service import (
    FinanceAnalyticsService
)

from services.period_comparison_service import (
    PeriodComparisonService
)


class StoreAnalyticsService:

    def __init__(
        self,
        tax_mode,
        tax_rate,
        minimum_tax_rate,
        advertising_cost,
        period_code="TODAY",
        date_to=None,
        analysis_date=None,
        expense_repository=None,
        finance_service=None,
        comparison_service=None
    ):

        self.period_service = (
            AnalysisPeriodService()
        )

        self.comparison_service = (
            comparison_service
            or PeriodComparisonService()
        )


        # Совместимость со старым запуском
        if analysis_date:

            self.period = {
                "error": False,
                "code": "TODAY",
                "label": "Сегодня",
                "days": 1,
                "date_from": str(
                    analysis_date
                ),
                "date_to": str(
                    analysis_date
                )
            }

        else:

            self.period = (
                self.period_service
                .get_period(
                    period_code=period_code,
                    date_to=date_to
                )
            )


        if self.period.get(
            "error"
        ):

            self.business_analytics = None
            self.finance_analytics = None

            return


        self.business_analytics = (
            BusinessAnalyticsService(
                tax_mode=tax_mode,
                tax_rate=tax_rate,
                minimum_tax_rate=minimum_tax_rate,
                advertising_cost=advertising_cost,
                date_from=self.period.get(
                    "date_from"
                ),
                date_to=self.period.get(
                    "date_to"
                ),
                expense_repository=(
                    expense_repository
                )
            )
        )


        self.finance_analytics = None

        if finance_service:

            self.finance_analytics = (
                FinanceAnalyticsService(
                    finance_service
                )
            )


    def get_period(
        self
    ):

        return self.period


    def get_previous_period(
        self
    ):

        if self.period.get(
            "error"
        ):

            return self.period


        return (
            self.period_service
            .get_previous_period(
                period_code=self.period.get(
                    "code"
                ),
                date_to=self.period.get(
                    "date_to"
                )
            )
        )


    def compare_periods(
        self,
        current_result,
        previous_result
    ):

        return (
            self.comparison_service
            .compare(
                current_result,
                previous_result
            )
        )


    def analyze(
        self,
        profits,
        previous_result=None
    ):

        if self.period.get(
            "error"
        ):

            return {
                "error": True,
                "message": self.period.get(
                    "message",
                    "Ошибка периода анализа"
                )
            }


        result = (
            self.business_analytics
            .calculate(
                profits
            )
        )


        result[
            "analysis_period"
        ] = self.period


        if previous_result:

            result[
                "comparison"
            ] = (
                self.compare_periods(
                    result,
                    previous_result
                )
            )


        return result


    def analyze_finance(
        self,
        sku=None
    ):

        if not self.finance_analytics:

            return {
                "error": True,
                "message": (
                    "FinanceService не подключён"
                )
            }


        return (
            self.finance_analytics
            .get_period_finance(
                date_from=self.period.get(
                    "date_from"
                ),
                date_to=self.period.get(
                    "date_to"
                ),
                sku=sku
            )
        )


    def print_period(
        self,
        period=None
    ):

        period = (
            period
            or self.period
        )

        print()

        print(
            "========================="
        )

        print(
            "Период анализа"
        )

        print(
            "========================="
        )

        print()

        print(
            period.get(
                "label",
                "Нет данных"
            )
        )

        if period.get(
            "date_from"
        ):

            print(
                "С:",
                period.get(
                    "date_from"
                )
            )

        print(
            "По:",
            period.get(
                "date_to"
            )
        )


    def print_comparison(
        self,
        comparison
    ):

        if not comparison:
            return


        if comparison.get(
            "error"
        ):

            return


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


        items = comparison.get(
            "comparison",
            {}
        )


        for item in items.values():

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


    def print_dashboards(
        self,
        result
    ):

        if result.get(
            "error"
        ):

            print()

            print(
                "AI Store Analytics"
            )

            print()

            print(
                result.get(
                    "message",
                    "Ошибка анализа"
                )
            )

            return


        self.print_period(
            result.get(
                "analysis_period",
                self.period
            )
        )


        self.print_comparison(
            result.get(
                "comparison"
            )
        )


        print()


        self.business_analytics.print_dashboards(
            result
        )