import sqlite3
from datetime import datetime, timezone

import pytest

from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_rate_cancellation_service import FifoCostRateCancellationService
from services.fifo_cost_rate_service import FifoCostRateService
from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "store-a", "product_id": "product-a",
    "offer_id": "offer-a", "sku": "3921245627",
}


@pytest.fixture
def future_rate(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-rate-cancellation.sqlite",
        now_provider=lambda: now,
    )
    anchor_service = FifoCostAnchorService(repository, now_provider=lambda: now)
    anchor = anchor_service.preview_opening_anchor(
        **IDENTITY,
        inventory_cutoff="2026-11-05",
        cost_layers=[{
            "sequence": 1, "unit_cost_rub": "20.00",
            "ozon_units": 10, "transit_units": 0, "home_units": 0,
        }],
        ozon_units_include_reserved_confirmed=True,
        transit_not_in_ozon_confirmed=True,
    )
    assert anchor["error"] is False, anchor
    anchored = anchor_service.commit_opening_anchor(
        preview_id=anchor["preview_id"],
        active_preview_id=anchor["preview_id"],
        idempotency_key="cancel-anchor01",
    )
    assert anchored["error"] is False, anchored
    rate_service = FifoCostRateService(repository)
    rate = rate_service.preview_new_cost(
        **IDENTITY, effective_date="2026-11-07",
        purchase_cost_rub="12.00", delivery_cost_rub="2.00",
        packaging_cost_rub="1.00", old_home_units=0,
        expected_revision=1,
    )
    assert rate["error"] is False, rate
    committed_rate = rate_service.confirm_new_cost(
        preview_id=rate["preview_id"], active_preview_id=rate["preview_id"],
        idempotency_key="cancel-rate01",
    )
    assert committed_rate["error"] is False, committed_rate
    try:
        yield repository, FifoCostRateCancellationService(repository), now
    finally:
        reset_current_tenant_user_id(token)


def _preview(context, *, rate_sequence=1, expected_revision=2):
    _, service, _ = context
    return service.preview(
        **IDENTITY, rate_sequence=rate_sequence,
        expected_revision=expected_revision,
    )


def _confirm(context, preview, *, key="cancel-future-rate01"):
    _, service, _ = context
    return service.confirm(
        preview_id=preview["preview_id"],
        active_preview_id=preview["active_preview_id"],
        idempotency_key=key,
        **IDENTITY,
    )


def test_fc23_future_rate_cancel_appends_audit_and_preserves_old_layer(future_rate):
    repository, _, _ = future_rate
    preview = _preview(future_rate)
    result = _confirm(future_rate, preview)

    history = FifoCostHistoryService(repository).get_sku_history(
        **IDENTITY, as_of_date="2026-11-06",
    )
    assert result["code"] == "FIFO_RATE_CANCELLATION_COMMITTED", result
    assert result["replay_required"] is True
    assert history["rates"][0]["unit_cost_rub"] == "15.00"
    assert history["rates"][0]["status"] == "CANCELLED"
    assert history["next_planned_rate"] is None
    assert history["next_unit_cost_rub"] == "20.00"
    assert history["layers"][0]["recorded_quantity"] == 10
    assert history["rate_cancellations"] == [{
        "rate_sequence": 1,
        "reason_code": "CANCELLED_FUTURE_CHANGE",
        "recorded_at": "2026-11-06T12:00:00.000000Z",
    }]

    connection = repository.get_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_changes").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_cancellations").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE fifo_cost_rate_cancellations SET reason_code='OTHER'",
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM fifo_cost_rate_cancellations")
    finally:
        connection.close()


def test_fc23_cancel_confirmation_is_idempotent_but_key_cannot_change(future_rate):
    preview = _preview(future_rate)
    first = _confirm(future_rate, preview)
    repeated = _confirm(future_rate, preview)
    conflict = _confirm(future_rate, preview, key="cancel-future-rate02")

    assert first["idempotent"] is False
    assert repeated["idempotent"] is True
    assert repeated["stream_revision"] == first["stream_revision"]
    assert conflict["code"] == "FIFO_PREVIEW_STALE"


