from decimal import Decimal

import pytest

from services.fifo_cost_allocation_service import (
    FifoCostLayer,
    FifoOutflowEvent,
    FifoOpenCostRate,
    FifoRestoreSlice,
    FifoRestockEvent,
    FifoSaleEvent,
)
from services.fifo_cost_replay_service import (
    FifoCostReplayService,
    FifoDatedAllocationEvent,
)


@pytest.fixture
def service():
    return FifoCostReplayService()


def _sale(event_id, quantity, sale_date, digest, **overrides):
    values = {
        "event": FifoSaleEvent(event_id, quantity),
        "effective_at": None,
        "effective_date": sale_date,
        "source_identity_digest": digest,
        "physical_time_confirmed": True,
        "cutoff_bridge_confirmed": True,
    }
    values.update(overrides)
    return FifoDatedAllocationEvent(**values)


def _return(event_id, quantity, return_date, digest, restores, **overrides):
    values = {
        "event": FifoRestockEvent(event_id, quantity, tuple(restores)),
        "effective_at": None,
        "effective_date": return_date,
        "source_identity_digest": digest,
        "physical_time_confirmed": True,
        "cutoff_bridge_confirmed": True,
        "saleable_recovery_confirmed": True,
    }
    values.update(overrides)
    return FifoDatedAllocationEvent(**values)


def _outflow(event_id, quantity, movement_date, digest, **overrides):
    values = {
        "event": FifoOutflowEvent(event_id, quantity, "HOME_SHORTAGE"),
        "effective_at": None,
        "effective_date": movement_date,
        "source_identity_digest": digest,
        "physical_time_confirmed": True,
        "cutoff_bridge_confirmed": True,
        "movement_reason_confirmed": True,
    }
    values.update(overrides)
    return FifoDatedAllocationEvent(**values)


def _preview(service, events, **overrides):
    values = {
        "layers": [FifoCostLayer("layer-1", "10.00", 2),
                   FifoCostLayer("layer-2", "20.00", 5)],
        "events": events,
        "stream_revision": 4,
        "expected_allocation_revision": 1,
        "source_set_fingerprint": "a" * 64,
        "anchor_cutoff_date": "2026-11-01",
        "anchor_status": "CONFIRMED",
        "cutoff_status": "RECONCILED",
        "source_completeness": "COMPLETE",
    }
    values.update(overrides)
    return service.preview(**values)


def test_fc16_replay_sorts_by_physical_date_and_is_request_order_independent(service):
    earlier = _sale("sale-early", 2, "2026-11-02", "1" * 64)
    later = _sale("sale-late", 2, "2026-11-03", "2" * 64)

    first = _preview(service, [later, earlier])
    second = _preview(service, [earlier, later])

    assert first["complete"] is True
    assert first["status"] == "COMPLETE"
    assert first["total_cogs_rub"] == "60.00"
    assert first["allocations"] == second["allocations"]
    assert first["preview_fingerprint"] == second["preview_fingerprint"]
    assert [row["event_id"] for row in first["allocations"]] == [
        "sale-early", "sale-late",
    ]
    assert Decimal(first["total_cogs_rub"]) == Decimal("60.00")


def test_fc16_date_only_events_on_same_day_are_not_given_guessed_fifo_order(service):
    result = _preview(service, [
        _sale("sale-a", 1, "2026-11-02", "1" * 64),
        _sale("sale-b", 1, "2026-11-02", "2" * 64),
    ])

    assert result["complete"] is False
    assert result["status"] == "SOURCE_BLOCKED"
    assert result["reason_code"] == "EVENT_ORDER_UNRESOLVED"
    assert result["allocations"] == []


def test_fc16_physical_time_and_cutoff_confirmation_are_required(service):
    no_time = _preview(service, [
        _sale("sale-a", 1, None, "1" * 64),
    ])
    no_bridge = _preview(service, [
        _sale("sale-a", 1, "2026-11-02", "1" * 64,
              cutoff_bridge_confirmed=False),
    ])

    assert no_time["reason_code"] == "EVENT_ORDER_UNRESOLVED"
    assert no_bridge["reason_code"] == "INVENTORY_CUTOFF_UNRECONCILED"
    assert no_bridge["complete"] is False


