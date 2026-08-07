from datetime import datetime



class ReportGenerator:



    def generate(
        self,
        metrics,
        risk,
        history=None
    ):


        lines = []


        lines.append(
            "================================"
        )

        lines.append(
            "Ozon AI Report"
        )

        lines.append(
            "================================"
        )


        lines.append("")



        lines.append(
            f"Товар: {metrics.get('offer_id')}"
        )


        lines.append(
            f"ID: {metrics.get('product_id')}"
        )



        lines.append("")



        lines.append(
            "Статус:"
        )



        if metrics.get("archived"):

            lines.append(
                "❌ Товар в архиве"
            )

        else:

            lines.append(
                "✅ Товар активен"
            )



        lines.append("")



        lines.append(
            "Склады:"
        )



        if metrics.get("has_fbo_stocks"):

            lines.append(
                "✅ FBO остатки есть"
            )

        else:

            lines.append(
                "⚠️ Нет FBO остатков"
            )



        if metrics.get("has_fbs_stocks"):

            lines.append(
                "✅ FBS остатки есть"
            )

        else:

            lines.append(
                "⚠️ Нет FBS остатков"
            )



        lines.append("")



        lines.append(
            "Риск:"
        )


        lines.append(
            risk.get("risk_level")
        )


        lines.append(
            f"Баллы риска: {risk.get('risk_score')}"
        )



        lines.append("")



        lines.append(
            "Причины:"
        )



        for reason in risk.get("reasons", []):

            lines.append(
                "- " + reason
            )



        lines.append("")



        lines.append(
            "Последняя проверка:"
        )


        lines.append(
            datetime.now()
            .strftime("%d.%m.%Y %H:%M")
        )



        lines.append(
            "================================"
        )


        return "\n".join(lines)