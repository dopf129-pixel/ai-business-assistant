class AssistantCoreService:


    def __init__(
        self,
        orchestrator_service,
        memory_service=None,
        request_context_service=None,
        user_context_service=None
    ):

        self.orchestrator_service = (
            orchestrator_service
        )

        self.memory_service = (
            memory_service
        )

        self.request_context_service = (
            request_context_service
        )

        self.user_context_service = (
            user_context_service
        )



    def ask(
        self,
        text,
        user_id=None
    ):


        context = None



        # 1. Сначала получаем старый контекст
        if (
            self.user_context_service
            and user_id is not None
        ):

            context = (
                self.user_context_service
                .get_context(
                    user_id
                )
            )



        elif (
            self.request_context_service
            and user_id is not None
        ):

            context = (
                self.request_context_service
                .build(
                    user_id,
                    text
                )
            )



        # 2. Передаем старый контекст в ядро
        result = (
            self.orchestrator_service
            .process(
                text,
                context
            )
        )



        # 3. Только после обработки обновляем последнее сообщение
        if (
            self.user_context_service
            and user_id is not None
        ):

            self.user_context_service.update(
                user_id,
                "last_message",
                text
            )



        # current_task НЕ меняем автоматически
        # иначе "Продолжи работу" затирает старую задачу



        if context:

            result["context"] = context



        return result