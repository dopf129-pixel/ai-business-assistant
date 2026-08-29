from copy import deepcopy

from product_task_freshness_state_promotion import (
    build_freshness_state_promotion,
)


def _verification(**values):
    result = {
        "status": "FRESHNESS_EVIDENCE_DURABLE_PERSISTENCE_VERIFIED",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "verified": True,
        "verified_evidence": {
            "sales_source_recorded_at": "2026-08-29T13:00:00+00:00",
            "stock_source_recorded_at": "2026-08-29T13:01:00+00:00",
        },
        "verified_evidence_count": 2,
        "mismatched_fields": [],
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_verified_readback_promotes_source_freshness_without_mutation():
    source = _verification()
    before = deepcopy(source)
    result = build_freshness_state_promotion(source)
    assert result["status"] == "SOURCE_FRESHNESS_PROVEN"
    assert result["source_freshness_proven"] is True
    assert result["promotion_ready"] is True
    assert result["proven_evidence_count"] == 2
    assert result["persistent"] is False
    assert result["task_draft_mutated"] is False
    assert result["product_decision_recomputed"] is False
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before


def test_promotion_id_changes_when_verified_evidence_changes():
    first = build_freshness_state_promotion(_verification())
    changed_evidence = deepcopy(_verification()["verified_evidence"])
    changed_evidence["stock_source_recorded_at"] = "2026-08-29T13:02:00+00:00"
    second = build_freshness_state_promotion(
        _verification(verified_evidence=changed_evidence)
    )
    assert first["freshness_promotion_id"] != second["freshness_promotion_id"]


def test_invalid_verification_status_is_blocked():
    result = build_freshness_state_promotion(_verification(status="OTHER"))
    assert result["code"] == "DURABLE_VERIFICATION_STATUS_INVALID"
    assert result["source_freshness_proven"] is False


def test_unverified_readback_is_blocked():
    result = build_freshness_state_promotion(_verification(verified=False))
    assert result["code"] == "DURABLE_VERIFICATION_NOT_CONFIRMED"


def test_mismatch_presence_is_blocked():
    result = build_freshness_state_promotion(
        _verification(mismatched_fields=["stock_source_recorded_at"])
    )
    assert result["code"] == "DURABLE_VERIFICATION_MISMATCH_PRESENT"


def test_execution_boundary_violation_is_blocked():
    result = build_freshness_state_promotion(_verification(execution_ready=True))
    assert result["code"] == "FRESHNESS_PROMOTION_SAFETY_BOUNDARY_VIOLATION"


def test_product_decision_mutation_boundary_violation_is_blocked():
    result = build_freshness_state_promotion(
        _verification(product_decision_mutated=True)
    )
    assert result["code"] == "FRESHNESS_PROMOTION_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_verified_evidence_is_blocked():
    evidence = deepcopy(_verification()["verified_evidence"])
    evidence["decision_type"] = "CHANGE_PRICE"
    result = build_freshness_state_promotion(
        _verification(verified_evidence=evidence, verified_evidence_count=3)
    )
    assert result["code"] == "VERIFIED_EVIDENCE_UNSAFE"


def test_verified_evidence_count_mismatch_is_blocked():
    result = build_freshness_state_promotion(
        _verification(verified_evidence_count=1)
    )
    assert result["code"] == "VERIFIED_EVIDENCE_COUNT_MISMATCH"


def test_missing_context_is_blocked():
    result = build_freshness_state_promotion(_verification(draft_id=""))
    assert result["code"] == "FRESHNESS_PROMOTION_CONTEXT_REQUIRED"
