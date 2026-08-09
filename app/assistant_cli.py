from assistant_app import create_assistant
from services.assistant_session_service import (
    AssistantSessionService
)


def main():

    assistant = create_assistant()


    session = (
        AssistantSessionService(
            assistant
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
                    "Вы:",
                    item["user"]
                )

                print(
                    "Ассистент:",
                    item["assistant"]["message"]
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