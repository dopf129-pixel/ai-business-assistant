from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_recompute_review_authorization(eligibility, decision):
    source = dict(eligibility or {})
    normalized_decision = str(decision or "").strip().upper()
    eligibility_id = str(source.get("recompute_eligibility_id") or "").strip()
    promotion_id = str(source.get("freshness_promotion_id") or "").strip()
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if normalized_decision not in {"AUTHORIZE", "REJECT"}:
        return _blocked("RECOMPUTE_AUTHORIZATION_DECISION_INVALID", source)
    if not eligibility_id or not promotion_id or not draft_id or not sku:
        return _blocked("RECOMPUTE_AUTHORIZATION_CONTEXT_REQUIRED", source)
    if eligibility_id != "recompute-review-eligibility:" + promotion_id:
        return _blocked("RECOMPUTE_ELIGIBILITY_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_RECOMPUTE_REVIEW_ELIGIBLE":
        return _blocked("RECOMPUTE_ELIGIBILITY_STATUS_INVALID", source)
    if source.get("source_freshness_proven") is not True:
        return _blocked("SOURCE_FRESHNESS_NOT_PROVEN", source)
    if source.get("recompute_review_eligible") is not True:
        return _blocked("RECOMPUTE_REVIEW_NOT_ELIGIBLE", source)
    if source.get("recompute_review_required") is not True:
        return _blocked("RECOMPUTE_REVIEW_NOT_REQUIRED", source)
    if source.get("recompute_allowed") is not False or source.get("recompute_started") is not False:
        return _blocked("RECOMPUTE_AUTHORIZATION_BOUNDARY_VIOLATION", source)
    if (
        source.get("persistent") is not False
        or source.get("task_draft_mutated") is not False
        or source.get("product_decision_recomputed") is not False
        or source.get("product_decision_mutated") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("RECOMPUTE_AUTHORIZATION_SAFETY_BOUNDARY_VIOLATION", source)

    evidence = _safe_evidence(source.get("eligible_evidence"))
    if not evidence:
        return _blocked("ELIGIBLE_EVIDENCE_REQUIRED", source)
    if evidence != source.get("eligible_evidence"):
        return _blocked("ELIGIBLE_EVIDENCE_UNSAFE", source)
    if source.get("eligible_evidence_count") != len(evidence):
        return _blocked("ELIGIBLE_EVIDENCE_COUNT_MISMATCH", source)

    authorization_id = "recompute-review-authorization:" + eligibility_id
    if normalized_decision == "REJECT":
        return {
            "error": False,
            "status": "PRODUCT_DECISION_RECOMPUTE_REVIEW_REJECTED",
            "recompute_authorization_id": authorization_id,
            "recompute_eligibility_id": eligibility_id,
            "freshness_promotion_id": promotion_id,
            "draft_id": draft_id,
            "sku": sku,
            "decision": "REJECT",
            "recompute_authorized": False,
            "recompute_rejected": True,
            "recompute_allowed": False,
            "recompute_started": False,
            "authorization_evidence": deepcopy(evidence),
            "authorization_evidence_count": len(evidence),
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    return {
        "error": False,
        "status": "PRODUCT_DECISION_RECOMPUTE_REVIEW_AUTHORIZED",
        "recompute_authorization_id": authorization_id,
        "recompute_eligibility_id": eligibility_id,
        "freshness_promotion_id": promotion_id,
        "draft_id": draft_id,
        "sku": sku,
        "decision": "AUTHORIZE",
        "recompute_authorized": True,
        "recompute_rejected": False,
        "recompute_allowed": True,
        "recompute_started": False,
        "authorization_evidence": deepcopy(evidence),
        "authorization_evidence_count": len(evidence),
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _safe_evidence(values):
    if not isinstance(values, dict):
        return {}
    return {
        field: deepcopy(value)
        for field, value in values.items()
        if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
    }


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_RECOMPUTE_REVIEW_AUTHORIZATION_BLOCKED",
        "recompute_authorization_id": None,
        "recompute_eligibility_id": source.get("recompute_eligibility_id"),
        "freshness_promotion_id": source.get("freshness_promotion_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "decision": None,
        "recompute_authorized": False,
        "recompute_rejected": False,
        "recompute_allowed": False,
        "recompute_started": False,
        "authorization_evidence": {},
        "authorization_evidence_count": 0,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
