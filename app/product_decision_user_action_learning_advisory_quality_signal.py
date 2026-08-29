from copy import deepcopy


def build_product_decision_user_action_learning_advisory_quality_signal(summary):
    source = deepcopy(dict(summary or {}))
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_EVALUATION_SUMMARY_READY":
        return _blocked("LEARNING_ADVISORY_QUALITY_SUMMARY_STATUS_INVALID")
    if (
        source.get("evaluation_scope") != "HUMAN_REPORTED_ADVISORY_USEFULNESS_ONLY"
        or source.get("causal_claim_allowed") is not False
        or source.get("decision_rule_update_allowed") is not False
        or source.get("automatic_execution_allowed") is not False
        or source.get("executed") is not False
    ):
        return _blocked("LEARNING_ADVISORY_QUALITY_SAFETY_BOUNDARY_VIOLATION")

    count = int(source.get("review_count") or 0)
    rate = source.get("human_reported_usefulness_rate")
    if count < 5 or rate is None:
        signal = "INSUFFICIENT_REVIEWS"
    elif rate >= 0.8:
        signal = "HIGH_REPORTED_USEFULNESS"
    elif rate >= 0.5:
        signal = "MIXED_REPORTED_USEFULNESS"
    else:
        signal = "LOW_REPORTED_USEFULNESS"

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_QUALITY_SIGNAL_READY",
        "review_count": count,
        "human_reported_usefulness_rate": rate,
        "quality_signal": signal,
        "quality_scope": "HUMAN_REPORTED_ADVISORY_QUALITY_ONLY",
        "advisory_improvement_review_recommended": signal in {"MIXED_REPORTED_USEFULNESS", "LOW_REPORTED_USEFULNESS"},
        "automatic_advisory_change_allowed": False,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_QUALITY_SIGNAL_BLOCKED",
        "quality_signal": None,
        "advisory_improvement_review_recommended": False,
        "automatic_advisory_change_allowed": False,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
