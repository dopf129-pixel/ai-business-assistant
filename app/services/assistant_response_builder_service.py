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



            last_completed = (
                result.get(
                    "last_completed"
                )
            )



            if last_completed:


                text += (
                    "\n\nПоследний выполненный шаг:\n"
                    +
                    last_completed.get(
                        "title",
                        ""
                    )
                )



                execution_result = (
                    last_completed
                    .get(
                        "result",
                        {}
                    )
                )



                if (
                    "result"
                    in execution_result
                ):

                    execution_result = (
                        execution_result["result"]
                    )



                if execution_result:


                    result_message = (
                        execution_result
                        .get(
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
                        execution_result
                        .get(
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
                    next_step
                    .get(
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





        if (
            message
            ==
            "Действие выполнено"
        ):


            action = (
                result.get(
                    "action"
                )
            )



            text = (
                "Действие выполнено"
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



            return {

                "error": False,

                "message":
                    text,

                "action":
                    action
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