class AssistantResponseBuilderService:


    def build(
        self,
        result
    ):


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







        message = (
            result.get(
                "message"
            )
        )



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


                action_result = (
                    action.get(
                        "result",
                        {}
                    )
                )


                if (
                    "result"
                    in action_result
                ):

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



            next_action = (
                result.get(
                    "next_action"
                )
            )


            if next_action:


                text += (
                    "\n\nСледующий шаг:\n"
                    +
                    next_action.get(
                        "title",
                        ""
                    )
                )



            completed = (
                result.get(
                    "completed",
                    False
                )
            )


            if completed:


                progress = (
                    result.get(
                        "progress",
                        {}
                    )
                )


                text += (
                    "\n\n✅ Задача выполнена"
                )


                text += (
                    "\n\nВыполнено: "
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