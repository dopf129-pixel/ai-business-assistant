from copy import deepcopy


HEALTH_STATES = {
    "NO_FEEDBACK_EVIDENCE",
    "FEEDBACK_ONLY",
    "EARLY_POST_FEEDBACK_SAMPLE",
    "MULTI_PRODUCT_DESCRIPTIVE_SAMPLE",
}


def build_product_decision_learning_health(summary):
    source = deepcopy(dict(summary or {}))

    if source.get("error") is not False:
        return _blocked("LEARNING_HEALTH_SUMMARY_ERROR")

    integer_fields = (
        "products_count",
        "decision_snapshots_count",
        "feedback_count",
        "outcome_count",
    )
    values = {}
    for field in integer_fields:
        value = source.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            return _blocked(
                "LEARNING_HEALTH_SUMMARY_COUNTS_INVALID"
            )
        values[field] = value

    feedback = source.get("feedback_counts")
    outcomes = source.get("outcome_counts")
    if not isinstance(feedback, dict) or not isinstance(outcomes, dict):
        return _blocked("LEARNING_HEALTH_SUMMARY_BREAKDOWN_REQUIRED")

    useful = _non_negative_int(feedback.get("USEFUL"))
    not_relevant = _non_negative_int(
        feedback.get("NOT_RELEVANT")
    )
    decreased = _non_negative_int(
        outcomes.get("PRIORITY_DECREASED")
    )
    increased = _non_negative_int(
        outcomes.get("PRIORITY_INCREASED")
    )
    changed = _non_negative_int(
        outcomes.get("DECISION_CHANGED")
    )
    if None in {
        useful,
        not_relevant,
        decreased,
        increased,
        changed,
    }:
        return _blocked("LEARNING_HEALTH_BREAKDOWN_COUNTS_INVALID")

    feedback_count = values["feedback_count"]
    outcome_count = values["outcome_count"]
    snapshot_count = values["decision_snapshots_count"]
    product_count = values["products_count"]

    if useful + not_relevant != feedback_count:
        return _blocked("LEARNING_HEALTH_FEEDBACK_TOTAL_MISMATCH")
    if decreased + increased + changed != outcome_count:
        return _blocked("LEARNING_HEALTH_OUTCOME_TOTAL_MISMATCH")
    if (
        product_count > snapshot_count
        or feedback_count > snapshot_count
        or outcome_count > snapshot_count
        or (snapshot_count == 0 and product_count != 0)
    ):
        return _blocked("LEARNING_HEALTH_HISTORY_COUNTS_INCONSISTENT")

    if feedback_count == 0 and outcome_count == 0:
        health_state = "NO_FEEDBACK_EVIDENCE"
        next_action = "COLLECT_USER_FEEDBACK"
    elif outcome_count == 0:
        health_state = "FEEDBACK_ONLY"
        next_action = "WAIT_FOR_LATER_DECISION_OBSERVATIONS"
    elif outcome_count < 3 or product_count < 2:
        health_state = "EARLY_POST_FEEDBACK_SAMPLE"
        next_action = "COLLECT_MORE_DESCRIPTIVE_OBSERVATIONS"
    else:
        health_state = "MULTI_PRODUCT_DESCRIPTIVE_SAMPLE"
        next_action = "REVIEW_DESCRIPTIVE_PATTERNS"

    return {
        "error": False,
        "status": "PRODUCT_DECISION_LEARNING_HEALTH_READY",
        "health_state": health_state,
        "next_action": next_action,
        "products_count": product_count,
        "decision_snapshots_count": snapshot_count,
        "feedback_count": feedback_count,
        "useful_count": useful,
        "not_relevant_count": not_relevant,
        "outcome_count": outcome_count,
        "priority_decreased_count": decreased,
        "priority_increased_count": increased,
        "decision_changed_count": changed,
        "evidence_scope": "DESCRIPTIVE_DECISION_HISTORY_ONLY",
        "causal_claim_allowed": False,
        "success_rate_claim_allowed": False,
        "profitability_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }


def _non_negative_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0:
        return None
    return value


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_LEARNING_HEALTH_BLOCKED",
        "health_state": None,
        "next_action": None,
        "evidence_scope": "DESCRIPTIVE_DECISION_HISTORY_ONLY",
        "causal_claim_allowed": False,
        "success_rate_claim_allowed": False,
        "profitability_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
