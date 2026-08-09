from assistant_app import create_assistant


from services.assistant_session_service import (
    AssistantSessionService
)


from services.assistant_session_storage_service import (
    AssistantSessionStorageService
)



def main():

    assistant = (
        create_assistant()
    )


    session = (
        AssistantSessionService(
            assistant,
            AssistantSessionStorageService()
        )
    )


    print(
        "AI Assistant запущен"
    )

    print(
        "Введите 'history' для истории"
    )

    print(
        "Введите 'exit' для выхода"
    )


    while True:

        text = input(
            "\nВы: "
        )


        if text.lower() == "exit":

            break



        if text.lower() == "history":

            history = (
                session.get_history()
            )


            print(
                "\nИстория:"
            )


            for item in history["history"]:

                print(
                    "\nВы:",
                    item["user"]
                )


                print(
                    "Ассистент:",
                    item["assistant"]["message"]
                )


                if (
                    "actions"
                    in item["assistant"]
                ):

                    for action in (
                        item["assistant"]["actions"]
                    ):

                        print(
                            "-",
                            action["title"],
                            "|",
                            action["priority"]
                        )


            continue



        result = (
            session.ask(
                text
            )
        )


        if result["error"]:

            print(
                "Ошибка:",
                result["message"]
            )

            continue



        print(
            "\nАссистент:"
        )


        print(
            result["message"]
        )


        for action in result.get(
            "actions",
            []
        ):

            print(
                "-",
                action["title"],
                "|",
                action["priority"]
            )



if __name__ == "__main__":

    main()