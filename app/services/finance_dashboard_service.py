class FinanceDashboardService:

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
        finance
    ):

        print()
        print("=========================")
        print("AI Finance Dashboard")
        print("=========================")

        if finance.get("error"):

            print()
            print(
                "Ошибка:",
                finance.get(
                    "message",
                    "Не удалось получить финансовые данные"
                )
            )

            return

        print()
        print(
            "Дата:",
            finance.get(
                "date",
                "Нет данных"
            )
        )

        print(
            "SKU:",
            finance.get(
                "sku",
                "Все товары"
            )
        )

        print(
            "Операций:",
            finance.get(
                "operations",
                0
            )
        )

        print(
            "Продаж:",
            finance.get(
                "sales_count",
                0
            )
        )

        print()
        print(
            "Выручка:",
            self.format_money(
                finance.get(
                    "gross_sales",
                    0
                )
            )
        )

        print(
            "Комиссия Ozon:",
            self.format_money(
                finance.get(
                    "commission",
                    0
                )
            )
        )

        print(
            "Логистика:",
            self.format_money(
                finance.get(
                    "logistics",
                    0
                )
            )
        )

        print(
            "Эквайринг:",
            self.format_money(
                finance.get(
                    "acquiring",
                    0
                )
            )
        )

        print(
            "Прочие начисления:",
            self.format_money(
                finance.get(
                    "other_fees",
                    0
                )
            )
        )

        print(
            "Чистое начисление:",
            self.format_money(
                finance.get(
                    "net_accrual",
                    0
                )
            )
        )

        print()
        print("Расшифровка начислений:")

        fee_breakdown = finance.get(
            "fee_breakdown",
            {}
        )

        if not fee_breakdown:

            print(
                "Нет детализации"
            )

        else:

            for name, amount in sorted(
                fee_breakdown.items()
            ):

                print(
                    "-",
                    name + ":",
                    self.format_money(
                        amount
                    )
                )