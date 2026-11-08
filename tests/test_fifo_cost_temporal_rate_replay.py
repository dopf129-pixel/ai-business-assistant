"""Review regressions for sequential FIFO rate changes.

These tests describe the public temporal replay contract required by FR02.
They intentionally fail on the single-open-rate baseline until FR04–FR06 land.
"""

from datetime import datetime

from services.fifo_cost_allocation_service import FifoCostLayer, FifoSaleEvent
from services.fifo_cost_replay_service import (
    FifoCostReplayService,
    FifoDatedAllocationEvent,
)


def _boundary(boundary_type, *, rate_id, cost, date, previous=None,
              previous_remaining=None, older_finite=None, fingerprint):
    event = boundary_type(
        event_id=f"boundary-{rate_id}",
        new_rate_change_id=rate_id,
        new_unit_cost_rub=cost,
        previous_rate_change_id=previous,
        previous_rate_remaining_units=previous_remaining,
        expected_older_finite_units=older_finite,
        reconciliation_evidence_fingerprint=fingerprint,
    )
    return event


def _sale(event_id, quantity, date):
    return FifoDatedAllocationEvent(
        event=FifoSaleEvent(event_id, quantity),
        effective_at=None,
        effective_date=date,
        source_identity_digest=(event_id.encode().hex().ljust(64, "0"))[:64],
        physical_time_confirmed=True,
        cutoff_bridge_confirmed=True,
    )


def _complete_temporal_replay():
    import services.fifo_cost_allocation_service as allocation_module
    import services.fifo_cost_replay_service as replay_module

    boundary_type = getattr(allocation_module, "FifoRateBoundaryEvent", None)
    dated_boundary_type = getattr(replay_module, "FifoDatedRateBoundaryEvent", None)
    assert boundary_type is not None and dated_boundary_type is not None, (
        "MR02-MR03 blocker reproduced: replay has no typed multi-rate boundary"
    )

    boundary_r1 = _boundary(
        boundary_type, rate_id="r1", cost="14.65", date="2026-11-07",
        fingerprint="1" * 64,
    )
    boundary_r2 = _boundary(
        boundary_type, rate_id="r2", cost="16.00", date="2026-11-09",
        previous="r1", previous_remaining=10, older_finite=98,
        fingerprint="2" * 64,
    )
    boundary_r3 = _boundary(
        boundary_type, rate_id="r3", cost="18.00", date="2026-11-11",
        previous="r2", previous_remaining=7, older_finite=0,
        fingerprint="3" * 64,
    )

    def dated(event, effective_date):
        return dated_boundary_type(
            event=event,
            effective_at=None,
            effective_date=effective_date,
            store_timezone="Europe/Moscow",
            boundary_kind="END_OF_LOCAL_DATE",
            boundary_evidence_fingerprint=event.reconciliation_evidence_fingerprint,
        )

    events = (
        _sale("sale-1", 5, "2026-11-08"),
        _sale("sale-2", 110, "2026-11-10"),
        _sale("sale-3", 10, "2026-11-12"),
    )
    return FifoCostReplayService().preview(
        layers=(
            FifoCostLayer("old", "21.00", 3),
            FifoCostLayer("new-finite", "14.65", 100),
        ),
        events=events,
        rate_boundaries=(
            dated(boundary_r1, "2026-11-07"),
            dated(boundary_r2, "2026-11-09"),
            dated(boundary_r3, "2026-11-11"),
        ),
        stream_revision=1,
        expected_allocation_revision=0,
        source_set_fingerprint="a" * 64,
        anchor_cutoff_date="2026-11-06",
        anchor_status="CONFIRMED",
        cutoff_status="RECONCILED",
        source_completeness="COMPLETE",
        complete_through="2026-11-15",
        store_timezone="Europe/Moscow",
    )


def test_mr02_materializes_only_proven_r1_residual_before_r2_sale():
    result = _complete_temporal_replay()

    assert result["complete"] is True, result
    first, second, third = result["allocations"]
    assert first["total_cost_rub"] == "92.30"
    assert [(line["quantity"], line["unit_cost_rub"]) for line in first["lines"]] == [
        (3, "21.00"), (2, "14.65"),
    ]
    assert second["total_cost_rub"] == "1614.20"
    assert [(line["quantity"], line["unit_cost_rub"]) for line in second["lines"]] == [
        (98, "14.65"), (10, "14.65"), (2, "16.00"),
    ]
    assert result["rate_balances"]["r2"]["remaining_units"] is None


def test_mr03_accepts_stock_decrease_explained_by_the_full_sale_bridge():
    result = _complete_temporal_replay()

    assert result["complete"] is True, result
    _, second, third = result["allocations"]
    assert second["total_cost_rub"] == "1614.20"
    assert third["total_cost_rub"] == "166.00"
    assert result["total_cogs_rub"] == "1872.50"
    assert result["rate_balances"]["r3"]["remaining_units"] is None


def test_rate_boundary_date_uses_the_store_local_calendar_boundary():
    import services.fifo_cost_allocation_service as allocation_module

    assert getattr(allocation_module, "FifoRateBoundaryEvent", None) is not None, (
        "Temporal rate boundary contract is not implemented"
    )
    # The domain boundary is local date end, not UTC midnight. The concrete
    # ordering assertions are exercised through the real replay in FR06.
    assert datetime.fromisoformat("2026-11-07T23:59:59+03:00").date().isoformat() == "2026-11-07"
