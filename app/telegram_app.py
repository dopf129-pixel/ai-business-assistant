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
        "\nSAVE MEMORY"
    )


    bot.memory_service.remember(
        user_1,
        "имя",
        "Алекс"
    )


    bot.memory_service.remember(
        user_2,
        "имя",
        "Мария"
    )



    print(
        "\nUSER 1001 PROFILE"
    )


    print(
        bot.profiles.get_user(
            user_1
        )
    )



    print(
        "\nUSER 2002 PROFILE"
    )


    print(
        bot.profiles.get_user(
            user_2
        )
    )



    print(
        "\nUSER 1001 MEMORY BUTTON"
    )


    print(
        bot.receive_callback(
            user_1,
            "memory"
        )
    )



    print(
        "\nUSER 2002 MEMORY BUTTON"
    )


    print(
        bot.receive_callback(
            user_2,
            "memory"
        )
    )