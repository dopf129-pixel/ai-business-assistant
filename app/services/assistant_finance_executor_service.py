class AssistantFinanceExecutorService:


    def __init__(
        self,
        finance_intelligence_service=None
    ):

        self.finance_intelligence_service = (
            finance_intelligence_service
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
            "Проверены финансовые показатели",
            "Финансовый анализ подготовлен"
        ]


        if self.finance_intelligence_service:

            intelligence = (
                self.finance_intelligence_service
                .analyze(
                    context.get(
                        "finance_data",
                        {}
                    ),
                    previous_data=(
                        context.get(
                            "previous_data"
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


            profit_label = (
                "Расчётный валовый результат"
                if intelligence.get(
                    "profit_scope"
                )
                == "PERIOD_GROSS_PROFIT"
                else "Расчётный финансовый результат"
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
                "Расходы по доступным данным: "
                +
                str(
                    metrics.get(
                        "expenses",
                        0
                    )
                ),
                profit_label
                +
                ": "
                +
                str(
                    metrics.get(
                        "profit",
                        0
                    )
                ),
                "Маржинальность по доступным данным: "
                +
                str(
                    metrics.get(
                        "margin",
                        0
                    )
                )
                +
                "%"
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
            "result": {
                "type": "finance",
                "message": "Финансовый анализ выполнен",
                "details": details,
                "priority": action.get(
                    "priority",
                    "NORMAL"
                )
            }
        }
