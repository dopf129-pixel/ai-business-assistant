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
        "file_content": "\ufeffАртикул;Ozon SKU;Себестоимость, ₽\nART-1;101;\n",
    }

    asyncio.run(telegram_api_bot._send_result(message, result))

    assert len(message.documents) == 1
    sent = message.documents[0]
    assert sent["filename"] == "sebestoymost.csv"
    assert sent["document"].getvalue().decode("utf-8").startswith("\ufeffАртикул;Ozon SKU")
    assert "отправьте этот CSV-файл обратно" in sent["caption"]


def test_build_application_registers_document_handler():
    application = telegram_api_bot.build_application("123456:TEST_TOKEN")
    callbacks = [
        handler.callback.__name__
        for group in application.handlers.values()
        for handler in group
        if hasattr(handler, "callback")
    ]
    assert "document_handler" in callbacks
