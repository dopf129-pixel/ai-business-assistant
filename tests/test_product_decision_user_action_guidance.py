from copy import deepcopy

from product_decision_user_action_guidance import build_product_decision_user_action_guidance


def _verification(decision_type="REPLENISH_HIGH_PRIORITY", **values):
    application_id = "product-decision-persistence-application:ready-1"
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_VERIFIED",
        "decision_persistence_verification_id": "product-decision-persistence-verification:" + application_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "decision_persistence_verified": True,
        "verified_snapshot": {
            "sku": "hook-2",
            "decision_type": decision_type,
            "priority": "HIGH",
            "reasons": ["LOW_STOCK"],
        },
        "persistent": True,
        "product_decision_persisted": True,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_replenishment_guidance_requires_user_execution_and_preserves_input():
    source = _verification()
    before = deepcopy(source)
    result = build_product_decision_user_action_guidance(source)
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY"
    assert result["action_type"] == "REVIEW_REPLENISHMENT"
    assert result["user_execution_required"] is True
    assert result["automatic_execution_prohibited"] is True
    assert result["execution_allowed"] is False
    assert source == before


def test_low_profit_maps_to_unit_economics_review():
    result = build_product_decision_user_action_guidance(_verification("INVESTIGATE_LOW_PROFIT"))
    assert result["action_type"] == "REVIEW_UNIT_ECONOMICS"


def test_low_margin_maps_to_margin_review():
    result = build_product_decision_user_action_guidance(_verification("WATCH_LOW_MARGIN"))
    assert result["action_type"] == "REVIEW_MARGIN"


def test_hold_stock_maps_to_monitor_only():
    result = build_product_decision_user_action_guidance(_verification("HOLD_STOCK"))
    assert result["action_type"] == "MONITOR_ONLY"


def test_forged_verification_id_blocks():
    result = build_product_decision_user_action_guidance(_verification(decision_persistence_verification_id="forged"))
    assert result["code"] == "USER_ACTION_GUIDANCE_VERIFICATION_ID_MISMATCH"


def test_unverified_state_blocks():
    result = build_product_decision_user_action_guidance(_verification(decision_persistence_verified=False))
    assert result["code"] == "USER_ACTION_GUIDANCE_VERIFICATION_REQUIRED"


def test_execution_boundary_violation_blocks():
    result = build_product_decision_user_action_guidance(_verification(execution_allowed=True))
    assert result["code"] == "USER_ACTION_GUIDANCE_SAFETY_BOUNDARY_VIOLATION"
    assert result["execution_allowed"] is False


def test_snapshot_sku_mismatch_blocks():
    source = _verification()
    source["verified_snapshot"]["sku"] = "other"
    result = build_product_decision_user_action_guidance(source)
    assert result["code"] == "USER_ACTION_GUIDANCE_SNAPSHOT_SKU_MISMATCH"


def test_unsupported_decision_blocks():
    result = build_product_decision_user_action_guidance(_verification("UNKNOWN"))
    assert result["code"] == "USER_ACTION_GUIDANCE_DECISION_UNSUPPORTED"
