class SalesIntelligenceService:


    def __init__(
        self,
        analytics_service
    ):

        self.analytics_service = (
            analytics_service
        )


    def analyze(
        self,
        profits,
        previous_result=None
    ):

        result = (
            self.analytics_service
            .analyze(
                profits,
                previous_result=previous_result
            )
        )

        if result.get(
            "error"
        ):

            return result


        store_profit = (
            result.get(
                "store_profit",
                {}
            )
        )

        business_profit = (
            result.get(
                "business_profit",
                {}
            )
        )

        metrics = {
            "revenue": store_profit.get(
                "gross_sales",
                0
            ),
            "gross_profit": store_profit.get(
                "gross_profit",
                0
            ),
            "business_profit": business_profit.get(
                "business_profit",
                0
            ),
            "margin_percent": business_profit.get(
                "margin_percent",
                0
            )
        }

        comparison = result.get(
            "comparison"
        )

        insights = (
            self.build_insights(
                comparison
            )
        )

        return {
            "error": False,
            "metrics": metrics,
            "comparison": comparison,
            "insights": insights,
            "analysis": result
        }


    def build_insights(
        self,
        comparison
    ):

        if (
            not comparison
            or comparison.get(
                "error"
            )
        ):

            return []

        revenue = (
            comparison.get(
                "comparison",
                {}
            )
            .get(
                "revenue"
            )
        )

        if not revenue:

            return []

        change = revenue.get(
            "change_percent",
            0
        )

        if change < 0:

            return [
                {
                    "type": "sales_decline",
                    "severity": "attention",
                    "change_percent": change,
                    "message": "Продажи снизились относительно предыдущего периода"
                }
            ]

        if change > 0:

            return [
                {
                    "type": "sales_growth",
                    "severity": "positive",
                    "change_percent": change,
                    "message": "Продажи выросли относительно предыдущего периода"
                }
            ]

        return [
            {
                "type": "sales_stable",
                "severity": "neutral",
                "change_percent": change,
                "message": "Продажи не изменились относительно предыдущего периода"
            }
        ]
