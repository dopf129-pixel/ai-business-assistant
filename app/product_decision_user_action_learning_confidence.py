from copy import deepcopy


MIN_SAMPLE_BY_CONFIDENCE = {
    "NONE": 0,
    "LOW": 3,
    "MEDIUM": 10,
    "HIGH": 30,
}


def build_product_decision_user_action_learning_confidence(quality):
    source = deepcopy(dict(quality or {}))
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_LEARNING_EVIDENCE_QUALITY_READY":
        return _blocked("LEARNING_CONFIDENCE_QUALITY_STATUS_INVALID")
    if (
        source.get("causal_inference_supported") is not False
        or source.get("decision_rule_update_allowed") is not False
        or source.get("automatic_execution_allowed") is not False
        or source.get("executed") is not False
    ):
        return _blocked("LEARNING_CONFIDENCE_SAFETY_BOUNDARY_VIOLATION")

    observation_count = int(source.get("observation_count") or 0)
    sku_count = int(source.get("sku_count") or 0)
    quality_name = source.get("evidence_quality")

    if observation_count < 3:
        confidence = "NONE"
    elif observation_count < 10 or sku_count < 2:
        confidence = "LOW"
    elif observation_count < 30 or sku_count < 3:
        confidence = "MEDIUM"
    else:
        confidence = "HIGH"

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_CONFIDENCE_READY",
        "evidence_quality": quality_name,
        "observation_count": observation_count,
        "sku_count": sku_count,
        "descriptive_confidence": confidence,
        "minimum_sample_required": MIN_SAMPLE_BY_CONFIDENCE[confidence],
        "confidence_scope": "DESCRIPTIVE_PATTERN_CONFIDENCE_ONLY",
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_CONFIDENCE_BLOCKED",
        "descriptive_confidence": "NONE",
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
