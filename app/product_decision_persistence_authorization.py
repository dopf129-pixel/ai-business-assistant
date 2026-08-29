from copy import deepcopy


REVIEWABLE_FIELDS = {
    "decision_type",
    "priority",
    "confidence",
    "reasons",
}


def build_product_decision_persistence_authorization(eligibility, decision):
    source = deepcopy(dict(eligibility or {}))
    normalized_decision = str(decision or "").strip().upper()
    eligibility_id = str(source.get("decision_persistence_eligibility_id") or "").strip()
    review_id = str(source.get("decision_preview_review_id") or "").strip()
    delta_id = str(source.get("decision_preview_delta_id") or "").strip()
    preview_id = str(source.get("recompute_preview_id") or "").strip()
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if normalized_decision not in {"AUTHORIZE", "REJECT"}:
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_DECISION_INVALID", source)
    if not eligibility_id or not review_id or not delta_id or not preview_id or not draft_id or not sku:
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_CONTEXT_REQUIRED", source)
    if eligibility_id != "product-decision-persistence-eligibility:" + review_id:
        return _blocked("DECISION_PERSISTENCE_ELIGIBILITY_ID_MISMATCH", source)
    if review_id != "product-decision-preview-review:" + delta_id:
        return _blocked("DECISION_PREVIEW_REVIEW_ID_MISMATCH", source)
    if delta_id != "product-decision-preview-delta:" + preview_id:
        return _blocked("DECISION_PREVIEW_DELTA_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_PERSISTENCE_ELIGIBLE":
        return _blocked("DECISION_PERSISTENCE_ELIGIBILITY_STATUS_INVALID", source)
    if source.get("decision_persistence_eligible") is not True:
        return _blocked("DECISION_PERSISTENCE_NOT_ELIGIBLE", source)
    if source.get("decision_persistence_review_required") is not True:
        return _blocked("DECISION_PERSISTENCE_REVIEW_NOT_REQUIRED", source)
    if source.get("decision_persistence_allowed") is not False:
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_BOUNDARY_VIOLATION", source)
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
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_SAFETY_BOUNDARY_VIOLATION", source)

    changed_fields = list(source.get("eligible_changed_fields") or [])
    changes = source.get("eligible_changes")
    preview_decision = source.get("eligible_preview_decision")
    if not changed_fields or not isinstance(changes, dict):
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_CHANGES_REQUIRED", source)
    if any(field not in REVIEWABLE_FIELDS for field in changed_fields):
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_CHANGES_UNSAFE", source)
    if set(changes) != set(changed_fields):
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_CHANGE_SET_MISMATCH", source)
    if not isinstance(preview_decision, dict):
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_PREVIEW_REQUIRED", source)
    if str(preview_decision.get("sku") or "").strip() != sku:
        return _blocked("DECISION_PERSISTENCE_AUTHORIZATION_PREVIEW_SKU_MISMATCH", source)

    authorization_id = "product-decision-persistence-authorization:" + eligibility_id
    authorized = normalized_decision == "AUTHORIZE"
    return {
        "error": False,
        "status": (
            "PRODUCT_DECISION_PERSISTENCE_AUTHORIZED"
            if authorized
            else "PRODUCT_DECISION_PERSISTENCE_REJECTED"
        ),
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": draft_id,
        "sku": sku,
        "decision": normalized_decision,
        "decision_persistence_authorized": authorized,
        "decision_persistence_rejected": not authorized,
        "decision_persistence_allowed": authorized,
        "authorized_changed_fields": deepcopy(changed_fields),
        "authorized_changes": deepcopy(changes),
        "authorized_preview_decision": deepcopy(preview_decision),
        "persistent": False,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_PERSISTENCE_AUTHORIZATION_BLOCKED",
        "decision_persistence_authorization_id": None,
        "decision_persistence_eligibility_id": source.get("decision_persistence_eligibility_id"),
        "decision_preview_review_id": source.get("decision_preview_review_id"),
        "decision_preview_delta_id": source.get("decision_preview_delta_id"),
        "recompute_preview_id": source.get("recompute_preview_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "decision": None,
        "decision_persistence_authorized": False,
        "decision_persistence_rejected": False,
        "decision_persistence_allowed": False,
        "authorized_changed_fields": [],
        "authorized_changes": {},
        "authorized_preview_decision": None,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
