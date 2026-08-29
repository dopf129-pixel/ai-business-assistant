from copy import deepcopy

from product_decision_persistence_eligibility import (
    build_product_decision_persistence_eligibility,
)


def _review(**values):
    result = {
        "status": "PRODUCT_DECISION_PREVIEW_REVIEW_ACCEPTED",
        "decision_preview_review_id": "product-decision-preview-review:product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "decision_preview_delta_id": "product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "recompute_preview_id": "product-decision-recompute-preview:auth-1",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision": "ACCEPT",
        "decision_review_accepted": True,
        "decision_review_rejected": False,
        "reviewed_changed_fields": ["decision_type", "priority", "reasons"],
        "reviewed_changes": {
            "decision_type": {"before": "REPLENISH_NORMAL", "after": "HOLD_STOCK"},
            "priority": {"before": "HIGH", "after": "LOW"},
            "reasons": {"before": ["DAYS_OF_STOCK_LOW"], "after": ["POSITIVE_UNIT_PROFIT"]},
        },
        "reviewed_preview_decision": {
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
        },
        "persistent": False,
        "decision_persistence_allowed": False,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_accepted_review_becomes_persistence_eligible_without_permission():
    review = _review()
    before = deepcopy(review)
    result = build_product_decision_persistence_eligibility(review)

    assert result["status"] == "PRODUCT_DECISION_PERSISTENCE_ELIGIBLE"
    assert result["decision_persistence_eligible"] is True
    assert result["decision_persistence_review_required"] is True
    assert result["decision_persistence_allowed"] is False
    assert result["product_decision_persisted"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert review == before


def test_rejected_review_is_blocked():
    result = build_product_decision_persistence_eligibility(
        _review(
            status="PRODUCT_DECISION_PREVIEW_REVIEW_REJECTED",
            decision="REJECT",
            decision_review_accepted=False,
            decision_review_rejected=True,
        )
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_STATUS_INVALID"


def test_forged_review_id_is_blocked():
    result = build_product_decision_persistence_eligibility(
        _review(decision_preview_review_id="forged")
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_ID_MISMATCH"


def test_forged_delta_id_is_blocked():
    result = build_product_decision_persistence_eligibility(
        _review(decision_preview_delta_id="forged")
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_ID_MISMATCH"


def test_prior_persistence_permission_is_blocked():
    result = build_product_decision_persistence_eligibility(
        _review(decision_persistence_allowed=True)
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_SAFETY_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = build_product_decision_persistence_eligibility(
        _review(execution_ready=True)
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_reviewed_field_is_blocked():
    changes = deepcopy(_review()["reviewed_changes"])
    changes["execution_allowed"] = {"before": False, "after": True}
    result = build_product_decision_persistence_eligibility(
        _review(
            reviewed_changed_fields=["decision_type", "priority", "reasons", "execution_allowed"],
            reviewed_changes=changes,
        )
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_CHANGES_UNSAFE"


def test_change_set_mismatch_is_blocked():
    result = build_product_decision_persistence_eligibility(
        _review(reviewed_changes={"decision_type": _review()["reviewed_changes"]["decision_type"]})
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_CHANGE_SET_MISMATCH"


def test_preview_sku_mismatch_is_blocked():
    preview = deepcopy(_review()["reviewed_preview_decision"])
    preview["sku"] = "other"
    result = build_product_decision_persistence_eligibility(
        _review(reviewed_preview_decision=preview)
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_PREVIEW_SKU_MISMATCH"


def test_change_after_must_match_reviewed_preview():
    changes = deepcopy(_review()["reviewed_changes"])
    changes["priority"]["after"] = "CRITICAL"
    result = build_product_decision_persistence_eligibility(
        _review(reviewed_changes=changes)
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_CHANGE_PREVIEW_MISMATCH"


def test_missing_context_is_blocked():
    result = build_product_decision_persistence_eligibility(_review(draft_id=""))
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_CONTEXT_REQUIRED"
