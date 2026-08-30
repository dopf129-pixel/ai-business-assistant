class AssistantRecommendationService:


    def analyze(
        self,
        report
    ):

        if not isinstance(
            report,
            dict
        ):

            return {
                "error": True,
                "message": "Недостаточно данных для рекомендаций",
                "recommendations": [],
                "count": 0
            }


        recommendations = []

        sales_context = report.get(
            "sales_context"
        )
        stock_context = report.get(
            "stock_context"
        )
        finance_context = report.get(
            "finance_context"
        )
        marketing_context = report.get(
            "marketing_context"
        )

        sales_context_valid = self._valid_context(
            sales_context
        )
        stock_context_valid = self._valid_context(
            stock_context
        )
        finance_context_valid = self._valid_context(
            finance_context
        )
        marketing_context_valid = self._valid_context(
            marketing_context
        )


        if (
            report.get("sales_down")
            and sales_context_valid
        ):

            recommendations.append(
                {
                    "type": "sales",
                    "message": "Проверить причины падения продаж",
                    "context": dict(
                        sales_context
                    )
                }
            )


        if (
            report.get("low_stock")
            and stock_context_valid
        ):

            recommendations.append(
                {
                    "type": "stock",
                    "message": "Проверить остатки товара",
                    "context": dict(
                        stock_context
                    )
                }
            )


        if (
            finance_context_valid
            and report.get(
                "finance_evidence_available"
            ) is not False
        ):

            recommendations.append(
                {
                    "type": "finance",
                    "message": "Проверить финансовые показатели",
                    "context": dict(
                        finance_context
                    )
                }
            )


        if (
            report.get("marketing_problem")
            and report.get(
                "marketing_evidence_available"
            ) is True
            and marketing_context_valid
        ):

            recommendations.append(
                {
                    "type": "marketing",
                    "message": "Проверить эффективность рекламных каналов",
                    "context": dict(
                        marketing_context
                    )
                }
            )


        if len(
            recommendations
        ) == 0:

            insufficient_evidence = (
                report.get(
                    "stock_evidence_available"
                ) is False
                or report.get(
                    "sales_evidence_available"
                ) is False
                or report.get(
                    "finance_evidence_available"
                ) is False
                or (
                    report.get("sales_down")
                    and not sales_context_valid
                )
                or (
                    report.get("low_stock")
                    and not stock_context_valid
                )
                or (
                    finance_context is not None
                    and not finance_context_valid
                )
                or (
                    report.get("marketing_problem")
                    and (
                        report.get(
                            "marketing_evidence_available"
                        ) is not True
                        or not marketing_context_valid
                    )
                )
            )

            recommendations.append(
                {
                    "type": "general",
                    "message": (
                        "Недостаточно данных для полной оценки бизнеса"
                        if insufficient_evidence
                        else "Критичных проблем не найдено"
                    )
                }
            )


        return {
            "error": False,
            "recommendations": recommendations,
            "count": len(
                recommendations
            )
        }


    def _valid_context(
        self,
        context
    ):

        return (
            isinstance(
                context,
                dict
            )
            and bool(
                context
            )
        )
