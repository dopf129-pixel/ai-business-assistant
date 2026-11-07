from datetime import datetime, timezone

import pytest

from services.fifo_cost_late_entry_reconstruction_service import (
    FifoCostLateEntryReconstructionService,
)
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_supply_evidence_service import FifoCostSupplyEvidenceService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


IDENTITY = {
    "store_id": "store-a", "product_id": "product-a",
    "offer_id": "offer-a", "sku": "3921245627",
}


def _source(kind, method, status, provenance, coverage, captured_at, cutoff):
    return {
        "kind": kind, "method": method, "status": status,
        "completeness": status, "provenance": provenance,
        "coverage_status": coverage, "captured_at": captured_at,
        "inventory_cutoff": cutoff,
    }


def _command(repository, events, source):
    preview = repository.preview_command(**IDENTITY, events=events, source=source)
    assert preview["error"] is False, preview
    result = repository.commit_command(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key=f"late-reconstruction-{preview['next_revision']:04d}",
    )
    assert result["error"] is False, result
    return result


def _snapshot():
    products = {"supply_acts": [{
        "act_id": 3001,
        "type": "ACCEPTANCE",
        "items": [{
            "sku_info": {"sku": int(IDENTITY["sku"])},
            "declared_quantity": 100,
            "approved_quantity": 0,
            "fact_quantity": 100,
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
            "created_date": "2026-11-04",
            "summary": {"fact_quantity": 100, "unidentified_quantity": 0},
        }],
    }]}
    return FifoCostSourceNormalizer().normalize_supply_act_snapshot(
        products, summary, store_id=IDENTITY["store_id"],
        expected_supply_id=2001, expected_order_id=11,
        captured_at=datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
        products_complete=True, summary_complete=True,
    )


def _build_stream(
    tmp_path, *, late_effective_date="2026-11-03", anchor_units=2, sale_quantity=5,
):
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-a", IDENTITY["store_id"]),
    )
    repository = FifoCostRepository(
        db_path=tmp_path / "late-reconstruction.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    anchor = _source(
        "OWNER_CONFIRMATION", "OWNER_CONFIRMED_FIFO_CUTOFF", "OWNER_CONFIRMED",
        "OWNER_CONFIRMED", "OWNER_CONFIRMED", "2026-11-06T12:00:00Z",
        "2026-11-01",
    )
    _command(repository, [{
        "kind": "OPENING_FIFO_ANCHOR", "quantity": anchor_units,
        "unit_cost_rub": "20.00", "effective_date": "2026-11-01",
        "inventory_cutoff": "2026-11-01", "location_to": "OZON",
    }], anchor)
    sale_source = _source(
        "OZON_REALIZATION", "OZON_REALIZATION_REPORT", "COMPLETE",
        "OZON_CONFIRMED_FIELD", "COMPLETE", "2026-11-06T12:05:00Z",
        "2026-11-01",
    )
    _command(repository, [{
        "kind": "PHYSICAL_SALE", "quantity": sale_quantity,
        "effective_date": "2026-11-05", "inventory_cutoff": "2026-11-01",
        "source_identity_digest": "a" * 64,
    }], sale_source)
    drafts = FifoCostSupplyEvidenceService(repository).record_late_entry_draft(
        **IDENTITY,
        expected_revision=2,
        snapshot=_snapshot(),
        owner_effective_date=late_effective_date,
        owner_old_home_units=12,
        purchase_cost_rub="40.00",
        delivery_cost_rub="3.00",
        packaging_cost_rub="1.50",
    )
    assert drafts["error"] is False, drafts
    try:
        yield repository, drafts["draft_id"]
    finally:
        reset_current_tenant_user_id(token)


@pytest.fixture
def stream(tmp_path):
    yield from _build_stream(tmp_path)


@pytest.fixture
def same_day_stream(tmp_path):
    yield from _build_stream(tmp_path, late_effective_date="2026-11-05")


@pytest.fixture
def old_stock_remains_stream(tmp_path):
    yield from _build_stream(tmp_path, anchor_units=100, sale_quantity=5)


