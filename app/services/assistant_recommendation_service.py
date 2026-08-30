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
            and report.get(
                "finance_evidence_available"
            ) is not False
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


            marketing_context = report.get(
                "marketing_context"
            )
            marketing_evidence_available = report.get(
                "marketing_evidence_available"
            )


            if (
                marketing_evidence_available is True
                and isinstance(
                    marketing_context,
                    dict
                )
                and marketing_context
            ):

                recommendations.append(
                    {
                        "type":
                            "marketing",

                        "message":
                            (
                                "Проверить эффективность рекламных каналов"
                            ),

                        "context":
                            dict(
                                marketing_context
                            )
                    }
                )


        if len(
            recommendations
        ) == 0:


            stock_evidence_available = (
                report.get(
                    "stock_evidence_available"
                )
            )
            sales_evidence_available = (
                report.get(
                    "sales_evidence_available"
                )
            )
            finance_evidence_available = (
                report.get(
                    "finance_evidence_available"
                )
            )


            recommendations.append(
                {
                    "type":
                        "general",

                    "message":
                        (
                            "Недостаточно данных для полной оценки бизнеса"
                            if (
                                stock_evidence_available is False
                                or sales_evidence_available is False
                                or finance_evidence_available is False
                                or (
                                    report.get("marketing_problem")
                                    and report.get("marketing_evidence_available")
                                    is not True
                                )
                            )
                            else "Критичных проблем не найдено"
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