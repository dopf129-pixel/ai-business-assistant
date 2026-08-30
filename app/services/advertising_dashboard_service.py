class AdvertisingDashboardService:

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
            return "—"

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
        advertising
    ):

        print()
        print("=========================")
        print("AI Advertising Dashboard")
        print("=========================")

        if advertising.get("error"):

            print()
            print(
                "Ошибка:",
                advertising.get(
                    "message",
                    "Не удалось рассчитать рекламу"
                )
            )

            return

        print()

        print(
            "Рекламные расходы:",
            self.format_money(
                advertising.get(
                    "advertising_cost",
                    0
                )
            )
        )

        if "campaigns" in advertising:

            print(
                "Кампаний:",
                advertising.get(
                    "campaigns",
                    0
                )
            )

        print()
        print(
            "Примечание:"
        )

        print(
            "На текущем этапе рекламные расходы "
            "передаются в систему отдельно. "
            "Позже источник можно подключить "
            "к Ozon Ads API или другому сервису."
        )