def test_fc16_runtime_cutoff_or_source_gap_cannot_publish_preview(service):
    sale = _sale("sale-a", 1, "2026-11-02", "1" * 64)
    cutoff = _preview(service, [sale], cutoff_status="INVENTORY_CUTOFF_UNRECONCILED")
    source = _preview(service, [sale], source_completeness="PARTIAL")
    movement = _preview(service, [sale], unsupported_event_count=1)

    assert cutoff["complete"] is False
    assert cutoff["reason_code"] == "INVENTORY_CUTOFF_UNRECONCILED"
    assert source["reason_code"] == "FIFO_SOURCE_INCOMPLETE"
    assert movement["reason_code"] == "FIFO_REPLAY_UNSUPPORTED_EVENT"
    assert all(not item["allocations"] for item in (cutoff, source, movement))


def test_fc16_duplicate_identity_and_equal_timestamp_are_blocked(service):
    duplicate = _preview(service, [
        _sale("sale-a", 1, "2026-11-02", "1" * 64),
        _sale("sale-b", 1, "2026-11-03", "1" * 64),
    ])
    same_instant = _preview(service, [
        _sale("sale-a", 1, "2026-11-02", "1" * 64,
              effective_at="2026-11-02T10:00:00Z"),
        _sale("sale-b", 1, "2026-11-02", "2" * 64,
              effective_at="2026-11-02T10:00:00+00:00"),
    ])

    assert duplicate["reason_code"] == "FIFO_SALE_IDENTITY_DUPLICATE"
    assert same_instant["reason_code"] == "EVENT_ORDER_UNRESOLVED"


def test_fc16_incomplete_allocation_is_not_mislabeled_complete(service):
    result = _preview(
        service,
        [_sale("sale-a", 8, "2026-11-02", "1" * 64)],
        layers=[FifoCostLayer("layer-1", "10.00", 2)],
    )

    assert result["complete"] is False
    assert result["status"] == "CONFLICT"
    assert result["reason_code"] == "FIFO_CONFIRMED_QUANTITY_EXHAUSTED"
    assert result["total_cogs_rub"] is None


def test_fc16_event_collection_is_bounded(service):
    result = _preview(
        service,
        (_sale(f"sale-{i}", 1, "2026-11-02", f"{i:064x}")
         for i in range(service.MAX_EVENTS + 1)),
    )

    assert result["complete"] is False
    assert result["reason_code"] == "FIFO_REPLAY_INPUT_LIMIT"
    assert result["allocations"] == []


def test_fc16_open_rate_does_not_cost_events_before_its_effective_date(service):
    sale_before = _sale("sale-before", 3, "2026-11-02", "1" * 64)
    blocked = _preview(
        service, [sale_before],
        layers=[FifoCostLayer("layer-1", "10.00", 2)],
        open_rate=FifoOpenCostRate("rate-1", "20.00"),
        open_rate_effective_date="2026-11-03",
    )
    later = _preview(
        service, [_sale("sale-after", 3, "2026-11-04", "2" * 64)],
        layers=[FifoCostLayer("layer-1", "10.00", 2)],
        open_rate=FifoOpenCostRate("rate-1", "20.00"),
        open_rate_effective_date="2026-11-03",
    )

    assert blocked["complete"] is False
    assert blocked["reason_code"] == "FIFO_RATE_TRANSITION_ORDER_UNRESOLVED"
    assert later["complete"] is True
    assert later["total_cogs_rub"] == "40.00"
    assert later["allocations"][0]["lines"][1]["rate_change_id"] == "rate-1"


