class AssistantTelegramAdapter:


    def __init__(
        self,
        assistant,
        keyboard_service,
        button_handler
    ):

        self.assistant = assistant

        self.keyboard_service = (
            keyboard_service
        )

        self.button_handler = (
            button_handler
        )



    def get_start_response(
        self
    ):

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
        text
    ):

        return (
            self.assistant
            .ask(
                text
            )
        )



    def handle_button(
        self,
        callback
    ):

        return (
            self.button_handler
            .handle(
                callback
            )
        )