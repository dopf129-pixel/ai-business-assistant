class AssistantStockExecutorService:


    def __init__(
        self,
        stock_intelligence_service=None
    ):

        self.stock_intelligence_service = (
            stock_intelligence_service
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
            "Проверены остатки товара",
            "Найдены позиции для контроля"
        ]


        if self.stock_intelligence_service:

            intelligence = (
                self.stock_intelligence_service
                .analyze(
                    context.get(
                        "stock_data",
                        {}
                    ),
                    context.get(
                        "sales_data",
                        {}
                    ),
                    context.get(
                        "period_days"
                    )
                )
            )


            if intelligence.get(
                "error"
            ):

                return intelligence


            details = [
                "Товар: "
                +
                str(
                    intelligence.get(
                        "product_id"
                    )
                ),
                "Текущий остаток: "
                +
                str(
                    intelligence.get(
                        "current_stock"
                    )
                ),
                "Скорость продаж: "
                +
                str(
                    intelligence.get(
                        "sales_velocity"
                    )
                ),
                "Запас на дней: "
                +
                str(
                    intelligence.get(
                        "days_of_stock"
                    )
                ),
                "Приоритет пополнения: "
                +
                str(
                    intelligence.get(
                        "priority"
                    )
                )
            ]


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
                        "stock",

                    "message":
                        "Проверка остатков выполнена",

                    "details":
                        details,

                    "priority":
                        action.get(
                            "priority",
                            "NORMAL"
                        )

                }

        }
