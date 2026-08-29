from copy import deepcopy


def build_product_decision_user_action_learning_advisory_evaluation_summary(reviews):
    rows = [deepcopy(dict(item)) for item in (reviews or []) if isinstance(item, dict)]
    valid = []
    for item in rows:
        if item.get("status") not in {
            "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_REVIEW_ACCEPTED",
            "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_REVIEW_REJECTED",
        }:
            continue
        if (
            item.get("review_source") != "USER"
            or item.get("persistent") is not False
            or item.get("advisory_only") is not True
            or item.get("causal_claim_allowed") is not False
            or item.get("decision_rule_update_allowed") is not False
            or item.get("automatic_execution_allowed") is not False
            or item.get("executed") is not False
        ):
            continue
        valid.append(item)

    accepted = sum(1 for item in valid if item.get("human_reported_useful") is True)
    rejected = sum(1 for item in valid if item.get("human_reported_useful") is False)
    total = len(valid)
    usefulness_rate = (accepted / total) if total else None

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_EVALUATION_SUMMARY_READY",
        "review_count": total,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "human_reported_usefulness_rate": usefulness_rate,
        "evaluation_scope": "HUMAN_REPORTED_ADVISORY_USEFULNESS_ONLY",
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
