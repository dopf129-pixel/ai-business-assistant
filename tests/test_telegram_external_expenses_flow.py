from contextlib import contextmanager
from datetime import date
from threading import Event, Thread

from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.expense_repository import ExpenseRepository
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from services.telegram_external_expense_runtime_service import (
    TelegramExternalExpenseRuntimeService,
)


@contextmanager
def _tenant(scope):
    token = set_current_tenant_user_id(scope)
    try:
        yield
    finally:
        reset_current_tenant_user_id(token)


def _runtime(db_path, today=date(2026, 8, 31), repository=None):
    repository = repository or ExpenseRepository(db_path)
    return TelegramExternalExpenseRuntimeService(
        repository=repository,
        keyboard_service=AssistantKeyboardService(),
        today_provider=lambda: today,
    ), repository


def _callback(result, prefix):
    return next(
        button["callback"]
        for button in result["keyboard"]["buttons"]
        if button["callback"].startswith(prefix)
    )


def _open_custom_period(runtime, user_id, period):
    with _tenant("store-a"):
        runtime.handle_callback("external_expenses", user_id=user_id)
        prompt = runtime.handle_callback(
            "external_expenses:period:custom",
            user_id=user_id,
        )
        result = runtime.handle_text(period, user_id=user_id)
    return prompt, result


def test_external_expense_main_menu_button_is_available():
    keyboard = AssistantKeyboardService().build_main_keyboard()
    assert any(
        button["callback"] == "external_expenses"
        for button in keyboard["buttons"]
    )


def test_button_handler_routes_expense_menu_and_pending_text(tmp_path):
    keyboard = AssistantKeyboardService()
    runtime, _ = _runtime(tmp_path / "expenses.db")
    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=keyboard,
        external_expense_runtime_service=runtime,
    )

    with _tenant("store-a"):
        menu = handler.handle("external_expenses", user_id=108)
        period_prompt = handler.handle(
            "external_expenses:period:custom",
            user_id=108,
        )
        period_view = handler.handle_text(
            "01.08.2026 — 31.08.2026",
            user_id=108,
        )

    assert menu["status"] == "TELEGRAM_EXTERNAL_EXPENSE_PERIOD_MENU"
    assert period_prompt["status"] == "TELEGRAM_EXTERNAL_EXPENSE_CUSTOM_PERIOD_INPUT"
    assert period_view["status"] == "TELEGRAM_EXTERNAL_EXPENSE_PERIOD_READY"


def test_expense_is_saved_only_after_preview_confirmation_and_callback_is_idempotent(
    tmp_path,
):
    runtime, repository = _runtime(tmp_path / "expenses.db")
    _, view = _open_custom_period(
        runtime,
        101,
        "01.08.2026 — 31.08.2026",
    )
    add = _callback(view, "external_expenses:add:")

    with _tenant("store-a"):
        date_prompt = runtime.handle_callback(add, user_id=101)
        category_prompt = runtime.handle_text("15.08.2026", user_id=101)
        amount_prompt = runtime.handle_text("Аренда", user_id=101)
        description_prompt = runtime.handle_text("1 250,50 ₽", user_id=101)
        preview = runtime.handle_callback(
            _callback(description_prompt, "external_expenses:skip-description:"),
            user_id=101,
        )

    assert "Проверьте внешний расход" in preview["message"]
    assert repository.get_expenses_by_period(
        "2026-08-01",
        "2026-08-31",
    ) == []
    save = _callback(preview, "external_expenses:expense-confirm:")

    with _tenant("store-a"):
        saved = runtime.handle_callback(save, user_id=101)
        repeated = runtime.handle_callback(save, user_id=101)

    rows = repository.get_expenses_by_period("2026-08-01", "2026-08-31")
    assert saved["status"] == "TELEGRAM_EXTERNAL_EXPENSE_SAVED"
    assert saved["executed"] is True
    assert len(rows) == 1
    assert rows[0]["amount"] == 1250.5
    assert rows[0]["category"] == "Аренда"
    assert repeated["status"] == "TELEGRAM_EXTERNAL_EXPENSE_ALREADY_SAVED"
    assert len(repository.get_expenses_by_period("2026-08-01", "2026-08-31")) == 1


