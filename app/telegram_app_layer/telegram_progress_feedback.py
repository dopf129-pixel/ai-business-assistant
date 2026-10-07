FINANCE_TOKENS = (
    "прибыл",
    "финанс",
    "выруч",
    "марж",
    "начислен",
    "profit",
)

MAX_TELEGRAM_TEXT_UNITS = 3800


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


def split_telegram_text(text, max_units=MAX_TELEGRAM_TEXT_UNITS):
    value = str(text or "")
    try:
        limit = int(max_units)
    except (TypeError, ValueError, OverflowError):
        limit = MAX_TELEGRAM_TEXT_UNITS
    if limit < 2:
        limit = MAX_TELEGRAM_TEXT_UNITS
    if not value:
        return [value]

    chunks = []
    start = 0
    while start < len(value):
        end = start
        units = 0
        while end < len(value):
            character_units = 2 if ord(value[end]) > 0xFFFF else 1
            if units + character_units > limit:
                break
            units += character_units
            end += 1

        if end == len(value):
            chunks.append(value[start:end])
            break

        newline = value.rfind("\n", start, end)
        space = value.rfind(" ", start, end)
        boundary = max(newline, space)
        if boundary >= start:
            end = boundary + 1
        chunks.append(value[start:end])
        start = end

    return chunks


async def finish_progress(message, progress_message, response, reply_markup=None):
    chunks = split_telegram_text(response)
    edited_first_chunk = False
    if progress_message is not None:
        editor = getattr(progress_message, "edit_text", None)
        if callable(editor):
            try:
                await editor(
                    chunks[0],
                    reply_markup=reply_markup if len(chunks) == 1 else None,
                )
                edited_first_chunk = True
            except Exception:
                pass

    first_unsent_chunk = 1 if edited_first_chunk else 0
    for index in range(first_unsent_chunk, len(chunks)):
        await message.reply_text(
            chunks[index],
            reply_markup=(reply_markup if index == len(chunks) - 1 else None),
        )

    if len(chunks) > 1:
        return "split"
    return "edited" if edited_first_chunk else "sent"
