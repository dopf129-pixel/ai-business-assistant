from copy import deepcopy


ALLOWED_DECISION_TYPES = {
    "REPLENISH_HIGH_PRIORITY",
    "REPLENISH_NORMAL",
    "WATCH_LOW_MARGIN",
    "INVESTIGATE_LOW_PROFIT",
    "HOLD_STOCK",
    "INSUFFICIENT_DATA",
}
PRIORITY_RANK = {
    "NONE": 0,
    "LOW": 1,
    "NORMAL": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


def build_product_decision_user_action_post_decision_outcome(
    observation,
    prior_decision,
):
    if not isinstance(observation, dict):
        return _blocked(
            "POST_DECISION_OUTCOME_OBSERVATION_INPUT_INVALID",
            {},
        )

    source = deepcopy(observation)

    if not isinstance(prior_decision, dict):
        return _blocked(
            "POST_DECISION_OUTCOME_PRIOR_DECISION_INVALID",
            source,
        )

    prior = deepcopy(prior_decision)

    observation_id = _required_string(source.get("observation_id"))
    checklist_status_id = _required_string(
        source.get("user_action_checklist_status_id")
    )
    checklist_id = _required_string(
        source.get("user_action_checklist_id")
    )
    guidance_id = _required_string(
        source.get("user_action_guidance_id")
    )
    verification_id = _required_string(
        source.get("decision_persistence_verification_id")
    )
    application_id = _required_string(
        source.get("decision_persistence_application_id")
    )
    sku = _required_string(source.get("sku"))
    verified_recorded_at = _required_string(
        source.get("verified_recorded_at")
    )

    if not all(
        (
            observation_id,
            checklist_status_id,
            checklist_id,
            guidance_id,
            verification_id,
            application_id,
            sku,
            verified_recorded_at,
        )
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_CONTEXT_REQUIRED",
            source,
        )

    if (
        observation_id
        != "product-decision-user-action-post-decision-observation:"
        + checklist_id
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_OBSERVATION_ID_MISMATCH",
            source,
        )

    if (
        checklist_status_id
        != "product-decision-user-action-checklist-status:" + checklist_id
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_CHECKLIST_STATUS_ID_MISMATCH",
            source,
        )

    if (
        checklist_id
        != "product-decision-user-action-checklist:" + guidance_id
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_CHECKLIST_ID_MISMATCH",
            source,
        )

    if (
        guidance_id
        != "product-decision-user-action-guidance:" + verification_id
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_GUIDANCE_ID_MISMATCH",
            source,
        )

    if (
        verification_id
        != "product-decision-persistence-verification:" + application_id
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_VERIFICATION_ID_MISMATCH",
            source,
        )

    if (
        source.get("error") is not False
        or source.get("status")
        != "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED"
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_OBSERVATION_STATUS_INVALID",
            source,
        )

    if source.get("decision_persistence_verified") is not True:
        return _blocked(
            "POST_DECISION_OUTCOME_VERIFICATION_REQUIRED",
            source,
        )

    if (
        source.get("aggregate_status") != "USER_REPORTED_COMPLETE"
        or source.get("completion_evidence_source") != "USER_REPORT"
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_COMPLETION_EVIDENCE_INVALID",
            source,
        )

    item_count = source.get("item_count")
    reported_count = source.get("reported_count")
    completed_count = source.get("completed_count")
    reported_item_ids = source.get("reported_item_ids")
    completed_item_ids = source.get("completed_item_ids")

    if (
        type(item_count) is not int
        or item_count < 1
        or type(reported_count) is not int
        or type(completed_count) is not int
        or reported_count != item_count
        or completed_count != item_count
        or not _canonical_item_ids(reported_item_ids, item_count)
        or not _canonical_item_ids(completed_item_ids, item_count)
        or reported_item_ids != completed_item_ids
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_COMPLETION_EVIDENCE_INVALID",
            source,
        )

    if (
        source.get("observation_only") is not True
        or source.get("causal_claim_allowed") is not False
        or source.get("externally_verified") is not False
        or source.get("persistent") is not False
        or source.get("checklist_mutated") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_CAUSAL_SAFETY_VIOLATION",
            source,
        )

    later_type = _required_string(source.get("later_decision_type"))
    later_priority = _required_string(source.get("later_priority"))
    later_confidence = _required_string(source.get("later_confidence"))
    later_reasons = _canonical_reasons(source.get("later_reasons"))

    if (
        later_type not in ALLOWED_DECISION_TYPES
        or later_priority not in PRIORITY_RANK
        or later_confidence not in ALLOWED_CONFIDENCE
        or later_reasons is None
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_DECISION_FIELDS_INVALID",
            source,
        )

    prior_sku = _required_string(prior.get("sku"))
    prior_type = _required_string(prior.get("decision_type"))
    prior_priority = _required_string(prior.get("priority"))
    prior_confidence = _required_string(prior.get("confidence"))
    prior_reasons = _canonical_reasons(prior.get("reasons"))

    if (
        prior_sku != sku
        or prior_type not in ALLOWED_DECISION_TYPES
        or prior_priority not in PRIORITY_RANK
        or prior_confidence not in ALLOWED_CONFIDENCE
        or prior_reasons is None
    ):
        return _blocked(
            "POST_DECISION_OUTCOME_PRIOR_DECISION_INVALID",
            source,
        )

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
        "outcome_id":
            "product-decision-user-action-post-decision-outcome:"
            + observation_id,
        "observation_id": observation_id,
        "user_action_checklist_status_id": checklist_status_id,
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": sku,
        "verified_recorded_at": verified_recorded_at,
        "decision_persistence_verified": True,
        "aggregate_status": "USER_REPORTED_COMPLETE",
        "item_count": item_count,
        "reported_count": reported_count,
        "completed_count": completed_count,
        "reported_item_ids": deepcopy(reported_item_ids),
        "completed_item_ids": deepcopy(completed_item_ids),
        "completion_evidence_source": "USER_REPORT",
        "prior_decision_type": prior_type,
        "later_decision_type": later_type,
        "prior_priority": prior_priority,
        "later_priority": later_priority,
        "prior_confidence": prior_confidence,
        "later_confidence": later_confidence,
        "prior_reasons": deepcopy(prior_reasons),
        "later_reasons": deepcopy(later_reasons),
        "decision_changed": decision_changed,
        "priority_change": priority_change,
        "outcome_type": outcome_type,
        "interpretation": "OBSERVED_AFTER_USER_REPORT",
        "observation_only": True,
        "causal_claim_allowed": False,
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _canonical_item_ids(value, expected_count):
    if not isinstance(value, list) or len(value) != expected_count:
        return False

    normalized = []
    for item_id in value:
        current = _required_string(item_id)
        if current is None:
            return False
        normalized.append(current)

    return (
        normalized == value
        and len(set(normalized)) == len(normalized)
    )


def _canonical_reasons(value):
    if not isinstance(value, list) or not value:
        return None

    normalized = []
    for reason in value:
        current = _required_string(reason)
        if current is None:
            return None
        normalized.append(current)

    if normalized != value:
        return None

    return normalized


def _required_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _blocked(code, source):
    safe_source = source if isinstance(source, dict) else {}
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_BLOCKED",
        "outcome_id": None,
        "observation_id": safe_source.get("observation_id"),
        "user_action_checklist_status_id":
            safe_source.get("user_action_checklist_status_id"),
        "user_action_checklist_id":
            safe_source.get("user_action_checklist_id"),
        "user_action_guidance_id":
            safe_source.get("user_action_guidance_id"),
        "decision_persistence_verification_id":
            safe_source.get("decision_persistence_verification_id"),
        "decision_persistence_application_id":
            safe_source.get("decision_persistence_application_id"),
        "sku": safe_source.get("sku"),
        "verified_recorded_at": None,
        "decision_persistence_verified": False,
        "causal_claim_allowed": False,
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
