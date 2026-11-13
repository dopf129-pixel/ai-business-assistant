from datetime import datetime, timezone

import pytest

from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_supply_acceptance_reconciliation_service import (
    FifoCostSupplyAcceptanceReconciliationService,
)


SKU = "3921245627"


def _snapshot(acts, *, minute, sku=SKU, supply_id=2001):
    summaries = []
    product_acts = []
    for act_id, quantity in acts:
        summaries.append({
            "type": "ACCEPTANCE",
            "act_state": "ACCEPTED",
            "act_id": act_id,
            "summary": {"fact_quantity": quantity, "unidentified_quantity": 0},
        })
        product_acts.append({
            "type": "ACCEPTANCE",
            "act_id": act_id,
            "items": [{
                "sku_info": {"sku": int(sku)},
                "fact_quantity": quantity,
                "unidentified_quantity": 0,
            }],
        })
    return FifoCostSourceNormalizer().normalize_supply_act_snapshot(
        {"supply_acts": product_acts},
        {"supplies_acts": [{
            "supply_id": supply_id,
            "is_agreement_completed": True,
            "supply_acts": summaries,
        }]},
        store_id="store-a",
        expected_supply_id=supply_id,
        captured_at=datetime(2026, 11, 8, 12, minute, tzinfo=timezone.utc),
        products_complete=True,
        summary_complete=True,
    )


def _partial_snapshot(*, minute, supply_id=2001):
    return FifoCostSourceNormalizer().normalize_supply_act_snapshot(
        {"supply_acts": []},
        {"supplies_acts": [{
            "supply_id": supply_id,
            "is_agreement_completed": True,
            "supply_acts": [],
        }]},
        store_id="store-a",
        expected_supply_id=supply_id,
        captured_at=datetime(2026, 11, 8, 12, minute, tzinfo=timezone.utc),
        products_complete=False,
        summary_complete=True,
    )


@pytest.fixture
def service():
    return FifoCostSupplyAcceptanceReconciliationService()


def test_cumulative_40_70_100_uses_latest_total_instead_of_summing(service):
    result = service.reconcile(
        snapshots=[
            _snapshot([(7001, 40)], minute=1),
            _snapshot([(7001, 70)], minute=2),
            _snapshot([(7001, 100)], minute=3),
        ],
        target_sku=SKU,
        declared_quantity=100,
    )

    assert result.status == "COMPLETE"
    assert result.accepted_quantity == 100
    assert result.candidate_quantity == 100
    assert result.unaccepted_quantity is None
    assert result.act_count == 1
    assert result.required_action == "NONE"


def test_repeated_stale_70_snapshot_after_100_does_not_reverse_latest_total(service):
    result = service.reconcile(
        snapshots=[
            _snapshot([(7001, 40)], minute=1),
            _snapshot([(7001, 70)], minute=2),
            _snapshot([(7001, 100)], minute=3),
            _snapshot([(7001, 70)], minute=4),
        ],
        target_sku=SKU,
        declared_quantity=100,
    )

    assert result.status == "COMPLETE"
    assert result.accepted_quantity == 100
    assert result.candidate_quantity == 100


def test_repeated_act_representation_across_pages_is_counted_once(service):
    repeated = _snapshot([(7001, 40), (7001, 40)], minute=1)
    assert repeated.status == "COMPLETE"

    result = service.reconcile(
        snapshots=[repeated], target_sku=SKU, declared_quantity=100,
    )

    assert result.status == "PARTIALLY_ACCEPTED"
    assert result.accepted_quantity == 40
    assert result.act_count == 1
    assert result.unaccepted_quantity == 60


def test_two_distinct_acceptance_acts_sum_but_duplicate_snapshots_do_not(service):
    two_acts = _snapshot([(7001, 40), (7002, 60)], minute=1)
    repeated_snapshot = _snapshot([(7001, 40), (7002, 60)], minute=2)

    result = service.reconcile(
        snapshots=[two_acts, repeated_snapshot],
        target_sku=SKU,
        declared_quantity=100,
    )

    assert result.status == "COMPLETE"
    assert result.accepted_quantity == 100
    assert result.act_count == 2
    assert result.act_reference_digests == tuple(sorted(two_acts.act_refs))


