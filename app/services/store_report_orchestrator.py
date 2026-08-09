class StoreReportOrchestrator:

    def __init__(
        self,
        summary_service,
        insight_service,
        formatter
    ):

        self.summary_service = (
            summary_service
        )

        self.insight_service = (
            insight_service
        )

        self.formatter = (
            formatter
        )


    def build(
        self,
        period_code,
        date_to,
        products
    ):

        summary = (
            self.summary_service
            .build(
                period_code=period_code,
                date_to=date_to,
                products=products
            )
        )


        if summary.get(
            "error"
        ):

            return {
                "error": True,
                "message": summary.get(
                    "message",
                    "Не удалось построить отчёт"
                ),
                "period_summary": summary
            }


        insights = (
            self.insight_service
            .analyze(
                summary
            )
        )


        text = (
            self.formatter
            .format(
                summary
            )
        )


        return {
            "error": False,
            "period_summary": summary,
            "period_insights": insights,
            "period_text": text
        }