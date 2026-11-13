from __future__ import annotations

import asyncio

from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter
from telegram_app_layer import telegram_api_bot


class _SellerCosts:
    def __init__(self):
        self.calls = []

    def import_table_for_user(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"error": False, "message": "CSV path preserved", "read_only_ozon": True}


class _ReportImporter:
    def __init__(self):
        self.documents = []
        self.callbacks = []

    def handle_document(self, *args):
        self.documents.append(args)
        return {"error": False, "handled": True, "code": "REPORT_ROUTE", "read_only_ozon": True}

    def handle_callback(self, *args):
        self.callbacks.append(args)
        return {"error": False, "handled": True, "code": "REPORT_CALLBACK", "read_only_ozon": True}


def test_xlsx_routes_to_fifo_importer_and_csv_keeps_existing_cost_table_path():
    seller_costs = _SellerCosts()
    importer = _ReportImporter()
    adapter = SellerCostTelegramAdapter(
        None, None, None,
        seller_cost_service=seller_costs,
        fifo_report_import_service=importer,
    )

    xlsx = adapter.handle_document(b"xlsx", user_id="owner-1", filename="stock.xlsx")
    csv = adapter.handle_document(b"csv", user_id="owner-1", filename="costs.csv")

    assert xlsx["code"] == "REPORT_ROUTE"
    assert importer.documents == [("owner-1", b"xlsx", "stock.xlsx")]
    assert csv["message"] == "CSV path preserved"
    assert len(seller_costs.calls) == 1


def test_fifo_report_callback_routes_without_interfering_with_existing_callbacks():
    importer = _ReportImporter()
    adapter = SellerCostTelegramAdapter(
        None, None, None,
        fifo_report_import_service=importer,
    )
    result = adapter.handle_button("fifo_report:confirm:012345abcdef", user_id="owner-1")
    assert result["code"] == "REPORT_CALLBACK"
    assert importer.callbacks == [("owner-1", "fifo_report:confirm:012345abcdef")]


def test_oversize_xlsx_is_rejected_before_telegram_download(monkeypatch):
    class _Message:
        document = type("Document", (), {
            "file_name": "oversize.xlsx",
            "file_size": 10 * 1024 * 1024 + 1,
            "file_id": "synthetic-file-id",
        })()

        def __init__(self):
            self.replies = []

        async def reply_text(self, value):
            self.replies.append(value)

    message = _Message()
    update = type("Update", (), {
        "effective_user": type("User", (), {"id": 7})(),
        "effective_chat": type("Chat", (), {"id": 7})(),
        "message": message,
    })()

    async def unexpected_progress(*args, **kwargs):
        raise AssertionError("oversize file should be rejected before progress/download")

    monkeypatch.setattr(telegram_api_bot, "begin_progress", unexpected_progress)
    asyncio.run(telegram_api_bot.document_handler(update, context=object()))
    assert len(message.replies) == 1
    assert "10 МиБ" in message.replies[0]
