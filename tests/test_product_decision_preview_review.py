from copy import deepcopy

from product_decision_preview_review import build_product_decision_preview_review


def _delta(**values):
    result = {
        "status": "PRODUCT_DECISION_PREVIEW_DELTA_READY",
        "decision_preview_delta_id": "product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "recompute_preview_id": "product-decision-recompute-preview:auth-1",
        "recompute_authorization_id": "auth-1",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_changed": True,
        "changed_fields": ["decision_type", "priority"],
        "changed_field_count": 2,
        "changes": {
            "decision_type": {"before": "REPLENISH_NORMAL", "after": "HOLD_STOCK"},
            "priority": {"before": "HIGH", "after": "LOW"},
        },
        "current_decision": {
            "sku": "hook-2",
            "decision_type": "REPLENISH_NORMAL",
            "priority": "HIGH",
            "confidence": "HIGH",
            "reasons": ["DAYS_OF_STOCK_LOW"],
        },
        "preview_decision": {
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
        },
        "persistent": False,
        "task_draft_mutated": False,
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


def test_accept_marks_preview_reviewed_without_persistence_permission():
    delta = _delta()
    before = deepcopy(delta)
    result = build_product_decision_preview_review(delta, "accept")
    assert result["status"] == "PRODUCT_DECISION_PREVIEW_REVIEW_ACCEPTED"
    assert result["decision_review_accepted"] is True
    assert result["decision_review_rejected"] is False
    assert result["decision_persistence_allowed"] is False
    assert result["product_decision_persisted"] is False
    assert result["execution_allowed"] is False
    assert result["executed"] is False
    assert delta == before


def test_reject_marks_preview_rejected_without_mutation():
    result = build_product_decision_preview_review(_delta(), "REJECT")
    assert result["status"] == "PRODUCT_DECISION_PREVIEW_REVIEW_REJECTED"
    assert result["decision_review_accepted"] is False
    assert result["decision_review_rejected"] is True
    assert result["decision_persistence_allowed"] is False


def test_invalid_review_decision_is_blocked():
    result = build_product_decision_preview_review(_delta(), "maybe")
    assert result["code"] == "DECISION_PREVIEW_REVIEW_DECISION_INVALID"


def test_forged_delta_id_is_blocked():
    result = build_product_decision_preview_review(
        _delta(decision_preview_delta_id="forged"), "ACCEPT"
    )
    assert result["code"] == "DECISION_PREVIEW_DELTA_ID_MISMATCH"


def test_unchanged_delta_is_blocked_as_review_not_required():
    result = build_product_decision_preview_review(
        _delta(decision_changed=False, changed_fields=[], changed_field_count=0, changes={}),
        "ACCEPT",
    )
    assert result["code"] == "DECISION_PREVIEW_DELTA_NO_CHANGE"


def test_execution_boundary_violation_is_blocked():
    result = build_product_decision_preview_review(
        _delta(execution_ready=True), "ACCEPT"
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_changed_field_is_blocked():
    changes = deepcopy(_delta()["changes"])
    changes["execution_allowed"] = {"before": False, "after": True}
    result = build_product_decision_preview_review(
        _delta(
            changed_fields=["decision_type", "priority", "execution_allowed"],
            changed_field_count=3,
            changes=changes,
        ),
        "ACCEPT",
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_CHANGES_UNSAFE"


def test_change_count_mismatch_is_blocked():
    result = build_product_decision_preview_review(
        _delta(changed_field_count=1), "ACCEPT"
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_CHANGE_COUNT_MISMATCH"


def test_change_set_mismatch_is_blocked():
    result = build_product_decision_preview_review(
        _delta(changes={"decision_type": _delta()["changes"]["decision_type"]}),
        "ACCEPT",
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_CHANGE_SET_MISMATCH"


def test_preview_sku_mismatch_is_blocked():
    preview = deepcopy(_delta()["preview_decision"])
    preview["sku"] = "other"
    result = build_product_decision_preview_review(
        _delta(preview_decision=preview), "ACCEPT"
    )
    assert result["code"] == "DECISION_PREVIEW_REVIEW_PREVIEW_SKU_MISMATCH"
