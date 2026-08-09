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

    user_2 = 2002



    print(
        "\nUSER 1001"
    )


    print(
        bot.start(
            user_1
        )
    )


    print(
        bot.receive_message(
            user_1,
            "Что нужно сделать?"
        )
    )



    print(
        "\nUSER 2002"
    )


    print(
        bot.start(
            user_2
        )
    )


    print(
        bot.receive_message(
            user_2,
            "Что нужно сделать?"
        )
    )