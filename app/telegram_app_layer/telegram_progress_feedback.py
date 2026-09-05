FINANCE_TOKENS = (
    "прибыл",
    "финанс",
    "выруч",
    "марж",
    "начислен",
    "profit",
)


def should_show_progress(text):
    value = " ".join(str(text or "").strip().lower().split())
    if not value:
        return False
    if value.startswith("/"):
        return False
    return True


def progress_text(text=None):
    value = " ".join(str(text or "").strip().lower().split())
    if any(token in value for token in FINANCE_TOKENS):
        return "⏳ Загружаю финансовые данные Ozon…"
    return "⏳ Обрабатываю запрос…"


async def begin_progress(message, bot=None, chat_id=None, text=None, force=False):
    if not force and not should_show_progress(text):
        return None

    if bot is not None and chat_id is not None:
        sender = getattr(bot, "send_chat_action", None)
        if callable(sender):
            try:
                await sender(chat_id=chat_id, action="typing")
            except Exception:
                pass

    try:
        return await message.reply_text(progress_text(text))
    except Exception:
        return None


async def finish_progress(message, progress_message, response, reply_markup=None):
    if progress_message is not None:
        editor = getattr(progress_message, "edit_text", None)
        if callable(editor):
            try:
                await editor(response, reply_markup=reply_markup)
                return "edited"
            except Exception:
                pass

    await message.reply_text(response, reply_markup=reply_markup)
    return "sent"
