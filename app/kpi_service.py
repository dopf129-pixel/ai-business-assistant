class KPIService:

    def format_number(self, value):

        try:
            return f"{int(value):,}".replace(",", " ")
        except (TypeError, ValueError):
            return "0"

    def calculate(
        self,
        metrics,
        health,
        risk,
        memory_analysis,
        trend
    ):

        health_score = int(
            health.get("score", 0)
        )

        risk_score = int(
            risk.get("risk_score", 0)
        )

        has_fbo_stocks = bool(
            metrics.get("has_fbo_stocks")
        )

        is_discounted = bool(
            metrics.get("is_discounted")
        )

        fbo_present = int(
            metrics.get("fbo_present", 0) or 0
        )

        fbo_reserved = int(
            metrics.get("fbo_reserved", 0) or 0
        )

        fbo_available = int(
            metrics.get("fbo_available", 0) or 0
        )

        days_without_discount = int(
            memory_analysis.get(
                "days_without_discount",
                0
            )
        )

        stock_change = int(
            memory_analysis.get(
                "stock_change",
                0
            )
        )

        trend_status = trend.get(
            "status",
            "Нет данных"
        )

        if fbo_present > 0:

            reserved_percent = round(
                fbo_reserved / fbo_present * 100,
                1
            )

        else:

            reserved_percent = 0.0

        if not has_fbo_stocks or fbo_available <= 0:

            stock_status = "🔴 Остатков нет"

        elif reserved_percent >= 50:

            stock_status = "🔴 Высокий резерв"

        elif reserved_percent >= 20:

            stock_status = "🟡 Повышенный резерв"

        else:

            stock_status = "🟢 Нормальный резерв"

        ai_score = health_score

        ai_score -= min(
            risk_score,
            40
        )

        if has_fbo_stocks and fbo_available > 0:
            ai_score += 15
        else:
            ai_score -= 30

        if reserved_percent >= 50:
            ai_score -= 15
        elif reserved_percent >= 20:
            ai_score -= 5

        if is_discounted:
            ai_score += 10

        if days_without_discount >= 14:
            ai_score -= 15
        elif days_without_discount >= 7:
            ai_score -= 10
        elif days_without_discount >= 3:
            ai_score -= 5

        if trend.get("change", 0) > 0:
            ai_score += 5
        elif trend.get("change", 0) < 0:
            ai_score -= 10

        ai_score = max(
            0,
            min(100, ai_score)
        )

        if ai_score >= 80:

            status = "🟢 Сильное состояние"

            conclusion = (
                "Товар находится в хорошем состоянии. "
                "Продолжайте мониторинг и поддерживайте остатки FBO."
            )

        elif ai_score >= 50:

            status = "🟡 Требует внимания"

            conclusion = (
                "Товар стабилен, но есть факторы, "
                "которые могут ограничивать рост."
            )

        else:

            status = "🔴 Высокий приоритет"

            conclusion = (
                "Товар требует срочного анализа "
                "и корректирующих действий."
            )

        return {
            "health_score": health_score,
            "risk_score": risk_score,
            "has_fbo_stocks": has_fbo_stocks,
            "is_discounted": is_discounted,
            "fbo_present": fbo_present,
            "fbo_reserved": fbo_reserved,
            "fbo_available": fbo_available,
            "reserved_percent": reserved_percent,
            "stock_status": stock_status,
            "stock_change": stock_change,
            "days_without_discount": days_without_discount,
            "trend_status": trend_status,
            "ai_score": ai_score,
            "status": status,
            "conclusion": conclusion
        }

    def print_dashboard(
        self,
        kpi
    ):

        print()
        print("=========================")
        print("AI KPI Dashboard")
        print("=========================")

        print()

        print(
            "Здоровье товара:",
            f'{kpi["health_score"]}/100'
        )

        print(
            "Риск:",
            f'{kpi["risk_score"]}/100'
        )

        print(
            "FBO остатки:",
            "✅ Есть"
            if kpi["has_fbo_stocks"]
            else "❌ Нет"
        )

        print(
            "FBO всего:",
            self.format_number(
                kpi["fbo_present"]
            ),
            "шт."
        )

        print(
            "Зарезервировано:",
            self.format_number(
                kpi["fbo_reserved"]
            ),
            "шт."
        )

        print(
            "Доступно:",
            self.format_number(
                kpi["fbo_available"]
            ),
            "шт."
        )

        print(
            "Доля резерва:",
            f'{kpi["reserved_percent"]}%'
        )

        print(
            "Оценка резерва:",
            kpi["stock_status"]
        )

        if kpi["stock_change"] > 0:

            print(
                "Изменение остатка:",
                "+",
                self.format_number(
                    kpi["stock_change"]
                ),
                "шт."
            )

        elif kpi["stock_change"] < 0:

            print(
                "Изменение остатка:",
                "-",
                self.format_number(
                    abs(kpi["stock_change"])
                ),
                "шт."
            )

        else:

            print(
                "Изменение остатка:",
                "0 шт."
            )

        print(
            "Скидка:",
            "✅ Есть"
            if kpi["is_discounted"]
            else "❌ Нет"
        )

        print(
            "Дней без скидки:",
            kpi["days_without_discount"]
        )

        print(
            "Тренд:",
            kpi["trend_status"]
        )

        print(
            "AI-оценка:",
            f'{kpi["ai_score"]}/100'
        )

        print(
            "Состояние:",
            kpi["status"]
        )

        print()
        print("Итог:")
        print(
            kpi["conclusion"]
        )