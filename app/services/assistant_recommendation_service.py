class AssistantRecommendationService:


    def analyze(
        self,
        report
    ):


        recommendations = []


        if (
            report.get(
                "sales_down"
            )
        ):


            recommendations.append(
                {
                    "type":
                        "sales",

                    "message":
                        (
                            "Проверить причины падения продаж"
                        ),

                    "context":
                        dict(
                            report.get(
                                "sales_context"
                            )
                            or
                            {}
                        )
                }
            )


        if (
            report.get(
                "low_stock"
            )
        ):


            recommendations.append(
                {
                    "type":
                        "stock",

                    "message":
                        (
                            "Проверить остатки товара"
                        ),

                    "context":
                        dict(
                            report.get(
                                "stock_context"
                            )
                            or
                            {}
                        )
                }
            )


        if (
            report.get(
                "finance_context"
            )
        ):


            recommendations.append(
                {
                    "type":
                        "finance",

                    "message":
                        (
                            "Проверить финансовые показатели"
                        ),

                    "context":
                        dict(
                            report.get(
                                "finance_context"
                            )
                            or
                            {}
                        )
                }
            )


        if (
            report.get(
                "marketing_problem"
            )
        ):


            recommendations.append(
                {
                    "type":
                        "marketing",

                    "message":
                        (
                            "Проверить эффективность рекламных каналов"
                        )
                }
            )


        if len(
            recommendations
        ) == 0:


            recommendations.append(
                {
                    "type":
                        "general",

                    "message":
                        (
                            "Критичных проблем не найдено"
                        )
                }
            )


        return {

            "error":
                False,

            "recommendations":
                recommendations,

            "count":
                len(
                    recommendations
                )

        }