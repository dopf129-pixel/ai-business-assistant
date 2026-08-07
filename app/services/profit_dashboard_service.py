class ProfitDashboardService:

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
        profit
    ):

        print()
        print("=========================")
        print("AI Profit Dashboard")
        print("=========================")

        if profit.get("error"):

            print()
            print(
                "Ошибка:",
                profit.get(
                    "message",
                    "Не удалось рассчитать прибыль"
                )
            )

            return

        print()
        print(
            "Продаж:",
            profit.get(
                "sales_count",
                0
            )
        )

        print(
            "Себестоимость 1 шт.:",
            self.format_money(
                profit.get(
                    "cost_price",
                    0
                )
            )
        )

        print(
            "Себестоимость проданных товаров:",
            self.format_money(
                profit.get(
                    "total_cost",
                    0
                )
            )
        )

        print(
            "Чистое начисление Ozon:",
            self.format_money(
                profit.get(
                    "net_accrual",
                    0
                )
            )
        )

        print()
        print(
            "Валовая прибыль:",
            self.format_money(
                profit.get(
                    "gross_profit",
                    0
                )
            )
        )

        print(
            "Прибыль на 1 шт.:",
            self.format_money(
                profit.get(
                    "profit_per_unit",
                    0
                )
            )
        )

        print(
            "Маржинальность:",
            f'{profit.get("margin_percent", 0):.2f}%'
        )

        print()
        print(
            "Примечание:"
        )

        print(
            "Расчёт выполнен после расходов Ozon "
            "и себестоимости, но до налогов, "
            "рекламы и других бизнес-расходов."
        )