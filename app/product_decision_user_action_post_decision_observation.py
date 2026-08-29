from copy import deepcopy


def build_product_decision_user_action_post_decision_observation(checklist_status, later_decision):
    source = deepcopy(dict(checklist_status or {}))
    decision = deepcopy(dict(later_decision or {}))
    checklist_id = str(source.get("user_action_checklist_id") or "").strip()
    sku = str(source.get("sku") or "").strip()
    if not checklist_id or not sku:
        return _blocked("POST_DECISION_OBSERVATION_CONTEXT_REQUIRED", source)
    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_READY":
        return _blocked("POST_DECISION_OBSERVATION_CHECKLIST_STATUS_INVALID", source)
    if source.get("aggregate_status") != "USER_REPORTED_COMPLETE":
        return _blocked("POST_DECISION_OBSERVATION_COMPLETE_REPORT_REQUIRED", source)
    if source.get("externally_verified") is not False or source.get("executed") is not False:
        return _blocked("POST_DECISION_OBSERVATION_SAFETY_BOUNDARY_VIOLATION", source)
    if not isinstance(decision, dict) or decision.get("error"):
        return _blocked("POST_DECISION_OBSERVATION_LATER_DECISION_REQUIRED", source)
    if str(decision.get("sku") or "").strip() != sku:
        return _blocked("POST_DECISION_OBSERVATION_SKU_MISMATCH", source)
    if not decision.get("decision_type") or not decision.get("priority"):
        return _blocked("POST_DECISION_OBSERVATION_LATER_DECISION_INVALID", source)
    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVED",
        "observation_id": "product-decision-user-action-post-decision-observation:" + checklist_id,
        "user_action_checklist_id": checklist_id,
        "sku": sku,
        "aggregate_status": "USER_REPORTED_COMPLETE",
        "later_decision_type": decision.get("decision_type"),
        "later_priority": decision.get("priority"),
        "later_confidence": decision.get("confidence"),
        "later_reasons": list(decision.get("reasons") or []),
        "observation_only": True,
        "causal_claim_allowed": False,
        "externally_verified": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_POST_DECISION_OBSERVATION_BLOCKED",
        "observation_id": None,
        "user_action_checklist_id": source.get("user_action_checklist_id"),
        "sku": source.get("sku"),
        "observation_only": True,
        "causal_claim_allowed": False,
        "externally_verified": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
