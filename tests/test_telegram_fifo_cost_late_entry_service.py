from datetime import datetime, timezone
from types import SimpleNamespace

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_supply_evidence_service import FifoCostSupplyEvidenceService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
from services.telegram_fifo_cost_late_entry_service import TelegramFifoCostLateEntryService
from telegram_app_layer.seller_cost_telegram_adapter import SellerCostTelegramAdapter


IDENTITY = {"store_id": "store-a", "product_id": "101", "offer_id": "hook-2", "sku": "3921245627"}


def _snapshot(*, sku=3921245627, quantity=100):
    products = {"supply_acts": [{
        "act_id": 3001,
        "type": "ACCEPTANCE",
        "items": [{
            "sku_info": {"sku": sku},
            "declared_quantity": quantity,
            "approved_quantity": 0,
            "fact_quantity": quantity,
            "unidentified_quantity": 0,
        }],
    }]}
    summary = {"supplies_acts": [{
        "supply_id": 2001,
        "is_agreement_completed": True,
        "supply_acts": [{
            "act_id": 3001,
            "type": "ACCEPTANCE",
            "act_state": "ACCEPTED",
            "created_date": "2026-10-16",
            "summary": {"fact_quantity": quantity, "unidentified_quantity": 0},
        }],
    }]}
    return FifoCostSourceNormalizer().normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        expected_order_id=11,
        captured_at=datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
        products_complete=True, summary_complete=True,
    )


class _Source:
    def __init__(self, result=None):
        self.result = result or SimpleNamespace(
            read_only=True, status="COMPLETE", issue_codes=(),
            continuation_token=None, supply_snapshot=_snapshot(),
        )
        self.calls = []

    def find_supply_by_id(self, supply_id, **kwargs):
        self.calls.append((supply_id, kwargs))
        return self.result


def _anchor(repository):
    preview = repository.preview_command(
        store_id="store-a", product_id="101", offer_id="hook-2", sku="3921245627",
        events=[{
            "kind": "OPENING_FIFO_ANCHOR", "quantity": 25, "unit_cost_rub": "20.00",
            "effective_date": "2026-10-01", "inventory_cutoff": "2026-10-01",
            "location_to": "OZON",
        }],
        source={
            "kind": "OWNER_CONFIRMATION", "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
            "status": "OWNER_CONFIRMED", "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED", "captured_at": "2026-11-06T12:00:00Z",
            "inventory_cutoff": "2026-10-01",
        },
    )
    assert preview["error"] is False
    result = repository.commit_command(
        preview_id=preview["preview_id"], active_preview_id=preview["preview_id"],
        idempotency_key="fifo-late-anchor-01",
    )
    assert result["error"] is False


def _flow(tmp_path, source=None, reconstruction=None):
    tenant = set_current_tenant_user_id("owner-1::ozon::store-a")
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-late-entry.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    _anchor(repository)
    history = FifoCostHistoryService(repository)
    telegram_history = TelegramFifoCostHistoryService(history)
    late = TelegramFifoCostLateEntryService(
        history_service=history,
        source_collection_service=source or _Source(),
        supply_evidence_service=FifoCostSupplyEvidenceService(repository),
        reconstruction_service=reconstruction,
        date_provider=lambda: datetime(2026, 11, 6).date(),
    )
    adapter = SellerCostTelegramAdapter(
        assistant=object(), keyboard_service=object(), button_handler=object(),
        fifo_history_service=telegram_history, fifo_late_entry_service=late,
    )
    return tenant, repository, history, telegram_history, late, adapter


def _open_late(adapter):
    opened = adapter.fifo_history_service.create_sku_callback(
        user_id="owner-1", store_id="store-a", product_id="101", offer_id="hook-2",
        sku="3921245627", display_name="Крючки",
    )
    card = adapter.handle_button(opened["callback"], user_id="owner-1")
    late_callback = next(
        item["callback"] for item in card["keyboard"]["buttons"]
        if item["callback"].startswith("fifo_history:late:")
    )
    return adapter.handle_button(late_callback, user_id="owner-1")