def test_adding_expense_does_not_implicitly_confirm_period_coverage(tmp_path):
    runtime, repository = _runtime(tmp_path / "expenses.db")
    _, view = _open_custom_period(runtime, 102, "01.08.2026 — 31.08.2026")
    with _tenant("store-a"):
        prompt = runtime.handle_callback(
            _callback(view, "external_expenses:add:"),
            user_id=102,
        )
        for text in ("15.08.2026", "Реклама вне Ozon", "1000"):
            prompt = runtime.handle_text(text, user_id=102)
        preview = runtime.handle_callback(
            _callback(prompt, "external_expenses:skip-description:"),
            user_id=102,
        )
        runtime.handle_callback(
            _callback(preview, "external_expenses:expense-confirm:"),
            user_id=102,
        )

    evidence = runtime.evidence_service.load("2026-08-01", "2026-08-31")
    assert evidence["expense_count"] == 1
    assert evidence["observed_expense_total"] == 1000.0
    assert evidence["coverage_complete"] is False
    assert evidence["complete_expense_total"] is None
    assert repository.get_coverage_by_period("2026-08-01", "2026-08-31") == []


def test_empty_period_becomes_known_zero_only_after_explicit_coverage_confirmation(
    tmp_path,
):
    runtime, repository = _runtime(tmp_path / "expenses.db")
    _, view = _open_custom_period(runtime, 103, "01.08.2026 — 31.08.2026")
    assert "не подтверждена" in view["message"]
    coverage = _callback(view, "external_expenses:coverage:")

    with _tenant("store-a"):
        preview = runtime.handle_callback(coverage, user_id=103)
    assert "пустой подтверждённый период будет считаться нулём" in preview["message"].lower()
    confirm = _callback(preview, "external_expenses:coverage-confirm:")

    with _tenant("store-a"):
        result = runtime.handle_callback(confirm, user_id=103)
        repeated = runtime.handle_callback(confirm, user_id=103)

    evidence = runtime.evidence_service.load("2026-08-01", "2026-08-31")
    assert result["status"] == "TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_CONFIRMED"
    assert evidence["coverage_complete"] is True
    assert evidence["observed_expense_total"] == 0.0
    assert evidence["complete_expense_total"] == 0.0
    assert repeated["status"] == "TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_ALREADY_CONFIRMED"
    assert len(repository.get_coverage_by_period("2026-08-01", "2026-08-31")) == 1


def test_partial_coverage_shows_unconfirmed_date_gaps(tmp_path):
    runtime, repository = _runtime(tmp_path / "expenses.db")
    repository.confirm_coverage("2026-08-01", "2026-08-10")
    _, view = _open_custom_period(runtime, 104, "01.08.2026 — 31.08.2026")

    assert "подтверждена частично" in view["message"]
    assert "11.08.2026 — 31.08.2026" in view["message"]
    assert view["coverage_complete"] is False


def test_bad_expense_amounts_and_out_of_period_dates_do_not_write(tmp_path):
    runtime, repository = _runtime(tmp_path / "expenses.db")
    _, view = _open_custom_period(runtime, 105, "01.08.2026 — 31.08.2026")
    with _tenant("store-a"):
        prompt = runtime.handle_callback(
            _callback(view, "external_expenses:add:"),
            user_id=105,
        )
        invalid_date = runtime.handle_text("01.09.2026", user_id=105)
        date_prompt = runtime.handle_text("15.08.2026", user_id=105)
        category_prompt = runtime.handle_text("Услуги", user_id=105)
        invalid_amount = runtime.handle_text("NaN", user_id=105)
        invalid_negative = runtime.handle_text("-1", user_id=105)
        invalid_infinity = runtime.handle_text("Infinity", user_id=105)

    assert "должна входить" in invalid_date["message"]
    assert "не получилось прочитать сумму" in invalid_amount["message"].lower()
    assert "не получилось прочитать сумму" in invalid_negative["message"].lower()
    assert "не получилось прочитать сумму" in invalid_infinity["message"].lower()
    assert prompt["status"].endswith("EXPENSE_DATE")
    assert date_prompt["status"].endswith("CATEGORY")
    assert category_prompt["status"].endswith("AMOUNT")
    assert repository.get_expenses_by_period("2026-08-01", "2026-08-31") == []


