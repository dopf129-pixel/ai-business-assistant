import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from telegram_app_layer.telegram_progress_feedback import (
    MAX_TELEGRAM_TEXT_UNITS,
    begin_progress,
    finish_progress,
    progress_text,
    should_show_progress,
    split_telegram_text,
)


class FakeProgressMessage:
    def __init__(self, fail_edit=False):
        self.fail_edit = fail_edit
        self.edits = []

    async def edit_text(self, text, reply_markup=None):
        if self.fail_edit:
            raise RuntimeError("edit unavailable")
        self.edits.append((text, reply_markup))


class FakeMessage:
    def __init__(self, progress=None, fail_reply=False):
        self.progress = progress or FakeProgressMessage()
        self.fail_reply = fail_reply
        self.replies = []

    async def reply_text(self, text, reply_markup=None):
        if self.fail_reply:
            raise RuntimeError("send unavailable")
        self.replies.append((text, reply_markup))
        if len(self.replies) == 1:
            return self.progress
        return FakeProgressMessage()


class FakeBot:
    def __init__(self, fail=False):
        self.fail = fail
        self.actions = []

    async def send_chat_action(self, chat_id, action):
        if self.fail:
            raise RuntimeError("typing unavailable")
        self.actions.append((chat_id, action))


class TestTelegramLoadingFeedbackV1451V1460(unittest.IsolatedAsyncioTestCase):
    def test_trivial_commands_skip_progress(self):
        self.assertFalse(should_show_progress("/help"))
        self.assertFalse(should_show_progress("/start"))
        self.assertFalse(should_show_progress("/costsku 1 100"))
        self.assertTrue(should_show_progress("Прибыль за 28 дней"))

    def test_finance_request_has_specific_text(self):
        self.assertEqual(
            progress_text("Прибыль за период"),
            "⏳ Загружаю финансовые данные Ozon…",
        )

    async def test_progress_is_sent_before_result_and_replaced(self):
        progress = FakeProgressMessage()
        message = FakeMessage(progress=progress)
        bot = FakeBot()

        handle = await begin_progress(
            message, bot=bot, chat_id=7, text="Прибыль за период"
        )
        self.assertIs(handle, progress)
        self.assertEqual(bot.actions, [(7, "typing")])
        self.assertEqual(
            message.replies[0][0],
            "⏳ Загружаю финансовые данные Ozon…",
        )

        mode = await finish_progress(message, handle, "Готовый отчёт")
        self.assertEqual(mode, "edited")
        self.assertEqual(progress.edits[0][0], "Готовый отчёт")
        self.assertEqual(len(message.replies), 1)

    async def test_edit_failure_falls_back_without_duplicate_final(self):
        progress = FakeProgressMessage(fail_edit=True)
        message = FakeMessage(progress=progress)
        handle = await begin_progress(message, text="Отчёт по прибыли")
        mode = await finish_progress(message, handle, "Готово")

        self.assertEqual(mode, "sent")
        self.assertEqual([item[0] for item in message.replies], [
            "⏳ Загружаю финансовые данные Ozon…",
            "Готово",
        ])

    async def test_typing_failure_does_not_block_progress_or_final(self):
        message = FakeMessage()
        handle = await begin_progress(
            message,
            bot=FakeBot(fail=True),
            chat_id=7,
            text="Продажи за период",
        )
        self.assertIsNotNone(handle)
        await finish_progress(message, handle, "Результат")
        self.assertEqual(handle.edits[0][0], "Результат")

    async def test_error_can_replace_same_progress_message(self):
        progress = FakeProgressMessage()
        message = FakeMessage(progress=progress)
        handle = await begin_progress(message, text="Финансы")
        await finish_progress(message, handle, "⚠️ Ошибка загрузки")
        self.assertEqual(progress.edits[0][0], "⚠️ Ошибка загрузки")

    async def test_long_report_is_split_and_keyboard_is_attached_to_last_part(self):
        progress = FakeProgressMessage()
        message = FakeMessage(progress=progress)
        keyboard = object()
        response = (
            "🧪 Экономика магазина\n"
            + "Детализация начислений Ozon — 123 456.78 ₽\n" * 180
        )

        mode = await finish_progress(
            message,
            progress,
            response,
            reply_markup=keyboard,
        )

        chunks = [progress.edits[0][0]] + [
            item[0] for item in message.replies
        ]
        marks = [progress.edits[0][1]] + [
            item[1] for item in message.replies
        ]
        self.assertEqual(mode, "split")
        self.assertEqual("".join(chunks), response)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(
            all(
                len(chunk.encode("utf-16-le")) // 2
                <= MAX_TELEGRAM_TEXT_UNITS
                for chunk in chunks
            )
        )
        self.assertTrue(all(mark is None for mark in marks[:-1]))
        self.assertIs(marks[-1], keyboard)

    async def test_long_report_falls_back_to_split_replies_if_edit_fails(self):
        progress = FakeProgressMessage(fail_edit=True)
        message = FakeMessage(progress=progress)
        keyboard = object()
        response = (
            "🧪 "
            + "Строка отчёта Ozon с подробной классификацией.\n" * 180
        )

        mode = await finish_progress(
            message,
            progress,
            response,
            reply_markup=keyboard,
        )

        chunks = [item[0] for item in message.replies]
        marks = [item[1] for item in message.replies]
        self.assertEqual(mode, "split")
        self.assertEqual("".join(chunks), response)
        self.assertTrue(
            all(
                len(chunk.encode("utf-16-le")) // 2
                <= MAX_TELEGRAM_TEXT_UNITS
                for chunk in chunks
            )
        )
        self.assertTrue(all(mark is None for mark in marks[:-1]))
        self.assertIs(marks[-1], keyboard)

    def test_split_uses_utf16_units_for_emoji(self):
        response = "🧪" * (MAX_TELEGRAM_TEXT_UNITS // 2 + 1)

        chunks = split_telegram_text(response)

        self.assertEqual(len(chunks), 2)
        self.assertEqual("".join(chunks), response)
        self.assertTrue(
            all(
                len(chunk.encode("utf-16-le")) // 2
                <= MAX_TELEGRAM_TEXT_UNITS
                for chunk in chunks
            )
        )


if __name__ == "__main__":
    unittest.main()
