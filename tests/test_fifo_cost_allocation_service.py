from decimal import Decimal

import pytest

from services import fifo_cost_allocation_service as fifo_allocation_module
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


@pytest.fixture
def service():
    return FifoCostAllocationService()


def _allocate(service, *, layers=(), events=(), open_rate=None, **kwargs):
    return service.allocate(
        layers=layers,
        events=events,
        anchor_status=kwargs.pop("anchor_status", "CONFIRMED"),
        cutoff_status=kwargs.pop("cutoff_status", "RECONCILED"),
        event_order_status=kwargs.pop("event_order_status", "PROVEN"),
        source_completeness=kwargs.pop("source_completeness", "COMPLETE"),
        open_rate=open_rate,
        **kwargs,
    )


def test_n01_distributes_multiple_sales_over_old_finite_layer_and_unknown_new_rate(service):
    result = _allocate(
        service,
        layers=[FifoCostLayer("old", "20.00", 450)],
        open_rate=FifoOpenCostRate("new-rate", "25.00"),
        events=[
            FifoSaleEvent("sale-1", 100),
            FifoSaleEvent("sale-2", 350),
            FifoSaleEvent("sale-3", 40),
        ],
    )

    assert result.complete is True
    assert [row.total_cost_rub for row in result.sale_allocations] == [
        Decimal("2000.00"), Decimal("7000.00"), Decimal("1000.00")
    ]
    assert result.total_cogs_rub == Decimal("10000.00")
    assert result.remaining_confirmed_units == 0
    assert result.total_available_units is None
    assert result.next_unit_cost_rub == Decimal("25.00")
    assert result.next_unit_cost_status == "RATE_ONLY_QUANTITY_UNKNOWN"
    assert result.sale_allocations[0].lines[0].quantity == 100
    assert result.sale_allocations[1].lines[0].quantity == 350
    assert result.sale_allocations[2].lines[0].layer_id == "new-rate"


def test_n02_confirmed_zero_uses_next_rate_but_unknown_anchor_fails_closed(service):
    complete = _allocate(
        service,
        anchor_status="CONFIRMED_ZERO",
        open_rate=FifoOpenCostRate("current-rate", "22.50"),
        events=[FifoSaleEvent("first-sale", 1)],
    )
    unknown = _allocate(
        service,
        anchor_status="UNKNOWN",
        open_rate=FifoOpenCostRate("current-rate", "22.50"),
        events=[FifoSaleEvent("first-sale", 1)],
    )

    assert complete.complete is True
    assert complete.total_cogs_rub == Decimal("22.50")
    assert complete.total_available_units is None
    assert unknown.complete is False
    assert unknown.reason_code == "ANCHOR_UNCONFIRMED"
    assert unknown.total_cogs_rub is None
    assert unknown.sale_allocations == ()


def test_n03_preserves_older_cost_layer_and_splits_one_sale_across_three_rates(service):
    result = _allocate(
        service,
        layers=[
            FifoCostLayer("oldest", "20.00", 150),
            FifoCostLayer("previous", "25.00", 200),
        ],
        open_rate=FifoOpenCostRate("current", "30.00"),
        events=[FifoSaleEvent("sale", 400)],
    )

    allocation = result.sale_allocations[0]
    assert [(line.layer_id, line.quantity, line.unit_cost_rub) for line in allocation.lines] == [
        ("oldest", 150, Decimal("20.00")),
        ("previous", 200, Decimal("25.00")),
        ("current", 50, Decimal("30.00")),
    ]
    assert allocation.total_cost_rub == Decimal("9500.00")
    assert result.total_cogs_rub == Decimal("9500.00")


