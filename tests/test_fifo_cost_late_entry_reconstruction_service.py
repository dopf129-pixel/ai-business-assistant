from datetime import datetime, timezone

import pytest

from services.fifo_cost_late_entry_reconstruction_service import (
    FifoCostLateEntryReconstructionService,
)
from services.fifo_cost_non_sale_movement_service import (
    FifoCostNonSaleMovementService,
)
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_return_restock_service import FifoCostReturnRestockService
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
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
    tmp_path, *, late_effective_date="2026-11-03", anchor_units=2,
    sale_quantity=5, sale_effective_date="2026-11-05",
    sale_identity_digest="a" * 64,
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
        "effective_date": sale_effective_date, "inventory_cutoff": "2026-11-01",
        "source_identity_digest": sale_identity_digest,
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


def _sale_digest(posting_number):
    result = FifoCostSaleEvidenceNormalizer.build_identity_digest(
        store_id=IDENTITY["store_id"], posting_number=posting_number,
        finance_sku=IDENTITY["sku"],
        identity={
            "mapping_confirmed": True,
            "offer_id": IDENTITY["offer_id"],
            "product_id": IDENTITY["product_id"],
        },
    )
    assert result["error"] is False, result
    return result["source_identity_digest"]


def _publish_current_allocation(repository):
    connection = repository.get_connection()
    try:
        connection.execute(
            "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED', queue_complete=1",
        )
    finally:
        connection.close()
    guard = repository.read_allocation_guard(**IDENTITY)
    assert guard["error"] is False, guard
    connection = repository.get_connection()
    try:
        identity = repository._normalize_identity(
            IDENTITY["store_id"], IDENTITY["product_id"],
            IDENTITY["offer_id"], IDENTITY["sku"], 1,
        )
        stream_id = "fifo_" + repository._sha256(identity)[:40]
        preview = repository._preview_allocation_from_connection(
            connection, stream_id,
            stream_revision=guard["stream_revision"],
            allocation_revision=guard["allocation_revision"],
            source_fingerprint=guard["source_set_fingerprint"],
            cutoff_status="RECONCILED", anchor_cutoff_date="2026-11-01",
        )
    finally:
        connection.close()
    assert preview["complete"] is True, preview
    result = repository.append_allocation_revision(
        **IDENTITY, preview=preview,
        idempotency_key=f"fl21-initial-{guard['stream_revision']:04d}",
    )
    assert result["error"] is False, result


def _append_supported_return_and_outflow(repository, sale_identity_digest):
    now = lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    return_service = FifoCostReturnRestockService(repository, now_provider=now)
    return_preview = return_service.preview_return(
        **IDENTITY,
        finance_sku=IDENTITY["sku"],
        identity={
            "mapping_confirmed": True,
            "offer_id": IDENTITY["offer_id"],
            "product_id": IDENTITY["product_id"],
        },
        return_record={
            "id": "return-1", "posting_number": "posting-before",
            "sku": IDENTITY["sku"], "quantity": 1,
            "type": "ClientReturn",
            "visual_status_sys_name": "ArrivedAtReturnPlace",
        },
        recovery_evidence={
            "error": False, "inventory_recovery_confirmed": True,
            "recovery_state": "SALEABLE_RESTORED", "source": "SELLER_CONFIRMED_BOT",
            "return_id": "return-1", "posting_number": "posting-before",
            "sku": IDENTITY["sku"], "quantity": 1,
            "confirmed_on": "2026-11-03",
        },
        return_sample_complete=True,
        cutoff_bridge_confirmed=True,
    )
    assert return_preview["code"] == "FIFO_RETURN_RESTOCK_PREVIEW_READY", return_preview
    returned = return_service.commit_return(
        **IDENTITY,
        preview_id=return_preview["preview_id"],
        active_preview_id=return_preview["preview_id"],
        idempotency_key="fl21-return-restock",
    )
    assert returned["code"] == "FIFO_RETURN_RESTOCK_COMMITTED", returned

    movement_service = FifoCostNonSaleMovementService(repository, now_provider=now)
    movement_preview = movement_service.preview_movement(
        **IDENTITY,
        movement_id="home-shortage-1", reason_code="HOME_SHORTAGE",
        quantity=1, effective_date="2026-11-04",
        cutoff_bridge_confirmed=True,
    )
    assert movement_preview["code"] == "FIFO_NON_SALE_MOVEMENT_PREVIEW_READY", movement_preview
    moved = movement_service.commit_movement(
        **IDENTITY,
        preview_id=movement_preview["preview_id"],
        active_preview_id=movement_preview["preview_id"],
        idempotency_key="fl21-home-shortage",
    )
    assert moved["code"] == "FIFO_NON_SALE_MOVEMENT_COMMITTED", moved

    sale_source = _source(
        "OZON_REALIZATION", "OZON_REALIZATION_REPORT", "COMPLETE",
        "OZON_CONFIRMED_FIELD", "COMPLETE", "2026-11-06T12:30:00Z",
        "2026-11-01",
    )
    sale_digest = _sale_digest("posting-after")
    assert sale_identity_digest != sale_digest
    _command(repository, [{
        "kind": "PHYSICAL_SALE", "quantity": 2,
        "effective_date": "2026-11-06", "inventory_cutoff": "2026-11-01",
        "source_identity_digest": sale_digest,
    }], sale_source)


