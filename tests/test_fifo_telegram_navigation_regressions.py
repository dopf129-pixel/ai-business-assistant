from contextlib import contextmanager
from datetime import date

from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.expense_repository import ExpenseRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.telegram_external_expense_runtime_service import (
    TelegramExternalExpenseRuntimeService,
)
from services.telegram_fifo_cost_rate_entry_service import (
    TelegramFifoCostRateEntryService,
)
from services.telegram_seller_cost_update_service import (
    TelegramSellerCostUpdateService,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from telegram_app_layer.return_inventory_telegram_adapter import (
    ReturnInventoryTelegramAdapter,
)
from telegram_app_layer.seller_cost_telegram_adapter import (
    SellerCostTelegramAdapter,
)
from telegram_app_layer.telegram_bot_service import TelegramBotService


@contextmanager
def _tenant(user="owner-a", store="store-a"):
    token = set_current_tenant_user_id(make_store_tenant_scope(user, store))
    try:
        yield
    finally:
        reset_current_tenant_user_id(token)


class _Assistant:
    def ask(self, text, user_id):
        return {"error": False, "message": "assistant fallback", "text": text}


class _Products:
    def load_products(self):
        return [
            ("product-a", "offer-a", "sku-a"),
            ("product-b", "offer-b", "sku-b"),
        ]


class _Costs:
    def get_all_costs(self):
        return []


class _LegacySellerCostFlow:
    def clear_pending(self, _user_id):
        return None

    def is_confirmation_callback(self, _callback):
        return False

    def handle_button(self, _user_id, _callback):
        return {"error": False, "handled": False}

    def handle_text(self, _user_id, _text):
        return {"error": False, "handled": False}


class _PendingFifoInput:
    def __init__(self, name):
        self.name = name
        self.pending = {}

    def clear_pending(self, user_id):
        self.pending.pop(str(user_id), None)

    def handle_text(self, user_id, _text):
        if str(user_id) in self.pending:
            return {
                "error": False,
                "handled": True,
                "message": self.name + " old wizard",
            }
        return {"error": False, "handled": False}


class _HistoryCallbacks:
    def handle_callback(self, _user_id, callback):
        if callback.endswith(":stale"):
            return {"error": True, "handled": True, "code": "FIFO_CALLBACK_STALE"}
        return {"error": False, "handled": True, "action": "open_history"}


class _RejectedUserProfile:
    def create_user(self, _user_id):
        return {"error": True, "code": "USER_PROFILE_REJECTED"}


def _keyboard_callback(result, prefix):
    return next(
        item["callback"]
        for item in result["keyboard"]["buttons"]
        if item["callback"].startswith(prefix)
    )


def _open_external_expense_amount(adapter, user_id):
    menu = adapter.handle_button("external_expenses", user_id=user_id)
    assert menu.get("status") == "TELEGRAM_EXTERNAL_EXPENSE_PERIOD_MENU", menu
    custom = adapter.handle_button(
        "external_expenses:period:custom", user_id=user_id,
    )
    assert custom.get("status") == "TELEGRAM_EXTERNAL_EXPENSE_CUSTOM_PERIOD_INPUT", custom
    period = adapter.handle_text("01.08.2026 — 31.08.2026", user_id=user_id)
    assert period.get("status") == "TELEGRAM_EXTERNAL_EXPENSE_PERIOD_READY", period
    date_prompt = adapter.handle_button(
        _keyboard_callback(period, "external_expenses:add:"),
        user_id=user_id,
    )
    category_prompt = adapter.handle_text("15.08.2026", user_id=user_id)
    amount_prompt = adapter.handle_text("Аренда", user_id=user_id)
    assert date_prompt["error"] is False
    assert category_prompt["error"] is False
    assert amount_prompt["status"] == "TELEGRAM_EXTERNAL_EXPENSE_INPUT_AMOUNT"


def test_valid_cost_return_for_another_sku_clears_old_fifo_text_master():
    keyboard = AssistantKeyboardService()
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(), keyboard_service=keyboard,
    )
    rate_entry = _PendingFifoInput("FIFO A")
    seller_cost = TelegramSellerCostUpdateService(
        _Products(), _Costs(), date_provider=lambda: date(2026, 11, 7),
    )
    adapter = SellerCostTelegramAdapter(
        assistant=_Assistant(), keyboard_service=keyboard,
        button_handler=handler, seller_cost_service=seller_cost,
        fifo_rate_entry_service=rate_entry,
    )
    rate_entry.pending["101"] = {"step": "awaiting_input"}

    with _tenant():
        callback = handler.create_seller_cost_return_callback(101, "sku-b")
        selected = adapter.handle_button(callback, user_id=101)
        cost_result = adapter.handle_text("123", user_id=101)

    assert selected["seller_cost_input_pending"] is True
    assert rate_entry.pending == {}
    assert cost_result["seller_cost_confirmation_pending"] is True
    assert cost_result["sku"] == "sku-b"
    assert cost_result["cost_price"] == 123.0

    with _tenant():
        missing_target = handler.create_seller_cost_return_callback(
            101, "sku-no-longer-in-catalog",
        )
        rate_entry.pending["101"] = {"step": "awaiting_input"}
        rejected_target = adapter.handle_button(missing_target, user_id=101)
        text_after_rejected_target = adapter.handle_text("321", user_id=101)

        rate_entry.pending["101"] = {"step": "awaiting_input"}
        stale = adapter.handle_button("seller_cost_return:expired", user_id=101)
        text_after_stale = adapter.handle_text("321", user_id=101)

    assert rejected_target["error"] is True
    assert text_after_rejected_target["message"] == "FIFO A old wizard"
    assert stale["error"] is True
    assert text_after_stale["message"] == "FIFO A old wizard"