def test_public_late_entry_saves_redacted_revision_bound_draft_only(tmp_path):
    tenant, repository, history, telegram_history, late, adapter = _flow(tmp_path)
    try:
        started = _open_late(adapter)
        assert started["error"] is False
        for text in ("40", "3", "1.5", "12", "2001"):
            step = adapter.handle_text(text, user_id="owner-1")
            assert step["error"] is False
        date_prompt = adapter.handle_text("2026-10-16", user_id="owner-1")
        assert "2026-10-16" in date_prompt["message"]
        assert date_prompt["message"].count("2026-10-16") >= 2
        confirm_callback = date_prompt["keyboard"]["buttons"][0]["callback"]
        cancel_callback = date_prompt["keyboard"]["buttons"][1]["callback"]
        saved = adapter.handle_button(confirm_callback, user_id="owner-1")
        stale_cancel = adapter.handle_button(cancel_callback, user_id="owner-1")
        free_text = late.handle_text("owner-1", "new unrelated request")
        assert saved["error"] is False
        assert saved["fifo_late_entry_draft_saved"] is True
        assert stale_cancel == saved
        assert free_text["handled"] is False
        assert "не пересчитаны" in saved["message"]
        assert "Поставка Ozon №2001" in saved["message"]

        drafts = repository.read_late_entry_drafts(**IDENTITY)
        assert len(drafts["drafts"]) == 1
        assert drafts["drafts"][0]["accepted_units"] == 100
        assert drafts["drafts"][0]["unit_cost_rub"] == "44.50"
        assert drafts["drafts"][0]["owner_old_home_units"] == 12
        snapshot = history.get_sku_history(**IDENTITY)
        assert snapshot["revision"] == 1
        assert snapshot["rates"] == []
        assert snapshot["layers"][0]["recorded_quantity"] == 25
        replayed = adapter.handle_button(confirm_callback, user_id="owner-1")
        assert replayed == saved
        assert len(drafts["drafts"]) == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_public_late_entry_reports_exact_historical_cutoff_gap(tmp_path):
    class _BlockedReconstruction:
        def __init__(self):
            self.calls = []

        def preview(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "error": False,
                "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_BLOCKED",
                "reason_code": "INVENTORY_CUTOFF_UNRECONCILED",
                "required_evidence": ["остаток на историческую дату по зонам"],
                "current_stock_used_as_historical": False,
                "period_profit_changed": False,
            }

    reconstruction = _BlockedReconstruction()
    tenant, _repository, _history, _telegram_history, _late, adapter = _flow(
        tmp_path, reconstruction=reconstruction,
    )
    try:
        _open_late(adapter)
        for text in ("40", "3", "1.5", "12", "2001", "2026-10-16"):
            response = adapter.handle_text(text, user_id="owner-1")
        callback = response["keyboard"]["buttons"][0]["callback"]
        result = adapter.handle_button(callback, user_id="owner-1")

        assert result["error"] is False
        assert "Текущий остаток Ozon не использован как исторический" in result["message"]
        assert "остаток на историческую дату по зонам" in result["message"]
        assert reconstruction.calls[0]["draft_id"].startswith("late_")
    finally:
        reset_current_tenant_user_id(tenant)


def test_late_entry_rejects_other_store_before_source_lookup(tmp_path):
    tenant, _repository, _history, _telegram_history, _late, adapter = _flow(tmp_path)
    try:
        # A valid SKU callback cannot be moved to another store by editing the ticket.
        result = adapter.fifo_late_entry_service.start(
            "owner-1", {**IDENTITY, "store_id": "store-b"}, "Крючки", 1,
        )
        assert result["error"] is True
        assert adapter.fifo_late_entry_service.source_collection_service.calls == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_late_entry_rejects_unfinished_or_mixed_supply_without_draft(tmp_path):
    source = _Source(SimpleNamespace(
        read_only=True, status="NOT_FOUND", issue_codes=("FIFO_SUPPLY_NOT_FOUND",),
        continuation_token=None, supply_snapshot=None,
    ))
    tenant, repository, _history, _telegram_history, _late, adapter = _flow(tmp_path, source)
    try:
        _open_late(adapter)
        for text in ("40", "3", "1", "0"):
            adapter.handle_text(text, user_id="owner-1")
        result = adapter.handle_text("2001", user_id="owner-1")
        assert result["error"] is True
        assert "завершённая поставка" in result["message"].lower()
        assert repository.read_late_entry_drafts(**IDENTITY)["drafts"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_late_entry_rejects_mixed_sku_act_and_stale_confirmation(tmp_path):
    mixed = _snapshot(sku=3921245628)
    source = _Source(SimpleNamespace(
        read_only=True, status="CONFLICT", issue_codes=("FIFO_SUPPLY_SKU_IDENTITY_MISMATCH",),
        continuation_token=None, supply_snapshot=mixed,
    ))
    tenant, repository, _history, _telegram_history, _late, adapter = _flow(tmp_path, source)
    try:
        _open_late(adapter)
        for text in ("40", "3", "1", "0"):
            adapter.handle_text(text, user_id="owner-1")
        result = adapter.handle_text("2001", user_id="owner-1")
        assert result["error"] is True
        assert "другая номенклатура" in result["message"]
        assert repository.read_late_entry_drafts(**IDENTITY)["drafts"] == []
    finally:
        reset_current_tenant_user_id(tenant)