def test_fl21_replays_exact_return_basis_and_outflow_without_counting_outflow_as_sale(tmp_path):
    sale_digest = _sale_digest("posting-before")
    stream = _build_stream(
        tmp_path,
        late_effective_date="2026-11-05", anchor_units=3, sale_quantity=2,
        sale_effective_date="2026-11-02", sale_identity_digest=sale_digest,
    )
    repository, stale_draft_id = next(stream)
    try:
        _publish_current_allocation(repository)
        _append_supported_return_and_outflow(repository, sale_digest)
        current = repository.read_cost_history_snapshot(**IDENTITY)
        refreshed = FifoCostSupplyEvidenceService(repository).record_late_entry_draft(
            **IDENTITY,
            expected_revision=current["revision"], snapshot=_snapshot(),
            owner_effective_date="2026-11-05", owner_old_home_units=12,
            purchase_cost_rub="10.00", delivery_cost_rub="3.00",
            packaging_cost_rub="1.65",
        )
        assert refreshed["error"] is False, refreshed
        assert refreshed["draft_id"] != stale_draft_id
        connection = repository.get_connection()
        try:
            connection.execute(
                "UPDATE fifo_cost_projections SET cutoff_status='RECONCILED', queue_complete=1",
            )
        finally:
            connection.close()

        result = FifoCostLateEntryReconstructionService(repository).preview(
            **IDENTITY, draft_id=refreshed["draft_id"],
        )

        assert result["code"] == "FIFO_LATE_ENTRY_RECONSTRUCTION_READY", result
        assert result["related_return_count"] == 1
        assert result["non_sale_outflow_count"] == 1
        assert result["candidate_total_cogs_rub"] == "74.65"
        assert result["candidate_rate_units"] == 1
        first_sale, second_sale = result["candidate_allocations"]
        assert result["sale_effective_dates"][first_sale["event_id"]] == "2026-11-02"
        assert result["sale_effective_dates"][second_sale["event_id"]] == "2026-11-06"
        assert first_sale["total_cost_rub"] == "40.00"
        assert first_sale["lines"][0]["unit_cost_rub"] == "20.00"
        assert second_sale["total_cost_rub"] == "34.65"
        assert second_sale["lines"][0]["layer_id"] == first_sale["lines"][0]["layer_id"]
        assert second_sale["lines"][0]["unit_cost_rub"] == "20.00"
        assert second_sale["lines"][1]["rate_change_id"] == (
            "late_candidate_" + refreshed["draft_id"][-24:]
        )
        assert second_sale["lines"][1]["unit_cost_rub"] == "14.65"
        assert result["candidate_outflows"][0]["quantity"] == 1
        assert result["candidate_outflows"][0]["estimated_value_rub"] == "20.00"
        assert result["candidate_non_sale_outflow_value_rub"] == "20.00"
        assert result["before_complete"] is False

    finally:
        stream.close()


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
    assert same_day["reason_code"] == "FIFO_RATE_TRANSITION_ORDER_UNRESOLVED"


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
