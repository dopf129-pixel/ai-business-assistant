from services.planning_extended_scenario_adapter import PlanningExtendedScenarioAdapter


def _extended():
    return {
        "schema_version": 1,
        "calculation_mode": "STRICT_RETAINED_COHORT",
        "expense_snapshot_ref": "a" * 64,
        "quantity_evidence_ref": "b" * 64,
        "expense_policy_revision": "unit-economics-v1",
        "included_component_keys": [],
        "excluded_component_statuses": {},
        "numerator_and_denominator_basis": {
            "numerator": "STRICT_COHORT_LOSS_RUB",
            "denominator": "RETAINED_UNITS_EXACT_COHORT",
        },
        "source_completeness": "COMPLETE",
        "assumed_inputs": [],
        "scope": {
            "scope_kind": "EXPERIMENT_PHASE_WINDOW",
            "from_date": "2026-10-01", "to_date": "2026-10-07",
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
        },
        "denominator_units": 100,
        "components": [],
    }


def _strict_evidence():
    return {
        "error": False,
        "status": "COMPLETE",
        "identity": {
            "owner_id": "owner-1", "store_id": "store-a",
            "product_id": "product-1", "offer_id": "offer-1",
            "sku": "sku-1", "sale_schema": "FBO",
        },
        "fees": {
            "status": "COMPLETE", "cohort_matches": True,
            "additional_exact_cohort_rub": "300.00",
            "return_id": "must-not-persist",
        },
        "quantity": {
            "status": "COMPLETE", "cohort_matches": True,
            "delivered_units": 110,
            "confirmed_returned_units_from_deliveries": 10,
            "retained_units": 100,
        },
        "inventory": {
            "status": "COMPLETE", "disposition_units": 10,
            "inventory_loss_cogs_rub": "60.00",
            "compensation_deduction_rub": "10.00",
            "raw_payload": {"supply_id": "must-not-persist"},
        },
        "strict_retained_cohort_loss": {
            "status": "AVAILABLE", "model_scope": "STRICT_RETAINED_COHORT",
            "denominator_kind": "RETAINED_UNITS_EXACT_COHORT",
            "denominator_units": 100, "fee_loss_pool_rub": "300.00",
            "loss_pool_rub": "350.00", "loss_per_retained_unit_rub": "3.50",
        },
        "read_only": True,
        "executed": False,
        "raw_response": {"token": "must-not-persist"},
    }


def test_schema_v1_extended_contract_is_bounded_and_preserved_exactly():
    source = _extended()

    projected = PlanningExtendedScenarioAdapter.project_extended(source)

    assert projected == source
    assert projected is not source
    assert PlanningExtendedScenarioAdapter.project_extended({**source, "headers": {}}) is None


def test_strict_evidence_projection_keeps_canonical_proof_and_drops_raw_identifiers():
    expected_identity = _strict_evidence()["identity"]

    projected = PlanningExtendedScenarioAdapter.project_strict_evidence(
        _strict_evidence(), expected_identity,
    )

    assert projected is not None
    assert projected["fees"] == {
        "status": "COMPLETE", "cohort_matches": True,
        "additional_exact_cohort_rub": "300.00",
    }
    assert "return_id" not in repr(projected)
    assert "supply_id" not in repr(projected)
    assert "raw_response" not in repr(projected)
    assert PlanningExtendedScenarioAdapter.project_strict_evidence(
        _strict_evidence(), {**expected_identity, "sku": "other-sku"},
    ) is None
