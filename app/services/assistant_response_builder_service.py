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
            "Следующий шаг"
        ):


            next_action = (
                result.get(
                    "next_action"
                )
            )


            text = (
                "Следующий шаг"
            )


            if next_action:


                title = (
                    next_action.get(
                        "title",
                        ""
                    )
                )


                if title:


                    text += (
                        "\n\n"
                        +
                        title
                    )



            return {

                "error": False,

                "message":
                    text
            }






        task_details = (
            result.get(
                "task_details"
            )
        )


        if task_details:


            text = ""


            task = (
                task_details.get(
                    "task"
                )
            )


            if task:


                text += (
                    "Детали задачи: "
                    +
                    task
                )



            history = (
                task_details.get(
                    "history",
                    []
                )
            )


            for item in history:


                text += (
                    "\n\n"
                    +
                    item.get(
                        "title",
                        ""
                    )
                )


                result_data = (
                    item.get(
                        "result",
                        {}
                    )
                )


                if "result" in result_data:


                    result_data = (
                        result_data["result"]
                    )



                if result_data:


                    message = (
                        result_data.get(
                            "message"
                        )
                    )


                    if message:


                        text += (
                            "\n\nРезультат:\n"
                            +
                            message
                        )



                    details = (
                        result_data.get(
                            "details",
                            []
                        )
                    )


                    if details:


                        text += (
                            "\n\nПодробности:"
                        )


                        for detail in details:


                            text += (
                                "\n• "
                                +
                                detail
                            )



            return {

                "error": False,

                "message":
                    text.strip()
            }
        task_history = (
            result.get(
                "task_history"
            )
        )


        if task_history:


            text = ""


            task = (
                task_history.get(
                    "task"
                )
            )


            if task:


                text += (
                    "История задачи: "
                    +
                    task
                )



            history = (
                task_history.get(
                    "history",
                    []
                )
            )


            if history:


                text += (
                    "\n\n"
                )


                for item in history:


                    text += (

                        "✅ "
                        +
                        item.get(
                            "title",
                            ""
                        )
                        +
                        "\n"

                    )


                    result_data = (
                        item.get(
                            "result",
                            {}
                        )
                    )


                    if "result" in result_data:


                        result_data = (
                            result_data["result"]
                        )



                    if result_data:


                        message_text = (
                            result_data.get(
                                "message"
                            )
                        )


                        if message_text:


                            text += (
                                message_text
                                +
                                "\n"
                            )



            return {

                "error": False,

                "message":
                    text.strip()
            }







        task_status = (
            result.get(
                "task_status"
            )
        )


        if task_status:


            text = ""


            task = (
                task_status.get(
                    "task"
                )
            )


            if task:


                text += (
                    "Задача: "
                    +
                    task
                )



            progress = (
                task_status.get(
                    "progress",
                    {}
                )
            )


            text += (
                "\n\nПрогресс: "
                +
                str(
                    progress.get(
                        "done",
                        0
                    )
                )
                +
                "/"
                +
                str(
                    progress.get(
                        "total",
                        0
                    )
                )
            )



            actions = (
                task_status.get(
                    "actions",
                    []
                )
            )


            if actions:


                text += (
                    "\n\n"
                )


                for action in actions:


                    text += (

                        action.get(
                            "icon",
                            ""
                        )
                        +
                        " "
                        +
                        action.get(
                            "title",
                            ""
                        )
                        +
                        "\n"

                    )



            return {

                "error": False,

                "message":
                    text.strip()
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