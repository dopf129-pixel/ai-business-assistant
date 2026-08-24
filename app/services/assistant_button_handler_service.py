class AssistantButtonHandlerService:


    def __init__(
        self,
        assistant,
        memory_service=None,
        history_service=None,
        task_context_service=None,
        keyboard_service=None,
        unit_economics_query=None
    ):

        self.assistant = (
            assistant
        )

        self.memory_service = (
            memory_service
        )

        self.history_service = (
            history_service
        )

        self.task_context_service = (
            task_context_service
        )

        self.keyboard_service = (
            keyboard_service
        )

        self.unit_economics_query = (
            unit_economics_query
        )



    def prepare_context(
        self,
        user_id,
        action,
        task
    ):


        if (
            self.task_context_service
            and user_id
        ):

            self.task_context_service.user_context_service.update(
                user_id,
                "last_action",
                action
            )


            self.task_context_service.update_task(
                user_id,
                task
            )



    def handle(
        self,
        button_id,
        user_id=None
    ):



        if button_id == "unit_economics":

            return (
                self._open_unit_economics_menu()
            )


        if button_id.startswith(
            "unit_economics:"
        ):

            sku = button_id.split(
                ":",
                1
            )[1]

            return (
                self._show_unit_economics(
                    sku
                )
            )



        if button_id == "analyze":


            self.prepare_context(
                user_id,
                "analyze",
                "Анализ продаж"
            )


            result = (
                self.assistant
                .ask(
                    "Что нужно сделать с продажами?",
                    user_id
                )
            )



            if (
                self.history_service
                and user_id
            ):

                self.history_service.add(
                    user_id,
                    "Выполнен анализ"
                )


            return result





        if button_id == "plan":


            self.prepare_context(
                user_id,
                "plan",
                "Создание плана действий"
            )


            result = (
                self.assistant
                .ask(
                    "Создай план действий",
                    user_id
                )
            )



            if (
                self.history_service
                and user_id
            ):

                self.history_service.add(
                    user_id,
                    "Создан план действий"
                )


            return result





        if button_id == "history":


            if (
                self.history_service
                and user_id
            ):

                return (
                    self.history_service
                    .get(
                        user_id
                    )
                )


            return {
                "error": False,
                "history": []
            }





        if button_id == "memory":


            if (
                self.memory_service
                and user_id
            ):

                return (
                    self.memory_service
                    .get_memory(
                        user_id
                    )
                )


            return {
                "error": False,
                "memory": {}
            }





        return {
            "error": True,
            "message": "Кнопка неизвестна"
        }



    def _open_unit_economics_menu(
        self
    ):

        if (
            not self.unit_economics_query
            or not self.keyboard_service
        ):

            return {
                "error": True,
                "message": (
                    "Юнит-экономика недоступна"
                )
            }


        products = (
            self.unit_economics_query
            .product_service
            .load_products()
        )


        skus = []


        for product in (products or []):

            sku = self._extract_sku(
                product
            )

            if sku is not None:

                skus.append(
                    str(sku)
                )


        if not skus:

            return {
                "error": False,
                "message": "Товары не найдены"
            }


        return {
            "error": False,
            "message": "Выберите товар:",
            "keyboard": (
                self.keyboard_service
                .build_unit_economics_keyboard(
                    skus
                )
            )
        }



    def _show_unit_economics(
        self,
        sku
    ):

        if not self.unit_economics_query:

            return {
                "error": True,
                "message": (
                    "Юнит-экономика недоступна"
                )
            }


        result = (
            self.unit_economics_query
            .query(
                sku
            )
        )


        return {
            "error": result.get(
                "error",
                False
            ),
            "message": (
                self.unit_economics_query
                .format_response(
                    result
                )
            ),
            "unit_economics": result
        }



    def _extract_sku(
        self,
        product
    ):

        if isinstance(
            product,
            dict
        ):

            return product.get(
                "sku"
            )


        try:

            return product[2]

        except (
            TypeError,
            IndexError
        ):

            return None