from copy import deepcopy


AUTHORIZED_FIELDS = {
    "decision_type",
    "priority",
    "confidence",
    "reasons",
}


def build_product_decision_persistence_application_readiness(authorization):
    source = deepcopy(dict(authorization or {}))
    authorization_id = str(
        source.get("decision_persistence_authorization_id") or ""
    ).strip()
    eligibility_id = str(
        source.get("decision_persistence_eligibility_id") or ""
    ).strip()
    review_id = str(source.get("decision_preview_review_id") or "").strip()
    delta_id = str(source.get("decision_preview_delta_id") or "").strip()
    preview_id = str(source.get("recompute_preview_id") or "").strip()
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if (
        not authorization_id
        or not eligibility_id
        or not review_id
        or not delta_id
        or not preview_id
        or not draft_id
        or not sku
    ):
        return _blocked("DECISION_PERSISTENCE_APPLICATION_CONTEXT_REQUIRED", source)
    if authorization_id != "product-decision-persistence-authorization:" + eligibility_id:
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_ID_MISMATCH", source)
    if eligibility_id != "product-decision-persistence-eligibility:" + review_id:
        return _blocked("DECISION_PERSISTENCE_ELIGIBILITY_ID_MISMATCH", source)
    if review_id != "product-decision-preview-review:" + delta_id:
        return _blocked("DECISION_PREVIEW_REVIEW_ID_MISMATCH", source)
    if delta_id != "product-decision-preview-delta:" + preview_id:
        return _blocked("DECISION_PREVIEW_DELTA_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_PERSISTENCE_AUTHORIZED":
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_STATUS_INVALID", source)
    if source.get("decision") != "AUTHORIZE":
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_DECISION_MISMATCH", source)
    if source.get("decision_persistence_authorized") is not True:
        return _blocked("DECISION_PERSISTENCE_NOT_AUTHORIZED", source)
    if source.get("decision_persistence_rejected") is not False:
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_REJECTED", source)
    if source.get("decision_persistence_allowed") is not True:
        return _blocked("DECISION_PERSISTENCE_PERMISSION_REQUIRED", source)
    if (
        source.get("persistent") is not False
        or source.get("product_decision_recomputed") is not True
        or source.get("product_decision_mutated") is not False
        or source.get("product_decision_persisted") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("DECISION_PERSISTENCE_APPLICATION_SAFETY_BOUNDARY_VIOLATION", source)

    changed_fields = list(source.get("authorized_changed_fields") or [])
    changes = source.get("authorized_changes")
    preview_decision = source.get("authorized_preview_decision")
    if not changed_fields or not isinstance(changes, dict):
        return _blocked("DECISION_PERSISTENCE_APPLICATION_CHANGES_REQUIRED", source)
    if any(field not in AUTHORIZED_FIELDS for field in changed_fields):
        return _blocked("DECISION_PERSISTENCE_APPLICATION_CHANGES_UNSAFE", source)
    if set(changes) != set(changed_fields):
        return _blocked("DECISION_PERSISTENCE_APPLICATION_CHANGE_SET_MISMATCH", source)
    if not isinstance(preview_decision, dict):
        return _blocked("DECISION_PERSISTENCE_APPLICATION_PREVIEW_REQUIRED", source)
    if str(preview_decision.get("sku") or "").strip() != sku:
        return _blocked("DECISION_PERSISTENCE_APPLICATION_PREVIEW_SKU_MISMATCH", source)
    if not preview_decision.get("decision_type") or not preview_decision.get("priority"):
        return _blocked("DECISION_PERSISTENCE_APPLICATION_PREVIEW_INVALID", source)

    for field in changed_fields:
        change = changes.get(field)
        if not isinstance(change, dict) or "after" not in change:
            return _blocked("DECISION_PERSISTENCE_APPLICATION_CHANGE_INVALID", source)
        expected = _normalized_value(field, preview_decision.get(field))
        actual = _normalized_value(field, change.get("after"))
        if actual != expected:
            return _blocked("DECISION_PERSISTENCE_APPLICATION_CHANGE_PREVIEW_MISMATCH", source)

    readiness_id = "product-decision-persistence-application-readiness:" + authorization_id
    return {
        "error": False,
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY",
        "decision_persistence_application_readiness_id": readiness_id,
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": draft_id,
        "sku": sku,
        "decision_persistence_allowed": True,
        "decision_persistence_application_ready": True,
        "decision_persistence_application_started": False,
        "ready_changed_fields": deepcopy(changed_fields),
        "ready_changes": deepcopy(changes),
        "ready_preview_decision": deepcopy(preview_decision),
        "persistent": False,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _normalized_value(field, value):
    if field == "reasons":
        return list(value or [])
    return value


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLICATION_BLOCKED",
        "decision_persistence_application_readiness_id": None,
        "decision_persistence_authorization_id": source.get(
            "decision_persistence_authorization_id"
        ),
        "decision_persistence_eligibility_id": source.get(
            "decision_persistence_eligibility_id"
        ),
        "decision_preview_review_id": source.get("decision_preview_review_id"),
        "decision_preview_delta_id": source.get("decision_preview_delta_id"),
        "recompute_preview_id": source.get("recompute_preview_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "decision_persistence_allowed": False,
        "decision_persistence_application_ready": False,
        "decision_persistence_application_started": False,
        "ready_changed_fields": [],
        "ready_changes": {},
        "ready_preview_decision": None,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