def test_final_accepted_shortage_is_discrepancy_and_requires_confirmed_movement(service):
    result = service.reconcile(
        snapshots=[_snapshot([(7001, 98)], minute=1)],
        target_sku=SKU,
        declared_quantity=100,
        final_state_confirmed=True,
    )

    assert result.status == "DISCREPANCY"
    assert result.accepted_quantity == 98
    assert result.unaccepted_quantity == 2
    assert result.required_action == "CONFIRM_SHORTAGE_MOVEMENT"
    assert result.issue_codes == ("FINAL_ACCEPTED_BELOW_DECLARED",)


def test_nonfinal_accepted_shortage_is_pending_not_inventory_discrepancy(service):
    result = service.reconcile(
        snapshots=[_snapshot([(7001, 98)], minute=1)],
        target_sku=SKU,
        declared_quantity=100,
        final_state_confirmed=False,
    )

    assert result.status == "PARTIALLY_ACCEPTED"
    assert result.accepted_quantity == 98
    assert result.unaccepted_quantity == 2
    assert result.required_action == "WAIT_FOR_FINAL_ACCEPTANCE"
    assert result.issue_codes == ()


def test_newer_partial_act_read_keeps_last_quantity_but_removes_complete_claim(service):
    result = service.reconcile(
        snapshots=[
            _snapshot([(7001, 100)], minute=1),
            _partial_snapshot(minute=2),
        ],
        target_sku=SKU,
        declared_quantity=100,
        final_state_confirmed=True,
    )

    assert result.status == "PARTIAL"
    assert result.accepted_quantity == 100
    assert result.candidate_quantity is None
    assert result.unaccepted_quantity is None
    assert result.required_action == "REFRESH_SOURCE"
    assert "SUPPLY_SOURCE_INCOMPLETE" in result.issue_codes


def test_downward_acceptance_correction_preserves_old_value_and_requires_review(service):
    result = service.reconcile(
        snapshots=[
            _snapshot([(7001, 100)], minute=1),
            _snapshot([(7001, 90)], minute=2),
        ],
        target_sku=SKU,
        declared_quantity=100,
        final_state_confirmed=True,
    )

    assert result.status == "CORRECTION_REVIEW_REQUIRED"
    assert result.accepted_quantity == 100
    assert result.candidate_quantity == 90
    assert result.unaccepted_quantity is None
    assert result.required_action == "CONFIRM_DOCUMENTED_CORRECTION"
    assert result.issue_codes == ("ACCEPTED_QUANTITY_DECREASE_REQUIRES_REVIEW",)


def test_other_sku_act_is_conflict_with_no_accepted_quantity(service):
    result = service.reconcile(
        snapshots=[_snapshot([(7001, 100)], minute=1, sku="3921245628")],
        target_sku=SKU,
        declared_quantity=100,
    )

    assert result.status == "CONFLICT"
    assert result.accepted_quantity is None
    assert result.required_action == "REVIEW_SKU_SPLIT"
    assert result.issue_codes == ("SUPPLY_PRODUCT_IDENTITY_CONFLICT",)


def test_accepted_above_owner_declaration_is_conflict(service):
    result = service.reconcile(
        snapshots=[_snapshot([(7001, 101)], minute=1)],
        target_sku=SKU,
        declared_quantity=100,
    )

    assert result.status == "CONFLICT"
    assert result.accepted_quantity is None
    assert result.candidate_quantity == 101
    assert result.required_action == "REVIEW_QUANTITIES"
    assert result.issue_codes == ("ACCEPTED_EXCEEDS_DECLARED",)


def test_competing_source_versions_at_same_capture_time_are_ambiguous(service):
    result = service.reconcile(
        snapshots=[
            _snapshot([(7001, 40)], minute=1),
            _snapshot([(7001, 70)], minute=1),
        ],
        target_sku=SKU,
        declared_quantity=100,
    )

    assert result.status == "CONFLICT"
    assert result.accepted_quantity is None
    assert result.required_action == "REVIEW_SOURCE_ORDER"
    assert result.issue_codes == ("SUPPLY_OBSERVATION_ORDER_AMBIGUOUS",)


@pytest.mark.parametrize("declared", [True, -1, 1_000_001, 1.0])
def test_invalid_declared_quantity_is_rejected(service, declared):
    result = service.reconcile(
        snapshots=[_snapshot([(7001, 1)], minute=1)],
        target_sku=SKU,
        declared_quantity=declared,
    )

    assert result.status == "INVALID"
    assert result.accepted_quantity is None
