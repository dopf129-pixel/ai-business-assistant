from collections import Counter
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
ALLOWED_OUTCOME_TYPES = {
    "DECISION_CHANGED",
    "SAME_DECISION_LOWER_PRIORITY",
    "SAME_DECISION_HIGHER_PRIORITY",
    "NO_DECISION_CHANGE",
}
ALLOWED_PRIORITY_CHANGES = {
    "PRIORITY_DECREASED",
    "PRIORITY_INCREASED",
    "PRIORITY_UNCHANGED",
}


def build_product_decision_user_action_learning_summary(outcomes):
    if not isinstance(outcomes, list):
        return _blocked("LEARNING_SUMMARY_OUTCOMES_INPUT_INVALID")

    valid = []
    seen_outcome_ids = set()

    for raw_item in outcomes:
        if not isinstance(raw_item, dict):
            return _blocked("LEARNING_SUMMARY_OUTCOME_INVALID")

        item = deepcopy(raw_item)
        error = _validate_outcome(item)
        if error is not None:
            return _blocked(error)

        outcome_id = item["outcome_id"]
        if outcome_id in seen_outcome_ids:
            return _blocked("LEARNING_SUMMARY_OUTCOME_ID_DUPLICATE")
        seen_outcome_ids.add(outcome_id)
        valid.append(item)

    outcome_counts = Counter(
        item["outcome_type"]
        for item in valid
    )
    priority_counts = Counter(
        item["priority_change"]
        for item in valid
    )
    sku_counts = Counter(
        item["sku"]
        for item in valid
    )

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_READY",
        "observation_count": len(valid),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "priority_change_counts": dict(sorted(priority_counts.items())),
        "sku_count": len(sku_counts),
        "sku_observation_counts": dict(sorted(sku_counts.items())),
        "outcome_ids": [item["outcome_id"] for item in valid],
        "completion_evidence_source": "USER_REPORT",
        "learning_scope": "DESCRIPTIVE_OBSERVATIONS_ONLY",
        "causal_claim_allowed": False,
        "externally_verified": False,
        "persistent": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _validate_outcome(item):
    outcome_id = _required_string(item.get("outcome_id"))
    observation_id = _required_string(item.get("observation_id"))
    checklist_status_id = _required_string(
        item.get("user_action_checklist_status_id")
    )
    checklist_id = _required_string(
        item.get("user_action_checklist_id")
    )
    guidance_id = _required_string(
        item.get("user_action_guidance_id")
    )
    verification_id = _required_string(
        item.get("decision_persistence_verification_id")
    )
    application_id = _required_string(
        item.get("decision_persistence_application_id")
    )
    sku = _required_string(item.get("sku"))
    verified_recorded_at = _required_string(
        item.get("verified_recorded_at")
    )

    if not all(
        (
            outcome_id,
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
        return "LEARNING_SUMMARY_OUTCOME_CONTEXT_REQUIRED"

    if (
        outcome_id
        != "product-decision-user-action-post-decision-outcome:"
        + observation_id
    ):
        return "LEARNING_SUMMARY_OUTCOME_ID_MISMATCH"

    if (
        observation_id
        != "product-decision-user-action-post-decision-observation:"
        + checklist_id
    ):
        return "LEARNING_SUMMARY_OBSERVATION_ID_MISMATCH"

    if (
        checklist_status_id
        != "product-decision-user-action-checklist-status:" + checklist_id
    ):
        return "LEARNING_SUMMARY_CHECKLIST_STATUS_ID_MISMATCH"

    if (
        checklist_id
        != "product-decision-user-action-checklist:" + guidance_id
    ):
        return "LEARNING_SUMMARY_CHECKLIST_ID_MISMATCH"

    if (
        guidance_id
        != "product-decision-user-action-guidance:" + verification_id
    ):
        return "LEARNING_SUMMARY_GUIDANCE_ID_MISMATCH"

    if (
        verification_id
        != "product-decision-persistence-verification:" + application_id
    ):
        return "LEARNING_SUMMARY_VERIFICATION_ID_MISMATCH"

    if (
        item.get("error") is not False
        or item.get("status")
        != "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OUTCOME_READY"
    ):
        return "LEARNING_SUMMARY_OUTCOME_RESULT_INVALID"

    if item.get("decision_persistence_verified") is not True:
        return "LEARNING_SUMMARY_VERIFICATION_REQUIRED"

    if (
        item.get("aggregate_status") != "USER_REPORTED_COMPLETE"
        or item.get("completion_evidence_source") != "USER_REPORT"
    ):
        return "LEARNING_SUMMARY_COMPLETION_EVIDENCE_INVALID"

    item_count = item.get("item_count")
    reported_count = item.get("reported_count")
    completed_count = item.get("completed_count")
    reported_item_ids = item.get("reported_item_ids")
    completed_item_ids = item.get("completed_item_ids")

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
        return "LEARNING_SUMMARY_COMPLETION_EVIDENCE_INVALID"

    if (
        item.get("interpretation") != "OBSERVED_AFTER_USER_REPORT"
        or item.get("observation_only") is not True
        or item.get("causal_claim_allowed") is not False
        or item.get("externally_verified") is not False
        or item.get("persistent") is not False
        or item.get("checklist_mutated") is not False
        or item.get("ozon_mutation_called") is not False
        or item.get("execution_allowed") is not False
        or item.get("execution_ready") is not False
        or item.get("executed") is not False
    ):
        return "LEARNING_SUMMARY_OUTCOME_SAFETY_INVALID"

    prior_type = _required_string(item.get("prior_decision_type"))
    later_type = _required_string(item.get("later_decision_type"))
    prior_priority = _required_string(item.get("prior_priority"))
    later_priority = _required_string(item.get("later_priority"))
    prior_confidence = _required_string(item.get("prior_confidence"))
    later_confidence = _required_string(item.get("later_confidence"))
    prior_reasons = _canonical_reasons(item.get("prior_reasons"))
    later_reasons = _canonical_reasons(item.get("later_reasons"))
    outcome_type = _required_string(item.get("outcome_type"))
    priority_change = _required_string(item.get("priority_change"))
    decision_changed = item.get("decision_changed")

    if (
        prior_type not in ALLOWED_DECISION_TYPES
        or later_type not in ALLOWED_DECISION_TYPES
        or prior_priority not in PRIORITY_RANK
        or later_priority not in PRIORITY_RANK
        or prior_confidence not in ALLOWED_CONFIDENCE
        or later_confidence not in ALLOWED_CONFIDENCE
        or prior_reasons is None
        or later_reasons is None
        or outcome_type not in ALLOWED_OUTCOME_TYPES
        or priority_change not in ALLOWED_PRIORITY_CHANGES
        or type(decision_changed) is not bool
    ):
        return "LEARNING_SUMMARY_OUTCOME_CLASSIFICATION_INVALID"

    expected_changed = prior_type != later_type
    delta = PRIORITY_RANK[later_priority] - PRIORITY_RANK[prior_priority]

    if delta < 0:
        expected_priority_change = "PRIORITY_DECREASED"
    elif delta > 0:
        expected_priority_change = "PRIORITY_INCREASED"
    else:
        expected_priority_change = "PRIORITY_UNCHANGED"

    if expected_changed:
        expected_outcome_type = "DECISION_CHANGED"
    elif delta < 0:
        expected_outcome_type = "SAME_DECISION_LOWER_PRIORITY"
    elif delta > 0:
        expected_outcome_type = "SAME_DECISION_HIGHER_PRIORITY"
    else:
        expected_outcome_type = "NO_DECISION_CHANGE"

    if (
        decision_changed is not expected_changed
        or priority_change != expected_priority_change
        or outcome_type != expected_outcome_type
    ):
        return "LEARNING_SUMMARY_OUTCOME_CLASSIFICATION_MISMATCH"

    return None


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


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_BLOCKED",
        "observation_count": 0,
        "outcome_counts": {},
        "priority_change_counts": {},
        "sku_count": 0,
        "sku_observation_counts": {},
        "outcome_ids": [],
        "completion_evidence_source": "USER_REPORT",
        "learning_scope": "DESCRIPTIVE_OBSERVATIONS_ONLY",
        "causal_claim_allowed": False,
        "externally_verified": False,
        "persistent": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
