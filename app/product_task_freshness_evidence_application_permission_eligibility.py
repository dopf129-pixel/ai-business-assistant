from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_evidence_application_permission_eligibility(authorization_signal):
    source = deepcopy(authorization_signal or {})
    error = _validate(source)
    if error:
        return _blocked(source, error)

    evidence = _safe_evidence(source.get("authorization_evidence"))
    return {
        "error": False,
        "permission_eligibility_id": "evidence-application-permission-eligibility:" + source["authorization_signal_id"],
        "authorization_signal_id": source["authorization_signal_id"],
        "authorization_id": source["authorization_id"],
        "preview_id": source["preview_id"],
        "eligibility_id": source["eligibility_id"],
        "signal_id": source["signal_id"],
        "approval_id": source["approval_id"],
        "request_id": source["request_id"],
        "draft_id": source["draft_id"],
        "sku": source["sku"],
        "status": "APPLICATION_PERMISSION_REVIEW_REQUIRED",
        "permission_eligible": True,
        "permission_review_required": True,
        "permission_granted": False,
        "application_allowed": False,
        "application_started": False,
        "permission_evidence": evidence,
        "permission_evidence_count": len(evidence),
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _validate(source):
    required = (
        "draft_id", "sku", "request_id", "approval_id", "signal_id",
        "eligibility_id", "preview_id", "authorization_id", "authorization_signal_id",
    )
    if any(not str(source.get(key) or "").strip() for key in required):
        return "APPLICATION_PERMISSION_ELIGIBILITY_CONTEXT_REQUIRED"

    draft_id = str(source["draft_id"])
    if source["request_id"] != "refresh:" + draft_id:
        return "REQUEST_ID_MISMATCH"
    if source["approval_id"] != "evidence-approval:" + draft_id:
        return "APPROVAL_ID_MISMATCH"
    if source["signal_id"] != "evidence-signal:" + source["approval_id"]:
        return "SIGNAL_ID_MISMATCH"
    if source["eligibility_id"] != "evidence-eligibility:" + source["signal_id"]:
        return "ELIGIBILITY_ID_MISMATCH"
    if source["preview_id"] != "evidence-application-preview:" + source["eligibility_id"]:
        return "PREVIEW_ID_MISMATCH"
    if source["authorization_id"] != "evidence-application-authorization:" + source["preview_id"]:
        return "AUTHORIZATION_ID_MISMATCH"
    expected_signal_id = "evidence-application-authorization-signal:" + source["authorization_id"]
    if source["authorization_signal_id"] != expected_signal_id:
        return "AUTHORIZATION_SIGNAL_ID_MISMATCH"

    if source.get("status") != "APPLICATION_AUTHORIZATION_GRANTED":
        return "APPLICATION_AUTHORIZATION_NOT_GRANTED"
    if source.get("decision") != "AUTHORIZE":
        return "APPLICATION_AUTHORIZATION_DECISION_MISMATCH"
    if source.get("authorization_signal_ready") is not True:
        return "APPLICATION_AUTHORIZATION_SIGNAL_NOT_READY"
    if source.get("authorization_granted") is not True:
        return "APPLICATION_AUTHORIZATION_NOT_GRANTED"
    if source.get("authorization_rejected") is not False:
        return "APPLICATION_AUTHORIZATION_REJECTED"
    if source.get("application_allowed") is not False or source.get("application_started") is not False:
        return "APPLICATION_BOUNDARY_VIOLATION"
    if source.get("persistent") is not False or source.get("source_freshness_proven") is not False:
        return "AUTHORIZATION_SIGNAL_BOUNDARY_VIOLATION"

    safety_fields = (
        "product_decision_recomputed", "product_decision_mutated", "task_draft_mutated",
        "execution_allowed", "execution_ready", "executed",
    )
    if any(source.get(field) is not False for field in safety_fields):
        return "AUTHORIZATION_SIGNAL_SAFETY_BOUNDARY_VIOLATION"

    evidence = _safe_evidence(source.get("authorization_evidence"))
    if not evidence:
        return "AUTHORIZATION_EVIDENCE_REQUIRED"
    if evidence != source.get("authorization_evidence"):
        return "AUTHORIZATION_EVIDENCE_UNSAFE"
    if source.get("authorization_evidence_count") != len(evidence):
        return "AUTHORIZATION_EVIDENCE_COUNT_MISMATCH"
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
        "permission_eligibility_id": None,
        "authorization_signal_id": source.get("authorization_signal_id"),
        "authorization_id": source.get("authorization_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "status": "APPLICATION_PERMISSION_ELIGIBILITY_BLOCKED",
        "permission_eligible": False,
        "permission_review_required": False,
        "permission_granted": False,
        "application_allowed": False,
        "application_started": False,
        "permission_evidence": {},
        "permission_evidence_count": 0,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
