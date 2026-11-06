from copy import deepcopy

from services.fifo_planning_quantity_allocation_service import (
    FifoPlanningQuantityAllocationService,
)
from services.planning_sales_mix_cost_snapshot_adapter import (
    PlanningSalesMixCostSnapshotAdapter,
)


def _item(*, open_rate=True):
    basis = {
        "schema_version": 1,
        "status": "AVAILABLE",
        "method": "FIFO_CURRENT_SNAPSHOT",
        "as_of_date": "2026-11-06",
        "cutoff_date": "2026-11-05",
        "revision": "fifo-r7",
        "remaining_status": "AT_CONFIRMED_SNAPSHOT",
        "movement_count": 0,
        "model_only": True,
        "factual_period_profit_eligible": False,
        "layers": [{
            "sequence": 1,
            "kind": "FINITE_LAYER",
            "quantity": 1,
            "unit_cost_rub": "100.00",
            "effective_date": "2026-11-05",
        }],
        "open_rate": ({
            "unit_cost_rub": "120.00",
            "effective_date": "2026-11-06",
        } if open_rate else None),
    }
    return {
        "row_id": "sku-1",
        "identity": {"sku": "sku-1"},
        "inputs": {"cost": "100.00"},
        "provenance": {"cost": "fifo_next_unit_cost"},
        "sources": {"completeness": {"cost": {
            "method": "FIFO_FINITE_LAYER",
            "revision": "fifo-r7",
            "quantity_allocation_basis": basis,
        }}},
    }


def _snapshot(item, quantity):
    mix = {
        "period_label": "01.10.2026 - 31.10.2026",
        "quantities": {"sku-1": quantity},
    }
    allocation = FifoPlanningQuantityAllocationService().allocate(
        quantity=quantity,
        basis=item["sources"]["completeness"]["cost"]["quantity_allocation_basis"],
    )
    projection = {
        "error": False,
        "rows": [{"row_id": "sku-1", "cost_allocation": allocation}],
        "excluded_rows": [],
    }
    adapter = PlanningSalesMixCostSnapshotAdapter()
    return adapter, mix, adapter.build([item], mix, projection)


def test_snapshot_persists_exact_fifo_split_and_rejects_tampered_allocation():
    item = _item()
    adapter, mix, snapshot = _snapshot(item, 2)

    assert snapshot["status"] == "COMPLETE"
    row = snapshot["rows"][0]
    assert row["source_revision"] == "fifo-r7"
    assert row["total_cost_rub"] == "220.00"
    assert [(line["quantity"], line["unit_cost_rub"]) for line in row["lines"]] == [
        (1, "100.00"), (1, "120.00"),
    ]
    assert adapter.normalize(snapshot, [item], mix) == snapshot

    tampered = deepcopy(snapshot)
    tampered["rows"][0]["lines"][0]["unit_cost_rub"] = "101.00"
    tampered["rows"][0]["lines"][0]["total_cost_rub"] = "101.00"
    tampered["rows"][0]["total_cost_rub"] = "221.00"
    tampered["rows"][0]["known_cost_rub"] = "221.00"
    assert adapter.normalize(tampered, [item], mix) is None


def test_snapshot_marks_fifo_quantity_exhaustion_partial_and_keeps_known_cost():
    item = _item(open_rate=False)
    adapter, mix, snapshot = _snapshot(item, 2)

    assert snapshot["status"] == "PARTIAL"
    row = snapshot["rows"][0]
    assert row["status"] == "PARTIAL"
    assert row["allocated_quantity"] == 1
    assert row["total_cost_rub"] is None
    assert row["known_cost_rub"] == "100.00"
    assert row["reason_code"] == "FIFO_PLANNING_CONFIRMED_QUANTITY_EXHAUSTED"
    assert adapter.normalize(snapshot, [item], mix) == snapshot


def test_snapshot_rejects_quantity_or_fifo_revision_mismatch():
    item = _item()
    adapter, mix, snapshot = _snapshot(item, 2)

    stale_mix = deepcopy(mix)
    stale_mix["quantities"]["sku-1"] = 1
    assert adapter.normalize(snapshot, [item], stale_mix) is None

    changed_item = deepcopy(item)
    changed_item["sources"]["completeness"]["cost"][
        "quantity_allocation_basis"
    ]["revision"] = "fifo-r8"
    assert adapter.normalize(snapshot, [changed_item], mix) is None
