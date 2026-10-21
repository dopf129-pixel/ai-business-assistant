from copy import deepcopy

from services.planning_cross_docking_adapter import PlanningCrossDockingAdapter


def _evidence():
    return {
        "evidence_complete": True, "rate_available": True,
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
    assert result["rate_available"] is True
    assert result["supplied_units_sku"] == 100
    assert result["denominator_kind"] == "DELIVERED_CROSSDOCK_UNITS"
    assert not ({"sku", "supply_id", "raw_response"} & set(result))


def test_persisted_evidence_can_be_projected_again_without_losing_rate():
    projected = PlanningCrossDockingAdapter.project_source({
        **_evidence(),
        "cross_docking_per_unit": "12.00",
        "rate_available": True,
    })
    item = {
        "inputs": {"cross_docking_per_unit": "12.0"},
        "sources": {"cross_docking": projected},
    }
    inputs, restored = PlanningCrossDockingAdapter.restore_item(
        {"calculation_version": 2}, item,
    )

    displayed = PlanningCrossDockingAdapter.display_source(restored)
    recaptured = PlanningCrossDockingAdapter.project_source(displayed)

    assert inputs["cross_docking_per_unit"] == "12.0"
    assert displayed["rate_available"] is True
    assert displayed["amount_per_unit"] == "12.00"
    assert recaptured["rate_available"] is True
    assert recaptured["amount_per_unit"] == "12.00"
    assert recaptured["model_version"] == 1


def test_runtime_model_version_is_preserved_as_safe_string():
    result = PlanningCrossDockingAdapter.project_source({
        "evidence_complete": True,
        "status": "SKU_SUPPLY_PERIOD_AVERAGE",
        "cross_docking_per_unit": "12.00",
        "method": "sku_accrual_cost_per_delivered_crossdock_unit",
        "applicable_to_sku": True,
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "model_version": "cross_docking_unit_cost_v1",
    })

    assert result["model_version"] == "cross_docking_unit_cost_v1"


def test_complete_window_without_a_rate_is_distinct_and_keeps_no_numeric_cost():
    result = PlanningCrossDockingAdapter.project_source({
        "evidence_complete": True,
        "status": "NO_CROSSDOCK_SUPPLIES",
        "reason": "NO_CROSSDOCK_SUPPLIES",
        "cross_docking_per_unit": None,
        "method": None,
        "applicable_to_sku": False,
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "supplied_units_sku": 0,
        "supplied_units_store": 0,
        "days_complete": 56,
        "days_expected": 56,
    })

    assert result["evidence_complete"] is True
    assert result["rate_available"] is False
    assert result["applicable_to_sku"] is False
    assert result["amount_per_unit"] is None
    assert PlanningCrossDockingAdapter.completeness_projection(result) == {
        "complete": True,
        "rate_available": False,
        "status": "NO_CROSSDOCK_SUPPLIES",
        "reason": "NO_CROSSDOCK_SUPPLIES",
    }

    item = {
        "inputs": {"price": "500.00", "cross_docking_per_unit": None},
        "sources": {"cross_docking": result},
    }
    payload = {"calculation_version": 2}
    inputs, evidence = PlanningCrossDockingAdapter.restore_item(payload, item)
    assert inputs["cross_docking_per_unit"] is None
    assert evidence["evidence_complete"] is True
    assert evidence["rate_available"] is False


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
