from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_evidence_approval_contract(
    draft,
    evidence_candidate,
    validation_preview,
):
    source = deepcopy(draft or {})
    candidate = deepcopy(evidence_candidate or {})
    preview = deepcopy(validation_preview or {})

    identity_error = _identity_error(source, candidate, preview)
    if identity_error:
        return _blocked(source, candidate, identity_error)

    if preview.get("status") != "PREVIEW_READY":
        return _blocked(source, candidate, "VALIDATION_PREVIEW_NOT_READY")

    if preview.get("preview_only") is not True:
        return _blocked(source, candidate, "VALIDATION_PREVIEW_NOT_READ_ONLY")

    if (
        preview.get("preview_freshness_validated") is not True
        or preview.get("preview_freshness_status") != "FRESH"
    ):
        return _blocked(source, candidate, "FRESHNESS_NOT_VALIDATED")

    candidate_evidence = _allowed_evidence(
        candidate.get("evidence_update") or {}
    )
    preview_evidence = _allowed_evidence(
        preview.get("applied_evidence") or {}
    )

    if not candidate_evidence:
        return _blocked(source, candidate, "EVIDENCE_UPDATE_REQUIRED")

    if candidate_evidence != preview_evidence:
        return _blocked(source, candidate, "VALIDATED_EVIDENCE_MISMATCH")

    approval_id = "evidence-approval:" + str(source.get("draft_id"))
    return {
        "error": False,
        "approval_id": approval_id,
        "request_id": candidate.get("request_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "status": "APPROVAL_REQUIRED",
        "approval_ready": True,
        "approval_required": True,
        "approval_granted": False,
        "application_allowed": False,
        "validated_evidence": candidate_evidence,
        "validated_evidence_count": len(candidate_evidence),
        "preview_freshness_status": preview.get("preview_freshness_status"),
        "freshness_guard_validated": True,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _identity_error(source, candidate, preview):
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()
    candidate_draft_id = str(candidate.get("draft_id") or "").strip()
    candidate_sku = str(candidate.get("sku") or "").strip()
    preview_draft_id = str(preview.get("draft_id") or "").strip()
    preview_sku = str(preview.get("sku") or "").strip()
    candidate_request_id = str(candidate.get("request_id") or "").strip()
    preview_request_id = str(preview.get("request_id") or "").strip()

    if not all((
        draft_id,
        sku,
        candidate_draft_id,
        candidate_sku,
        preview_draft_id,
        preview_sku,
        candidate_request_id,
        preview_request_id,
    )):
        return "CONTEXT_IDENTITY_REQUIRED"
    if candidate_draft_id != draft_id or preview_draft_id != draft_id:
        return "DRAFT_ID_MISMATCH"
    if candidate_sku != sku or preview_sku != sku:
        return "SKU_MISMATCH"
    if candidate_request_id != preview_request_id:
        return "REQUEST_ID_MISMATCH"
    return None


def _allowed_evidence(values):
    return {
        field: deepcopy(value)
        for field, value in dict(values or {}).items()
        if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
    }


def _blocked(source, candidate, code):
    return {
        "error": True,
        "code": code,
        "approval_id": None,
        "request_id": candidate.get("request_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "status": "APPROVAL_BLOCKED",
        "approval_ready": False,
        "approval_required": False,
        "approval_granted": False,
        "application_allowed": False,
        "validated_evidence": {},
        "validated_evidence_count": 0,
        "freshness_guard_validated": False,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
