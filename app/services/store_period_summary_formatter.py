class StorePeriodSummaryFormatter:

    def format(
        self,
        summary
    ):

        if summary.get(
            "error"
        ):

            return (
                "Не удалось получить "
                "сравнение периодов."
            )


        comparison = (
            summary.get(
                "comparison",
                {}
            )
        )


        lines = []

        lines.append(
            "================================"
        )

        lines.append(
            "Сравнение периодов"
        )

        lines.append(
            "================================"
        )


        status = (
            comparison.get(
                "status"
            )
        )

        if status:

            lines.append(
                status
            )


        score = (
            comparison.get(
                "score"
            )
        )

        if score is not None:

            lines.append(
                f"Оценка: {score}/4"
            )


        metrics = (
            comparison.get(
                "comparison",
                {}
            )
        )


        for item in metrics.values():

            name = (
                item.get(
                    "name",
                    ""
                )
            )

            change = (
                item.get(
                    "change_percent"
                )
            )

            trend = (
                item.get(
                    "trend",
                    ""
                )
            )


            if name:

                lines.append(
                    f"{name}: {change}% ({trend})"
                )


        return "\n".join(
            lines
        )