from assistant_app import create_assistant


from services.assistant_keyboard_service import (
    AssistantKeyboardService
)


from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)



def main():

    assistant = (
        create_assistant()
    )


    keyboard = (
        AssistantKeyboardService()
    )


    buttons = (
        AssistantButtonHandlerService(
            assistant
        )
    )


    print(
        "AI Assistant кнопочное меню"
    )


    while True:

        menu = (
            keyboard
            .build_main_keyboard()
        )


        print(
            "\nВыберите действие:"
        )


        for index, button in enumerate(
            menu["buttons"],
            start=1
        ):

            print(
                f"{index}. {button['text']}"
            )


        print(
            "0. Выход"
        )


        choice = input(
            "\nВаш выбор: "
        )


        if choice == "0":

            break


        try:

            button = (
                menu["buttons"]
                [
                    int(choice) - 1
                ]
            )


        except Exception:

            print(
                "Неверный выбор"
            )

            continue



        result = (
            buttons.handle(
                button["callback"]
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


        if "message" in result:

            print(
                result["message"]
            )


        elif "actions" in result:

            print(
                result.get(
                    "message",
                    "Готово"
                )
            )


            for action in result["actions"]:

                print(
                    "-",
                    action["title"],
                    "|",
                    action["priority"]
                )


        else:

            print(
                result
            )



if __name__ == "__main__":

    main()