from services.store_period_runner_service import (
    StorePeriodRunnerService
)


class StorePeriodSummaryService:

    def __init__(
        self,
        period_runner=None
    ):

        self.period_runner = (
            period_runner
            or StorePeriodRunnerService()
        )


    def build(
        self,
        period_code,
        date_to,
        products
    ):

        report = (
            self.period_runner
            .build_store_period_report(
                period_code=period_code,
                date_to=date_to,
                products=products
            )
        )

        if not isinstance(report, dict):

            return {
                "error": True,
                "message": "Не удалось построить периодический отчёт"
            }


        if report.get(
            "error"
        ):

            return {
                "error": True,
                "message": report.get(
                    "message",
                    "Не удалось построить периодический отчёт"
                )
            }


        comparison = (
            report.get(
                "comparison",
                {}
            )
        )


        return {
            "error": False,
            "period": {
                "code": period_code,
                "date_to": str(
                    date_to
                )
            },
            "comparison": comparison,
            "raw": report
        }


    def print_summary(
        self,
        summary
    ):

        if summary.get(
            "error"
        ):

            print(
                summary.get(
                    "message",
                    "Ошибка периодического отчёта"
                )
            )

            return


        print()
        print(
            "================================"
        )
        print(
            "Сравнение периодов"
        )
        print(
            "================================"
        )

        print(
            summary.get(
                "comparison",
                {}
            )
        )