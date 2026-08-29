from copy import deepcopy


COMPARABLE_FIELDS = {
    "decision_type",
    "priority",
    "confidence",
    "reasons",
}


def build_product_decision_preview_review(delta, decision):
    source = deepcopy(dict(delta or {}))
    normalized_decision = str(decision or "").strip().upper()
    delta_id = str(source.get("decision_preview_delta_id") or "").strip()
    preview_id = str(source.get("recompute_preview_id") or "").strip()
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if normalized_decision not in {"ACCEPT", "REJECT"}:
        return _blocked("DECISION_PREVIEW_REVIEW_DECISION_INVALID", source)
    if not delta_id or not preview_id or not draft_id or not sku:
        return _blocked("DECISION_PREVIEW_REVIEW_CONTEXT_REQUIRED", source)
    if delta_id != "product-decision-preview-delta:" + preview_id:
        return _blocked("DECISION_PREVIEW_DELTA_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_PREVIEW_DELTA_READY":
        return _blocked("DECISION_PREVIEW_DELTA_STATUS_INVALID", source)
    if source.get("decision_changed") is not True:
        return _blocked("DECISION_PREVIEW_DELTA_NO_CHANGE", source)
    if (
        source.get("persistent") is not False
        or source.get("task_draft_mutated") is not False
        or source.get("product_decision_recomputed") is not True
        or source.get("product_decision_mutated") is not False
        or source.get("product_decision_persisted") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("DECISION_PREVIEW_REVIEW_SAFETY_BOUNDARY_VIOLATION", source)

    changed_fields = list(source.get("changed_fields") or [])
    changes = source.get("changes")
    if not changed_fields or not isinstance(changes, dict):
        return _blocked("DECISION_PREVIEW_REVIEW_CHANGES_REQUIRED", source)
    if any(field not in COMPARABLE_FIELDS for field in changed_fields):
        return _blocked("DECISION_PREVIEW_REVIEW_CHANGES_UNSAFE", source)
    if source.get("changed_field_count") != len(changed_fields):
        return _blocked("DECISION_PREVIEW_REVIEW_CHANGE_COUNT_MISMATCH", source)
    if set(changes) != set(changed_fields):
        return _blocked("DECISION_PREVIEW_REVIEW_CHANGE_SET_MISMATCH", source)

    current = source.get("current_decision")
    preview = source.get("preview_decision")
    if not isinstance(current, dict) or not isinstance(preview, dict):
        return _blocked("DECISION_PREVIEW_REVIEW_DECISIONS_REQUIRED", source)
    if str(current.get("sku") or "").strip() != sku:
        return _blocked("DECISION_PREVIEW_REVIEW_CURRENT_SKU_MISMATCH", source)
    if str(preview.get("sku") or "").strip() != sku:
        return _blocked("DECISION_PREVIEW_REVIEW_PREVIEW_SKU_MISMATCH", source)

    review_id = "product-decision-preview-review:" + delta_id
    accepted = normalized_decision == "ACCEPT"
    return {
        "error": False,
        "status": (
            "PRODUCT_DECISION_PREVIEW_REVIEW_ACCEPTED"
            if accepted
            else "PRODUCT_DECISION_PREVIEW_REVIEW_REJECTED"
        ),
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": draft_id,
        "sku": sku,
        "decision": normalized_decision,
        "decision_review_accepted": accepted,
        "decision_review_rejected": not accepted,
        "reviewed_changed_fields": deepcopy(changed_fields),
        "reviewed_changes": deepcopy(changes),
        "reviewed_preview_decision": deepcopy(preview),
        "persistent": False,
        "decision_persistence_allowed": False,
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
        "status": "PRODUCT_DECISION_PREVIEW_REVIEW_BLOCKED",
        "decision_preview_review_id": None,
        "decision_preview_delta_id": source.get("decision_preview_delta_id"),
        "recompute_preview_id": source.get("recompute_preview_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "decision": None,
        "decision_review_accepted": False,
        "decision_review_rejected": False,
        "reviewed_changed_fields": [],
        "reviewed_changes": {},
        "reviewed_preview_decision": None,
        "persistent": False,
        "decision_persistence_allowed": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
