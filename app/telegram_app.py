from telegram_assistant_factory import (
    create_telegram_assistant
)



if __name__ == "__main__":


    bot = (
        create_telegram_assistant()
    )


    print(
        "Telegram Assistant ready"
    )


    user_1 = 1001


    print(
        "\nUSER MESSAGE"
    )


    print(
        bot.receive_message(
            user_1,
            "запомни имя Алекс"
        )
    )


    print(
        "\nMEMORY BUTTON"
    )


    print(
        bot.receive_callback(
            user_1,
            "memory"
        )
    )