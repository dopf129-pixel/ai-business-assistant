from copy import deepcopy


VALID_REVIEW_DECISIONS = {"ACCEPT_USEFUL", "REJECT_NOT_USEFUL"}


def build_product_decision_user_action_learning_advisory_review(advisory, decision):
    source = deepcopy(dict(advisory or {}))
    normalized = str(decision or "").strip().upper()
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_READY":
        return _blocked("LEARNING_ADVISORY_REVIEW_STATUS_INVALID")
    if normalized not in VALID_REVIEW_DECISIONS:
        return _blocked("LEARNING_ADVISORY_REVIEW_DECISION_INVALID")
    if (
        source.get("advisory_only") is not True
        or source.get("causal_claim_allowed") is not False
        or source.get("decision_rule_update_allowed") is not False
        or source.get("automatic_execution_allowed") is not False
        or source.get("executed") is not False
    ):
        return _blocked("LEARNING_ADVISORY_REVIEW_SAFETY_BOUNDARY_VIOLATION")

    accepted = normalized == "ACCEPT_USEFUL"
    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_REVIEW_ACCEPTED" if accepted else "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_REVIEW_REJECTED",
        "review_decision": normalized,
        "human_reported_useful": accepted,
        "review_source": "USER",
        "observation_count": int(source.get("observation_count") or 0),
        "descriptive_confidence": source.get("descriptive_confidence") or "NONE",
        "reviewed_insights": list(source.get("insights") or []),
        "persistent": False,
        "advisory_only": True,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_REVIEW_BLOCKED",
        "human_reported_useful": False,
        "persistent": False,
        "advisory_only": True,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