def test_old_view_callback_and_other_store_cannot_create_expense(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path / "storage"))
    runtime, repository = _runtime(None, repository=ExpenseRepository())
    with _tenant("store-a"):
        runtime.handle_callback("external_expenses", user_id=106)
        custom = runtime.handle_callback(
            "external_expenses:period:custom",
            user_id=106,
        )
        first_view = runtime.handle_text("01.08.2026 — 31.08.2026", user_id=106)
        old_add = _callback(first_view, "external_expenses:add:")
        runtime.handle_callback(old_add, user_id=106)
    with _tenant("store-b"):
        foreign_result = runtime.handle_callback(old_add, user_id=106)
        store_b_rows = repository.get_expenses_by_period("2026-08-01", "2026-08-31")
    with _tenant("store-a"):
        stale_result = runtime.handle_callback(old_add, user_id=106)
        store_a_rows = repository.get_expenses_by_period("2026-08-01", "2026-08-31")

    assert custom["status"] == "TELEGRAM_EXTERNAL_EXPENSE_CUSTOM_PERIOD_INPUT"
    assert stale_result["status"] == "TELEGRAM_EXTERNAL_EXPENSE_CALLBACK_STALE"
    assert foreign_result["status"] == "TELEGRAM_EXTERNAL_EXPENSE_CALLBACK_STALE"
    assert store_a_rows == []
    assert store_b_rows == []


class _FailedExpenseRepository:
    def __init__(self):
        self.calls = 0

    def add_expense(self, *args):
        self.calls += 1
        return {"error": True, "message": "write failed"}

    def get_expenses_by_period(self, date_from, date_to):
        return []

    def get_coverage_by_period(self, date_from, date_to):
        return []


def test_repository_write_error_keeps_confirmation_preview_retryable():
    repository = _FailedExpenseRepository()
    runtime = TelegramExternalExpenseRuntimeService(
        repository=repository,
        keyboard_service=AssistantKeyboardService(),
        today_provider=lambda: date(2026, 8, 31),
    )
    _, view = _open_custom_period(runtime, 107, "01.08.2026 — 31.08.2026")
    with _tenant("store-a"):
        prompt = runtime.handle_callback(
            _callback(view, "external_expenses:add:"),
            user_id=107,
        )
        for text in ("15.08.2026", "Аренда", "100"):
            prompt = runtime.handle_text(text, user_id=107)
        preview = runtime.handle_callback(
            _callback(prompt, "external_expenses:skip-description:"),
            user_id=107,
        )
        retry_preview = runtime.handle_callback(
            _callback(preview, "external_expenses:expense-confirm:"),
            user_id=107,
        )

    assert repository.calls == 1
    assert retry_preview["status"] == "TELEGRAM_EXTERNAL_EXPENSE_PREVIEW"
    assert "Проверьте внешний расход" in retry_preview["message"]


class _FailedCoverageRepository(_FailedExpenseRepository):
    def confirm_coverage(self, *args, **kwargs):
        return {"error": True, "message": "write failed"}


