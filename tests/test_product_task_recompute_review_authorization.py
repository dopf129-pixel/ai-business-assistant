from copy import deepcopy

from product_task_recompute_review_authorization import (
    build_recompute_review_authorization,
)


def _eligibility(**values):
    result = {
        "status": "PRODUCT_DECISION_RECOMPUTE_REVIEW_ELIGIBLE",
        "recompute_eligibility_id": "recompute-review-eligibility:freshness-state-promotion:draft-1:hook-2:abc123",
        "freshness_promotion_id": "freshness-state-promotion:draft-1:hook-2:abc123",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "source_freshness_proven": True,
        "recompute_review_eligible": True,
        "recompute_review_required": True,
        "recompute_allowed": False,
        "recompute_started": False,
        "eligible_evidence": {
            "sales_source_recorded_at": "2026-08-29T13:00:00+00:00",
            "stock_source_recorded_at": "2026-08-29T13:01:00+00:00",
        },
        "eligible_evidence_count": 2,
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


def test_authorize_grants_recompute_permission_without_starting_recompute():
    source = _eligibility()
    before = deepcopy(source)
    result = build_recompute_review_authorization(source, " authorize ")
    assert result["status"] == "PRODUCT_DECISION_RECOMPUTE_REVIEW_AUTHORIZED"
    assert result["decision"] == "AUTHORIZE"
    assert result["recompute_authorized"] is True
    assert result["recompute_rejected"] is False
    assert result["recompute_allowed"] is True
    assert result["recompute_started"] is False
    assert result["product_decision_recomputed"] is False
    assert result["product_decision_mutated"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before


def test_reject_keeps_recompute_disallowed():
    result = build_recompute_review_authorization(_eligibility(), "REJECT")
    assert result["status"] == "PRODUCT_DECISION_RECOMPUTE_REVIEW_REJECTED"
    assert result["recompute_authorized"] is False
    assert result["recompute_rejected"] is True
    assert result["recompute_allowed"] is False
    assert result["recompute_started"] is False


def test_invalid_decision_is_blocked():
    result = build_recompute_review_authorization(_eligibility(), "YES")
    assert result["code"] == "RECOMPUTE_AUTHORIZATION_DECISION_INVALID"
    assert result["recompute_allowed"] is False


def test_lineage_mismatch_is_blocked():
    result = build_recompute_review_authorization(
        _eligibility(recompute_eligibility_id="forged"), "AUTHORIZE"
    )
    assert result["code"] == "RECOMPUTE_ELIGIBILITY_ID_MISMATCH"


def test_invalid_eligibility_status_is_blocked():
    result = build_recompute_review_authorization(
        _eligibility(status="OTHER"), "AUTHORIZE"
    )
    assert result["code"] == "RECOMPUTE_ELIGIBILITY_STATUS_INVALID"


def test_unproven_freshness_is_blocked():
    result = build_recompute_review_authorization(
        _eligibility(source_freshness_proven=False), "AUTHORIZE"
    )
    assert result["code"] == "SOURCE_FRESHNESS_NOT_PROVEN"


def test_preexisting_recompute_permission_is_blocked():
    result = build_recompute_review_authorization(
        _eligibility(recompute_allowed=True), "AUTHORIZE"
    )
    assert result["code"] == "RECOMPUTE_AUTHORIZATION_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = build_recompute_review_authorization(
        _eligibility(execution_ready=True), "AUTHORIZE"
    )
    assert result["code"] == "RECOMPUTE_AUTHORIZATION_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_evidence_is_blocked():
    evidence = deepcopy(_eligibility()["eligible_evidence"])
    evidence["decision_type"] = "CHANGE_PRICE"
    result = build_recompute_review_authorization(
        _eligibility(eligible_evidence=evidence, eligible_evidence_count=3),
        "AUTHORIZE",
    )
    assert result["code"] == "ELIGIBLE_EVIDENCE_UNSAFE"


def test_evidence_count_mismatch_is_blocked():
    result = build_recompute_review_authorization(
        _eligibility(eligible_evidence_count=1), "AUTHORIZE"
    )
    assert result["code"] == "ELIGIBLE_EVIDENCE_COUNT_MISMATCH"


def test_missing_context_is_blocked():
    result = build_recompute_review_authorization(
        _eligibility(draft_id=""), "AUTHORIZE"
    )
    assert result["code"] == "RECOMPUTE_AUTHORIZATION_CONTEXT_REQUIRED"