def test_fc18_exact_full_return_restores_original_multi_layer_basis(service):
    sale = _sale("sale-a", 5, "2026-11-02", "1" * 64)
    returned = _return(
        "return-a", 5, "2026-11-03", "a" * 64,
        [
                FifoRestoreSlice("sale-a", "layer-1", 3),
                FifoRestoreSlice("sale-a", "layer-2", 2),
        ],
    )
    result = _preview(
        service, [returned, sale],
        layers=[FifoCostLayer("layer-1", "20.00", 3),
                FifoCostLayer("layer-2", "25.00", 2)],
    )

    assert result["complete"] is True
    assert result["total_cogs_rub"] == "110.00"
    assert result["restored_units"] == 5
    assert result["remaining_confirmed_units"] == 5
    assert result["allocations"][0]["event_id"] == "sale-a"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"saleable_recovery_confirmed": False}, "FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED"),
        ({"physical_time_confirmed": False}, "FIFO_RETURN_EFFECTIVE_DATE_UNAVAILABLE"),
        ({"cutoff_bridge_confirmed": False}, "INVENTORY_CUTOFF_UNRECONCILED"),
        ({"source_identity_digest": None}, "FIFO_RETURN_IDENTITY_UNCONFIRMED"),
    ],
)
def test_fc18_return_requires_exact_recovery_time_and_cutoff_evidence(
    service, overrides, reason,
):
    result = _preview(service, [
        _sale("sale-a", 1, "2026-11-02", "1" * 64),
        _return(
            "return-a", 1, "2026-11-03", "a" * 64,
            [FifoRestoreSlice("sale-a", "layer-1", 1)],
            **overrides,
        ),
    ])

    assert result["complete"] is False
    assert result["reason_code"] == reason
    assert result["allocations"] == []


def test_fc18_duplicate_return_identity_and_over_restoration_fail_closed(service):
    sale = _sale("sale-a", 2, "2026-11-02", "1" * 64)
    first = _return(
        "return-a", 1, "2026-11-03", "a" * 64,
        [FifoRestoreSlice("sale-a", "layer-1", 1)],
    )
    duplicate = _return(
        "return-b", 1, "2026-11-04", "a" * 64,
        [FifoRestoreSlice("sale-a", "layer-1", 1)],
    )
    excessive = _return(
        "return-c", 2, "2026-11-04", "c" * 64,
        [FifoRestoreSlice("sale-a", "layer-1", 2)],
    )

    duplicate_result = _preview(service, [sale, first, duplicate])
    excessive_result = _preview(service, [sale, first, excessive])

    assert duplicate_result["reason_code"] == "FIFO_RETURN_IDENTITY_DUPLICATE"
    assert duplicate_result["allocations"] == []
    assert excessive_result["reason_code"] == "FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN"
    assert excessive_result["allocations"] == []


def test_fc19_non_sale_outflow_has_separate_fifo_estimate_and_no_sales_cogs(service):
    result = _preview(service, [
        _outflow("loss-a", 1, "2026-11-02", "b" * 64),
    ])
    assert result["complete"] is True
    assert result["total_cogs_rub"] == "0.00"
    assert result["non_sale_outflow_value_rub"] == "10.00"
    assert result["outflows"][0]["estimated_value_rub"] == "10.00"
    assert result["outflows"][0]["valuation_method"] == "FIFO_FINITE_LAYER_ESTIMATE"
    assert result["remaining_confirmed_units"] == 6


def test_fc19_unconfirmed_reason_or_open_rate_outflow_basis_is_blocked(service):
    no_reason = _preview(service, [
        _outflow("loss-a", 1, "2026-11-02", "b" * 64,
                 movement_reason_confirmed=False),
    ])
    unknown_basis = _preview(service, [
        _outflow("loss-b", 8, "2026-11-04", "c" * 64),
    ], layers=[FifoCostLayer("finite", "10.00", 2)],
       open_rate=FifoOpenCostRate("open", "20.00"),
       open_rate_effective_date="2026-11-03")
    assert no_reason["reason_code"] == "FIFO_MOVEMENT_REASON_UNCONFIRMED"
    assert unknown_basis["reason_code"] == "FIFO_OUTFLOW_FINITE_BASIS_UNAVAILABLE"
