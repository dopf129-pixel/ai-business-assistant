from datetime import date, datetime, timezone

from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_rate_cancellation_service import FifoCostRateCancellationService
from services.fifo_cost_rate_service import FifoCostRateService
from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
from services.telegram_fifo_cost_rate_entry_service import TelegramFifoCostRateEntryService
from services.telegram_seller_cost_update_service import TelegramSellerCostUpdateService
from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-101",
    "offer_id": "hook-2",
    "sku": "3921245627",
}


def _anchored_history(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "telegram-fifo-history.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    anchor_service = FifoCostAnchorService(repository)
    preview = anchor_service.preview_opening_anchor(
        **IDENTITY,
        inventory_cutoff="2026-11-05",
        cost_layers=[{
            "sequence": 1,
            "unit_cost_rub": "10.00",
            "ozon_units": 4,
            "transit_units": 0,
            "home_units": 2,
        }],
        ozon_units_include_reserved_confirmed=True,
        transit_not_in_ozon_confirmed=True,
    )
    assert preview["error"] is False, preview
    committed = anchor_service.commit_opening_anchor(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="telegram-fifo-anchor01",
    )
    assert committed["error"] is False
    return repository, FifoCostHistoryService(repository)


def _commit_planned_rate(
    repository, *, expected_revision=1, effective_date="2026-11-07",
    purchase_cost_rub="12.00",
):
    rates = FifoCostRateService(repository)
    preview = rates.preview_new_cost(
        **IDENTITY,
        effective_date=effective_date,
        purchase_cost_rub=purchase_cost_rub,
        delivery_cost_rub="2.00",
        packaging_cost_rub="1.00",
        old_home_units=0,
        expected_revision=expected_revision,
    )
    assert preview["error"] is False, preview
    result = rates.confirm_new_cost(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key=f"telegram-future-rate{expected_revision:02d}",
    )
    assert result["error"] is False
    return result


def test_history_callback_is_opaque_revision_bound_and_user_facing(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, history = _anchored_history(tmp_path)
        ui = TelegramFifoCostHistoryService(history)
        ticket = ui.create_sku_callback(
            user_id=101,
            **IDENTITY,
            display_name="Крючки для дома",
        )
        assert ticket["error"] is False
        callback = ticket["callback"]
        assert callback.startswith("fifo_history:open:")
        assert len(callback.encode("utf-8")) <= 64
        assert "store-a" not in callback
        assert "product-101" not in callback
        assert IDENTITY["sku"] not in callback

        card = ui.handle_callback(101, callback)
        assert card["error"] is False
        assert "Следующая единица на подтверждённом срезе: 10.00 ₽/шт." in card["message"]
        assert "отчётах прибыли" in card["message"]
        assert all("FIFO" not in value for value in card["message"].splitlines() if "INVENTORY_" in value)
        assert {item["callback"].split(":")[1] for item in card["keyboard"]["buttons"]} == {
            "new", "late", "history", "correct", "sku",
        }

        new_callback = next(
            item["callback"] for item in card["keyboard"]["buttons"]
            if item["callback"].split(":")[1] == "new"
        )
        action = ui.handle_callback(101, new_callback)
        assert action["error"] is False
        assert action["action"] == "start_new_rate"
        assert action["identity"] == IDENTITY
        assert action["expected_revision"] == 1

        other_user = ui.handle_callback(202, callback)
        assert other_user["error"] is True
        assert "store-a" not in other_user["message"]
    finally:
        reset_current_tenant_user_id(tenant)


def test_fifo_history_export_is_read_only_redacted_and_revision_bound(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository, history = _anchored_history(tmp_path)
        ui = TelegramFifoCostHistoryService(history)
        ticket = ui.create_sku_callback(
            user_id=101, **IDENTITY, display_name="Крючки",
        )
        card = ui.handle_callback(101, ticket["callback"])
        history_callback = next(
            button["callback"] for button in card["keyboard"]["buttons"]
            if button["callback"].split(":")[1] == "history"
        )
        history_result = ui.handle_callback(101, history_callback)
        export_callback = next(
            button["callback"] for button in history_result["keyboard"]["buttons"]
            if button["callback"].split(":")[1] == "export"
        )
        exported = ui.handle_callback(101, export_callback)
        assert exported["error"] is False
        assert exported["document_kind"] == "analytics_export"
        assert exported["revision"] == 1
        assert "FINITE_LAYER" in exported["file_content"]
        assert "2026-11-05" in exported["file_content"]
        assert "store-a" not in exported["file_content"]
        assert "product-101" not in exported["file_content"]
        assert "fifo-cost-history.csv" == exported["filename"]

        # A cost change invalidates the export ticket before another file is returned.
        _commit_planned_rate(repository, expected_revision=1)
        stale = ui.handle_callback(101, export_callback)
        assert stale["error"] is True
        assert stale["code"] == "FIFO_HISTORY_CALLBACK_STALE"
    finally:
        reset_current_tenant_user_id(tenant)


def test_history_buttons_fail_closed_after_stream_revision_changes(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository, history = _anchored_history(tmp_path)
        ui = TelegramFifoCostHistoryService(history)
        ticket = ui.create_sku_callback(
            user_id=101, **IDENTITY, display_name="Товар",
        )
        callback = ticket["callback"]
        movement = repository.preview_command(
            **IDENTITY,
            events=[{
                "kind": "INVENTORY_TRANSFER",
                "quantity": 1,
                "effective_date": "2026-11-06",
                "location_from": "HOME",
                "location_to": "TRANSIT",
            }],
            source={
                "kind": "OWNER_CONFIRMATION",
                "method": "OWNER_CONFIRMED_TEST_MOVEMENT",
                "status": "OWNER_CONFIRMED",
                "completeness": "OWNER_CONFIRMED",
                "provenance": "OWNER_CONFIRMED",
                "coverage_status": "OWNER_CONFIRMED",
                "captured_at": "2026-11-06T13:00:00Z",
                "references": [],
            },
            expected_revision=1,
        )
        assert movement["error"] is False
        committed = repository.commit_command(
            preview_id=movement["preview_id"],
            active_preview_id=movement["preview_id"],
            idempotency_key="telegram-fifo-movement01",
        )
        assert committed["error"] is False
        result = ui.handle_callback(101, callback)
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["error"] is True
    assert "устарела" in result["message"]
    assert "revision" not in result["message"].lower()


def test_owner_can_cancel_future_rate_and_history_refreshes_with_audit_status(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository, history = _anchored_history(tmp_path)
        _commit_planned_rate(repository)
        ui = TelegramFifoCostHistoryService(
            history,
            FifoCostRateCancellationService(repository),
        )
        ticket = ui.create_sku_callback(
            user_id=101, **IDENTITY, display_name="Крючки для дома",
        )
        card = ui.handle_callback(101, ticket["callback"])
        history_callback = next(
            item["callback"] for item in card["keyboard"]["buttons"]
            if item["callback"].split(":")[1] == "history"
        )
        report = ui.handle_callback(101, history_callback)
        cancel_callback = next(
            item["callback"] for item in report["keyboard"]["buttons"]
            if item["callback"].split(":")[1] == "cancel_rate"
        )
        assert len(cancel_callback.encode("utf-8")) <= 64

        confirmation = ui.handle_callback(101, cancel_callback)
        assert confirmation["error"] is False
        assert "Отменить запланированную ставку 15.00 ₽/шт." in confirmation["message"]
        confirm_callback = next(
            item["callback"] for item in confirmation["keyboard"]["buttons"]
            if item["callback"].split(":")[1] == "confirm_rate_cancel"
        )
        assert len(confirm_callback.encode("utf-8")) <= 64

        result = ui.handle_callback(101, confirm_callback)
        assert result["error"] is False
        assert result["fifo_rate_cancelled"] is True
        assert "отменена" in result["message"]
        assert "отменена, запись сохранена" in result["message"]
        assert not any(
            item["callback"].split(":")[1] == "cancel_rate"
            for item in result["keyboard"]["buttons"]
        )
        updated = history.get_sku_history(**IDENTITY)
        assert updated["rates"][0]["status"] == "CANCELLED"
        assert len(updated["rate_cancellations"]) == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_rate_cancellation_confirmation_is_rejected_after_stream_changes(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository, history = _anchored_history(tmp_path)
        _commit_planned_rate(repository)
        ui = TelegramFifoCostHistoryService(
            history,
            FifoCostRateCancellationService(repository),
        )
        ticket = ui.create_sku_callback(
            user_id=101, **IDENTITY, display_name="Товар",
        )
        card = ui.handle_callback(101, ticket["callback"])
        report = ui.handle_callback(
            101,
            next(item["callback"] for item in card["keyboard"]["buttons"]
                 if item["callback"].split(":")[1] == "history"),
        )
        confirmation = ui.handle_callback(
            101,
            next(item["callback"] for item in report["keyboard"]["buttons"]
                 if item["callback"].split(":")[1] == "cancel_rate"),
        )
        confirm_callback = next(
            item["callback"] for item in confirmation["keyboard"]["buttons"]
            if item["callback"].split(":")[1] == "confirm_rate_cancel"
        )
        movement = repository.preview_command(
            **IDENTITY,
            events=[{
                "kind": "INVENTORY_TRANSFER",
                "quantity": 1,
                "effective_date": "2026-11-06",
                "location_from": "HOME",
                "location_to": "TRANSIT",
            }],
            source={
                "kind": "OWNER_CONFIRMATION",
                "method": "OWNER_CONFIRMED_TEST_MOVEMENT",
                "status": "OWNER_CONFIRMED",
                "completeness": "OWNER_CONFIRMED",
                "provenance": "OWNER_CONFIRMED",
                "coverage_status": "OWNER_CONFIRMED",
                "captured_at": "2026-11-06T11:00:00Z",
                "references": [],
            },
            expected_revision=2,
        )
        assert movement["error"] is False
        committed = repository.commit_command(
            preview_id=movement["preview_id"],
            active_preview_id=movement["preview_id"],
            idempotency_key="telegram-cancel-stale-move01",
        )
        assert committed["error"] is False

        result = ui.handle_callback(101, confirm_callback)
        assert result["error"] is True
        assert result["code"] == "FIFO_HISTORY_CALLBACK_STALE"
        updated = history.get_sku_history(**IDENTITY)
        assert updated["rates"][0]["status"] == "PLANNED"
        assert updated["rate_cancellations"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_cancellation_preview_selects_latest_of_multiple_planned_rates():
    class _CancellationStub:
        rate_sequence = None

        def preview(self, **payload):
            self.rate_sequence = payload["rate_sequence"]
            return {"error": False, "preview_id": "rate_cancel_" + "a" * 64}

    cancellation = _CancellationStub()
    ui = TelegramFifoCostHistoryService(rate_cancellation_service=cancellation)
    owner = "101"
    token = "opaque123"
    ui._tickets[(owner, token)] = {"revision": 3}
    ticket = {
        "token": token,
        "revision": 3,
        "identity": IDENTITY,
        "snapshot": {
            "rates": [
                {"sequence": 1, "status": "PLANNED", "unit_cost_rub": "15.00",
                 "effective_date": "2026-11-07"},
                {"sequence": 2, "status": "PLANNED", "unit_cost_rub": "19.00",
                 "effective_date": "2026-11-08"},
            ],
        },
    }
    confirmation = ui._preview_rate_cancellation(owner, ticket)

    assert cancellation.rate_sequence == 2
    assert "Отменить запланированную ставку 19.00 ₽/шт. с 2026-11-08?" in confirmation["message"]


def test_history_button_expires_and_store_switch_invalidates_ticket(tmp_path, monkeypatch):
    tenant_a = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        _repository, history = _anchored_history(tmp_path)
        ui = TelegramFifoCostHistoryService(history)
        now = [100.0]
        monkeypatch.setattr(
            "services.telegram_fifo_cost_history_service.monotonic",
            lambda: now[0],
        )
        ticket = ui.create_sku_callback(
            user_id=101, **IDENTITY, display_name="Товар",
        )
        now[0] += ui.TTL_SECONDS + 1
        expired = ui.handle_callback(101, ticket["callback"])
        assert expired["error"] is True

        fresh = ui.create_sku_callback(
            user_id=101, **IDENTITY, display_name="Товар",
        )
    finally:
        reset_current_tenant_user_id(tenant_a)

    tenant_b = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-b"))
    try:
        switched = ui.handle_callback(101, fresh["callback"])
    finally:
        reset_current_tenant_user_id(tenant_b)

    assert switched["error"] is True
    assert "другому магазину" in switched["message"]


class _HistoryStub:
    def get_sku_history(self, **_identity):
        return {"error": False, "queue_initialized": True, "revision": 3}


class _RateStub:
    def __init__(self):
        self.preview_payload = None
        self.confirm_payloads = []
        self.preview_error = None

    def preview_new_cost(self, **payload):
        self.preview_payload = payload
        if self.preview_error is not None:
            return self.preview_error
        return {
            "error": False,
            "code": "FIFO_RATE_PREVIEW_READY",
            "preview_id": "private-preview-id",
            "unit_cost_rub": "132.75",
            "effective_date": "2026-11-06",
            "finite_units_at_anchor": 6,
            "prior_rate_unit_cost_rub": "100.00",
        }

    def confirm_new_cost(self, **payload):
        self.confirm_payloads.append(payload)
        return {"error": False, "code": "FIFO_RATE_COMMITTED"}


def test_new_rate_flow_collects_components_and_confirms_without_batch_quantity():
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        rate_stub = _RateStub()
        entry = TelegramFifoCostRateEntryService(
            _HistoryStub(), rate_stub, date_provider=lambda: date(2026, 11, 6),
        )
        started = entry.start(101, IDENTITY, "Крючки", 3)
        assert started["error"] is False
        assert "закупочную стоимость" in started["message"]

        assert "доставку" in entry.handle_text(101, "100")["message"]
        assert "упаковки" in entry.handle_text(101, "20,50")["message"]
        assert "осталось у вас дома" in entry.handle_text(101, "12")["message"]
        preview = entry.handle_text(101, "2")
        assert preview["fifo_rate_confirmation_pending"] is True
        assert "132.75 ₽/шт." in preview["message"]
        assert "Конечные старые единицы" in preview["message"]
        assert "Количество новой партии не задано и не добавляется" in preview["message"]
        assert "private-preview-id" not in preview["message"]
        assert "FIFO_RATE_PREVIEW_READY" not in preview["message"]
        assert rate_stub.preview_payload["old_home_units"] == 2
        assert rate_stub.preview_payload["expected_revision"] == 3

        confirm = preview["keyboard"]["buttons"][0]["callback"]
        saved = entry.handle_callback(101, confirm)
        repeated = entry.handle_callback(101, confirm)
        assert saved["fifo_rate_saved"] is True
        assert repeated == saved
        assert len(rate_stub.confirm_payloads) == 1
        assert rate_stub.confirm_payloads[0]["active_preview_id"] == "private-preview-id"
    finally:
        reset_current_tenant_user_id(tenant)


def test_new_rate_flow_explains_missing_reconciliation_and_does_not_confirm():
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        rate_stub = _RateStub()
        rate_stub.preview_error = {
            "error": True,
            "code": "FIFO_RATE_RECONCILIATION_REQUIRED",
        }
        entry = TelegramFifoCostRateEntryService(
            _HistoryStub(), rate_stub, date_provider=lambda: date(2026, 11, 6),
        )
        entry.start(101, IDENTITY, "Крючки", 3)
        for value in ("100", "20", "5", "2"):
            result = entry.handle_text(101, value)
        assert result["error"] is True
        assert "полная сверка старого остатка" in result["message"]
        assert "новую ставку не сохранил" in result["message"]
        assert "FIFO_RATE_RECONCILIATION_REQUIRED" not in result["message"]
        assert rate_stub.confirm_payloads == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_new_rate_flow_commits_to_fifo_without_changing_old_layers(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository, history = _anchored_history(tmp_path)
        entry = TelegramFifoCostRateEntryService(
            history,
            FifoCostRateService(repository),
            date_provider=lambda: date(2026, 11, 6),
        )
        started = entry.start(101, IDENTITY, "Крючки", 1)
        assert started["error"] is False
        for value in ("120", "5.50", "7", "2"):
            result = entry.handle_text(101, value)
        assert result["fifo_rate_confirmation_pending"] is True
        callback = result["keyboard"]["buttons"][0]["callback"]
        saved = entry.handle_callback(101, callback)
        assert saved["fifo_rate_saved"] is True

        snapshot = history.get_sku_history(
            **IDENTITY,
            as_of_date=date(2026, 11, 6),
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert snapshot["revision"] == 2
    assert [layer["unit_cost_rub"] for layer in snapshot["layers"]] == ["10.00", "10.00"]
    assert sum(layer["remaining_units"] for layer in snapshot["layers"]) == 6
    assert snapshot["active_rate"]["unit_cost_rub"] == "132.50"
    assert snapshot["rates"][0]["owner_old_home_units"] == 2
    assert snapshot["projection"]["cutoff_status"] == "INVENTORY_CUTOFF_UNRECONCILED"


def test_rate_draft_expires_and_store_switch_does_not_save(monkeypatch):
    tenant_a = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        rate_stub = _RateStub()
        entry = TelegramFifoCostRateEntryService(
            _HistoryStub(), rate_stub, date_provider=lambda: date(2026, 11, 6),
        )
        now = [200.0]
        monkeypatch.setattr(
            "services.telegram_fifo_cost_rate_entry_service.monotonic",
            lambda: now[0],
        )
        entry.start(101, IDENTITY, "Товар", 3)
        now[0] += entry.TTL_SECONDS + 1
        expired = entry.handle_text(101, "100")
        assert expired["handled"] is False
        assert rate_stub.preview_payload is None

        entry.start(101, IDENTITY, "Товар", 3)
        for value in ("100", "20", "5", "0"):
            result = entry.handle_text(101, value)
        callback = result["keyboard"]["buttons"][0]["callback"]
    finally:
        reset_current_tenant_user_id(tenant_a)

    tenant_b = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-b"))
    try:
        switched = entry.handle_callback(101, callback)
    finally:
        reset_current_tenant_user_id(tenant_b)

    assert switched["error"] is True
    assert rate_stub.confirm_payloads == []


class _ButtonHandler:
    def handle(self, *_args):
        return {"error": False}


class _Assistant:
    def ask(self, *_args):
        return {"error": False, "message": "assistant fallback"}


class _LegacySellerCostService:
    def clear_pending(self, _user_id):
        pass

    def is_confirmation_callback(self, _callback):
        return False

    def handle_text(self, _user_id, _text):
        return {"error": False, "handled": False}


class _HistoryCallbackStub:
    def handle_callback(self, _user_id, _callback):
        return {
            "error": False,
            "handled": True,
            "action": "start_new_rate",
            "identity": dict(IDENTITY),
            "display_name": "Крючки",
            "expected_revision": 3,
        }


class _RateEntryCallbackStub:
    def __init__(self):
        self.started = None
        self.callbacks = []

    def start(self, *args):
        self.started = args
        return {"error": False, "handled": True, "message": "Введите закупку."}

    def handle_text(self, _user_id, _text):
        return {"error": False, "handled": False}

    def handle_callback(self, user_id, callback):
        self.callbacks.append((user_id, callback))
        return {"error": False, "handled": True, "message": "Сохранено."}

    def clear_pending(self, _user_id):
        pass


def test_seller_cost_adapter_routes_fifo_actions_to_explicit_services():
    rate_entry = _RateEntryCallbackStub()
    adapter = SellerCostTelegramAdapter(
        assistant=_Assistant(),
        keyboard_service=None,
        button_handler=_ButtonHandler(),
        seller_cost_service=_LegacySellerCostService(),
        fifo_history_service=_HistoryCallbackStub(),
        fifo_rate_entry_service=rate_entry,
    )

    started = adapter.handle_button("fifo_history:new:opaque-token", user_id=101)
    text_result = adapter.handle_text("120", user_id=101)
    confirmed = adapter.handle_button("fifo_rate:confirm:opaque-draft", user_id=101)

    assert started["message"] == "Введите закупку."
    assert rate_entry.started == (101, IDENTITY, "Крючки", 3)
    assert text_result["message"] == "assistant fallback"
    assert confirmed["message"] == "Сохранено."
    assert rate_entry.callbacks == [(101, "fifo_rate:confirm:opaque-draft")]


class _Products:
    def load_products(self):
        return [("product-101", "hook-2", "3921245627")]


class _Costs:
    def get_all_costs(self):
        return [{"sku": "3921245627"}]


class _MenuHistoryStub:
    def __init__(self):
        self.calls = []

    def create_sku_callback(self, **kwargs):
        self.calls.append(kwargs)
        return {"error": False, "callback": "fifo_history:open:abc123"}


def test_seller_cost_menu_adds_fifo_history_entry_without_removing_legacy_entry():
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        history = _MenuHistoryStub()
        service = TelegramSellerCostUpdateService(
            _Products(), _Costs(), fifo_history_service=history,
        )
        result = service.open_menu(user_id=101)
    finally:
        reset_current_tenant_user_id(tenant)

    callbacks = [button["callback"] for button in result["keyboard"]["buttons"]]
    assert "seller_cost:3921245627" in callbacks
    assert "fifo_history:open:abc123" in callbacks
    assert history.calls[0]["store_id"] == "store-a"
    assert history.calls[0]["sku"] == IDENTITY["sku"]
