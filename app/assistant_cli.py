from assistant_app import create_assistant


def main():

    assistant = create_assistant()


    print(
        "AI Assistant запущен"
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


        result = (
            assistant.ask(
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