def test_coverage_write_error_keeps_explicit_confirmation_retryable():
    repository = _FailedCoverageRepository()
    runtime = TelegramExternalExpenseRuntimeService(
        repository=repository,
        keyboard_service=AssistantKeyboardService(),
        today_provider=lambda: date(2026, 8, 31),
    )
    _, view = _open_custom_period(runtime, 110, "01.08.2026 — 31.08.2026")
    with _tenant("store-a"):
        preview = runtime.handle_callback(
            _callback(view, "external_expenses:coverage:"),
            user_id=110,
        )
        retry_preview = runtime.handle_callback(
            _callback(preview, "external_expenses:coverage-confirm:"),
            user_id=110,
        )

    assert retry_preview["status"] == "TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_PREVIEW"
    assert "Не удалось записать подтверждение полноты" in retry_preview["message"]
    assert repository.calls == 0


def test_concurrent_confirmation_only_starts_one_expense_write(tmp_path):
    entered = Event()
    release = Event()

    class BlockingRepository(ExpenseRepository):
        def __init__(self, path):
            self.calls = 0
            super().__init__(path)

        def add_expense(self, *args, **kwargs):
            self.calls += 1
            entered.set()
            assert release.wait(timeout=5)
            return super().add_expense(*args, **kwargs)

    repository = BlockingRepository(tmp_path / "expenses.db")
    runtime = TelegramExternalExpenseRuntimeService(
        repository=repository,
        keyboard_service=AssistantKeyboardService(),
        today_provider=lambda: date(2026, 8, 31),
    )
    _, view = _open_custom_period(runtime, 111, "01.08.2026 — 31.08.2026")
    with _tenant("store-a"):
        prompt = runtime.handle_callback(
            _callback(view, "external_expenses:add:"),
            user_id=111,
        )
        for text in ("15.08.2026", "Аренда", "100"):
            prompt = runtime.handle_text(text, user_id=111)
        preview = runtime.handle_callback(
            _callback(prompt, "external_expenses:skip-description:"),
            user_id=111,
        )
    confirm = _callback(preview, "external_expenses:expense-confirm:")
    worker_result = []

    def confirm_in_worker():
        with _tenant("store-a"):
            worker_result.append(runtime.handle_callback(confirm, user_id=111))

    worker = Thread(target=confirm_in_worker)
    worker.start()
    assert entered.wait(timeout=5)
    with _tenant("store-a"):
        duplicate = runtime.handle_callback(confirm, user_id=111)
    release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert duplicate["status"] == "TELEGRAM_EXTERNAL_EXPENSE_SAVE_IN_PROGRESS"
    assert repository.calls == 1
    assert len(repository.get_expenses_by_period("2026-08-01", "2026-08-31")) == 1
    assert worker_result[0]["status"] == "TELEGRAM_EXTERNAL_EXPENSE_SAVED"


class _UncertainExpenseRepository(_FailedExpenseRepository):
    def add_expense(self, *args):
        self.calls += 1
        raise RuntimeError("write result uncertain")


def test_uncertain_write_result_cannot_be_replayed_by_old_confirmation():
    repository = _UncertainExpenseRepository()
    runtime = TelegramExternalExpenseRuntimeService(
        repository=repository,
        keyboard_service=AssistantKeyboardService(),
        today_provider=lambda: date(2026, 8, 31),
    )
    _, view = _open_custom_period(runtime, 109, "01.08.2026 — 31.08.2026")
    with _tenant("store-a"):
        prompt = runtime.handle_callback(
            _callback(view, "external_expenses:add:"),
            user_id=109,
        )
        for text in ("15.08.2026", "Аренда", "100"):
            prompt = runtime.handle_text(text, user_id=109)
        preview = runtime.handle_callback(
            _callback(prompt, "external_expenses:skip-description:"),
            user_id=109,
        )
        confirm = _callback(preview, "external_expenses:expense-confirm:")
        uncertain = runtime.handle_callback(confirm, user_id=109)
        repeated = runtime.handle_callback(confirm, user_id=109)

    assert uncertain["status"] == "TELEGRAM_EXTERNAL_EXPENSE_SAVE_UNCERTAIN"
    assert repeated["status"] == "TELEGRAM_EXTERNAL_EXPENSE_CALLBACK_STALE"
    assert repository.calls == 1
