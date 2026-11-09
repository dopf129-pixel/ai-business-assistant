from datetime import date, datetime, timezone

from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_rate_service import FifoCostRateService
from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-101",
    "offer_id": "hook-2",
    "sku": "3921245627",
}


def _source(captured_at="2026-11-06T12:00:00Z"):
    return {
        "kind": "OWNER_CONFIRMATION",
        "method": "OWNER_CONFIRMED_TEST_RECEIPT",
        "status": "OWNER_CONFIRMED",
        "completeness": "OWNER_CONFIRMED",
        "provenance": "OWNER_CONFIRMED",
        "coverage_status": "OWNER_CONFIRMED",
        "captured_at": captured_at,
        "references": [],
    }


def _setup(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-history.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    anchor_service = FifoCostAnchorService(repository)
    preview = anchor_service.preview_opening_anchor(
        **IDENTITY,
        inventory_cutoff="2026-11-05",
        cost_layers=[
            {
                "sequence": 1, "unit_cost_rub": "5.00",
                "ozon_units": 2, "transit_units": 0, "home_units": 0,
            },
            {
                "sequence": 2, "unit_cost_rub": "10.00",
                "ozon_units": 1, "transit_units": 0, "home_units": 1,
            },
        ],
        ozon_units_include_reserved_confirmed=True,
        transit_not_in_ozon_confirmed=True,
    )
    assert preview["error"] is False
    committed = anchor_service.commit_opening_anchor(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="history-anchor01",
    )
    assert committed["error"] is False
    return repository


def test_fifo_history_returns_empty_scope_without_guessing_a_queue(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        service = FifoCostHistoryService(
            FifoCostRepository(db_path=tmp_path / "fifo-empty-history.sqlite")
        )
        result = service.get_sku_history(**IDENTITY, as_of_date=date(2026, 11, 6))
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is False
    assert result["queue_initialized"] is False
    assert result["layers"] == []
    assert result["rates"] == []
    assert result["next_unit_cost_rub"] is None


def test_fifo_history_separates_old_finite_next_unit_and_planned_rate(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = _setup(tmp_path)
        rate_service = FifoCostRateService(repository)
        preview = rate_service.preview_new_cost(
            **IDENTITY,
            effective_date="2026-11-07",
            purchase_cost_rub="12.00",
            delivery_cost_rub="2.00",
            packaging_cost_rub="1.00",
            old_home_units=1,
            expected_revision=1,
        )
        assert preview["error"] is False
        committed = rate_service.confirm_new_cost(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="history-rate-change01",
        )
        assert committed["error"] is False

        result = FifoCostHistoryService(repository).get_sku_history(
            **IDENTITY, as_of_date=date(2026, 11, 6),
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["queue_initialized"] is True
    assert result["revision"] == 2
    assert result["cutoff_date"] == "2026-11-05"
    assert result["remaining_status"] == "AT_CONFIRMED_SNAPSHOT"
    assert result["next_unit_cost_rub"] == "5.00"
    assert result["next_unit_cost_basis"] == "FINITE_FIFO_LAYER"
    assert [row["remaining_units"] for row in result["layers"]] == [2, 1, 1]
    assert result["next_planned_rate"]["unit_cost_rub"] == "15.00"
    assert result["next_planned_rate"]["status"] == "PLANNED"
    assert {row["provenance_label"] for row in result["layers"]} == {
        "подтверждено владельцем",
    }
    assert not any(
        any("id" in key.lower() or "fingerprint" in key.lower() for key in row)
        for row in result["layers"] + result["rates"]
    )


def test_history_does_not_claim_remaining_units_after_unreplayed_movement(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = _setup(tmp_path)
        preview = repository.preview_command(
            **IDENTITY,
            events=[{
                "kind": "INVENTORY_TRANSFER",
                "quantity": 1,
                "effective_date": "2026-11-06",
                "location_from": "HOME",
                "location_to": "TRANSIT",
            }],
            source=_source(),
            expected_revision=1,
        )
        assert preview["error"] is False
        committed = repository.commit_command(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="history-movement01",
        )
        assert committed["error"] is False
        result = FifoCostHistoryService(repository).get_sku_history(
            **IDENTITY, as_of_date=date(2026, 11, 6),
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["movement_count"] == 1
    assert result["remaining_status"] == "REPLAY_REQUIRED"
    assert result["next_unit_cost_rub"] is None
    assert all(row["remaining_units"] is None for row in result["layers"])


def test_history_preserves_proven_zero_rate_balance_without_making_it_next_unit():
    snapshot = {
        "error": False,
        "code": "FIFO_HISTORY_READY",
        "revision": 3,
        "stream_state": "FIFO_READY",
        "cutoff_date": "2026-11-05",
        "projection": {"queue_complete": True},
        "layers": [{
            "sequence": 1, "recorded_quantity": 10,
            "unit_cost_rub": "5.00", "effective_date": "2026-11-05",
            "location": "OZON", "provenance": "OWNER_CONFIRMED",
        }],
        "rates": [
            {
                "sequence": 1, "effective_date": "2026-11-06",
                "unit_cost_rub": "10.00", "provenance": "OWNER_CONFIRMED",
                "cancelled": False,
            },
            {
                "sequence": 2, "effective_date": "2026-11-07",
                "unit_cost_rub": "20.00", "provenance": "OWNER_CONFIRMED",
                "cancelled": False,
            },
        ],
        "rate_reconciliations": [{
            "reconciled_rate_sequence": 1,
            "transition_rate_sequence": 2,
            "prior_rate_units": 0,
            "reconciled_total_units": 10,
        }],
        "rate_cancellations": [],
        "movement_count": 1,
        "latest_allocation": {
            "revision": 4,
            "stream_revision": 3,
            "status": "COMPLETE",
            "cutoff_status": "RECONCILED",
            "stale": False,
            "replayed_remaining_layers": [{
                "sequence": 1, "remaining_units": 0,
            }],
            "replayed_rate_balances": [
                {"sequence": 1, "remaining_units": 0, "unit_cost_rub": "10.00"},
                {"sequence": 2, "remaining_units": None, "unit_cost_rub": "20.00"},
            ],
        },
    }

    class _SnapshotRepository:
        @staticmethod
        def read_cost_history_snapshot(**_kwargs):
            return snapshot

    result = FifoCostHistoryService(_SnapshotRepository()).get_sku_history(
        **IDENTITY, as_of_date="2026-11-07",
    )

    assert result["remaining_status"] == "AFTER_CONFIRMED_REPLAY"
    assert result["reconciled_rate_layers"] == [{
        "sequence": 1,
        "recorded_quantity": 0,
        "remaining_units": 0,
        "unit_cost_rub": "10.00",
        "effective_date": "2026-11-06",
        "provenance": "OWNER_CONFIRMED",
        "provenance_label": "подтверждено владельцем",
        "kind": "RECONCILED_RATE",
        "remaining_status": "AFTER_CONFIRMED_REPLAY",
    }]
    assert result["next_unit_cost_rub"] == "20.00"
    assert result["next_unit_cost_basis"] == "OPEN_RATE_QUANTITY_UNKNOWN"

    latest = snapshot["latest_allocation"]
    invalid_allocations = [
        {**latest, "stream_revision": 2},
        {**latest, "stale": True},
        {**latest, "replayed_rate_balances": latest["replayed_rate_balances"][:1]},
        {
            **latest,
            "replayed_rate_balances": [
                {"sequence": 1, "remaining_units": 0, "unit_cost_rub": "11.00"},
                latest["replayed_rate_balances"][1],
            ],
        },
    ]
    for invalid_allocation in invalid_allocations:
        invalid_snapshot = {
            **snapshot,
            "latest_allocation": invalid_allocation,
        }

        class _InvalidSnapshotRepository:
            @staticmethod
            def read_cost_history_snapshot(**_kwargs):
                return invalid_snapshot

        invalid = FifoCostHistoryService(_InvalidSnapshotRepository()).get_sku_history(
            **IDENTITY, as_of_date="2026-11-07",
        )
        assert invalid["remaining_status"] == "REPLAY_REQUIRED"
        assert invalid["next_unit_cost_rub"] is None
        assert all(row["remaining_units"] is None for row in invalid["layers"])


def test_late_delivery_transfer_does_not_create_a_second_cost_layer(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = FifoCostRepository(
            db_path=tmp_path / "fifo-late-delivery-transfer.sqlite",
            now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
        )
        anchor = FifoCostAnchorService(repository)
        preview = anchor.preview_opening_anchor(
            **IDENTITY,
            inventory_cutoff="2026-11-05",
            cost_layers=[
                {
                    "sequence": 1, "unit_cost_rub": "21.00",
                    "ozon_units": 1, "transit_units": 2, "home_units": 0,
                },
                {
                    "sequence": 2, "unit_cost_rub": "14.65",
                    "ozon_units": 100, "transit_units": 0, "home_units": 0,
                },
            ],
            ozon_units_include_reserved_confirmed=True,
            transit_not_in_ozon_confirmed=True,
        )
        assert preview["error"] is False
        committed = anchor.commit_opening_anchor(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="late-delivery-opening01",
        )
        assert committed["error"] is False

        connection = repository.get_connection()
        try:
            before_layers = [tuple(row) for row in connection.execute(
                "SELECT layer_sequence, quantity, unit_cost_rub "
                "FROM fifo_cost_layers ORDER BY layer_sequence"
            ).fetchall()]
        finally:
            connection.close()

        movement = repository.preview_command(
            **IDENTITY,
            events=[{
                "kind": "INVENTORY_TRANSFER", "quantity": 2,
                "effective_date": "2026-11-08",
                "location_from": "TRANSIT", "location_to": "OZON",
            }],
            source={**_source(), "inventory_cutoff": "2026-11-05"},
            expected_revision=1,
        )
        assert movement["error"] is False
        moved = repository.commit_command(
            preview_id=movement["preview_id"],
            active_preview_id=movement["preview_id"],
            idempotency_key="late-delivery-transfer01",
        )
        assert moved["error"] is False

        connection = repository.get_connection()
        try:
            after_layers = [tuple(row) for row in connection.execute(
                "SELECT layer_sequence, quantity, unit_cost_rub "
                "FROM fifo_cost_layers ORDER BY layer_sequence"
            ).fetchall()]
            transfer_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events WHERE event_kind='INVENTORY_TRANSFER'"
            ).fetchone()[0]
            receipt_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_events WHERE event_kind='COST_LAYER_RECEIPT'"
            ).fetchone()[0]
        finally:
            connection.close()

        assert after_layers == before_layers
        assert transfer_count == 1
        assert receipt_count == 0
    finally:
        reset_current_tenant_user_id(token)

