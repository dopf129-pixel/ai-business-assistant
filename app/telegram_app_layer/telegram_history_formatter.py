class TelegramHistoryFormatter:


    def format(
        self,
        result
    ):


        history = (
            result.get("history", [])
        )


        if not history:

            return (
                "📜 История пустая"
            )


        text = (
            "📜 История:\n\n"
        )


        for index, item in enumerate(
            history,
            1
        ):

            text += (
                f"{index}. {item}\n"
            )


        return text