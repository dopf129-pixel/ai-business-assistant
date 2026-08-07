class StoreProfitDashboardService:

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
        store_profit
    ):

        print()
        print("=========================")
        print("AI Store Profit Dashboard")
        print("=========================")

        print()
        print(
            "Продаж:",
            store_profit.get(
                "sales_count",
                0
            )
        )

        print(
            "Чистое начисление Ozon:",
            self.format_money(
                store_profit.get(
                    "net_accrual",
                    0
                )
            )
        )

        print(
            "Себестоимость товаров:",
            self.format_money(
                store_profit.get(
                    "total_cost",
                    0
                )
            )
        )

        print()
        print(
            "Валовая прибыль магазина:",
            self.format_money(
                store_profit.get(
                    "gross_profit",
                    0
                )
            )
        )

        print(
            "Маржинальность:",
            f'{store_profit.get("margin_percent", 0):.2f}%'
        )

        print()
        print(
            "Прибыльных товаров:",
            store_profit.get(
                "profitable_products",
                0
            )
        )

        print(
            "Убыточных товаров:",
            store_profit.get(
                "loss_products",
                0
            )
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