def test_n08_exact_return_basis_restores_inventory_value_without_rewriting_sale_cogs(service):
    result = _allocate(
        service,
        layers=[
            FifoCostLayer("layer-20", "20.00", 3),
            FifoCostLayer("layer-25", "25.00", 2),
        ],
        events=[
            FifoSaleEvent("sale", 5),
            FifoRestockEvent(
                "return",
                5,
                (
                    FifoRestoreSlice("sale", "layer-20", 3),
                    FifoRestoreSlice("sale", "layer-25", 2),
                ),
            ),
        ],
    )

    assert result.total_cogs_rub == Decimal("110.00")
    assert result.inventory_restored_value_rub == Decimal("110.00")
    assert result.restored_units == 5
    assert result.remaining_confirmed_units == 5
    assert result.total_available_units == 5
    assert result.next_unit_cost_rub == Decimal("20.00")


def test_fc_review_same_rate_lines_keep_distinct_return_basis_until_full_return(service):
    result = _allocate(
        service,
        anchor_status="CONFIRMED_ZERO",
        events=[
            FifoRateBoundaryEvent(
                "rate-start", "rate-1", "10.00", None, None, None, "a" * 64,
            ),
            FifoSaleEvent("sale-1", 1),
            FifoSaleEvent("sale-2", 1),
            FifoRestockEvent("return-1", 1, (
                FifoRestoreSlice("sale-1", "rate-1", 1, 1),
            )),
            FifoRestockEvent("return-2", 1, (
                FifoRestoreSlice("sale-2", "rate-1", 1, 1),
            )),
            FifoRateBoundaryEvent(
                "rate-close", "rate-2", "20.00", "rate-1", 0, 2, "b" * 64,
            ),
            FifoSaleEvent("sale-3", 2),
            FifoRestockEvent("return-3", 2, (
                FifoRestoreSlice("sale-3", "rate-1", 1, 1),
                FifoRestoreSlice("sale-3", "rate-1", 1, 2),
            )),
        ],
    )

    assert result.complete is True
    sale_lines = result.sale_allocations[-1].lines
    assert len(sale_lines) == 2
    assert [line.rate_change_id for line in sale_lines] == ["rate-1", "rate-1"]
    assert [line.quantity for line in sale_lines] == [1, 1]
    assert result.restored_units == 4
    assert result.remaining_confirmed_units == 2


def test_fc19_non_sale_outflow_reduces_fifo_stock_and_is_valued_outside_sales_cogs(service):
    result = _allocate(
        service,
        layers=[FifoCostLayer("old", "20.00", 3), FifoCostLayer("new", "25.00", 5)],
        events=[FifoSaleEvent("sale", 4), FifoOutflowEvent("loss", 2, "HOME_SHORTAGE")],
    )
    assert result.complete is True
    assert result.total_cogs_rub == Decimal("85.00")
    assert result.non_sale_outflow_value_rub == Decimal("50.00")
    assert result.outflow_allocations[0].estimated_value_rub == Decimal("50.00")
    assert [(line.layer_id, line.quantity) for line in result.outflow_allocations[0].lines] == [("new", 2)]
    assert result.remaining_confirmed_units == 2


def test_fc19_outflow_never_uses_unknown_open_rate_quantity(service):
    result = _allocate(
        service,
        layers=[FifoCostLayer("old", "20.00", 1)],
        open_rate=FifoOpenCostRate("rate", "25.00"),
        events=[FifoOutflowEvent("loss", 2, "OZON_DISPOSAL")],
    )
    assert result.complete is False
    assert result.reason_code == "FIFO_OUTFLOW_FINITE_BASIS_UNAVAILABLE"
    assert result.non_sale_outflow_value_rub is None


