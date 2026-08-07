class StorePeriodInsightService:

    def analyze(
        self,
        period_summary
    ):

        if period_summary.get(
            "error"
        ):

            return {
                "error": True,
                "insights": [],
                "recommendations": []
            }


        comparison = (
            period_summary
            .get(
                "comparison",
                {}
            )
        )


        insights = []
        recommendations = []


        status = (
            comparison.get(
                "status"
            )
        )


        if status:

            insights.append(
                status
            )


        metrics = (
            comparison.get(
                "comparison",
                {}
            )
        )


        revenue = (
            metrics.get(
                "revenue",
                {}
            )
        )

        profit = (
            metrics.get(
                "business_profit",
                {}
            )
        )

        margin = (
            metrics.get(
                "margin",
                {}
            )
        )


        if (
            revenue.get("change_percent")
            and profit.get("change_percent")
        ):

            if (
                profit["change_percent"]
                >
                revenue["change_percent"]
            ):

                insights.append(
                    "Прибыль растёт быстрее выручки — эффективность бизнеса улучшилась."
                )


        if margin.get(
            "trend"
        ) == "Рост":

            insights.append(
                "Маржинальность увеличилась."
            )


        if (
            status
            ==
            "🟢 Бизнес растёт"
        ):

            recommendations.append(
                "Проверить товары, которые дали основной вклад в рост."
            )

            recommendations.append(
                "Оценить эффективность рекламных расходов."
            )


        return {
            "error": False,
            "insights": insights,
            "recommendations": recommendations
        }