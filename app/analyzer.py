def analyze_metrics(metrics):

    result = []


    product_id = metrics.get(
        "product_id"
    )

    offer_id = metrics.get(
        "offer_id"
    )


    result.append(
        f"Товар: {offer_id}"
    )


    if metrics.get("archived"):

        result.append(
            "❌ Товар находится в архиве"
        )

    else:

        result.append(
            "✅ Товар активен"
        )


    if metrics.get("has_fbo_stocks"):

        result.append(
            "✅ FBO остатки есть"
        )

    else:

        result.append(
            "⚠️ Нет FBO остатков"
        )



    if metrics.get("has_fbs_stocks"):

        result.append(
            "✅ FBS остатки есть"
        )

    else:

        result.append(
            "⚠️ Нет FBS остатков"
        )



    if metrics.get("is_discounted"):

        result.append(
            "🏷 Есть активная скидка"
        )

    else:

        result.append(
            "ℹ️ Активной скидки нет"
        )



    if (
        metrics.get("has_fbo_stocks")
        and not metrics.get("has_fbs_stocks")
    ):

        result.append(
            "💡 Рекомендация: проверить продажи FBS"
        )



    return result