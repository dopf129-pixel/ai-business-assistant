"""User-facing Telegram capability guide.

Keep the discoverability text here so the /help command and the inline Help
button cannot drift into two different manuals.
"""


def build_telegram_help_response():
    return {
        "error": False,
        "text": (
            "Как пользоваться ботом\n\n"
            "Выберите готовое действие кнопкой ниже. Бот работает с Ozon "
            "только на чтение и не меняет товары, цены или остатки.\n\n"
            "Если подключено несколько магазинов, откройте /stores и выберите "
            "активный. SKU, себестоимость и аналитика разделяются по магазинам.\n\n"
            "Если нужного действия нет на экране, откройте «Все команды» "
            "или «Примеры фраз».\n\n"
            "Команды: /start, /help, /memory, /ozon_connect, /stores, "
            "/ozon_status, /ozon_disconnect, /costsku."
        ),
        "message": (
            "Как пользоваться ботом\n\n"
            "Выберите готовое действие кнопкой ниже. Бот работает с Ozon "
            "только на чтение и не меняет товары, цены или остатки.\n\n"
            "Если подключено несколько магазинов, откройте /stores и выберите "
            "активный. SKU, себестоимость и аналитика разделяются по магазинам.\n\n"
            "Если нужного действия нет на экране, откройте «Все команды» "
            "или «Примеры фраз».\n\n"
            "Команды: /start, /help, /memory, /ozon_connect, /stores, "
            "/ozon_status, /ozon_disconnect, /costsku."
        ),
        "keyboard": {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "🏪 Магазины Ozon", "callback": "ozon_stores"},
                {"text": "💵 Прибыль за период", "callback": "period_profit"},
                {"text": "💰 Себестоимость", "callback": "seller_cost"},
                {"text": "🧠 Память", "callback": "memory"},
                {"text": "📋 Все команды", "callback": "help:commands"},
                {"text": "💡 Примеры фраз", "callback": "help:examples"},
                {"text": "🏠 Главное меню", "callback": "help:main"},
            ],
        },
        "read_only_ozon": True,
        "executed_ozon": False,
    }


def build_telegram_command_reference():
    return _reference_response(
        "Все команды\n\n"
        "/start — продолжить настройку или открыть главное меню\n"
        "/help — открыть эту памятку\n"
        "/memory — показать сохранённые факты\n"
        "/ozon_connect CLIENT_ID API_KEY — подключить ещё один кабинет Ozon и сделать его активным\n"
        "/stores — показать подключённые магазины и выбрать активный\n"
        "/ozon_status — показать активный магазин Ozon\n"
        "/ozon_disconnect — отключить только активный магазин\n"
        "/costsku SKU СУММА — технический способ сохранить текущую "
        "себестоимость SKU для активного магазина\n\n"
        "API Key никогда не показывается в ответе. Подключение Ozon "
        "используется только для чтения данных. Данные разных магазинов "
        "хранятся в отдельных контурах."
    )


def build_telegram_phrase_examples():
    return _reference_response(
        "Примеры фраз\n\n"
        "Память:\n"
        "• запомни цена sky = 1290\n"
        "• запомни поставщик sky ООО Пример\n\n"
        "Прибыль за произвольный период:\n"
        "• прибыль с 01.08.2026 по 31.08.2026\n\n"
        "Историческая себестоимость (только с датой начала действия):\n"
        "• SKU 123: себестоимость 450 ₽ с 01.01.2026\n\n"
        "Связь старого и текущего SKU:\n"
        "• SKU 111 и SKU 222 — один товар\n"
        "• Отменить связь SKU 111 и SKU 222\n\n"
        "Свободные факты сохраняются только по явной фразе «запомни». "
        "Подтверждение связи SKU не создаёт себестоимость, а неизвестные "
        "финансовые данные бот не угадывает."
    )


def _reference_response(message):
    return {
        "error": False,
        "text": message,
        "message": message,
        "keyboard": {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "⬅️ К помощи", "callback": "help"},
                {"text": "🏠 Главное меню", "callback": "help:main"},
            ],
        },
        "read_only_ozon": True,
        "executed_ozon": False,
    }
