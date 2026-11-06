from decimal import Decimal

from services.fifo_planning_quantity_allocation_service import (
    FifoPlanningQuantityAllocationService,
)


def _basis(layers, open_rate=None, **updates):
    result = {
        "schema_version": 1,
        "status": "AVAILABLE",
        "method": "FIFO_CURRENT_SNAPSHOT",
        "as_of_date": "2026-11-06",
        "cutoff_date": "2026-11-05",
        "revision": "a" * 64,
        "remaining_status": "AT_CONFIRMED_SNAPSHOT",
        "movement_count": 0,
        "model_only": True,
        "factual_period_profit_eligible": False,
        "layers": layers,
        "open_rate": open_rate,
    }
    result.update(updates)
    return result


def _layer(sequence, quantity, cost, *, date="2026-11-05", kind="FINITE_LAYER"):
    return {
        "sequence": sequence,
        "kind": kind,
        "quantity": quantity,
        "unit_cost_rub": cost,
        "effective_date": date,
    }


def test_n01_allocates_the_whole_planned_quantity_without_consuming_the_snapshot():
    service = FifoPlanningQuantityAllocationService()
    basis = _basis(
        [_layer(1, 450, "20.00")],
        {"unit_cost_rub": "25.00", "effective_date": "2026-11-06"},
    )

    first = service.allocate(quantity=490, basis=basis)
    second = service.allocate(quantity=490, basis=basis)

    assert first["status"] == "COMPLETE"
    assert first["total_cost_rub"] == "10000.00"
    assert [(line["quantity"], line["unit_cost_rub"]) for line in first["lines"]] == [
        (450, "20.00"), (40, "25.00"),
    ]
    assert second == first
    assert basis["layers"][0]["quantity"] == 450


def test_n03_uses_reconciled_prior_rate_units_as_finite_layers():
    result = FifoPlanningQuantityAllocationService().allocate(
        quantity=400,
        basis=_basis([
            _layer(1, 150, "20.00"),
            _layer(2, 200, "25.00", date="2026-11-06", kind="RECONCILED_RATE"),
            _layer(3, 70, "30.00", date="2026-11-07", kind="RECONCILED_RATE"),
        ], {"unit_cost_rub": "40.00", "effective_date": "2026-11-08"},
            as_of_date="2026-11-08"),
    )

    assert result["status"] == "COMPLETE"
    assert result["total_cost_rub"] == "9500.00"
    assert [line["quantity"] for line in result["lines"]] == [150, 200, 50]
    assert [line["unit_cost_rub"] for line in result["lines"]] == [
        "20.00", "25.00", "30.00",
    ]


def test_n20_allocates_volume_over_finite_stock_then_active_rate():
    result = FifoPlanningQuantityAllocationService().allocate(
        quantity=100,
        basis=_basis(
            [_layer(1, 80, "20.00")],
            {"unit_cost_rub": "25.00", "effective_date": "2026-11-06"},
        ),
    )

    assert result["total_cost_rub"] == "2100.00"
    assert result["average_cost_rub"] == "21.00"


def test_n21_display_average_never_replaces_exact_total():
    result = FifoPlanningQuantityAllocationService().allocate(
        quantity=3,
        basis=_basis([_layer(1, 1, "1.00"), _layer(2, 2, "2.00")]),
    )

    assert result["total_cost_rub"] == "5.00"
    assert result["average_cost_rub"] == "1.67"
    exact_from_lines = sum(
        (int(line["quantity"]) * Decimal(line["unit_cost_rub"]) for line in result["lines"]),
        Decimal("0.00"),
    )
    assert exact_from_lines == Decimal(result["total_cost_rub"]) == Decimal("5.00")


def test_known_finite_quantity_exhaustion_is_partial_not_a_guessed_average():
    result = FifoPlanningQuantityAllocationService().allocate(
        quantity=5, basis=_basis([_layer(1, 3, "7.50")]),
    )

    assert result["status"] == "PARTIAL"
    assert result["reason_code"] == "FIFO_PLANNING_CONFIRMED_QUANTITY_EXHAUSTED"
    assert result["allocated_quantity"] == 3
    assert result["known_cost_rub"] == "22.50"
    assert result["total_cost_rub"] is None
    assert result["average_cost_rub"] is None


def test_movement_or_uncertain_snapshot_stays_unavailable():
    basis = _basis([_layer(1, 5, "10.00")], movement_count=1)

    result = FifoPlanningQuantityAllocationService().allocate(quantity=2, basis=basis)

    assert result["status"] == "UNAVAILABLE"
    assert result["reason_code"] == "FIFO_PLANNING_BASIS_INCOMPLETE"
    assert result["total_cost_rub"] is None


def test_open_rate_must_follow_finite_layers_and_quantity_is_bounded():
    service = FifoPlanningQuantityAllocationService()
    ambiguous = service.allocate(
        quantity=4,
        basis=_basis(
            [_layer(1, 3, "10.00", date="2026-11-06")],
            {"unit_cost_rub": "20.00", "effective_date": "2026-11-06"},
        ),
    )
    too_large = service.allocate(
        quantity=100_001,
        basis=_basis([_layer(1, 3, "10.00")]),
    )

    assert ambiguous["reason_code"] == "FIFO_PLANNING_OPEN_RATE_ORDER_AMBIGUOUS"
    assert too_large["reason_code"] == "FIFO_PLANNING_QUANTITY_INVALID"


def test_persisted_basis_is_allowlisted_and_rejects_external_identifiers():
    basis = _basis([_layer(1, 3, "10.00")])

    safe = FifoPlanningQuantityAllocationService.normalize_persisted_basis(basis)
    unsafe = FifoPlanningQuantityAllocationService.normalize_persisted_basis({
        **basis,
        "layers": [{**basis["layers"][0], "ozon_sku": "private"}],
    })

    assert safe["status"] == "AVAILABLE"
    assert safe["layers"][0]["sequence"] == 1
    assert unsafe is None
