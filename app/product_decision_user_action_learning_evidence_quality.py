from copy import deepcopy


def build_product_decision_user_action_learning_evidence_quality(summary):
    source = deepcopy(dict(summary or {}))
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_READY":
        return _blocked("LEARNING_EVIDENCE_QUALITY_SUMMARY_STATUS_INVALID")
    if (
        source.get("learning_scope") != "DESCRIPTIVE_OBSERVATIONS_ONLY"
        or source.get("causal_claim_allowed") is not False
        or source.get("decision_rule_update_allowed") is not False
        or source.get("automatic_execution_allowed") is not False
        or source.get("executed") is not False
    ):
        return _blocked("LEARNING_EVIDENCE_QUALITY_SAFETY_BOUNDARY_VIOLATION")

    observation_count = int(source.get("observation_count") or 0)
    sku_count = int(source.get("sku_count") or 0)
    outcome_counts = dict(source.get("outcome_counts") or {})

    if observation_count <= 0:
        quality = "NO_EVIDENCE"
        score = 0
    elif observation_count < 3:
        quality = "VERY_LIMITED"
        score = 1
    elif observation_count < 10 or sku_count < 2:
        quality = "LIMITED"
        score = 2
    else:
        quality = "DESCRIPTIVE_BASELINE"
        score = 3

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_EVIDENCE_QUALITY_READY",
        "observation_count": observation_count,
        "sku_count": sku_count,
        "outcome_counts": outcome_counts,
        "evidence_quality": quality,
        "evidence_quality_score": score,
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_EVIDENCE_QUALITY_BLOCKED",
        "evidence_quality": None,
        "evidence_quality_score": 0,
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
