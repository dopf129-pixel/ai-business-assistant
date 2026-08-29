from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_proven_recompute_eligibility(promotion):
    source = dict(promotion or {})
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()
    promotion_id = str(source.get("freshness_promotion_id") or "").strip()

    if not draft_id or not sku or not promotion_id:
        return _blocked("RECOMPUTE_ELIGIBILITY_CONTEXT_REQUIRED", source)
    if source.get("status") != "SOURCE_FRESHNESS_PROVEN":
        return _blocked("SOURCE_FRESHNESS_STATUS_INVALID", source)
    if source.get("source_freshness_proven") is not True:
        return _blocked("SOURCE_FRESHNESS_NOT_PROVEN", source)
    if source.get("promotion_ready") is not True:
        return _blocked("FRESHNESS_PROMOTION_NOT_READY", source)
    if source.get("persistent") is not False or source.get("task_draft_mutated") is not False:
        return _blocked("RECOMPUTE_ELIGIBILITY_MUTATION_BOUNDARY_VIOLATION", source)
    if (
        source.get("product_decision_recomputed") is not False
        or source.get("product_decision_mutated") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("RECOMPUTE_ELIGIBILITY_SAFETY_BOUNDARY_VIOLATION", source)

    evidence = _safe_evidence(source.get("proven_evidence"))
    if not evidence:
        return _blocked("PROVEN_EVIDENCE_REQUIRED", source)
    if evidence != source.get("proven_evidence"):
        return _blocked("PROVEN_EVIDENCE_UNSAFE", source)
    if source.get("proven_evidence_count") != len(evidence):
        return _blocked("PROVEN_EVIDENCE_COUNT_MISMATCH", source)

    return {
        "error": False,
        "status": "PRODUCT_DECISION_RECOMPUTE_REVIEW_ELIGIBLE",
        "recompute_eligibility_id": "recompute-review-eligibility:" + promotion_id,
        "freshness_promotion_id": promotion_id,
        "draft_id": draft_id,
        "sku": sku,
        "source_freshness_proven": True,
        "recompute_review_eligible": True,
        "recompute_review_required": True,
        "recompute_allowed": False,
        "recompute_started": False,
        "eligible_evidence": deepcopy(evidence),
        "eligible_evidence_count": len(evidence),
        "persistent": False,
        "task_draft_mutated": False,
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
        "status": "PRODUCT_DECISION_RECOMPUTE_REVIEW_ELIGIBILITY_BLOCKED",
        "recompute_eligibility_id": None,
        "freshness_promotion_id": source.get("freshness_promotion_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "source_freshness_proven": False,
        "recompute_review_eligible": False,
        "recompute_review_required": False,
        "recompute_allowed": False,
        "recompute_started": False,
        "eligible_evidence": {},
        "eligible_evidence_count": 0,
        "persistent": False,
        "task_draft_mutated": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
