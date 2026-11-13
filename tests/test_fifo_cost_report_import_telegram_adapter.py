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


def test_selected_physical_sales_file_uses_transition_route_before_legacy_cost_csv():
    class _TransitionRuntime:
        def __init__(self):
            self.documents = []
            self.callbacks = []

        def has_physical_sales_document_selection(self, user_id):
            return user_id == "owner-1"

        def handle_physical_sales_document(self, user_id, content, filename):
            self.documents.append((user_id, content, filename))
            return {"error": False, "handled": True, "code": "PHYSICAL_ROUTE"}

        def handle_physical_sales_callback(self, user_id, callback):
            self.callbacks.append((user_id, callback))
            return {"error": False, "handled": True, "code": "PHYSICAL_CALLBACK"}

        def preflight_physical_sales_document(self, user_id, filename, file_size):
            return {"error": False, "selected": True, "accepted": True}

    seller_costs = _SellerCosts()
    runtime = _TransitionRuntime()
    adapter = SellerCostTelegramAdapter(
        None, None, None,
        seller_cost_service=seller_costs,
        fifo_transition_runtime_service=runtime,
    )
    result = adapter.handle_document(b"physical", user_id="owner-1", filename="sales.csv")
    callback = adapter.handle_button(
        "fifo_physical:confirm:012345abcdef", user_id="owner-1",
    )
    admission = adapter.preflight_document_upload(
        "owner-1", "sales.csv", 100,
    )
    assert result["code"] == "PHYSICAL_ROUTE"
    assert runtime.documents == [("owner-1", b"physical", "sales.csv")]
    assert callback["code"] == "PHYSICAL_CALLBACK"
    assert runtime.callbacks == [("owner-1", "fifo_physical:confirm:012345abcdef")]
    assert admission["accepted"] is True
    assert seller_costs.calls == []


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

    monkeypatch.setattr(
        telegram_api_bot, "get_runner",
        lambda: type("Runner", (), {
            "preflight_document_upload": lambda self, *args: {
                "error": False, "selected": False,
            },
        })(),
    )
    monkeypatch.setattr(telegram_api_bot, "begin_progress", unexpected_progress)
    asyncio.run(telegram_api_bot.document_handler(update, context=object()))
    assert len(message.replies) == 1
    assert "10 МиБ" in message.replies[0]


def test_selected_oversize_physical_sales_csv_is_rejected_before_download(monkeypatch):
    class _Message:
        document = type("Document", (), {
            "file_name": "physical-sales.csv",
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
    context = type("Context", (), {
        "bot": type("Bot", (), {
            "get_file": lambda *args: (_ for _ in ()).throw(
                AssertionError("oversize file must be rejected before get_file")
            ),
        })(),
    })()

    class _Runner:
        def preflight_document_upload(self, user_id, filename, file_size):
            assert user_id == 7 and filename == "physical-sales.csv"
            assert file_size == 10 * 1024 * 1024 + 1
            return {
                "error": False,
                "selected": True,
                "accepted": False,
                "message": "CSV больше 10 МиБ; не загружен.",
            }

    monkeypatch.setattr(telegram_api_bot, "get_runner", lambda: _Runner())
    asyncio.run(telegram_api_bot.document_handler(update, context=context))
    assert message.replies == ["CSV больше 10 МиБ; не загружен."]
