from config import SELLING_MODEL


class HealthScore:

    def calculate(self, metrics):

        score = 0
        reasons = []

        #
        # Архив
        #

        if not metrics.get("archived"):

            score += 30

        else:

            score -= 20
            reasons.append(
                "Товар в архиве"
            )

        #
        # FBO
        #

        if metrics.get("has_fbo_stocks"):

            score += 30

        else:

            score -= 30
            reasons.append(
                "Нет FBO остатков"
            )

        #
        # FBS
        #

        if SELLING_MODEL in ("HYBRID", "FBS"):

            if metrics.get("has_fbs_stocks"):

                score += 15

            else:

                score -= 15
                reasons.append(
                    "Нет FBS остатков"
                )

        #
        # Скидка
        #

        if metrics.get("is_discounted"):

            score += 10

        #
        # Ограничения
        #

        if score < 0:
            score = 0

        if score > 100:
            score = 100

        #
        # Статус
        #

        if score >= 80:

            status = "🟢 Отличное состояние"

        elif score >= 50:

            status = "🟡 Требует внимания"

        else:

            status = "🔴 Критическое состояние"

        return {
            "score": score,
            "status": status,
            "reasons": reasons
        }