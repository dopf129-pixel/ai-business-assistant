from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_evidence_application_preview(
    draft,
    eligibility,
    freshness_service,
    readiness_service,
):
    source = deepcopy(draft or {})
    eligible = deepcopy(eligibility or {})

    context_error = _context_error(source, eligible)
    if context_error:
        return _blocked(source, eligible, context_error)

    if eligible.get("status") != "ELIGIBLE_FOR_APPLICATION_REVIEW":
        return _blocked(source, eligible, "APPLICATION_NOT_ELIGIBLE")
    if eligible.get("application_eligible") is not True:
        return _blocked(source, eligible, "APPLICATION_NOT_ELIGIBLE")
    if eligible.get("application_review_required") is not True:
        return _blocked(source, eligible, "APPLICATION_REVIEW_NOT_REQUIRED")
    if eligible.get("application_allowed") is not False:
        return _blocked(source, eligible, "APPLICATION_BOUNDARY_VIOLATION")
    if eligible.get("application_started") is not False:
        return _blocked(source, eligible, "APPLICATION_ALREADY_STARTED")
    if eligible.get("persistent") is not False:
        return _blocked(source, eligible, "ELIGIBILITY_PERSISTENCE_BOUNDARY_VIOLATION")
    if eligible.get("source_freshness_proven") is not False:
        return _blocked(source, eligible, "ELIGIBILITY_FRESHNESS_BOUNDARY_VIOLATION")
    if any(eligible.get(field) is not False for field in (
        "product_decision_recomputed",
        "product_decision_mutated",
        "task_draft_mutated",
        "execution_allowed",
        "execution_ready",
        "executed",
    )):
        return _blocked(source, eligible, "ELIGIBILITY_SAFETY_BOUNDARY_VIOLATION")

    evidence = _safe_evidence(eligible.get("approved_evidence"))
    if not evidence:
        return _blocked(source, eligible, "APPROVED_EVIDENCE_REQUIRED")
    if evidence != eligible.get("approved_evidence"):
        return _blocked(source, eligible, "APPROVED_EVIDENCE_UNSAFE")
    if eligible.get("approved_evidence_count") != len(evidence):
        return _blocked(source, eligible, "APPROVED_EVIDENCE_COUNT_MISMATCH")
    if freshness_service is None:
        return _blocked(source, eligible, "FRESHNESS_SERVICE_REQUIRED")
    if readiness_service is None:
        return _blocked(source, eligible, "READINESS_SERVICE_REQUIRED")

    preview = deepcopy(source)
    for field, value in evidence.items():
        preview[field] = deepcopy(value)

    before_freshness = freshness_service.evaluate(source)
    after_freshness = freshness_service.evaluate(preview)
    before_readiness = readiness_service.evaluate(source)
    after_readiness = readiness_service.evaluate(preview)

    return {
        "error": False,
        "preview_id": "evidence-application-preview:" + str(eligible.get("eligibility_id")),
        "eligibility_id": eligible.get("eligibility_id"),
        "signal_id": eligible.get("signal_id"),
        "approval_id": eligible.get("approval_id"),
        "request_id": eligible.get("request_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "status": "APPLICATION_PREVIEW_READY",
        "preview_only": True,
        "applied_evidence": evidence,
        "before_freshness": before_freshness,
        "after_freshness": after_freshness,
        "before_readiness": before_readiness,
        "after_readiness": after_readiness,
        "application_allowed": False,
        "application_started": False,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _context_error(source, eligible):
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()
    eligible_draft_id = str(eligible.get("draft_id") or "").strip()
    eligible_sku = str(eligible.get("sku") or "").strip()
    eligibility_id = str(eligible.get("eligibility_id") or "").strip()
    signal_id = str(eligible.get("signal_id") or "").strip()
    approval_id = str(eligible.get("approval_id") or "").strip()
    request_id = str(eligible.get("request_id") or "").strip()

    if not all((draft_id, sku, eligible_draft_id, eligible_sku, eligibility_id, signal_id, approval_id, request_id)):
        return "APPLICATION_PREVIEW_CONTEXT_REQUIRED"
    if draft_id != eligible_draft_id:
        return "DRAFT_ID_MISMATCH"
    if sku != eligible_sku:
        return "SKU_MISMATCH"
    if request_id != "refresh:" + draft_id:
        return "REQUEST_ID_MISMATCH"
    if approval_id != "evidence-approval:" + draft_id:
        return "APPROVAL_ID_MISMATCH"
    if signal_id != "evidence-signal:" + approval_id:
        return "SIGNAL_ID_MISMATCH"
    if eligibility_id != "evidence-eligibility:" + signal_id:
        return "ELIGIBILITY_ID_MISMATCH"
    return None


def _safe_evidence(values):
    if not isinstance(values, dict):
        return {}
    return {
        field: deepcopy(value)
        for field, value in values.items()
        if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
    }


def _blocked(source, eligible, code):
    return {
        "error": True,
        "code": code,
        "preview_id": None,
        "eligibility_id": eligible.get("eligibility_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "status": "APPLICATION_PREVIEW_BLOCKED",
        "preview_only": True,
        "applied_evidence": {},
        "application_allowed": False,
        "application_started": False,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
