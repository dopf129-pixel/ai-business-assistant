from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def apply_freshness_evidence_to_draft(draft, readiness):
    if not isinstance(draft, dict):
        return _blocked(readiness or {}, "DRAFT_REQUIRED")

    source = deepcopy(readiness or {})
    error = _validate(source, draft)
    if error:
        return _blocked(source, error)

    evidence = _safe_evidence(source.get("readiness_evidence"))
    before = {field: deepcopy(draft.get(field)) for field in evidence}
    changed_fields = [field for field, value in evidence.items() if draft.get(field) != value]

    for field, value in evidence.items():
        draft[field] = deepcopy(value)

    after = {field: deepcopy(draft.get(field)) for field in evidence}
    return {
        "error": False,
        "status": "FRESHNESS_EVIDENCE_APPLIED_TO_DRAFT",
        "application_readiness_id": source["application_readiness_id"],
        "draft_id": source["draft_id"],
        "sku": source["sku"],
        "applied_fields": list(evidence),
        "applied_field_count": len(evidence),
        "changed_fields": changed_fields,
        "changed_field_count": len(changed_fields),
        "idempotent_noop": not changed_fields,
        "audit": {
            "before": before,
            "after": after,
        },
        "task_draft_mutated": bool(changed_fields),
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _validate(source, draft):
    required = (
        "application_readiness_id",
        "permission_signal_id",
        "draft_id",
        "sku",
    )
    if any(not str(source.get(key) or "").strip() for key in required):
        return "DRAFT_APPLICATION_CONTEXT_REQUIRED"

    expected_readiness_id = "evidence-application-readiness:" + source["permission_signal_id"]
    if source["application_readiness_id"] != expected_readiness_id:
        return "APPLICATION_READINESS_ID_MISMATCH"
    if source.get("status") != "APPLICATION_READY_FOR_SEPARATE_STEP":
        return "APPLICATION_NOT_READY"
    if source.get("application_ready") is not True:
        return "APPLICATION_NOT_READY"
    if source.get("application_review_complete") is not True:
        return "APPLICATION_REVIEW_NOT_COMPLETE"
    if source.get("application_allowed") is not False or source.get("application_started") is not False:
        return "APPLICATION_BOUNDARY_VIOLATION"
    if source.get("persistent") is not False or source.get("source_freshness_proven") is not False:
        return "READINESS_BOUNDARY_VIOLATION"

    safety_fields = (
        "product_decision_recomputed",
        "product_decision_mutated",
        "task_draft_mutated",
        "execution_allowed",
        "execution_ready",
        "executed",
    )
    if any(source.get(field) is not False for field in safety_fields):
        return "READINESS_SAFETY_BOUNDARY_VIOLATION"

    if str(draft.get("draft_id") or "") != str(source["draft_id"]):
        return "DRAFT_ID_MISMATCH"
    if str(draft.get("sku") or "") != str(source["sku"]):
        return "DRAFT_SKU_MISMATCH"

    evidence = _safe_evidence(source.get("readiness_evidence"))
    if not evidence:
        return "READINESS_EVIDENCE_REQUIRED"
    if evidence != source.get("readiness_evidence"):
        return "READINESS_EVIDENCE_UNSAFE"
    if source.get("readiness_evidence_count") != len(evidence):
        return "READINESS_EVIDENCE_COUNT_MISMATCH"
    return None


def _safe_evidence(values):
    if not isinstance(values, dict):
        return {}
    return {
        field: deepcopy(value)
        for field, value in values.items()
        if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
    }


def _blocked(source, code):
    return {
        "error": True,
        "code": code,
        "status": "FRESHNESS_EVIDENCE_DRAFT_APPLICATION_BLOCKED",
        "application_readiness_id": source.get("application_readiness_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "applied_fields": [],
        "applied_field_count": 0,
        "changed_fields": [],
        "changed_field_count": 0,
        "idempotent_noop": False,
        "audit": {"before": {}, "after": {}},
        "task_draft_mutated": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
