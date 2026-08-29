from copy import deepcopy

from product_task_freshness_proven_recompute_eligibility import (
    build_freshness_proven_recompute_eligibility,
)


def _promotion(**values):
    result = {
        "status": "SOURCE_FRESHNESS_PROVEN",
        "freshness_promotion_id": "freshness-state-promotion:draft-1:hook-2:abc123",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "source_freshness_proven": True,
        "promotion_ready": True,
        "proven_evidence": {
            "sales_source_recorded_at": "2026-08-29T13:00:00+00:00",
            "stock_source_recorded_at": "2026-08-29T13:01:00+00:00",
        },
        "proven_evidence_count": 2,
        "persistent": False,
        "task_draft_mutated": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_proven_freshness_becomes_recompute_review_eligible_without_recompute():
    source = _promotion()
    before = deepcopy(source)
    result = build_freshness_proven_recompute_eligibility(source)
    assert result["status"] == "PRODUCT_DECISION_RECOMPUTE_REVIEW_ELIGIBLE"
    assert result["recompute_review_eligible"] is True
    assert result["recompute_review_required"] is True
    assert result["recompute_allowed"] is False
    assert result["recompute_started"] is False
    assert result["product_decision_recomputed"] is False
    assert result["product_decision_mutated"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before


def test_invalid_promotion_status_is_blocked():
    result = build_freshness_proven_recompute_eligibility(_promotion(status="OTHER"))
    assert result["code"] == "SOURCE_FRESHNESS_STATUS_INVALID"


def test_unproven_freshness_is_blocked():
    result = build_freshness_proven_recompute_eligibility(
        _promotion(source_freshness_proven=False)
    )
    assert result["code"] == "SOURCE_FRESHNESS_NOT_PROVEN"


def test_not_ready_promotion_is_blocked():
    result = build_freshness_proven_recompute_eligibility(
        _promotion(promotion_ready=False)
    )
    assert result["code"] == "FRESHNESS_PROMOTION_NOT_READY"


def test_persistence_boundary_violation_is_blocked():
    result = build_freshness_proven_recompute_eligibility(_promotion(persistent=True))
    assert result["code"] == "RECOMPUTE_ELIGIBILITY_MUTATION_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = build_freshness_proven_recompute_eligibility(_promotion(execution_ready=True))
    assert result["code"] == "RECOMPUTE_ELIGIBILITY_SAFETY_BOUNDARY_VIOLATION"


def test_product_decision_recompute_boundary_violation_is_blocked():
    result = build_freshness_proven_recompute_eligibility(
        _promotion(product_decision_recomputed=True)
    )
    assert result["code"] == "RECOMPUTE_ELIGIBILITY_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_proven_evidence_is_blocked():
    evidence = deepcopy(_promotion()["proven_evidence"])
    evidence["decision_type"] = "CHANGE_PRICE"
    result = build_freshness_proven_recompute_eligibility(
        _promotion(proven_evidence=evidence, proven_evidence_count=3)
    )
    assert result["code"] == "PROVEN_EVIDENCE_UNSAFE"


def test_evidence_count_mismatch_is_blocked():
    result = build_freshness_proven_recompute_eligibility(
        _promotion(proven_evidence_count=1)
    )
    assert result["code"] == "PROVEN_EVIDENCE_COUNT_MISMATCH"


def test_missing_context_is_blocked():
    result = build_freshness_proven_recompute_eligibility(_promotion(draft_id=""))
    assert result["code"] == "RECOMPUTE_ELIGIBILITY_CONTEXT_REQUIRED"
