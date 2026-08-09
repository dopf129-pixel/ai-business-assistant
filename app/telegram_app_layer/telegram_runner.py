class TelegramRunner:


    def __init__(
        self,
        bot_service
    ):

        self.bot_service = bot_service

        self.history_service = None

        self.context_service = None



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



        if (
            self.context_service
            and user_id
        ):

            self.context_service.update(
                user_id,
                "last_action",
                "start"
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



        if (
            self.context_service
            and user_id
            and text
        ):

            self.context_service.update(
                user_id,
                "last_message",
                text
            )



            self.context_service.update(
                user_id,
                "current_task",
                text
            )



        try:

            return (
                self.bot_service
                .on_message(
                    user_id,
                    text
                )
            )


        except TypeError:

            return (
                self.bot_service
                .on_message(
                    text
                )
            )



    def receive_callback(
        self,
        user_id,
        callback=None
    ):


        if callback is None:

            callback = user_id
            user_id = None



        if (
            self.history_service
            and user_id
            and callback not in [
                "history",
                "memory"
            ]
        ):

            self.history_service.add(
                user_id,
                f"Нажата кнопка: {callback}"
            )



        if (
            self.context_service
            and user_id
        ):

            self.context_service.update(
                user_id,
                "last_action",
                callback
            )



        try:

            return (
                self.bot_service
                .on_callback(
                    user_id,
                    callback
                )
            )


        except TypeError:

            return (
                self.bot_service
                .on_callback(
                    callback
                )
            )