def test_unknown_partial_return_basis_and_duplicate_restoration_do_not_publish_partial_totals(service):
    missing_basis = _allocate(
        service,
        layers=[FifoCostLayer("layer", "20.00", 5)],
        events=[FifoSaleEvent("sale", 5), FifoRestockEvent("return", 1, ())],
    )
    replayed_return = FifoRestockEvent(
        "return-once", 1, (FifoRestoreSlice("sale", "layer", 1),)
    )
    duplicate_return = _allocate(
        service,
        layers=[FifoCostLayer("layer", "20.00", 5)],
        events=[
            FifoSaleEvent("sale", 5),
            replayed_return,
            replayed_return,
        ],
    )
    excessive_return = _allocate(
        service,
        layers=[FifoCostLayer("layer", "20.00", 5)],
        events=[
            FifoSaleEvent("sale", 5),
            FifoRestockEvent("return", 6, (FifoRestoreSlice("sale", "layer", 6),)),
        ],
    )

    assert missing_basis.complete is False
    assert missing_basis.reason_code == "FIFO_RETURN_BASIS_MISSING"
    assert missing_basis.total_cogs_rub is None
    assert duplicate_return.complete is False
    assert duplicate_return.reason_code == "FIFO_EVENT_ID_DUPLICATE"
    assert duplicate_return.sale_allocations == ()
    assert excessive_return.reason_code == "FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN"


def test_fc_review_mixed_return_basis_formats_share_one_origin_quantity_limit(service):
    result = _allocate(
        service,
        layers=[FifoCostLayer("layer", "20.00", 1)],
        events=[
            FifoSaleEvent("sale", 1),
            FifoRestockEvent(
                "return-legacy", 1,
                (FifoRestoreSlice("sale", "layer", 1),),
            ),
            FifoRestockEvent(
                "return-line", 1,
                (FifoRestoreSlice("sale", "layer", 1, 1),),
            ),
        ],
    )

    assert result.complete is False
    assert result.reason_code == "FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN"
    assert result.total_cogs_rub is None
    assert result.sale_allocations == ()


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"cutoff_status": "UNRECONCILED"}, "INVENTORY_CUTOFF_UNRECONCILED"),
        ({"event_order_status": "UNKNOWN"}, "EVENT_ORDER_UNRESOLVED"),
        ({"source_completeness": "PARTIAL"}, "FIFO_SOURCE_INCOMPLETE"),
    ],
)
def test_cutoff_order_and_source_gates_fail_closed(service, overrides, expected_reason):
    result = _allocate(
        service,
        layers=[FifoCostLayer("old", "20.00", 2)],
        events=[FifoSaleEvent("sale", 1)],
        **overrides,
    )

    assert result.complete is False
    assert result.reason_code == expected_reason
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


def test_default_cutoff_gate_does_not_publish_even_a_numerically_valid_allocation(service):
    result = service.allocate(
        layers=[FifoCostLayer("old", "20.00", 2)],
        events=[FifoSaleEvent("sale", 1)],
        anchor_status="CONFIRMED",
    )

    assert result.complete is False
    assert result.reason_code == "INVENTORY_CUTOFF_UNRECONCILED"
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


def test_layer_input_limit_is_bounded_and_returns_no_partial_projection(service):
    def layers():
        for index in range(100_001):
            yield FifoCostLayer(f"layer-{index}", "1.00", 1)

    result = _allocate(
        service,
        layers=layers(),
        anchor_status="CONFIRMED",
    )

    assert result.complete is False
    assert result.reason_code == "FIFO_LAYER_INPUT_LIMIT"
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


def test_event_replay_limit_is_bounded_and_returns_no_partial_projection(service):
    def events():
        for index in range(100_001):
            yield FifoSaleEvent(f"sale-{index}", 1)

    result = _allocate(
        service,
        anchor_status="CONFIRMED_ZERO",
        open_rate=FifoOpenCostRate("rate", "1.00"),
        events=events(),
    )

    assert result.complete is False
    assert result.reason_code == "FIFO_REPLAY_EVENT_LIMIT"
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


def test_broken_input_iterator_fails_closed_without_partial_projection(service):
    def layers():
        yield FifoCostLayer("old", "20.00", 2)
        raise RuntimeError("synthetic iterator failure")

    result = _allocate(service, layers=layers())

    assert result.complete is False
    assert result.reason_code == "FIFO_LAYER_INPUT_INVALID"
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


