from collections import Counter
from copy import deepcopy


def build_product_decision_user_action_learning_summary(outcomes):
    rows = [deepcopy(dict(item)) for item in (outcomes or []) if isinstance(item, dict)]
    valid = []
    for item in rows:
        if item.get("status") != "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_READY":
            continue
        if item.get("causal_claim_allowed") is not False or item.get("executed") is not False:
            continue
        if item.get("interpretation") != "OBSERVED_AFTER_USER_REPORT":
            continue
        valid.append(item)

    outcome_counts = Counter(item.get("outcome_type") for item in valid if item.get("outcome_type"))
    priority_counts = Counter(item.get("priority_change") for item in valid if item.get("priority_change"))
    sku_counts = Counter(item.get("sku") for item in valid if item.get("sku"))

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_READY",
        "observation_count": len(valid),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "priority_change_counts": dict(sorted(priority_counts.items())),
        "sku_count": len(sku_counts),
        "sku_observation_counts": dict(sorted(sku_counts.items())),
        "learning_scope": "DESCRIPTIVE_OBSERVATIONS_ONLY",
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
