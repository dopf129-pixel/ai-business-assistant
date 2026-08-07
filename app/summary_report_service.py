from datetime import datetime
from pathlib import Path


class SummaryReportService:

    def __init__(
        self,
        reports_dir="reports"
    ):

        self.reports_dir = Path(
            reports_dir
        )

        self.reports_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def format_number(
        self,
        value
    ):

        try:
            return (
                f"{int(value):,}"
                .replace(",", " ")
            )
        except (
            TypeError,
            ValueError
        ):
            return "0"

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

    def build_report(
        self,
        product_id,
        offer_id,
        health,
        risk,
        memory_analysis,
        predictions,
        stock_forecast,
        kpi,
        finance=None,
        profit=None
    ):

        finance = finance or {}
        profit = profit or {}

        lines = []

        lines.append("=========================")
        lines.append("Ozon AI Summary")
        lines.append("=========================")
        lines.append("")

        lines.append(
            f"Товар: {offer_id}"
        )

        lines.append(
            f"ID: {product_id}"
        )

        lines.append("")

        lines.append(
            "Здоровье: "
            f'{health.get("score", 0)}/100'
        )

        lines.append(
            "Статус здоровья: "
            f'{health.get("status", "Нет данных")}'
        )

        lines.append(
            "Риск: "
            f'{risk.get("risk_score", 0)}/100'
        )

        lines.append(
            "Уровень риска: "
            f'{risk.get("risk_level", "Нет данных")}'
        )

        lines.append("")

        lines.append(
            "AI-оценка: "
            f'{kpi.get("ai_score", 0)}/100'
        )

        lines.append(
            "Состояние: "
            f'{kpi.get("status", "Нет данных")}'
        )

        lines.append("")

        lines.append(
            "FBO остатки:"
        )

        lines.append(
            "Всего: "
            f'{self.format_number(kpi.get("fbo_present", 0))} '
            "шт."
        )

        lines.append(
            "Зарезервировано: "
            f'{self.format_number(kpi.get("fbo_reserved", 0))} '
            "шт."
        )

        lines.append(
            "Доступно: "
            f'{self.format_number(kpi.get("fbo_available", 0))} '
            "шт."
        )

        lines.append("")

        lines.append(
            "AI-память:"
        )

        lines.append(
            memory_analysis.get(
                "summary",
                "Истории пока недостаточно"
            )
        )

        lines.append("")

        lines.append(
            "Прогноз остатков FBO:"
        )

        lines.append(
            "Статус: "
            f'{stock_forecast.get("status", "Нет данных")}'
        )

        lines.append(
            "Средний расход: "
            f'{stock_forecast.get("daily_consumption", 0)} '
            "шт./день"
        )

        days_left = stock_forecast.get(
            "days_left"
        )

        if days_left is None:

            lines.append(
                "Примерно дней запаса: "
                "недостаточно данных"
            )

        else:

            lines.append(
                "Примерно дней запаса: "
                f"{days_left}"
            )

        message = stock_forecast.get(
            "message"
        )

        if message:
            lines.append(message)

        lines.append("")

        lines.append(
            "Финансы Ozon:"
        )

        if finance.get("error"):

            lines.append(
                "Финансовые данные недоступны: "
                f'{finance.get("message", "Неизвестная ошибка")}'
            )

        elif finance:

            lines.append(
                "Дата: "
                f'{finance.get("date", "Нет данных")}'
            )

            lines.append(
                "SKU: "
                f'{finance.get("sku", "Все товары")}'
            )

            lines.append(
                "Операций: "
                f'{finance.get("operations", 0)}'
            )

            lines.append(
                "Товарных начислений POSTING: "
                f'{finance.get("sales_count", 0)}'
            )

            lines.append(
                "Выручка: "
                f'{self.format_money(finance.get("gross_sales", 0))}'
            )

            lines.append(
                "Комиссия Ozon: "
                f'{self.format_money(finance.get("commission", 0))}'
            )

            lines.append(
                "Логистика: "
                f'{self.format_money(finance.get("logistics", 0))}'
            )

            lines.append(
                "Эквайринг: "
                f'{self.format_money(finance.get("acquiring", 0))}'
            )

            lines.append(
                "Прочие начисления: "
                f'{self.format_money(finance.get("other_fees", 0))}'
            )

            lines.append(
                "Чистое начисление Ozon: "
                f'{self.format_money(finance.get("net_accrual", 0))}'
            )

            fee_breakdown = finance.get(
                "fee_breakdown",
                {}
            )

            if fee_breakdown:

                lines.append(
                    "Расшифровка начислений:"
                )

                for name, amount in sorted(
                    fee_breakdown.items()
                ):

                    lines.append(
                        f"- {name}: "
                        f"{self.format_money(amount)}"
                    )

        else:

            lines.append(
                "Финансовые данные не переданы"
            )

        lines.append("")

        lines.append(
            "Экономика товара:"
        )

        if profit.get("error"):

            lines.append(
                "Расчёт прибыли недоступен: "
                f'{profit.get("message", "Неизвестная ошибка")}'
            )

        elif profit:

            lines.append(
                "Продаж: "
                f'{profit.get("sales_count", 0)}'
            )

            lines.append(
                "Себестоимость 1 шт.: "
                f'{self.format_money(profit.get("cost_price", 0))}'
            )

            lines.append(
                "Себестоимость проданных товаров: "
                f'{self.format_money(profit.get("total_cost", 0))}'
            )

            lines.append(
                "Чистое начисление Ozon: "
                f'{self.format_money(profit.get("net_accrual", 0))}'
            )

            lines.append(
                "Валовая прибыль: "
                f'{self.format_money(profit.get("gross_profit", 0))}'
            )

            lines.append(
                "Прибыль на 1 шт.: "
                f'{self.format_money(profit.get("profit_per_unit", 0))}'
            )

            margin_percent = profit.get(
                "margin_percent",
                0
            )

            lines.append(
                "Маржинальность: "
                f"{float(margin_percent):.2f}%"
            )

        else:

            lines.append(
                "Данные о прибыли не переданы"
            )

        lines.append("")

        lines.append(
            "AI-прогноз:"
        )

        if predictions:

            for prediction in predictions:

                lines.append(
                    f'- [{prediction.get("level", "Нет данных")}] '
                    f'{prediction.get("title", "Без названия")}: '
                    f'{prediction.get("message", "")}'
                )

        else:

            lines.append(
                "- Прогнозов нет"
            )

        lines.append("")

        lines.append(
            "Итог:"
        )

        lines.append(
            kpi.get(
                "conclusion",
                "Итоговая оценка отсутствует"
            )
        )

        lines.append("")

        lines.append(
            "Примечание: валовая прибыль рассчитана "
            "после расходов Ozon и себестоимости товара, "
            "но до налогов, рекламы и других "
            "бизнес-расходов."
        )

        lines.append("")

        lines.append(
            "Создано: "
            + datetime.now().strftime(
                "%d.%m.%Y %H:%M:%S"
            )
        )

        return "\n".join(
            lines
        )

    def save_report(
        self,
        product_id,
        offer_id,
        health,
        risk,
        memory_analysis,
        predictions,
        stock_forecast,
        kpi,
        finance=None,
        profit=None
    ):

        report = self.build_report(
            product_id=product_id,
            offer_id=offer_id,
            health=health,
            risk=risk,
            memory_analysis=memory_analysis,
            predictions=predictions,
            stock_forecast=stock_forecast,
            kpi=kpi,
            finance=finance,
            profit=profit
        )

        safe_offer_id = str(
            offer_id or product_id
        )

        safe_offer_id = "".join(
            char
            if char.isalnum()
            or char in (
                "-",
                "_"
            )
            else "_"
            for char in safe_offer_id
        )

        filename = (
            f"{safe_offer_id}_summary_"
            f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            ".txt"
        )

        filepath = (
            self.reports_dir
            / filename
        )

        filepath.write_text(
            report,
            encoding="utf-8"
        )

        return str(
            filepath
        )