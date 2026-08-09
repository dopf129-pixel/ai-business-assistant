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


    user_id = 1001



    print(
        "\nSTART"
    )

    print(
        bot.receive_message(
            user_id,
            "/start"
        )
    )



    print(
        "\nHELP"
    )

    print(
        bot.receive_message(
            user_id,
            "/help"
        )
    )



    print(
        "\nMEMORY BEFORE"
    )

    print(
        bot.receive_message(
            user_id,
            "/memory"
        )
    )



    print(
        "\nSAVE MEMORY"
    )

    print(
        bot.receive_message(
            user_id,
            "запомни имя Алекс"
        )
    )



    print(
        "\nMEMORY AFTER"
    )

    print(
        bot.receive_message(
            user_id,
            "/memory"
        )
    )