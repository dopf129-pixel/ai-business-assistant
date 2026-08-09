class TelegramRunner:


    def __init__(
        self,
        bot_service
    ):

        self.bot_service = (
            bot_service
        )



    def start(
        self
    ):

        response = (
            self.bot_service
            .on_start()
        )


        return response



    def receive_message(
        self,
        text
    ):

        return (
            self.bot_service
            .on_message(
                text
            )
        )



    def receive_callback(
        self,
        callback
    ):

        return (
            self.bot_service
            .on_callback(
                callback
            )
        )