from product_decision_user_action_post_decision_observation import build_product_decision_user_action_post_decision_observation


def _status(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_READY",
        "user_action_checklist_id": "check-1",
        "sku": "hook-2",
        "aggregate_status": "USER_REPORTED_COMPLETE",
        "externally_verified": False,
        "executed": False,
    }
    result.update(values)
    return result


def _decision(**values):
    result = {"sku": "hook-2", "decision_type": "HOLD_STOCK", "priority": "LOW", "confidence": "HIGH", "reasons": ["POSITIVE_UNIT_PROFIT"]}
    result.update(values)
    return result


def test_observes_later_decision_without_causal_claim():
    result = build_product_decision_user_action_post_decision_observation(_status(), _decision())
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED"
    assert result["observation_only"] is True
    assert result["causal_claim_allowed"] is False
    assert result["executed"] is False


def test_partial_report_blocks():
    result = build_product_decision_user_action_post_decision_observation(_status(aggregate_status="USER_REPORTED_PARTIAL"), _decision())
    assert result["code"] == "POST_DECISION_OBSERVATION_COMPLETE_REPORT_REQUIRED"


def test_sku_mismatch_blocks():
    result = build_product_decision_user_action_post_decision_observation(_status(), _decision(sku="other"))
    assert result["code"] == "POST_DECISION_OBSERVATION_SKU_MISMATCH"


def test_external_verification_flag_blocks():
    result = build_product_decision_user_action_post_decision_observation(_status(externally_verified=True), _decision())
    assert result["code"] == "POST_DECISION_OBSERVATION_SAFETY_BOUNDARY_VIOLATION"


def test_invalid_later_decision_blocks():
    result = build_product_decision_user_action_post_decision_observation(_status(), {"sku": "hook-2"})
    assert result["code"] == "POST_DECISION_OBSERVATION_LATER_DECISION_INVALID"
