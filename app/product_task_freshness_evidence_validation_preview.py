from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_evidence_validation_preview(
    draft,
    evidence_candidate,
    freshness_service,
):
    source = deepcopy(draft or {})
    candidate = deepcopy(evidence_candidate or {})

    if freshness_service is None:
        return _blocked(source, candidate, "FRESHNESS_SERVICE_REQUIRED")

    before = freshness_service.evaluate(source)
    preview_draft = deepcopy(source)
    applied_evidence = {}

    for field, value in (candidate.get("evidence_update") or {}).items():
        if field not in ALLOWED_EVIDENCE_FIELDS:
            continue
        if value in (None, ""):
            continue
        preview_draft[field] = deepcopy(value)
        applied_evidence[field] = deepcopy(value)

    after = freshness_service.evaluate(preview_draft)
    changed_components = []
    before_components = before.get("components") or {}
    after_components = after.get("components") or {}

    for component in sorted(set(before_components) | set(after_components)):
        before_status = (before_components.get(component) or {}).get("status")
        after_status = (after_components.get(component) or {}).get("status")
        if before_status != after_status:
            changed_components.append({
                "component": component,
                "before": before_status,
                "after": after_status,
            })

    return {
        "error": False,
        "request_id": candidate.get("request_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "status": "PREVIEW_READY",
        "applied_evidence": applied_evidence,
        "applied_evidence_count": len(applied_evidence),
        "before": before,
        "after": after,
        "overall_status_changed": before.get("status") != after.get("status"),
        "changed_components": changed_components,
        "changed_component_count": len(changed_components),
        "source_freshness_proven": after.get("status") == "FRESH",
        "preview_only": True,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _blocked(source, candidate, code):
    return {
        "error": True,
        "code": code,
        "request_id": candidate.get("request_id"),
        "draft_id": source.get("draft_id"),
        "status": "PREVIEW_BLOCKED",
        "applied_evidence": {},
        "applied_evidence_count": 0,
        "source_freshness_proven": False,
        "preview_only": True,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
