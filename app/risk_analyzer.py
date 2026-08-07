from config import SELLING_MODEL


def analyze_risk(metrics):

    score = 0
    reasons = []

    #
    # Архив
    #

    if metrics.get("archived"):

        score += 100

        reasons.append(
            "Товар находится в архиве"
        )

    #
    # FBO
    #

    if not metrics.get("has_fbo_stocks"):

        score += 50

        reasons.append(
            "Нет FBO остатков"
        )

    #
    # FBS
    #

    if SELLING_MODEL in ("HYBRID", "FBS"):

        if not metrics.get("has_fbs_stocks"):

            score += 20

            reasons.append(
                "Нет FBS остатков"
            )

    #
    # Скидка
    #

    if not metrics.get("is_discounted"):

        score += 5

        reasons.append(
            "Нет активной скидки"
        )

    #
    # Уровень риска
    #

    if score <= 20:

        level = "🟢 Низкий риск"

    elif score <= 50:

        level = "🟡 Средний риск"

    else:

        level = "🔴 Высокий риск"

    return {

        # новые поля
        "score": score,
        "level": level,
        "reasons": reasons,

        # совместимость
        "risk_score": score,
        "risk_level": level

    }