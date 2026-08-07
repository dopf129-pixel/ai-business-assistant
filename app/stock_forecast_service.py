from datetime import datetime


class StockForecastService:

    def calculate(
        self,
        history
    ):

        if not history or len(history) < 2:

            return {
                "status": "Недостаточно данных",
                "records": len(history) if history else 0,
                "daily_consumption": 0,
                "days_left": None,
                "stock_change": 0,
                "message": (
                    "Для прогноза нужно минимум "
                    "2 ежедневных снимка остатков."
                )
            }

        newest = history[0]
        oldest = history[-1]

        newest_available = int(
            newest[6] or 0
        )

        oldest_available = int(
            oldest[6] or 0
        )

        newest_date = datetime.strptime(
            newest[7],
            "%Y-%m-%d"
        ).date()

        oldest_date = datetime.strptime(
            oldest[7],
            "%Y-%m-%d"
        ).date()

        days_between = (
            newest_date - oldest_date
        ).days

        if days_between <= 0:

            return {
                "status": "Недостаточно данных",
                "records": len(history),
                "daily_consumption": 0,
                "days_left": None,
                "stock_change": 0,
                "message": (
                    "Снимки должны быть сделаны "
                    "в разные календарные дни."
                )
            }

        stock_change = (
            newest_available
            - oldest_available
        )

        consumed = max(
            0,
            oldest_available
            - newest_available
        )

        daily_consumption = round(
            consumed / days_between,
            2
        )

        if daily_consumption <= 0:

            return {
                "status": "🟢 Остаток не снижается",
                "records": len(history),
                "daily_consumption": 0,
                "days_left": None,
                "stock_change": stock_change,
                "message": (
                    "По сохранённой истории "
                    "расход остатков не обнаружен."
                )
            }

        days_left = round(
            newest_available
            / daily_consumption
        )

        if days_left <= 7:

            status = "🔴 Критический запас"

        elif days_left <= 21:

            status = "🟠 Низкий запас"

        elif days_left <= 45:

            status = "🟡 Требует контроля"

        else:

            status = "🟢 Запас достаточный"

        return {
            "status": status,
            "records": len(history),
            "daily_consumption": daily_consumption,
            "days_left": days_left,
            "stock_change": stock_change,
            "message": (
                f"Средний расход: "
                f"{daily_consumption} шт. в день. "
                f"Остатка хватит примерно "
                f"на {days_left} дней."
            )
        }

    def print_forecast(
        self,
        forecast
    ):

        print()
        print("=========================")
        print("Прогноз FBO-остатков")
        print("=========================")

        print()
        print(
            "Статус:",
            forecast["status"]
        )

        print(
            "Снимков использовано:",
            forecast["records"]
        )

        print(
            "Средний расход:",
            forecast["daily_consumption"],
            "шт. в день"
        )

        if forecast["days_left"] is not None:

            print(
                "Примерно дней запаса:",
                forecast["days_left"]
            )

        print(
            "Описание:",
            forecast["message"]
        )