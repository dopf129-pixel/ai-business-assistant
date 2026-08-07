class ExpenseDashboardService:

    def format_money(
        self,
        value
    ):

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
        print("AI Expense Dashboard")
        print("=========================")

        if result.get("error"):

            print()
            print(
                "Ошибка:",
                result.get(
                    "message",
                    "Не удалось рассчитать расходы"
                )
            )

            return

        print()

        print(
            "Количество расходов:",
            result.get(
                "expenses_count",
                0
            )
        )

        expenses = result.get(
            "expenses",
            []
        )

        if expenses:

            print()
            print("Расшифровка расходов:")

            for expense in expenses:

                print(
                    "-",
                    expense.get(
                        "name",
                        "Без названия"
                    ),
                    ":",
                    self.format_money(
                        expense.get(
                            "amount",
                            0
                        )
                    )
                )

        print()

        print(
            "Прочие расходы всего:",
            self.format_money(
                result.get(
                    "other_expenses",
                    0
                )
            )
        )

        print()
        print("Примечание:")

        print(
            "В этом блоке учитываются расходы, "
            "которые не входят в начисления Ozon, "
            "себестоимость, налог и рекламу."
        )