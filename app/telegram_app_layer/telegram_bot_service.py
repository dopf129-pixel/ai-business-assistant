from telegram_app_layer.telegram_call_compat import (
    call_with_legacy_arity,
)


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

        return call_with_legacy_arity(
            self.adapter
            .get_start_response,
            (
                user_id,
            ),
            (),
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

            try:

                command_result = (
                    self.command_service
                    .handle(
                        user_id,
                        text
                    )
                )

            except Exception:

                return {
                    "error": True,
                    "message":
                        "TELEGRAM_COMMAND_DISPATCH_FAILED"
                }

            if command_result is not None:

                if (
                    not isinstance(
                        command_result,
                        dict
                    )
                    or type(
                        command_result.get(
                            "error"
                        )
                    )
                    is not bool
                ):

                    return {
                        "error": True,
                        "message":
                            "INVALID_TELEGRAM_COMMAND_RESULT"
                    }

                return command_result

        return call_with_legacy_arity(
            self.adapter
            .handle_text,
            (
                text,
                user_id,
            ),
            (
                text,
            ),
        )


    def on_callback(
        self,
        user_id,
        callback=None
    ):

        if callback is None:

            callback = user_id
            user_id = None

        return call_with_legacy_arity(
            self.adapter
            .handle_button,
            (
                callback,
                user_id,
            ),
            (
                callback,
            ),
        )
