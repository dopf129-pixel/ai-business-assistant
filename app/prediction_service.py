class PredictionService:

    def predict(
        self,
        metrics,
        memory_analysis
    ):

        predictions = []

        health_change = memory_analysis.get(
            "health_change",
            0
        )

        risk_change = memory_analysis.get(
            "risk_change",
            0
        )

        days_without_discount = memory_analysis.get(
            "days_without_discount",
            0
        )

        fbo_stable = memory_analysis.get(
            "fbo_stable",
            False
        )

        if not metrics.get("has_fbo_stocks"):

            predictions.append(
                {
                    "level": "Высокий",
                    "title": "Риск отсутствия продаж",
                    "message": (
                        "На FBO нет остатков. "
                        "Продажи могут остановиться."
                    )
                }
            )

        if health_change < 0:

            predictions.append(
                {
                    "level": "Высокий",
                    "title": "Ухудшение состояния товара",
                    "message": (
                        "Здоровье товара снижается. "
                        "Нужно проверить остатки, цену и продвижение."
                    )
                }
            )

        if risk_change > 0:

            predictions.append(
                {
                    "level": "Высокий",
                    "title": "Рост риска",
                    "message": (
                        "Риск товара увеличился по сравнению "
                        "с предыдущими днями."
                    )
                }
            )

        if days_without_discount >= 7:

            predictions.append(
                {
                    "level": "Средний",
                    "title": "Долгое отсутствие скидки",
                    "message": (
                        f"Товар без скидки уже "
                        f"{days_without_discount} дней. "
                        "Стоит оценить необходимость акции."
                    )
                }
            )

        elif days_without_discount >= 3:

            predictions.append(
                {
                    "level": "Низкий",
                    "title": "Нет маркетинговой активности",
                    "message": (
                        f"Товар без скидки "
                        f"{days_without_discount} дня подряд."
                    )
                }
            )

        if (
            fbo_stable
            and health_change == 0
            and risk_change == 0
        ):

            predictions.append(
                {
                    "level": "Низкий",
                    "title": "Стабильное состояние",
                    "message": (
                        "FBO остатки стабильны, "
                        "здоровье и риск не ухудшаются."
                    )
                }
            )

        if not predictions:

            predictions.append(
                {
                    "level": "Низкий",
                    "title": "Недостаточно данных",
                    "message": (
                        "Для прогноза нужно накопить "
                        "больше ежедневных снимков."
                    )
                }
            )

        return predictions