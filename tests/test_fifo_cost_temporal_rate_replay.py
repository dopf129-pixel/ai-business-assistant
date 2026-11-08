"""Acceptance regressions for sequential FIFO rate changes and replay ordering."""

from datetime import datetime
from decimal import Decimal

import pytest

from services.fifo_cost_allocation_service import (
    FifoCostAllocationService,
    FifoCostLayer,
    FifoOpenCostRate,
    FifoOutflowEvent,
    FifoRateBoundaryEvent,
    FifoRestoreSlice,
    FifoRestockEvent,
    FifoSaleEvent,
)
from services.fifo_cost_replay_service import (
    FifoCostReplayService,
    FifoDatedAllocationEvent,
    FifoDatedRateBoundaryEvent,
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


def _kernel_boundary(rate_id, cost, fingerprint, *, previous=None,
                     previous_remaining=None, older_finite=None):
    return FifoRateBoundaryEvent(
        event_id=f"boundary-{rate_id}",
        new_rate_change_id=rate_id,
        new_unit_cost_rub=cost,
        previous_rate_change_id=previous,
        previous_rate_remaining_units=previous_remaining,
        expected_older_finite_units=older_finite,
        reconciliation_evidence_fingerprint=fingerprint,
    )


def _allocate_kernel(*, layers, events, anchor_status="CONFIRMED"):
    return FifoCostAllocationService().allocate(
        layers=layers,
        events=events,
        anchor_status=anchor_status,
        cutoff_status="RECONCILED",
        event_order_status="PROVEN",
        source_completeness="COMPLETE",
    )


def test_mr01_mr02_mr03_pure_kernel_replays_three_rates_without_inventing_receipts():
    result = _allocate_kernel(
        layers=(
            FifoCostLayer("old", "21.00", 3),
            FifoCostLayer("new-finite", "14.65", 100),
        ),
        events=(
            _kernel_boundary("r1", "14.65", "1" * 64),
            FifoSaleEvent("sale-1", 5),
            _kernel_boundary(
                "r2", "16.00", "2" * 64, previous="r1",
                previous_remaining=10, older_finite=98,
            ),
            FifoSaleEvent("sale-2", 110),
            _kernel_boundary(
                "r3", "18.00", "3" * 64, previous="r2",
                previous_remaining=7, older_finite=0,
            ),
            FifoSaleEvent("sale-3", 10),
        ),
    )

    assert result.complete is True, result
    first, second, third = result.sale_allocations
    assert first.total_cost_rub == Decimal("92.30")
    assert [(line.quantity, line.unit_cost_rub) for line in first.lines] == [
        (3, Decimal("21.00")), (2, Decimal("14.65")),
    ]
    assert second.total_cost_rub == Decimal("1614.20")
    assert [(line.quantity, line.unit_cost_rub, line.basis_kind, line.rate_change_id)
            for line in second.lines] == [
        (98, Decimal("14.65"), "FINITE_LAYER", None),
        (10, Decimal("14.65"), "MATERIALIZED_RATE_BALANCE", "r1"),
        (2, Decimal("16.00"), "OPEN_RATE", "r2"),
    ]
    assert third.total_cost_rub == Decimal("166.00")
    assert [(line.quantity, line.unit_cost_rub, line.rate_change_id)
            for line in third.lines] == [
        (7, Decimal("16.00"), "r2"),
        (3, Decimal("18.00"), "r3"),
    ]
    assert result.total_cogs_rub == Decimal("1872.50")
    balances = {row.rate_change_id: row for row in result.rate_balances}
    assert balances["r1"].remaining_units == 0
    assert balances["r2"].remaining_units == 0
    assert balances["r3"].remaining_units is None
    assert balances["r3"].reconciliation_evidence_fingerprint == "3" * 64
    assert result.remaining_confirmed_units == 0
    assert result.total_available_units is None


def test_mr04_mr05_return_from_closed_rate_restores_cost_and_origin_before_current_rate():
    result = _allocate_kernel(
        layers=(
            FifoCostLayer("old", "21.00", 3),
            FifoCostLayer("new-finite", "14.65", 100),
        ),
        events=(
            _kernel_boundary("r1", "14.65", "1" * 64),
            FifoSaleEvent("sale-1", 5),
            _kernel_boundary(
                "r2", "16.00", "2" * 64, previous="r1",
                previous_remaining=10, older_finite=98,
            ),
            FifoSaleEvent("sale-2", 110),
            _kernel_boundary(
                "r3", "18.00", "3" * 64, previous="r2",
                previous_remaining=7, older_finite=0,
            ),
            FifoSaleEvent("sale-3", 10),
            FifoRestockEvent(
                "return-r2", 1, (FifoRestoreSlice("sale-2", "r2", 1),),
            ),
            FifoSaleEvent("sale-4", 1),
        ),
    )

    assert result.complete is True, result
    assert result.total_cogs_rub == Decimal("1888.50")
    restored_sale = result.sale_allocations[-1]
    assert restored_sale.total_cost_rub == Decimal("16.00")
    assert len(restored_sale.lines) == 1
    assert restored_sale.lines[0].origin_sale_event_id == "sale-2"
    assert restored_sale.lines[0].rate_change_id == "r2"


def test_mr06_outflow_consumes_only_finite_fifo_layers_before_rate_sale():
    result = _allocate_kernel(
        layers=(
            FifoCostLayer("old", "21.00", 3),
            FifoCostLayer("new-finite", "14.65", 100),
        ),
        events=(
            _kernel_boundary("r1", "14.65", "1" * 64),
            FifoOutflowEvent("outflow", 1, "HOME_SHORTAGE"),
            FifoSaleEvent("sale", 5),
        ),
    )

    assert result.complete is True, result
    assert result.outflow_allocations[0].estimated_value_rub == Decimal("21.00")
    assert result.sale_allocations[0].total_cost_rub == Decimal("85.95")
    assert result.total_cogs_rub == Decimal("85.95")


def test_mr07_open_rate_values_sales_but_never_claims_known_quantity_or_values_outflow():
    base = _allocate_kernel(
        layers=(),
        anchor_status="CONFIRMED_ZERO",
        events=(
            _kernel_boundary("r1", "14.65", "1" * 64),
            FifoSaleEvent("sale", 4),
        ),
    )
    outflow = _allocate_kernel(
        layers=(),
        anchor_status="CONFIRMED_ZERO",
        events=(
            _kernel_boundary("r1", "14.65", "1" * 64),
            FifoOutflowEvent("outflow", 1, "OZON_DISPOSAL"),
        ),
    )

    assert base.complete is True
    assert base.total_cogs_rub == Decimal("58.60")
    assert base.remaining_confirmed_units == 0
    assert base.total_available_units is None
    assert {row.rate_change_id: row.remaining_units for row in base.rate_balances} == {
        "r1": None,
    }
    assert outflow.complete is False
    assert outflow.reason_code == "FIFO_OUTFLOW_FINITE_BASIS_UNAVAILABLE"


@pytest.mark.parametrize("events,reason", [
    (
        (_kernel_boundary("r1", "14.65", "1" * 64),
         FifoSaleEvent("sale", 1),
         _kernel_boundary("r2", "16.00", "2" * 64, previous="wrong",
                          previous_remaining=1, older_finite=0)),
        "FIFO_RATE_CHAIN_CONFLICT",
    ),
    (
        (_kernel_boundary("r1", "14.65", "1" * 64),
         FifoSaleEvent("sale", 1),
         _kernel_boundary("r2", "16.00", "2" * 64, previous="r1",
                          previous_remaining=1, older_finite=0)),
        "FIFO_RATE_BALANCE_MISMATCH",
    ),
])
def test_fr05_rate_chain_and_finite_balance_conflicts_fail_closed(events, reason):
    result = _allocate_kernel(
        layers=(FifoCostLayer("finite", "20.00", 2),),
        events=events,
    )

    assert result.complete is False
    assert result.reason_code == reason
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


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
    assert result["rate_balances"]["r2"]["remaining_units"] == 0
    assert result["rate_balances"]["r3"]["remaining_units"] is None


def test_mr03_accepts_stock_decrease_explained_by_the_full_sale_bridge():
    result = _complete_temporal_replay()

    assert result["complete"] is True, result
    _, second, third = result["allocations"]
    assert second["total_cost_rub"] == "1614.20"
    assert third["total_cost_rub"] == "166.00"
    assert result["total_cogs_rub"] == "1872.50"
    assert result["rate_balances"]["r3"]["remaining_units"] is None


def test_rate_boundary_date_uses_the_store_local_calendar_boundary():
    boundary = FifoRateBoundaryEvent(
        event_id="r1-boundary",
        new_rate_change_id="r1",
        new_unit_cost_rub="14.654",
        previous_rate_change_id=None,
        previous_rate_remaining_units=None,
        expected_older_finite_units=None,
        reconciliation_evidence_fingerprint="1" * 64,
    )
    dated = FifoDatedRateBoundaryEvent(
        event=boundary,
        effective_at=None,
        effective_date="2026-11-07",
        store_timezone="Europe/Moscow",
        boundary_kind="END_OF_LOCAL_DATE",
        boundary_evidence_fingerprint="1" * 64,
    )

    assert boundary.new_unit_cost_rub.as_tuple().exponent == -2
    assert dated.boundary_kind == "END_OF_LOCAL_DATE"
    # A timestamp on the same local date precedes the end-of-date boundary.
    timestamp = datetime.fromisoformat("2026-11-07T23:59:59+03:00")
    assert timestamp.date().isoformat() == dated.effective_date


def _dated_boundary(rate_id, cost, date_or_instant, *, fingerprint,
                    previous=None, previous_remaining=None, older_finite=None,
                    timezone_name="Europe/Moscow", exact=False):
    event = _kernel_boundary(
        rate_id, cost, fingerprint, previous=previous,
        previous_remaining=previous_remaining, older_finite=older_finite,
    )
    return FifoDatedRateBoundaryEvent(
        event=event,
        effective_at=date_or_instant if exact else None,
        effective_date=None if exact else date_or_instant,
        store_timezone=timezone_name,
        boundary_kind="EXACT_INSTANT" if exact else "END_OF_LOCAL_DATE",
        boundary_evidence_fingerprint=fingerprint,
    )


def _rate_sale(event_id, quantity, *, timestamp=None, date=None, digest=None):
    return FifoDatedAllocationEvent(
        event=FifoSaleEvent(event_id, quantity),
        effective_at=timestamp,
        effective_date=date,
        source_identity_digest=digest or (event_id.encode().hex().ljust(64, "0"))[:64],
        physical_time_confirmed=True,
        cutoff_bridge_confirmed=True,
    )


def _rate_preview(*, boundaries, events, timezone_name="Europe/Moscow",
                  complete_through="2026-11-15", anchor_cutoff="2026-11-05",
                  layers=(), anchor_status="CONFIRMED_ZERO"):
    return FifoCostReplayService().preview(
        layers=layers,
        events=events,
        rate_boundaries=boundaries,
        store_timezone=timezone_name,
        complete_through=complete_through,
        stream_revision=1,
        expected_allocation_revision=0,
        source_set_fingerprint="a" * 64,
        anchor_cutoff_date=anchor_cutoff,
        anchor_status=anchor_status,
        cutoff_status="RECONCILED",
        source_completeness="COMPLETE",
    )


def test_fr06_end_of_local_date_boundary_follows_same_day_sale():
    result = _rate_preview(
        boundaries=(
            _dated_boundary("r1", "14.65", "2026-11-06", fingerprint="1" * 64),
            _dated_boundary(
                "r2", "16.00", "2026-11-07", fingerprint="2" * 64,
                previous="r1", previous_remaining=0, older_finite=0,
            ),
        ),
        events=(
            _rate_sale("sale-same-day", 1, date="2026-11-07"),
            _rate_sale("sale-next-day", 1, date="2026-11-08"),
        ),
    )

    assert result["complete"] is True, result
    assert [row["event_id"] for row in result["allocations"]] == [
        "sale-same-day", "sale-next-day",
    ]
    assert [row["lines"][0]["rate_change_id"] for row in result["allocations"]] == [
        "r1", "r2",
    ]
    assert result["allocations"][0]["lines"][0]["basis_kind"] == "OPEN_RATE"


def test_fr06_exact_timestamps_compare_in_store_timezone_not_utc_date():
    timezone_name = "America/Los_Angeles"
    result = _rate_preview(
        timezone_name=timezone_name,
        anchor_cutoff="2026-11-05",
        boundaries=(
            _dated_boundary(
                "r1", "14.65", "2026-11-06", fingerprint="1" * 64,
                timezone_name=timezone_name,
            ),
            _dated_boundary(
                "r2", "16.00", "2026-11-07", fingerprint="2" * 64,
                previous="r1", previous_remaining=0, older_finite=0,
                timezone_name=timezone_name,
            ),
        ),
        events=(
            # UTC date is Nov 8, but the instant is still Nov 7 in the store.
            _rate_sale(
                "sale-local-nov-7", 1, timestamp="2026-11-08T01:00:00Z",
                date="2026-11-07",
            ),
            _rate_sale(
                "sale-local-nov-8", 1, timestamp="2026-11-08T09:00:00Z",
                date="2026-11-08",
            ),
        ),
    )

    assert result["complete"] is True, result
    assert [row["lines"][0]["rate_change_id"] for row in result["allocations"]] == [
        "r1", "r2",
    ]


def test_fr06_exact_same_instant_boundary_and_sale_block_when_order_changes_basis():
    result = _rate_preview(
        boundaries=(
            _dated_boundary(
                "r1", "14.65", "2026-11-07T12:00:00Z",
                fingerprint="1" * 64, exact=True,
            ),
        ),
        events=(
            _rate_sale(
                "sale-tie", 1, timestamp="2026-11-07T12:00:00Z",
                digest="a" * 64,
            ),
        ),
        anchor_status="CONFIRMED_ZERO",
    )

    assert result["complete"] is False
    assert result["reason_code"] == "EVENT_ORDER_UNRESOLVED"
    assert result["allocations"] == []


def test_fr06_duplicate_boundary_and_permuted_source_rows_keep_one_stable_fingerprint():
    r1 = _dated_boundary("r1", "14.65", "2026-11-06", fingerprint="1" * 64)
    r2 = _dated_boundary(
        "r2", "16.00", "2026-11-07", fingerprint="2" * 64,
        previous="r1", previous_remaining=0, older_finite=0,
    )
    first = _rate_preview(
        boundaries=(r1, r2, r1),
        events=(
            _rate_sale("sale-b", 1, date="2026-11-08"),
            _rate_sale("sale-a", 1, date="2026-11-07"),
        ),
    )
    second = _rate_preview(
        boundaries=(r2, r1),
        events=(
            _rate_sale("sale-a", 1, date="2026-11-07"),
            _rate_sale("sale-b", 1, date="2026-11-08"),
        ),
    )

    assert first["complete"] is True, first
    assert first["allocations"] == second["allocations"]
    assert first["rate_balances"] == second["rate_balances"]
    assert first["rate_boundary_set_fingerprint"] == second["rate_boundary_set_fingerprint"]
    assert first["preview_fingerprint"] == second["preview_fingerprint"]


def test_fr06_exact_duplicate_sale_page_collapses_to_one_sale_but_conflicting_duplicate_blocks():
    boundary = _dated_boundary("r1", "14.65", "2026-11-06", fingerprint="1" * 64)
    sale = _rate_sale(
        "sale-unique", 2, date="2026-11-07", digest="d" * 64,
    )
    duplicate_page = _rate_preview(
        boundaries=(boundary,), events=(sale, sale),
    )
    single_page = _rate_preview(
        boundaries=(boundary,), events=(sale,),
    )
    conflicting_sale = _rate_sale(
        "sale-unique", 3, date="2026-11-07", digest="d" * 64,
    )
    conflict = _rate_preview(
        boundaries=(boundary,), events=(sale, conflicting_sale),
    )

    assert duplicate_page["complete"] is True, duplicate_page
    assert len(duplicate_page["allocations"]) == 1
    assert duplicate_page["preview_fingerprint"] == single_page["preview_fingerprint"]
    assert conflict["complete"] is False
    assert conflict["reason_code"] == "FIFO_EVENT_ID_DUPLICATE"


def test_fr06_conflicting_boundary_position_and_incomplete_horizon_fail_closed():
    first = _dated_boundary("r1", "14.65", "2026-11-07", fingerprint="1" * 64)
    competing = _dated_boundary("r2", "16.00", "2026-11-07", fingerprint="2" * 64)
    conflict = _rate_preview(boundaries=(first, competing), events=())
    horizon = _rate_preview(
        boundaries=(first,),
        events=(_rate_sale("sale-late", 1, date="2026-11-16"),),
        complete_through="2026-11-15",
    )

    assert conflict["complete"] is False
    assert conflict["reason_code"] == "FIFO_RATE_CHAIN_CONFLICT"
    assert horizon["complete"] is False
    assert horizon["reason_code"] == "FIFO_SOURCE_INCOMPLETE"


def test_fr06_end_of_day_and_next_midnight_boundary_are_same_proven_position():
    end_of_day = _dated_boundary(
        "r1", "14.65", "2026-11-07", fingerprint="1" * 64,
    )
    exact_midnight = _dated_boundary(
        "r2", "16.00", "2026-11-07T21:00:00Z", fingerprint="2" * 64,
        previous="r1", previous_remaining=0, older_finite=0, exact=True,
    )

    result = _rate_preview(boundaries=(end_of_day, exact_midnight), events=())

    assert result["complete"] is False
    assert result["reason_code"] == "FIFO_RATE_CHAIN_CONFLICT"


@pytest.mark.parametrize("kwargs,code", [
    ({"new_unit_cost_rub": True}, "FIFO_RATE_BOUNDARY_UNPROVEN"),
    ({"new_unit_cost_rub": "0.00"}, "FIFO_RATE_BOUNDARY_UNPROVEN"),
    ({"new_unit_cost_rub": float("nan")}, "FIFO_RATE_BOUNDARY_UNPROVEN"),
    ({"new_unit_cost_rub": "-0.01"}, "FIFO_RATE_BOUNDARY_UNPROVEN"),
    ({"previous_rate_change_id": "r1", "previous_rate_remaining_units": True,
      "expected_older_finite_units": 1}, "FIFO_RATE_BOUNDARY_UNPROVEN"),
    ({"previous_rate_change_id": "r1", "previous_rate_remaining_units": 1,
      "expected_older_finite_units": None}, "FIFO_RATE_BOUNDARY_UNPROVEN"),
    ({"previous_rate_change_id": None, "previous_rate_remaining_units": 0,
      "expected_older_finite_units": 0}, "FIFO_RATE_CHAIN_CONFLICT"),
    ({"previous_rate_change_id": "r2"}, "FIFO_RATE_CHAIN_CONFLICT"),
    ({"reconciliation_evidence_fingerprint": "A" * 64}, "FIFO_RATE_BOUNDARY_UNPROVEN"),
])
def test_rate_boundary_rejects_untrusted_values(kwargs, code):
    values = {
        "event_id": "boundary-r2",
        "new_rate_change_id": "r2",
        "new_unit_cost_rub": "16.00",
        "previous_rate_change_id": "r1",
        "previous_rate_remaining_units": 10,
        "expected_older_finite_units": 98,
        "reconciliation_evidence_fingerprint": "2" * 64,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=code):
        FifoRateBoundaryEvent(**values)


@pytest.mark.parametrize("kwargs", [
    {"effective_at": "2026-11-07T10:00:00", "effective_date": None,
     "boundary_kind": "EXACT_INSTANT"},
    {"effective_at": "2026-11-07T10:00:00Z", "effective_date": "2026-11-07",
     "boundary_kind": "EXACT_INSTANT"},
    {"effective_at": None, "effective_date": "2026-02-30",
     "boundary_kind": "END_OF_LOCAL_DATE"},
    {"effective_at": None, "effective_date": "2026-11-07",
     "boundary_kind": "EXACT_INSTANT"},
    {"effective_at": None, "effective_date": "2026-11-07",
     "boundary_kind": "END_OF_LOCAL_DATE", "store_timezone": "Mars/Olympus"},
    {"effective_at": None, "effective_date": "2026-11-07",
     "boundary_kind": "END_OF_LOCAL_DATE", "boundary_evidence_fingerprint": "3" * 64},
])
def test_dated_rate_boundary_requires_explicit_timezone_and_matching_proof(kwargs):
    boundary = FifoRateBoundaryEvent(
        event_id="boundary-r2",
        new_rate_change_id="r2",
        new_unit_cost_rub="16.00",
        previous_rate_change_id="r1",
        previous_rate_remaining_units=10,
        expected_older_finite_units=98,
        reconciliation_evidence_fingerprint="2" * 64,
    )
    values = {
        "event": boundary,
        "effective_at": None,
        "effective_date": "2026-11-07",
        "store_timezone": "Europe/Moscow",
        "boundary_kind": "END_OF_LOCAL_DATE",
        "boundary_evidence_fingerprint": "2" * 64,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match="FIFO_RATE_BOUNDARY_UNPROVEN"):
        FifoDatedRateBoundaryEvent(**values)


def test_legacy_single_open_rate_kernel_contract_remains_available():
    result = FifoCostAllocationService().allocate(
        layers=(FifoCostLayer("old", "21.00", 1),),
        events=(FifoSaleEvent("sale", 2),),
        anchor_status="CONFIRMED",
        cutoff_status="RECONCILED",
        event_order_status="PROVEN",
        source_completeness="COMPLETE",
        open_rate=FifoOpenCostRate("r1", "14.65"),
    )

    assert result.complete is True
    assert result.total_cogs_rub == Decimal("35.65")
