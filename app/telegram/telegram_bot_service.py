class TelegramBotService:


    def __init__(
        self,
        adapter
    ):

        self.adapter = (
            adapter
        )



    def on_start(
        self
    ):

        return (
            self.adapter
            .get_start_response()
        )



    def on_message(
        self,
        text
    ):

        return (
            self.adapter
            .handle_text(
                text
            )
        )



    def on_callback(
        self,
        callback
    ):

        return (
            self.adapter
            .handle_button(
                callback
            )
        )