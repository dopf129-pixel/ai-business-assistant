from copy import deepcopy

from product_decision_persistence_application_readiness import (
    build_product_decision_persistence_application_readiness,
)


def _authorization(**values):
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_AUTHORIZED",
        "decision_persistence_authorization_id": "product-decision-persistence-authorization:product-decision-persistence-eligibility:product-decision-preview-review:product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "decision_persistence_eligibility_id": "product-decision-persistence-eligibility:product-decision-preview-review:product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "decision_preview_review_id": "product-decision-preview-review:product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "decision_preview_delta_id": "product-decision-preview-delta:product-decision-recompute-preview:auth-1",
        "recompute_preview_id": "product-decision-recompute-preview:auth-1",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision": "AUTHORIZE",
        "decision_persistence_authorized": True,
        "decision_persistence_rejected": False,
        "decision_persistence_allowed": True,
        "authorized_changed_fields": ["decision_type", "priority", "reasons"],
        "authorized_changes": {
            "decision_type": {"before": "REPLENISH_NORMAL", "after": "HOLD_STOCK"},
            "priority": {"before": "HIGH", "after": "LOW"},
            "reasons": {"before": ["DAYS_OF_STOCK_LOW"], "after": ["POSITIVE_UNIT_PROFIT"]},
        },
        "authorized_preview_decision": {
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


def test_authorized_decision_becomes_application_ready_without_starting():
    source = _authorization()
    before = deepcopy(source)
    result = build_product_decision_persistence_application_readiness(source)

    assert result["status"] == "PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY"
    assert result["decision_persistence_allowed"] is True
    assert result["decision_persistence_application_ready"] is True
    assert result["decision_persistence_application_started"] is False
    assert result["product_decision_mutated"] is False
    assert result["product_decision_persisted"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before


def test_rejected_authorization_is_blocked():
    result = build_product_decision_persistence_application_readiness(
        _authorization(
            status="PRODUCT_DECISION_PERSISTENCE_REJECTED",
            decision="REJECT",
            decision_persistence_authorized=False,
            decision_persistence_rejected=True,
            decision_persistence_allowed=False,
        )
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_STATUS_INVALID"


def test_forged_authorization_id_is_blocked():
    result = build_product_decision_persistence_application_readiness(
        _authorization(decision_persistence_authorization_id="forged")
    )
    assert result["code"] == "DECISION_PERSISTENCE_AUTHORIZATION_ID_MISMATCH"


def test_missing_persistence_permission_is_blocked():
    result = build_product_decision_persistence_application_readiness(
        _authorization(decision_persistence_allowed=False)
    )
    assert result["code"] == "DECISION_PERSISTENCE_PERMISSION_REQUIRED"


def test_already_persisted_boundary_is_blocked():
    result = build_product_decision_persistence_application_readiness(
        _authorization(product_decision_persisted=True)
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_SAFETY_BOUNDARY_VIOLATION"


def test_execution_boundary_is_blocked():
    result = build_product_decision_persistence_application_readiness(
        _authorization(execution_ready=True)
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_authorized_field_is_blocked():
    changes = deepcopy(_authorization()["authorized_changes"])
    changes["execution_allowed"] = {"before": False, "after": True}
    result = build_product_decision_persistence_application_readiness(
        _authorization(
            authorized_changed_fields=[
                "decision_type",
                "priority",
                "reasons",
                "execution_allowed",
            ],
            authorized_changes=changes,
        )
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_CHANGES_UNSAFE"


def test_change_set_mismatch_is_blocked():
    result = build_product_decision_persistence_application_readiness(
        _authorization(
            authorized_changes={
                "decision_type": _authorization()["authorized_changes"]["decision_type"]
            }
        )
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_CHANGE_SET_MISMATCH"


def test_preview_sku_mismatch_is_blocked():
    preview = deepcopy(_authorization()["authorized_preview_decision"])
    preview["sku"] = "other"
    result = build_product_decision_persistence_application_readiness(
        _authorization(authorized_preview_decision=preview)
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_PREVIEW_SKU_MISMATCH"


def test_change_after_must_match_authorized_preview():
    changes = deepcopy(_authorization()["authorized_changes"])
    changes["priority"]["after"] = "CRITICAL"
    result = build_product_decision_persistence_application_readiness(
        _authorization(authorized_changes=changes)
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_CHANGE_PREVIEW_MISMATCH"


def test_invalid_preview_is_blocked():
    preview = deepcopy(_authorization()["authorized_preview_decision"])
    preview["priority"] = None
    result = build_product_decision_persistence_application_readiness(
        _authorization(authorized_preview_decision=preview)
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_PREVIEW_INVALID"


def test_missing_context_is_blocked():
    result = build_product_decision_persistence_application_readiness(
        _authorization(draft_id="")
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_CONTEXT_REQUIRED"