def test_fc23_cancelled_rate_can_be_replaced_by_a_new_later_plan(future_rate):
    repository, _, _ = future_rate
    preview = _preview(future_rate)
    cancelled = _confirm(future_rate, preview)
    assert cancelled["error"] is False, cancelled

    replacement_service = FifoCostRateService(repository)
    replacement = replacement_service.preview_new_cost(
        **IDENTITY,
        effective_date="2026-11-08",
        purchase_cost_rub="14.00",
        delivery_cost_rub="1.00",
        packaging_cost_rub="1.00",
        old_home_units=0,
        expected_revision=cancelled["stream_revision"],
    )
    assert replacement["error"] is False, replacement
    assert replacement["rate_sequence"] == 2

    committed = replacement_service.confirm_new_cost(
        preview_id=replacement["preview_id"],
        active_preview_id=replacement["preview_id"],
        idempotency_key="replacement-rate-plan01",
    )
    assert committed["error"] is False, committed
    history = FifoCostHistoryService(repository).get_sku_history(
        **IDENTITY, as_of_date="2026-11-06",
    )
    assert history["rates"][0]["status"] == "CANCELLED"
    assert history["rates"][1]["status"] == "PLANNED"
    assert history["next_planned_rate"]["sequence"] == 2


def test_fc23_new_physical_event_invalidates_cancel_preview(future_rate):
    repository, _, _ = future_rate
    preview = _preview(future_rate)
    event = repository.preview_command(
        **IDENTITY,
        expected_revision=2,
        events=[{
            "kind": "PHYSICAL_SALE", "quantity": 1,
            "effective_date": "2026-11-06", "inventory_cutoff": "2026-11-05",
            "source_identity_digest": "a" * 64,
        }],
        source={
            "kind": "OZON_REALIZATION", "method": "OZON_REALIZATION_REPORT",
            "status": "COMPLETE", "completeness": "COMPLETE",
            "provenance": "OZON_CONFIRMED_FIELD", "coverage_status": "COMPLETE",
            "captured_at": "2026-11-06T12:10:00Z", "inventory_cutoff": "2026-11-05",
        },
    )
    assert event["error"] is False, event
    recorded = repository.commit_command(
        preview_id=event["preview_id"], active_preview_id=event["preview_id"],
        idempotency_key="sale-before-cancel01",
    )
    assert recorded["error"] is False, recorded

    result = _confirm(future_rate, preview)

    assert result["error"] is True
    assert result["code"] in {"FIFO_PREVIEW_STALE", "FIFO_RATE_CANCELLATION_STALE"}
    assert repository.read_cost_history_snapshot(**IDENTITY)["revision"] == 3
    assert repository.read_cost_history_snapshot(**IDENTITY)["rate_cancellations"] == []


def test_fc23_cannot_cancel_rate_after_effective_date(future_rate):
    repository, service, _ = future_rate
    repository._now_provider = lambda: datetime(2026, 11, 7, 0, 1, tzinfo=timezone.utc)

    result = service.preview(
        **IDENTITY, rate_sequence=1, expected_revision=2,
    )

    assert result == {"error": True, "code": "FIFO_RATE_CANCELLATION_NOT_FUTURE"}


def test_fc23_future_event_at_rate_boundary_blocks_cancellation(future_rate):
    repository, _, _ = future_rate
    event = repository.preview_command(
        **IDENTITY,
        expected_revision=2,
        events=[{
            "kind": "PHYSICAL_SALE", "quantity": 1,
            "effective_date": "2026-11-07", "inventory_cutoff": "2026-11-05",
            "source_identity_digest": "b" * 64,
        }],
        source={
            "kind": "OZON_REALIZATION", "method": "OZON_REALIZATION_REPORT",
            "status": "COMPLETE", "completeness": "COMPLETE",
            "provenance": "OZON_CONFIRMED_FIELD", "coverage_status": "COMPLETE",
            "captured_at": "2026-11-06T12:10:00Z", "inventory_cutoff": "2026-11-05",
        },
    )
    assert event["error"] is False, event
    recorded = repository.commit_command(
        preview_id=event["preview_id"], active_preview_id=event["preview_id"],
        idempotency_key="sale-at-future-boundary01",
    )
    assert recorded["error"] is False, recorded

    result = _preview(future_rate, expected_revision=3)

    assert result["error"] is True
    assert result["code"] in {
        "FIFO_REVISION_CONFLICT",
        "FIFO_RATE_FUTURE_EVENT_ALREADY_USED",
    }
    assert repository.read_cost_history_snapshot(**IDENTITY)["rate_cancellations"] == []