def test_accepted_fifo_navigation_clears_external_form_but_stale_callback_preserves_it(
    tmp_path,
):
    keyboard = AssistantKeyboardService()
    expenses = TelegramExternalExpenseRuntimeService(
        repository=ExpenseRepository(tmp_path / "expenses.sqlite"),
        keyboard_service=keyboard,
        today_provider=lambda: date(2026, 8, 31),
    )
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(), keyboard_service=keyboard,
        external_expense_runtime_service=expenses,
    )
    rate_entry = _PendingFifoInput("FIFO")
    adapter = ReturnInventoryTelegramAdapter(
        assistant=_Assistant(), keyboard_service=keyboard,
        button_handler=handler, fifo_history_service=_HistoryCallbacks(),
        seller_cost_service=_LegacySellerCostFlow(),
        fifo_rate_entry_service=rate_entry,
    )

    with _tenant():
        _open_external_expense_amount(adapter, 101)
        stale = adapter.handle_button("fifo_history:open:stale", user_id=101)
        text_after_stale = adapter.handle_text("123", user_id=101)

        _open_external_expense_amount(adapter, 102)
        rate_entry.pending["102"] = {"step": "awaiting_input"}
        accepted = adapter.handle_button("fifo_history:open:valid", user_id=102)
        text_after_accepted = adapter.handle_text("123", user_id=102)
        direct_pending = expenses.handle_text("123", user_id=102)

    assert stale["error"] is True
    assert text_after_stale["status"] == "TELEGRAM_EXTERNAL_EXPENSE_INPUT_DESCRIPTION"
    assert accepted["error"] is False
    assert rate_entry.pending == {}
    assert text_after_accepted["message"] == "assistant fallback"
    assert direct_pending is None


def test_start_command_clears_fifo_and_external_text_masters(tmp_path):
    keyboard = AssistantKeyboardService()
    expenses = TelegramExternalExpenseRuntimeService(
        repository=ExpenseRepository(tmp_path / "start-expenses.sqlite"),
        keyboard_service=keyboard,
        today_provider=lambda: date(2026, 8, 31),
    )
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(), keyboard_service=keyboard,
        external_expense_runtime_service=expenses,
    )
    rate_entry = _PendingFifoInput("FIFO rate")
    late_entry = _PendingFifoInput("FIFO late")
    anchor_entry = _PendingFifoInput("FIFO anchor")
    adapter = ReturnInventoryTelegramAdapter(
        assistant=_Assistant(), keyboard_service=keyboard,
        button_handler=handler,
        seller_cost_service=_LegacySellerCostFlow(),
        fifo_rate_entry_service=rate_entry,
        fifo_late_entry_service=late_entry,
        fifo_anchor_entry_service=anchor_entry,
    )
    bot = TelegramBotService(adapter)

    with _tenant():
        _open_external_expense_amount(adapter, 101)
        rate_entry.pending["101"] = {"step": "awaiting_input"}
        late_entry.pending["101"] = {"step": "awaiting_input"}
        anchor_entry.pending["101"] = {"step": "awaiting_input"}
        started = bot.on_start(user_id=101)
        ordinary_text = bot.on_message(101, "123")

    assert started["error"] is False
    assert rate_entry.pending == {}
    assert late_entry.pending == {}
    assert anchor_entry.pending == {}
    assert ordinary_text["message"] == "assistant fallback"


def test_rejected_start_does_not_clear_fifo_input_masters():
    keyboard = AssistantKeyboardService()
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(), keyboard_service=keyboard,
    )
    rate_entry = _PendingFifoInput("FIFO rate")
    rate_entry.pending["101"] = {"step": "awaiting_input"}
    adapter = ReturnInventoryTelegramAdapter(
        assistant=_Assistant(), keyboard_service=keyboard,
        button_handler=handler,
        user_profile_service=_RejectedUserProfile(),
        fifo_rate_entry_service=rate_entry,
    )

    with _tenant():
        result = TelegramBotService(adapter).on_start(user_id=101)

    assert result["error"] is True
    assert rate_entry.pending["101"]["step"] == "awaiting_input"
