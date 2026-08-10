class AssistantResponseBuilderService:


    def build(
        self,
        result
    ):


        message = (
            result.get(
                "message"
            )
        )



        execution = (
            result.get(
                "execution"
            )
        )



        if execution:


            action = (
                execution.get(
                    "action"
                )
            )


            text = (
                execution.get(
                    "message",
                    "Действие выполнено"
                )
            )


            if action:


                text += (
                    "\n\n"
                    +
                    action.get(
                        "title",
                        ""
                    )
                )


                action_result = (
                    action.get(
                        "result",
                        {}
                    )
                )


                if "result" in action_result:

                    action_result = (
                        action_result["result"]
                    )


                if action_result:


                    result_message = (
                        action_result.get(
                            "message"
                        )
                    )


                    if result_message:

                        text += (
                            "\n\nРезультат:\n"
                            +
                            result_message
                        )


                    details = (
                        action_result.get(
                            "details",
                            []
                        )
                    )


                    if details:


                        text += (
                            "\n\nДетали:"
                        )


                        for item in details:

                            text += (
                                "\n• "
                                +
                                item
                            )



            return {

                "error": False,

                "message":
                    text,

                "action":
                    action
            }





        if (
            message
            ==
            "Продолжаем работу"
        ):


            text = (
                "Продолжаем работу"
            )


            task = (
                result.get(
                    "task"
                )
            )


            if task:


                text += (
                    "\n\nЗадача: "
                    +
                    task
                )



            next_step = (
                result.get(
                    "next_step"
                )
            )


            if isinstance(
                next_step,
                dict
            ):


                title = (
                    next_step.get(
                        "title",
                        ""
                    )
                )


                if title:

                    text += (
                        "\n\nСледующий шаг:\n"
                        +
                        title
                    )


            elif next_step:


                text += (
                    "\n\nСледующий шаг:\n"
                    +
                    str(
                        next_step
                    )
                )



            return {

                "error": False,

                "message":
                    text
            }





        count = (
            result.get(
                "count",
                0
            )
        )



        if count == 0:


            return {

                "error": False,

                "message":
                    "Проблем не найдено"
            }



        return {

            "error": False,

            "message":
                f"Создано действий: {count}",

            "actions":
                result.get(
                    "actions",
                    []
                )
        }