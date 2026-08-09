class StoreReportDashboardService:

    def build(
        self,
        report
    ):

        if report.get(
            "error"
        ):

            return {
                "error": True,
                "message": report.get(
                    "message",
                    "Ошибка отчёта"
                )
            }


        summary = (
            report.get(
                "period_summary",
                {}
            )
        )


        insights = (
            report.get(
                "period_insights",
                {}
            )
        )


        return {
            "error": False,
            "period": (
                summary
                .get(
                    "period",
                    {}
                )
            ),
            "insights": (
                insights
                .get(
                    "insights",
                    []
                )
            ),
            "recommendations": (
                insights
                .get(
                    "recommendations",
                    []
                )
            )
        }