def test_allocation_line_work_limit_is_fail_closed(service, monkeypatch):
    monkeypatch.setattr(fifo_allocation_module, "_MAX_REPLAY_ALLOCATION_LINES", 1)

    result = _allocate(
        service,
        layers=[
            FifoCostLayer("old-1", "20.00", 1),
            FifoCostLayer("old-2", "25.00", 1),
        ],
        events=[FifoSaleEvent("sale", 2)],
    )

    assert result.complete is False
    assert result.reason_code == "FIFO_REPLAY_WORK_LIMIT"
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


def test_restore_basis_work_limit_is_checked_before_replay(service, monkeypatch):
    monkeypatch.setattr(fifo_allocation_module, "_MAX_REPLAY_ALLOCATION_LINES", 1)

    result = _allocate(
        service,
        layers=[
            FifoCostLayer("old-1", "20.00", 1),
            FifoCostLayer("old-2", "25.00", 1),
        ],
        events=[
            FifoSaleEvent("sale", 2),
            FifoRestockEvent(
                "return",
                2,
                (
                    FifoRestoreSlice("sale", "old-1", 1),
                    FifoRestoreSlice("sale", "old-2", 1),
                ),
            ),
        ],
    )

    assert result.complete is False
    assert result.reason_code == "FIFO_REPLAY_WORK_LIMIT"
    assert result.sale_allocations == ()
    assert result.total_cogs_rub is None


def test_n21_decimal_total_is_exact_and_replay_order_is_stable(service):
    layers = [FifoCostLayer("one", "1.00", 1), FifoCostLayer("two", "2.00", 2)]
    events = [FifoSaleEvent("sale", 3)]
    first = _allocate(service, layers=layers, events=events)
    second = _allocate(service, layers=layers, events=events)

    assert first.total_cogs_rub == Decimal("5.00")
    assert first.sale_allocations == second.sale_allocations
    assert first.total_cogs_rub == second.total_cogs_rub


@pytest.mark.parametrize("invalid_quantity", [0, -1, 1.5, True, "2"])
def test_invalid_sale_quantities_are_rejected_without_partial_result(service, invalid_quantity):
    result = _allocate(
        service,
        layers=[FifoCostLayer("old", "20.00", 5)],
        events=[FifoSaleEvent("sale", invalid_quantity)],
    )

    assert result.complete is False
    assert result.reason_code == "FIFO_EVENT_INPUT_INVALID"
    assert result.total_cogs_rub is None


@pytest.mark.parametrize("invalid_cost", [-1, "NaN", "Infinity", True, 1.25, float("inf")])
def test_invalid_money_and_float_inputs_fail_closed(service, invalid_cost):
    result = _allocate(
        service,
        layers=[FifoCostLayer("old", invalid_cost, 5)],
        events=[FifoSaleEvent("sale", 1)],
    )

    assert result.complete is False
    assert result.reason_code == "FIFO_LAYER_INPUT_INVALID"
    assert result.total_cogs_rub is None


def test_money_is_rounded_once_at_the_input_boundary_and_insufficient_layers_are_incomplete(service):
    rounded = _allocate(
        service,
        layers=[FifoCostLayer("old", Decimal("1.005"), 2)],
        events=[FifoSaleEvent("sale", 2)],
    )
    insufficient = _allocate(
        service,
        layers=[FifoCostLayer("old", "1.00", 1)],
        events=[FifoSaleEvent("first", 1), FifoSaleEvent("second", 1)],
    )

    assert rounded.total_cogs_rub == Decimal("2.02")
    assert rounded.sale_allocations[0].lines[0].unit_cost_rub == Decimal("1.01")
    assert insufficient.complete is False
    assert insufficient.reason_code == "FIFO_CONFIRMED_QUANTITY_EXHAUSTED"
    assert insufficient.sale_allocations == ()
    assert insufficient.total_cogs_rub is None
