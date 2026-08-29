from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_evidence_application_authorization(application_preview):
    preview = deepcopy(application_preview or {})

    context_error = _context_error(preview)
    if context_error:
        return _blocked(preview, context_error)

    if preview.get("status") != "APPLICATION_PREVIEW_READY":
        return _blocked(preview, "APPLICATION_PREVIEW_NOT_READY")
    if preview.get("preview_only") is not True:
        return _blocked(preview, "APPLICATION_PREVIEW_NOT_READ_ONLY")
    if preview.get("application_allowed") is not False:
        return _blocked(preview, "APPLICATION_BOUNDARY_VIOLATION")
    if preview.get("application_started") is not False:
        return _blocked(preview, "APPLICATION_ALREADY_STARTED")
    if preview.get("persistent") is not False:
        return _blocked(preview, "PREVIEW_PERSISTENCE_BOUNDARY_VIOLATION")
    if preview.get("source_freshness_proven") is not False:
        return _blocked(preview, "PREVIEW_FRESHNESS_BOUNDARY_VIOLATION")
    if any(preview.get(field) is not False for field in (
        "product_decision_recomputed",
        "product_decision_mutated",
        "task_draft_mutated",
        "execution_allowed",
        "execution_ready",
        "executed",
    )):
        return _blocked(preview, "PREVIEW_SAFETY_BOUNDARY_VIOLATION")

    evidence = _safe_evidence(preview.get("applied_evidence"))
    if not evidence:
        return _blocked(preview, "APPLIED_EVIDENCE_REQUIRED")
    if evidence != preview.get("applied_evidence"):
        return _blocked(preview, "APPLIED_EVIDENCE_UNSAFE")

    after_freshness = preview.get("after_freshness")
    if not isinstance(after_freshness, dict):
        return _blocked(preview, "AFTER_FRESHNESS_REQUIRED")
    if after_freshness.get("status") != "FRESH":
        return _blocked(preview, "AFTER_FRESHNESS_NOT_FRESH")
    if after_freshness.get("execution_ready") is not False:
        return _blocked(preview, "AFTER_FRESHNESS_EXECUTION_BOUNDARY_VIOLATION")
    if after_freshness.get("executed") is not False:
        return _blocked(preview, "AFTER_FRESHNESS_EXECUTION_BOUNDARY_VIOLATION")

    after_readiness = preview.get("after_readiness")
    if not isinstance(after_readiness, dict):
        return _blocked(preview, "AFTER_READINESS_REQUIRED")
    if after_readiness.get("review_ready") is not True:
        return _blocked(preview, "AFTER_READINESS_NOT_READY")
    if after_readiness.get("review_status") != "READY_FOR_REVIEW":
        return _blocked(preview, "AFTER_READINESS_NOT_READY")
    if after_readiness.get("execution_ready") is not False:
        return _blocked(preview, "AFTER_READINESS_EXECUTION_BOUNDARY_VIOLATION")
    if after_readiness.get("executed") is not False:
        return _blocked(preview, "AFTER_READINESS_EXECUTION_BOUNDARY_VIOLATION")

    return {
        "error": False,
        "authorization_id": "evidence-application-authorization:" + str(preview.get("preview_id")),
        "preview_id": preview.get("preview_id"),
        "eligibility_id": preview.get("eligibility_id"),
        "signal_id": preview.get("signal_id"),
        "approval_id": preview.get("approval_id"),
        "request_id": preview.get("request_id"),
        "draft_id": preview.get("draft_id"),
        "sku": preview.get("sku"),
        "status": "APPLICATION_AUTHORIZATION_REQUIRED",
        "authorization_ready": True,
        "authorization_required": True,
        "authorization_granted": False,
        "application_allowed": False,
        "application_started": False,
        "authorized_evidence": evidence,
        "authorized_evidence_count": len(evidence),
        "validated_freshness_status": "FRESH",
        "validated_review_status": "READY_FOR_REVIEW",
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _context_error(preview):
    draft_id = str(preview.get("draft_id") or "").strip()
    sku = str(preview.get("sku") or "").strip()
    request_id = str(preview.get("request_id") or "").strip()
    approval_id = str(preview.get("approval_id") or "").strip()
    signal_id = str(preview.get("signal_id") or "").strip()
    eligibility_id = str(preview.get("eligibility_id") or "").strip()
    preview_id = str(preview.get("preview_id") or "").strip()

    if not all((draft_id, sku, request_id, approval_id, signal_id, eligibility_id, preview_id)):
        return "APPLICATION_AUTHORIZATION_CONTEXT_REQUIRED"
    if request_id != "refresh:" + draft_id:
        return "REQUEST_ID_MISMATCH"
    if approval_id != "evidence-approval:" + draft_id:
        return "APPROVAL_ID_MISMATCH"
    if signal_id != "evidence-signal:" + approval_id:
        return "SIGNAL_ID_MISMATCH"
    if eligibility_id != "evidence-eligibility:" + signal_id:
        return "ELIGIBILITY_ID_MISMATCH"
    if preview_id != "evidence-application-preview:" + eligibility_id:
        return "PREVIEW_ID_MISMATCH"
    return None


def _safe_evidence(values):
    if not isinstance(values, dict):
        return {}
    return {
        field: deepcopy(value)
        for field, value in values.items()
        if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
    }


def _blocked(preview, code):
    return {
        "error": True,
        "code": code,
        "authorization_id": None,
        "preview_id": preview.get("preview_id"),
        "eligibility_id": preview.get("eligibility_id"),
        "signal_id": preview.get("signal_id"),
        "approval_id": preview.get("approval_id"),
        "request_id": preview.get("request_id"),
        "draft_id": preview.get("draft_id"),
        "sku": preview.get("sku"),
        "status": "APPLICATION_AUTHORIZATION_BLOCKED",
        "authorization_ready": False,
        "authorization_required": False,
        "authorization_granted": False,
        "application_allowed": False,
        "application_started": False,
        "authorized_evidence": {},
        "authorized_evidence_count": 0,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
