from copy import deepcopy


ALLOWED_DECISION_TYPES = {
    "REPLENISH_HIGH_PRIORITY",
    "REPLENISH_NORMAL",
    "WATCH_LOW_MARGIN",
    "INVESTIGATE_LOW_PROFIT",
    "HOLD_STOCK",
    "INSUFFICIENT_DATA",
}
ALLOWED_PRIORITIES = {"CRITICAL", "HIGH", "NORMAL", "LOW", "NONE"}
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


def build_product_decision_user_action_post_decision_observation(
    checklist_status,
    later_decision,
):
    if not isinstance(checklist_status, dict):
        return _blocked(
            "POST_DECISION_OBSERVATION_CHECKLIST_INPUT_INVALID",
            {},
        )

    source = deepcopy(checklist_status)

    if not isinstance(later_decision, dict):
        return _blocked(
            "POST_DECISION_OBSERVATION_LATER_DECISION_REQUIRED",
            source,
        )

    decision = deepcopy(later_decision)

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
            "POST_DECISION_OBSERVATION_CONTEXT_REQUIRED",
            source,
        )

    if (
        checklist_status_id
        != "product-decision-user-action-checklist-status:" + checklist_id
    ):
        return _blocked(
            "POST_DECISION_OBSERVATION_STATUS_ID_MISMATCH",
            source,
        )

    if (
        checklist_id
        != "product-decision-user-action-checklist:" + guidance_id
    ):
        return _blocked(
            "POST_DECISION_OBSERVATION_CHECKLIST_ID_MISMATCH",
            source,
        )

    if (
        guidance_id
        != "product-decision-user-action-guidance:" + verification_id
    ):
        return _blocked(
            "POST_DECISION_OBSERVATION_GUIDANCE_ID_MISMATCH",
            source,
        )

    if (
        verification_id
        != "product-decision-persistence-verification:" + application_id
    ):
        return _blocked(
            "POST_DECISION_OBSERVATION_VERIFICATION_ID_MISMATCH",
            source,
        )

    if (
        source.get("error") is not False
        or source.get("status")
        != "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_READY"
    ):
        return _blocked(
            "POST_DECISION_OBSERVATION_CHECKLIST_STATUS_INVALID",
            source,
        )

    if source.get("decision_persistence_verified") is not True:
        return _blocked(
            "POST_DECISION_OBSERVATION_VERIFICATION_REQUIRED",
            source,
        )

    if source.get("aggregate_status") != "USER_REPORTED_COMPLETE":
        return _blocked(
            "POST_DECISION_OBSERVATION_COMPLETE_REPORT_REQUIRED",
            source,
        )

    if source.get("completion_evidence_source") != "USER_REPORT":
        return _blocked(
            "POST_DECISION_OBSERVATION_USER_REPORT_EVIDENCE_REQUIRED",
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
            "POST_DECISION_OBSERVATION_COMPLETE_REPORT_INVALID",
            source,
        )

    if any(
        (
            source.get("externally_verified") is not False,
            source.get("persistent") is not False,
            source.get("checklist_mutated") is not False,
            source.get("ozon_mutation_called") is not False,
            source.get("execution_allowed") is not False,
            source.get("execution_ready") is not False,
            source.get("executed") is not False,
        )
    ):
        return _blocked(
            "POST_DECISION_OBSERVATION_SAFETY_BOUNDARY_VIOLATION",
            source,
        )

    decision_error = decision.get("error")
    if type(decision_error) is not bool:
        return _blocked(
            "POST_DECISION_OBSERVATION_LATER_DECISION_RESULT_INVALID",
            source,
        )
    if decision_error is True:
        return _blocked(
            "POST_DECISION_OBSERVATION_LATER_DECISION_FAILED",
            source,
        )

    decision_sku = _required_string(decision.get("sku"))
    if not decision_sku:
        return _blocked(
            "POST_DECISION_OBSERVATION_LATER_DECISION_INVALID",
            source,
        )
    if decision_sku != sku:
        return _blocked(
            "POST_DECISION_OBSERVATION_SKU_MISMATCH",
            source,
        )

    decision_type = _required_string(
        decision.get("decision_type")
    )
    priority = _required_string(decision.get("priority"))
    confidence = _required_string(
        decision.get("confidence")
    )
    reasons = decision.get("reasons")

    if (
        decision_type not in ALLOWED_DECISION_TYPES
        or priority not in ALLOWED_PRIORITIES
        or confidence not in ALLOWED_CONFIDENCE
        or not isinstance(reasons, list)
        or any(
            _required_string(reason) is None
            for reason in reasons
        )
    ):
        return _blocked(
            "POST_DECISION_OBSERVATION_LATER_DECISION_INVALID",
            source,
        )

    return {
        "error": False,
        "status":
            "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED",
        "observation_id":
            "product-decision-user-action-post-decision-observation:"
            + checklist_id,
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
        "later_decision_type": decision_type,
        "later_priority": priority,
        "later_confidence": confidence,
        "later_reasons": deepcopy(reasons),
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
        "status":
            "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVATION_BLOCKED",
        "observation_id": None,
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
