class TaxDashboardService:

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
        tax
    ):

        print()
        print("=========================")
        print("AI Tax Dashboard")
        print("=========================")

        if tax.get("error"):

            print()
            print(
                "Ошибка:",
                tax.get(
                    "message",
                    "Не удалось рассчитать налог"
                )
            )

            return

        print()
        print(
            "Налоговый режим:",
            tax.get(
                "mode_name",
                "Нет данных"
            )
        )

        print(
            "Налоговая база:",
            self.format_money(
                tax.get(
                    "tax_base",
                    0
                )
            )
        )

        print(
            "Ставка:",
            f'{tax.get("tax_rate", 0):.2f}%'
        )

        if (
            tax.get("mode")
            == "USN_INCOME_MINUS_EXPENSES"
        ):

            print(
                "Расчётный налог:",
                self.format_money(
                    tax.get(
                        "regular_tax",
                        0
                    )
                )
            )

            print(
                "Минимальный налог:",
                self.format_money(
                    tax.get(
                        "minimum_tax",
                        0
                    )
                )
            )

        print()
        print(
            "Налог к учёту:",
            self.format_money(
                tax.get(
                    "tax_amount",
                    0
                )
            )
        )

        print()
        print(
            "Примечание:"
        )

        print(
            "Расчёт является аналитическим. "
            "Фактический налог зависит от "
            "налогового режима, применимых "
            "ставок и правил учёта."
        )