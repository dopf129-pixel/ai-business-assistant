class TelegramBotService:


    def __init__(
        self,
        adapter,
        command_service=None
    ):

        self.adapter = (
            adapter
        )

        self.command_service = (
            command_service
        )



    def on_start(
        self,
        user_id=None
    ):

        try:

            return (
                self.adapter
                .get_start_response(
                    user_id
                )
            )

        except TypeError:

            return (
                self.adapter
                .get_start_response()
            )



    def on_message(
        self,
        user_id,
        text=None
    ):


        if text is None:

            text = user_id
            user_id = None



        if (
            self.command_service
        ):

            command_result = (
                self.command_service
                .handle(
                    user_id,
                    text
                )
            )


            if command_result:

                return command_result



        try:

            return (
                self.adapter
                .handle_text(
                    text,
                    user_id
                )
            )

        except TypeError:

            return (
                self.adapter
                .handle_text(
                    text
                )
            )



    def on_callback(
        self,
        user_id,
        callback=None
    ):


        if callback is None:

            callback = user_id
            user_id = None


        try:

            return (
                self.adapter
                .handle_button(
                    callback,
                    user_id
                )
            )

        except TypeError:

            return (
                self.adapter
                .handle_button(
                    callback
                )
            )