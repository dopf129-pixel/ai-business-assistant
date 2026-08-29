from copy import deepcopy

from product_decision_persistence_authorization import (
    build_product_decision_persistence_authorization,
)


def _eligibility(**values):
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_ELIGIBLE",
        "decision_persistence_eligibility_id": "product-decision-persistence-eligibility:product-decision-preview-review:product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "decision_preview_review_id": "product-decision-preview-review:product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "decision_preview_delta_id": "product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "recompute_preview_id": "product-decision-recompute-preview:auth-1",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_persistence_eligible": True,
        "decision_persistence_review_required": True,
        "decision_persistence_allowed": False,
        "eligible_changed_fields": ["decision_type", "priority"],
        "eligible_changes": {
            "decision_type": {"before": "REPLENISH_NORMAL", "after": "HOLD_STOCK"},
            "priority": {"before": "HIGH", "after": "LOW"},
        },
        "eligible_preview_decision": {
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
        },
        "persistent": False,
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


def test_authorize_opens_persistence_permission_without_persisting():
    source = _eligibility()
    before = deepcopy(source)
    result = build_product_decision_persistence_authorization(source, "authorize")
    assert result["status"] == "PRODUCT_DECISION_PERSISTENCE_AUTHORIZED"
    assert result["decision_persistence_authorized"] is True
    assert result["decision_persistence_rejected"] is False
    assert result["decision_persistence_allowed"] is True
    assert result["persistent"] is False
    assert result["product_decision_mutated"] is False
    assert result["product_decision_persisted"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before


def test_reject_keeps_persistence_permission_closed():
    result = build_product_decision_persistence_authorization(_eligibility(), "REJECT")
    assert result["status"] == "PRODUCT_DECISION_PERSISTENCE_REJECTED"
    assert result["decision_persistence_authorized"] is False
    assert result["decision_persistence_rejected"] is True
    assert result["decision_persistence_allowed"] is False
    assert result["product_decision_persisted"] is False


def test_invalid_decision_is_blocked():
    result = build_product_decision_persistence_authorization(_eligibility(), "maybe")
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_DECISION_INVALID"


def test_forged_eligibility_id_is_blocked():
    result = build_product_decision_persistence_authorization(
        _eligibility(decision_persistence_eligibility_id="forged"), "AUTHORIZE"
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_ID_MISMATCH"


def test_not_eligible_is_blocked():
    result = build_product_decision_persistence_authorization(
        _eligibility(decision_persistence_eligible=False), "AUTHORIZE"
    )
    assert result["code"] == "DECISION_PERSISTENCE_NOT_ELIGIBLE"


def test_prior_permission_is_blocked():
    result = build_product_decision_persistence_authorization(
        _eligibility(decision_persistence_allowed=True), "AUTHORIZE"
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_BOUNDARY_VIOLATION"


def test_already_persisted_boundary_is_blocked():
    result = build_product_decision_persistence_authorization(
        _eligibility(product_decision_persisted=True), "AUTHORIZE"
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_SAFETY_BOUNDARY_VIOLATION"


def test_execution_boundary_is_blocked():
    result = build_product_decision_persistence_authorization(
        _eligibility(execution_ready=True), "AUTHORIZE"
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_changed_field_is_blocked():
    changes = deepcopy(_eligibility()["eligible_changes"])
    changes["execution_allowed"] = {"before": False, "after": True}
    result = build_product_decision_persistence_authorization(
        _eligibility(
            eligible_changed_fields=["decision_type", "priority", "execution_allowed"],
            eligible_changes=changes,
        ),
        "AUTHORIZE",
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_CHANGES_UNSAFE"


def test_change_set_mismatch_is_blocked():
    result = build_product_decision_persistence_authorization(
        _eligibility(eligible_changes={"decision_type": _eligibility()["eligible_changes"]["decision_type"]}),
        "AUTHORIZE",
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_CHANGE_SET_MISMATCH"


def test_preview_sku_mismatch_is_blocked():
    preview = deepcopy(_eligibility()["eligible_preview_decision"])
    preview["sku"] = "other"
    result = build_product_decision_persistence_authorization(
        _eligibility(eligible_preview_decision=preview), "AUTHORIZE"
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_PREVIEW_SKU_MISMATCH"


def test_missing_context_is_blocked():
    result = build_product_decision_persistence_authorization(
        _eligibility(draft_id=""), "AUTHORIZE"
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_CONTEXT_REQUIRED"
