class TelegramRunner:


    def __init__(
        self,
        bot_service
    ):

        self.bot_service = bot_service



    def start(
        self,
        user_id=None
    ):

        try:

            return (
                self.bot_service
                .on_start(
                    user_id
                )
            )

        except TypeError:

            return (
                self.bot_service
                .on_start()
            )



    def receive_message(
        self,
        user_id,
        text=None
    ):

        if text is None:

            text = user_id
            user_id = None


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