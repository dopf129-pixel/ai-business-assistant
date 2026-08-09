from assistant_app import create_assistant


from services.assistant_session_service import (
    AssistantSessionService
)


from services.assistant_session_storage_service import (
    AssistantSessionStorageService
)


from services.assistant_user_memory_service import (
    AssistantUserMemoryService
)


from services.assistant_user_memory_storage_service import (
    AssistantUserMemoryStorageService
)


from services.assistant_memory_command_service import (
    AssistantMemoryCommandService
)



def main():

    assistant = (
        create_assistant()
    )


    memory = (
        AssistantUserMemoryService(
            AssistantUserMemoryStorageService()
        )
    )


    memory_commands = (
        AssistantMemoryCommandService(
            memory
        )
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
        "Команды:"
    )

    print(
        "history - история"
    )

    print(
        "exit - выход"
    )

    print(
        "запомни ключ значение - сохранить память"
    )

    print(
        "кто я - получить имя"
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
                    "Вы:",
                    item["user"]
                )

                print(
                    "Ассистент:",
                    item["assistant"]["message"]
                )

            continue



        memory_result = (
            memory_commands.handle(
                text
            )
        )


        if not memory_result["error"]:

            if "saved" in memory_result:

                print(
                    "\nАссистент:"
                )

                print(
                    "Запомнил"
                )

                continue



            if "value" in memory_result:

                print(
                    "\nАссистент:"
                )

                print(
                    memory_result["value"]
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