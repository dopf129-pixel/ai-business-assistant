class TelegramRunner:


    def __init__(
        self,
        bot_service
    ):

        self.bot_service = (
            bot_service
        )

        self.history_service = None



    def start(
        self,
        user_id=None
    ):

        try:

            result = (
                self.bot_service
                .on_start(
                    user_id
                )
            )


        except TypeError:

            result = (
                self.bot_service
                .on_start()
            )



        if (
            self.history_service
            and user_id
        ):

            self.history_service.add(
                user_id,
                "Запущен ассистент"
            )



        return result



    def receive_message(
        self,
        user_id,
        text=None
    ):


        if text is None:

            text = user_id
            user_id = None



        if (
            self.history_service
            and user_id
            and text
        ):

            self.history_service.add(
                user_id,
                f"Сообщение: {text}"
            )



        try:

            result = (
                self.bot_service
                .on_message(
                    user_id,
                    text
                )
            )


        except TypeError:

            result = (
                self.bot_service
                .on_message(
                    text
                )
            )



        return result



    def receive_callback(
        self,
        user_id,
        callback=None
    ):


        if callback is None:

            callback = user_id
            user_id = None



        # Не записываем технические кнопки
        # истории и памяти

        if (
            self.history_service
            and user_id
            and callback
            and callback not in [
                "history",
                "memory"
            ]
        ):

            self.history_service.add(
                user_id,
                f"Нажата кнопка: {callback}"
            )



        try:

            result = (
                self.bot_service
                .on_callback(
                    user_id,
                    callback
                )
            )


        except TypeError:

            result = (
                self.bot_service
                .on_callback(
                    callback
                )
            )



        return result