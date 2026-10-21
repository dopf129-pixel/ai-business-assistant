from copy import deepcopy

from services.planning_cross_docking_adapter import PlanningCrossDockingAdapter


def _evidence():
    return {
        "evidence_complete": True,
        "status": "SKU_SUPPLY_PERIOD_AVERAGE", "reason": None,
        "method": "sku_accrual_cost_per_delivered_crossdock_unit",
        "amount_per_unit": "12.00", "applicable_to_sku": True,
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "expense_total": "1200.00", "expense_by_sku": "1200.00",
        "supplied_units_sku": 100, "supplied_units_store": 100,
        "days_complete": 56, "days_expected": 56,
        "date_from": "2026-08-24", "date_to": "2026-10-18",
        "as_of": "2026-10-19T12:00:00Z", "timezone": "Europe/Moscow",
        "financial_date_basis": "ACCRUAL_DATE",
        "supply_date_basis": "COMPLETED_SINGLE_CROSSDOCK_ORDER_STATE_UPDATED_DATE",
        "model_version": 1,
    }


def test_source_projection_keeps_safe_formula_evidence_and_drops_external_ids():
    raw = {
        "evidence_complete": True,
        "status": "SKU_SUPPLY_PERIOD_AVERAGE",
        "cross_docking_per_unit": "12.00",
        "method": "sku_accrual_cost_per_delivered_crossdock_unit",
        "applicable_to_sku": True,
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "expense_total": "1200.00", "expense_by_sku": "1200.00",
        "supplied_units_sku": 100, "supplied_units_store": 100,
        "days_complete": 56, "days_expected": 56,
        "date_from": "2026-08-24", "date_to": "2026-10-18",
        "as_of": "2026-10-19T12:00:00Z", "timezone": "Europe/Moscow",
        "financial_date_basis": "ACCRUAL_DATE",
        "supply_date_basis": "COMPLETED_SINGLE_CROSSDOCK_ORDER_STATE_UPDATED_DATE",
        "model_version": 1,
        "sku": "private-sku", "supply_id": "private-supply", "raw_response": {"secret": "no"},
    }

    result = PlanningCrossDockingAdapter.project_source(raw)

    assert result["amount_per_unit"] == "12.00"
    assert result["supplied_units_sku"] == 100
    assert result["denominator_kind"] == "DELIVERED_CROSSDOCK_UNITS"
    assert not ({"sku", "supply_id", "raw_response"} & set(result))


def test_legacy_plan_restore_discards_new_cross_docking_values_and_sources():
    item = {
        "inputs": {"price": "500.00", "cross_docking_per_unit": "12.00"},
        "sources": {"cross_docking": _evidence(), "completeness": {"cross_docking": {"complete": True}}},
    }

    inputs, evidence = PlanningCrossDockingAdapter.restore_item(
        {"calculation_version": 1}, item,
    )
    payload = {"calculation_version": 1, "items": [item]}
    adapted = PlanningCrossDockingAdapter.items_for_sales_mix(payload)

    assert "cross_docking_per_unit" not in inputs
    assert evidence == {}
    assert "cross_docking_per_unit" not in adapted[0]["inputs"]
    assert "cross_docking" not in adapted[0]["sources"]


def test_legacy_payload_without_explicit_version_uses_repository_v1_default():
    item = {
        "inputs": {"price": "500.00", "cross_docking_per_unit": "12.00"},
        "sources": {"cross_docking": _evidence()},
    }
    payload = {"items": [item]}

    inputs, evidence = PlanningCrossDockingAdapter.restore_item(payload, item)

    assert inputs == {"price": "500.00"}
    assert evidence == {}
    assert PlanningCrossDockingAdapter.supports(payload, 2)
    assert not PlanningCrossDockingAdapter.is_current(payload)
    assert "cross_docking_per_unit" not in PlanningCrossDockingAdapter.items_for_sales_mix(payload)[0]["inputs"]

    schema_only_legacy = {"schema_version": 1, "items": [item]}
    invalid_boolean_schema = {"schema_version": True, "items": [item]}
    assert PlanningCrossDockingAdapter.restore_item(schema_only_legacy, item)[1] == {}
    assert not PlanningCrossDockingAdapter.supports(invalid_boolean_schema, 2)


def test_v2_restore_uses_only_frozen_matching_evidence():
    item = {
        "inputs": {"price": "500.00", "cross_docking_per_unit": "12.00"},
        "sources": {"cross_docking": _evidence()},
    }

    inputs, evidence = PlanningCrossDockingAdapter.restore_item(
        {"calculation_version": 2}, item,
    )
    mismatched = deepcopy(item)
    mismatched["inputs"]["cross_docking_per_unit"] = "13.00"
    rejected = PlanningCrossDockingAdapter.restore_item(
        {"calculation_version": 2}, mismatched,
    )

    assert inputs["cross_docking_per_unit"] == "12.00"
    assert evidence == _evidence()
    assert rejected == (None, None)
    assert PlanningCrossDockingAdapter.supports({"calculation_version": 1}, 2)
    assert not PlanningCrossDockingAdapter.supports({"calculation_version": 1}, 3)
