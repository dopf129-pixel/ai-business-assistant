class PeriodComparisonService:

    def safe_percent_change(
        self,
        current,
        previous
    ):

        current = float(
            current or 0
        )

        previous = float(
            previous or 0
        )

        if previous == 0:

            if current == 0:
                return 0.0

            return 100.0

        return round(
            (
                (current - previous)
                / abs(previous)
            )
            * 100,
            2
        )


    def compare_value(
        self,
        name,
        current,
        previous
    ):

        change = (
            self.safe_percent_change(
                current,
                previous
            )
        )

        if change > 0:

            trend = "Рост"

        elif change < 0:

            trend = "Снижение"

        else:

            trend = "Без изменений"


        return {
            "name": name,
            "current": float(
                current or 0
            ),
            "previous": float(
                previous or 0
            ),
            "change_percent": change,
            "trend": trend
        }


    def compare(
        self,
        current,
        previous
    ):

        if (
            not current
            or not previous
        ):

            return {
                "error": True,
                "message": (
                    "Недостаточно данных "
                    "для сравнения периодов"
                )
            }


        current_profit = (
            current.get(
                "business_profit",
                {}
            )
        )

        previous_profit = (
            previous.get(
                "business_profit",
                {}
            )
        )


        current_store = (
            current.get(
                "store_profit",
                {}
            )
        )

        previous_store = (
            previous.get(
                "store_profit",
                {}
            )
        )


        comparison = {

            "revenue": (
                self.compare_value(
                    "Выручка",
                    current_store.get(
                        "gross_sales",
                        0
                    ),
                    previous_store.get(
                        "gross_sales",
                        0
                    )
                )
            ),

            "gross_profit": (
                self.compare_value(
                    "Валовая прибыль",
                    current_store.get(
                        "gross_profit",
                        0
                    ),
                    previous_store.get(
                        "gross_profit",
                        0
                    )
                )
            ),

            "business_profit": (
                self.compare_value(
                    "Прибыль после расходов",
                    current_profit.get(
                        "business_profit",
                        0
                    ),
                    previous_profit.get(
                        "business_profit",
                        0
                    )
                )
            ),

            "margin": (
                self.compare_value(
                    "Маржинальность",
                    current_profit.get(
                        "margin_percent",
                        0
                    ),
                    previous_profit.get(
                        "margin_percent",
                        0
                    )
                )
            )

        }


        score = 0


        for item in comparison.values():

            change = item[
                "change_percent"
            ]

            if change > 0:

                score += 1

            elif change < 0:

                score -= 1


        if score >= 2:

            status = (
                "🟢 Бизнес растёт"
            )

        elif score <= -2:

            status = (
                "🔴 Бизнес ухудшается"
            )

        else:

            status = (
                "🟡 Стабильное состояние"
            )


        return {
            "error": False,
            "status": status,
            "score": score,
            "comparison": comparison
        }