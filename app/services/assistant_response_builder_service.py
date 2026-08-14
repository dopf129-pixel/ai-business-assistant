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


        if (
            execution
            and
            execution.get(
                "error"
            )
        ):


            return {

                "error": True,

                "message":
                    execution.get(
                        "message",
                        "Ошибка выполнения"
                    ),

                "execution":
                    execution

            }



        if (
            message
            ==
            "Задача поставлена на паузу"
        ):


            return {

                "error": False,

                "message":
                    "Задача поставлена на паузу",

                "status":
                    result.get(
                        "status"
                    )

            }



        if (
            message
            ==
            "Задача возобновлена"
        ):


            return {

                "error": False,

                "message":
                    "Задача возобновлена",

                "status":
                    result.get(
                        "status"
                    )

            }



        if (
            message
            ==
            "Задача отменена"
        ):


            task = (
                result.get(
                    "cancelled_task",
                    ""
                )
            )


            text = (
                "Задача отменена"
            )


            if task:


                text += (
                    "\n\n"
                    +
                    task
                )


            return {

                "error": False,

                "message":
                    text

            }



        if (
            message
            ==
            "Шаг пропущен"
        ):


            action = (
                result.get(
                    "action"
                )
            )


            next_action = (
                result.get(
                    "next_action"
                )
            )


            text = (
                "Шаг пропущен"
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


            if next_action:


                text += (
                    "\n\nСледующий шаг:\n"
                    +
                    next_action.get(
                        "title",
                        ""
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


                text += (
                    "\n\n"
                    +
                    next_action.get(
                        "title",
                        ""
                    )
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


            if history:


                for item in history:


                    text += (
                        "\n\n"
                        +
                        item.get(
                            "title",
                            ""
                        )
                    )


                    if item.get(
                        "message"
                    ):


                        text += (
                            "\n"
                            +
                            item.get(
                                "message"
                            )
                        )


                    item_result = (
                        item.get(
                            "result"
                        )
                        or
                        {}
                    )


                    if (
                        "result"
                        in
                        item_result
                    ):


                        item_result = (
                            item_result["result"]
                        )


                    if item_result:


                        item_message = (
                            item_result.get(
                                "message"
                            )
                        )


                        if item_message:


                            text += (
                                "\n"
                                +
                                item_message
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


                    status = (
                        item.get(
                            "status"
                        )
                    )


                    if status == "SKIPPED":

                        icon = "⏭"

                    else:

                        icon = "✅"



                    text += (
                        icon
                        +
                        " "
                        +
                        item.get(
                            "title",
                            ""
                        )
                        +
                        "\n"
                        +
                        item.get(
                            "message",
                            "Действие выполнено"
                        )
                        +
                        "\n"
                    )


                    if item.get(
                        "message"
                    ):


                        text += (
                            item.get(
                                "message"
                            )
                            +
                            "\n"
                        )


                    item_result = (
                        item.get(
                            "result"
                        )
                        or
                        {}
                    )


                    if (
                        "result"
                        in
                        item_result
                    ):


                        item_result = (
                            item_result["result"]
                        )


                    if item_result:


                        item_message = (
                            item_result.get(
                                "message"
                            )
                        )


                        if item_message:


                            text += (
                                item_message
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


                action_result = (
                    action.get(
                        "result",
                        {}
                    )
                )


                if (
                    "result"
                    in
                    action_result
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
                            "\n\n"
                            +
                            result_message
                        )


                    details = (
                        action_result.get(
                            "details",
                            []
                        )
                    )


                    for detail in details:


                        text += (
                            "\n- "
                            +
                            detail
                        )


            return {

                "error": False,

                "message":
                    text,

                "action":
                    action

            }


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


            return {

                "error": False,

                "message":
                    message,

                "task":
                    result.get(
                        "task",
                        ""
                    ),

                "next_step":
                    result.get(
                        "next_step"
                    )

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