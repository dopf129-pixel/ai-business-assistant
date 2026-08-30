from math import isfinite


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

        if not isinstance(
            result,
            dict
        ):
            return self._missing_data_result()

        if result.get(
            "error"
        ):

            return result


        store_profit = (
            result.get(
                "store_profit"
            )
        )

        if not isinstance(
            store_profit,
            dict
        ):
            store_profit = {}

        business_profit = (
            result.get(
                "business_profit"
            )
        )

        if not isinstance(
            business_profit,
            dict
        ):
            business_profit = {}

        metrics = {
            "revenue": self._number(
                store_profit.get(
                    "gross_sales"
                )
            ),
            "gross_profit": self._number(
                store_profit.get(
                    "gross_profit"
                )
            ),
            "business_profit": self._number(
                business_profit.get(
                    "business_profit"
                )
            ),
            "margin_percent": self._number(
                business_profit.get(
                    "margin_percent"
                )
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
            not isinstance(
                comparison,
                dict
            )
            or comparison.get(
                "error"
            )
        ):

            return []

        comparison_items = (
            comparison.get(
                "comparison"
            )
        )

        if not isinstance(
            comparison_items,
            dict
        ):

            return []

        revenue = (
            comparison_items.get(
                "revenue"
            )
        )

        if not isinstance(
            revenue,
            dict
        ):

            return []

        change = self._number(
            revenue.get(
                "change_percent"
            )
        )

        if change is None:

            return []

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


    def _number(
        self,
        value
    ):

        if (
            value is None
            or isinstance(
                value,
                bool
            )
        ):

            return None

        try:

            number = float(
                value
            )

        except (
            TypeError,
            ValueError
        ):

            return None

        if not isfinite(
            number
        ):

            return None

        if number.is_integer():

            return int(
                number
            )

        return number


    def _missing_data_result(
        self
    ):

        return {
            "error": True,
            "message": "Недостаточно данных для анализа продаж",
            "metrics": {
                "revenue": None,
                "gross_profit": None,
                "business_profit": None,
                "margin_percent": None
            },
            "comparison": None,
            "insights": []
        }
