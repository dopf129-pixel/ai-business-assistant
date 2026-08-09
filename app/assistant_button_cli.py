from assistant_app import create_assistant


from services.assistant_menu_service import (
    AssistantMenuService
)

from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)



def main():

    assistant = (
        create_assistant()
    )


    menu = (
        AssistantMenuService()
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

        menu_result = (
            menu.get_menu()
        )


        print(
            "\nВыберите действие:"
        )


        for index, button in enumerate(
            menu_result["buttons"],
            start=1
        ):

            print(
                f"{index}. {button['title']}"
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

            index = (
                int(choice) - 1
            )

            button_id = (
                menu_result["buttons"]
                [index]
                ["id"]
            )


        except Exception:

            print(
                "Неверный выбор"
            )

            continue



        result = (
            buttons.handle(
                button_id
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

        else:

            print(
                result
            )



if __name__ == "__main__":

    main()