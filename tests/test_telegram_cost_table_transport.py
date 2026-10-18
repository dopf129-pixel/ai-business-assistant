import asyncio
from types import SimpleNamespace

from telegram_app_layer import telegram_api_bot


class _Message:
    def __init__(self):
        self.documents = []
        self.texts = []

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)

    async def reply_text(self, text, **kwargs):
        self.texts.append((text, kwargs))


def test_send_result_sends_generated_cost_table_as_document():
    message = _Message()
    result = {
        "error": False,
        "message": "Таблица готова",
        "filename": "sebestoymost.csv",
        "mime_type": "text/csv",
        "document_kind": "seller_cost_import_template",
        "file_content": "\ufeffАртикул;Ozon SKU;Себестоимость, ₽\nART-1;101;\n",
    }

    asyncio.run(telegram_api_bot._send_result(message, result))

    assert len(message.documents) == 1
    sent = message.documents[0]
    assert sent["filename"] == "sebestoymost.csv"
    assert sent["document"].getvalue().decode("utf-8").startswith("\ufeffАртикул;Ozon SKU")
    assert "отправьте этот CSV-файл обратно" in sent["caption"]


def test_failed_document_delivery_does_not_report_success():
    class FailingMessage(_Message):
        async def reply_document(self, **kwargs):
            raise RuntimeError("transport unavailable")

    message = FailingMessage()
    result = {
        "error": False,
        "message": "Таблица готова",
        "filename": "sebestoymost.csv",
        "mime_type": "text/csv",
        "document_kind": "seller_cost_import_template",
        "file_content": "\ufeffАртикул;Ozon SKU\n",
    }

    outcome = asyncio.run(telegram_api_bot._send_result(message, result))

    assert outcome["status"] == "TELEGRAM_DOCUMENT_SEND_FAILED"
    assert len(message.documents) == 0
    assert len(message.texts) == 1
    assert "не удалось отправить" in message.texts[0][0].lower()
    assert "Таблица готова" not in message.texts[0][0]


def test_failed_support_diagnostic_delivery_does_not_report_success():
    class FailingMessage(_Message):
        async def reply_document(self, **kwargs):
            raise RuntimeError("transport unavailable")

    message = FailingMessage()
    result = {
        "error": False,
        "message": "Обезличенная диагностика готова",
        "filename": "period_profit_support_diagnostic.json",
        "mime_type": "application/json",
        "document_kind": "support_diagnostic",
        "file_content": b'{"schema":"period_profit_support_diagnostic"}',
    }

    outcome = asyncio.run(telegram_api_bot._send_result(message, result))

    assert outcome["status"] == "TELEGRAM_DOCUMENT_SEND_FAILED"
    assert len(message.documents) == 0
    assert len(message.texts) == 1
    assert "не удалось отправить" in message.texts[0][0].lower()
    assert "диагностика готова" not in message.texts[0][0].lower()


def test_analytics_export_document_uses_read_only_caption():
    message = _Message()
    payload = b'{"document_kind":"owner_analytics_export"}'
    result = {
        "error": False,
        "message": "Экспорт сформирован",
        "filename": "ozon_period_profit_export.json",
        "mime_type": "application/json",
        "document_kind": "analytics_export",
        "file_content": payload,
    }

    asyncio.run(telegram_api_bot._send_result(message, result))

    assert len(message.documents) == 1
    assert message.documents[0]["document"].getvalue() == payload
    assert "нельзя загружать как таблицу себестоимости" in message.documents[0]["caption"]


def test_public_callback_handler_delivers_analytics_export(monkeypatch):
    message = _Message()
    message.chat_id = 101

    class _Query:
        from_user = SimpleNamespace(id=505)
        data = "period_profit_export:json:012345abcdef"

        async def answer(self):
            self.answered = True

    class _Runner:
        def receive_callback(self, user_id, callback):
            assert user_id == 505
            assert callback == "period_profit_export:json:012345abcdef"
            return {
                "error": False,
                "message": "Экспорт сформирован",
                "filename": "ozon_period_profit_export.json",
                "mime_type": "application/json",
                "document_kind": "analytics_export",
                "file_content": b'{"document_kind":"owner_analytics_export"}',
            }

    query = _Query()
    query.message = message
    async def begin_progress(*args, **kwargs):
        return None
    monkeypatch.setattr(telegram_api_bot, "begin_progress", begin_progress)
    async def run_sync(function, **kwargs):
        return function()
    monkeypatch.setattr(telegram_api_bot, "_run_sync_with_stall_notice", run_sync)
    monkeypatch.setattr(telegram_api_bot, "get_runner", lambda: _Runner())

    asyncio.run(telegram_api_bot.callback_handler(
        SimpleNamespace(callback_query=query), SimpleNamespace(bot=object())
    ))

    assert query.answered is True
    assert len(message.documents) == 1
    assert message.documents[0]["filename"] == "ozon_period_profit_export.json"


def test_build_application_registers_document_handler():
    application = telegram_api_bot.build_application("123456:TEST_TOKEN")
    callbacks = [
        handler.callback.__name__
        for group in application.handlers.values()
        for handler in group
        if hasattr(handler, "callback")
    ]
    assert "document_handler" in callbacks