def test_fc21_requires_historical_cutoff_and_never_uses_current_stock_as_past(stream):
    repository, draft_id = stream
    service = FifoCostLateEntryReconstructionService(repository)

    result = service.preview(**IDENTITY, draft_id=draft_id)

    assert result["code"] == "FIFO_LATE_ENTRY_RECONSTRUCTION_BLOCKED"
    assert result["reason_code"] == "INVENTORY_CUTOFF_UNRECONCILED"
    assert result["required_evidence"]
    assert result["current_stock_used_as_historical"] is False
    assert result["period_profit_changed"] is False


def test_fc21_replays_complete_history_with_hypothetical_rate_without_writes(stream):
    repository, draft_id = stream
    connection = repository.get_connection()
    connection.execute(
        "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED', queue_complete=1",
    )
    connection.close()
    revision_before = repository.read_cost_history_snapshot(**IDENTITY)["revision"]
    service = FifoCostLateEntryReconstructionService(repository)

    result = service.preview(**IDENTITY, draft_id=draft_id)

    assert result["code"] == "FIFO_LATE_ENTRY_RECONSTRUCTION_READY", result
    assert result["candidate_total_cogs_rub"] == "173.50"
    assert result["candidate_rate_units"] == 3
    assert result["sales_before_boundary"] == 0
    assert result["sales_after_boundary"] == 1
    assert result["accepted_units_documentary_only"] == 100
    assert result["accepted_units_added_to_stock"] == 0
    assert result["period_profit_changed"] is False
    assert repository.read_cost_history_snapshot(**IDENTITY)["revision"] == revision_before
    assert repository.read_late_entry_drafts(**IDENTITY)["drafts"][0]["draft_id"] == draft_id
    assert repository.read_cost_history_snapshot(**IDENTITY)["rates"] == []


def test_fc21_keeps_unsold_old_layer_ahead_of_late_rate(old_stock_remains_stream):
    repository, draft_id = old_stock_remains_stream
    connection = repository.get_connection()
    connection.execute(
        "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED', queue_complete=1",
    )
    connection.close()

    result = FifoCostLateEntryReconstructionService(repository).preview(
        **IDENTITY, draft_id=draft_id,
    )

    assert result["code"] == "FIFO_LATE_ENTRY_RECONSTRUCTION_READY", result
    assert result["candidate_rate_units"] == 0
    assert result["candidate_total_cogs_rub"] == "100.00"


def test_fc21_stale_draft_is_blocked_after_new_fifo_event(stream):
    repository, draft_id = stream
    _command(repository, [{
        "kind": "COST_LAYER_RECEIPT", "quantity": 1, "unit_cost_rub": "30.00",
        "effective_date": "2026-11-04", "inventory_cutoff": "2026-11-01",
    }], _source(
        "OWNER_CONFIRMATION", "OWNER_CONFIRMED_FIFO_CUTOFF", "OWNER_CONFIRMED",
        "OWNER_CONFIRMED", "OWNER_CONFIRMED", "2026-11-06T12:10:00Z",
        "2026-11-01",
    ))
    stale = FifoCostLateEntryReconstructionService(repository).preview(
        **IDENTITY, draft_id=draft_id,
    )
    assert stale["reason_code"] == "STALE_PREVIEW"


def test_fc21_date_only_sale_on_the_transition_day_is_ambiguous(same_day_stream):
    repository, draft_id = same_day_stream
    connection = repository.get_connection()
    connection.execute(
        "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED', queue_complete=1",
    )
    connection.close()
    same_day = FifoCostLateEntryReconstructionService(repository).preview(
        **IDENTITY, draft_id=draft_id,
    )
    assert same_day["reason_code"] == "EVENT_ORDER_UNRESOLVED"


def test_fc21_other_store_cannot_read_draft(stream):
    repository, draft_id = stream
    token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-other", "store-b"),
    )
    try:
        result = repository.preview_late_entry_reconstruction(
            **{**IDENTITY, "store_id": "store-b"}, draft_id=draft_id,
        )
        assert result["error"] is True
        assert result["code"] == "FIFO_LATE_ENTRY_DRAFT_NOT_FOUND"
    finally:
        reset_current_tenant_user_id(token)
