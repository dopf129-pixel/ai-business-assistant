class BusinessProfitDashboardService:

    def format_money(
        self,
        value
    ):

        if value is None:
            return "—"

        try:
            number = float(value)
        except (
            TypeError,
            ValueError
        ):
            number = 0.0

        formatted = (
            f"{abs(number):,.2f}"
            .replace(",", " ")
            .replace(".", ",")
        )

        if number < 0:
            return f"−{formatted} ₽"

        return f"{formatted} ₽"

    def print_dashboard(
        self,
        result
    ):

        print()
        print("=========================")
        print("AI Business Profit Dashboard")
        print("=========================")

        if result.get("error"):

            print()
            print(
                "Ошибка:",
                result.get(
                    "message",
                    "Не удалось рассчитать прибыль бизнеса"
                )
            )

            return

        print()
        print(
            "Выручка:",
            self.format_money(
                result.get(
                    "gross_sales",
                    0
                )
            )
        )

        print(
            "Валовая прибыль:",
            self.format_money(
                result.get(
                    "gross_profit",
                    0
                )
            )
        )

        print(
            "Налог:",
            self.format_money(
                result.get(
                    "tax_amount",
                    0
                )
            )
        )

        print(
            "Реклама:",
            self.format_money(
                result.get(
                    "advertising_cost",
                    0
                )
            )
        )

        print(
            "Прочие расходы:",
            self.format_money(
                result.get(
                    "other_expenses",
                    0
                )
            )
        )

        print()
        print(
            "Прибыль после налога:",
            self.format_money(
                result.get(
                    "business_profit",
                    0
                )
            )
        )

        margin_percent = result.get(
            "margin_percent"
        )

        print(
            "Маржинальность после налога:",
            (
                f"{margin_percent:.2f}%"
                if margin_percent is not None
                else "—"
            )
        )

        print()
        print(
            "Примечание:"
        )

        print(
            "Показатель пока учитывает расходы Ozon, "
            "себестоимость и расчётный налог. "
            "Реклама и прочие расходы будут подключаться "
            "отдельными модулями."
        )