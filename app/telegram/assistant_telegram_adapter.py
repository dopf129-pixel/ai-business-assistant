class AssistantTelegramAdapter:


    def __init__(
        self,
        assistant,
        keyboard_service,
        button_handler,
        user_profile_service=None
    ):

        self.assistant = (
            assistant
        )

        self.keyboard_service = (
            keyboard_service
        )

        self.button_handler = (
            button_handler
        )

        self.user_profile_service = (
            user_profile_service
        )



    def get_start_response(
        self,
        user_id=None
    ):


        if (
            self.user_profile_service
            and user_id is not None
        ):

            self.user_profile_service.create_user(
                user_id
            )


        return {
            "text": (
                "Привет! Я AI Assistant. "
                "Выберите действие:"
            ),

            "keyboard": (
                self.keyboard_service
                .build_main_keyboard()
            )
        }



    def handle_text(
        self,
        text,
        user_id=None
    ):


        if (
            self.user_profile_service
            and user_id is not None
        ):

            self.user_profile_service.create_user(
                user_id
            )


        return (
            self.assistant
            .ask(
                text,
                user_id
            )
        )



    def handle_button(
        self,
        callback,
        user_id=None
    ):


        if (
            self.user_profile_service
            and user_id is not None
        ):

            self.user_profile_service.create_user(
                user_id
            )


        try:

            return (
                self.button_handler
                .handle(
                    callback,
                    user_id
                )
            )


        except TypeError:

            return (
                self.button_handler
                .handle(
                    callback
                )
            )