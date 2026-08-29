from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_state_promotion(verification):
    source = dict(verification or {})
    draft_id = str(source.get("draft_id") or "").strip()
    sku = str(source.get("sku") or "").strip()
    if not draft_id or not sku:
        return _blocked("FRESHNESS_PROMOTION_CONTEXT_REQUIRED", source)

    if source.get("status") != "FRESHNESS_EVIDENCE_DURABLE_PERSISTENCE_VERIFIED":
        return _blocked("DURABLE_VERIFICATION_STATUS_INVALID", source)
    if source.get("verified") is not True:
        return _blocked("DURABLE_VERIFICATION_NOT_CONFIRMED", source)
    if source.get("mismatched_fields") != []:
        return _blocked("DURABLE_VERIFICATION_MISMATCH_PRESENT", source)

    if (
        source.get("product_decision_recomputed") is not False
        or source.get("product_decision_mutated") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("FRESHNESS_PROMOTION_SAFETY_BOUNDARY_VIOLATION", source)

    evidence = _safe_evidence(source.get("verified_evidence"))
    if not evidence:
        return _blocked("VERIFIED_EVIDENCE_REQUIRED", source)
    if evidence != source.get("verified_evidence"):
        return _blocked("VERIFIED_EVIDENCE_UNSAFE", source)
    if source.get("verified_evidence_count") != len(evidence):
        return _blocked("VERIFIED_EVIDENCE_COUNT_MISMATCH", source)

    verification_fingerprint = ":".join(
        [draft_id, sku, str(source.get("verified_evidence_count"))]
    )
    return {
        "error": False,
        "status": "SOURCE_FRESHNESS_PROVEN",
        "freshness_promotion_id": "freshness-state-promotion:" + verification_fingerprint,
        "draft_id": draft_id,
        "sku": sku,
        "source_freshness_proven": True,
        "promotion_ready": True,
        "proven_evidence": deepcopy(evidence),
        "proven_evidence_count": len(evidence),
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
        "status": "FRESHNESS_STATE_PROMOTION_BLOCKED",
        "freshness_promotion_id": None,
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "source_freshness_proven": False,
        "promotion_ready": False,
        "proven_evidence": {},
        "proven_evidence_count": 0,
        "persistent": False,
        "task_draft_mutated": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
