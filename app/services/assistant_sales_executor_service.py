class AssistantSalesExecutorService:


    def __init__(
        self,
        sales_intelligence_service=None
    ):

        self.sales_intelligence_service = (
            sales_intelligence_service
        )


    def execute(
        self,
        action
    ):


        context = (
            action.get(
                "context",
                {}
            )
        )


        reason = (
            context.get(
                "reason"
            )
        )


        details = [
            "Проверено падение продаж",
            "Найдены возможные причины"
        ]


        if self.sales_intelligence_service:

            intelligence = (
                self.sales_intelligence_service
                .analyze(
                    context.get(
                        "profits",
                        []
                    ),
                    previous_result=(
                        context.get(
                            "previous_result"
                        )
                    )
                )
            )


            if intelligence.get(
                "error"
            ):

                return intelligence


            metrics = (
                intelligence.get(
                    "metrics",
                    {}
                )
            )


            business_profit = metrics.get(
                "business_profit"
            )

            margin_percent = metrics.get(
                "margin_percent"
            )

            details = [
                "Выручка: "
                +
                str(
                    metrics.get(
                        "revenue",
                        0
                    )
                ),
                "Валовая прибыль: "
                +
                str(
                    metrics.get(
                        "gross_profit",
                        0
                    )
                ),
                "Прибыль после расходов: "
                +
                (
                    str(business_profit)
                    if business_profit is not None
                    else "—"
                ),
                "Маржинальность: "
                +
                (
                    str(margin_percent) + "%"
                    if margin_percent is not None
                    else "—"
                )
            ]


            for insight in intelligence.get(
                "insights",
                []
            ):

                message = insight.get(
                    "message"
                )

                if message:

                    details.append(
                        message
                    )


        if reason:


            details.append(
                "Причина анализа: "
                +
                reason
            )


        return {

            "error": False,

            "result":
                {

                    "type":
                        "sales",

                    "message":
                        "Анализ продаж выполнен",

                    "details":
                        details,

                    "priority":
                        action.get(
                            "priority",
                            "NORMAL"
                        )

                }

        }
