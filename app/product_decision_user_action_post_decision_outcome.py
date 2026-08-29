from copy import deepcopy


PRIORITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def build_product_decision_user_action_post_decision_outcome(observation, prior_decision):
    source = deepcopy(dict(observation or {}))
    prior = deepcopy(dict(prior_decision or {}))
    observation_id = str(source.get("observation_id") or "").strip()
    checklist_id = str(source.get("user_action_checklist_id") or "").strip()
    sku = str(source.get("sku") or "").strip()
    if not observation_id or not checklist_id or not sku:
        return _blocked("POST_DECISION_OUTCOME_CONTEXT_REQUIRED", source)
    if observation_id != "product-decision-user-action-post-decision-observation:" + checklist_id:
        return _blocked("POST_DECISION_OUTCOME_OBSERVATION_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED":
        return _blocked("POST_DECISION_OUTCOME_OBSERVATION_STATUS_INVALID", source)
    if source.get("observation_only") is not True or source.get("causal_claim_allowed") is not False:
        return _blocked("POST_DECISION_OUTCOME_CAUSAL_SAFETY_VIOLATION", source)
    if not isinstance(prior, dict) or str(prior.get("sku") or "").strip() != sku:
        return _blocked("POST_DECISION_OUTCOME_PRIOR_DECISION_INVALID", source)
    prior_type = str(prior.get("decision_type") or "").strip()
    later_type = str(source.get("later_decision_type") or "").strip()
    prior_priority = str(prior.get("priority") or "").strip()
    later_priority = str(source.get("later_priority") or "").strip()
    if not prior_type or not later_type or prior_priority not in PRIORITY_RANK or later_priority not in PRIORITY_RANK:
        return _blocked("POST_DECISION_OUTCOME_DECISION_FIELDS_INVALID", source)

    decision_changed = prior_type != later_type
    delta = PRIORITY_RANK[later_priority] - PRIORITY_RANK[prior_priority]
    if delta < 0:
        priority_change = "PRIORITY_DECREASED"
    elif delta > 0:
        priority_change = "PRIORITY_INCREASED"
    else:
        priority_change = "PRIORITY_UNCHANGED"

    if decision_changed:
        outcome_type = "DECISION_CHANGED"
    elif delta < 0:
        outcome_type = "SAME_DECISION_LOWER_PRIORITY"
    elif delta > 0:
        outcome_type = "SAME_DECISION_HIGHER_PRIORITY"
    else:
        outcome_type = "NO_DECISION_CHANGE"

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_READY",
        "outcome_id": "product-decision-user-action-post-decision-outcome:" + observation_id,
        "observation_id": observation_id,
        "user_action_checklist_id": checklist_id,
        "sku": sku,
        "prior_decision_type": prior_type,
        "later_decision_type": later_type,
        "prior_priority": prior_priority,
        "later_priority": later_priority,
        "decision_changed": decision_changed,
        "priority_change": priority_change,
        "outcome_type": outcome_type,
        "interpretation": "OBSERVED_AFTER_USER_REPORT",
        "causal_claim_allowed": False,
        "executed": False,
    }


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_BLOCKED",
        "outcome_id": None,
        "observation_id": source.get("observation_id"),
        "user_action_checklist_id": source.get("user_action_checklist_id"),
        "sku": source.get("sku"),
        "causal_claim_allowed": False,
        "executed": False,
    }
