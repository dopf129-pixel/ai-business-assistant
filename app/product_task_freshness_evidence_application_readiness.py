from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_evidence_application_readiness(permission_signal):
    source = deepcopy(permission_signal or {})
    error = _validate(source)
    if error:
        return _blocked(source, error)

    evidence = _safe_evidence(source.get("permission_evidence"))
    return {
        "error": False,
        "application_readiness_id": "evidence-application-readiness:" + source["permission_signal_id"],
        "permission_signal_id": source["permission_signal_id"],
        "permission_eligibility_id": source["permission_eligibility_id"],
        "authorization_signal_id": source["authorization_signal_id"],
        "authorization_id": source["authorization_id"],
        "preview_id": source["preview_id"],
        "eligibility_id": source["eligibility_id"],
        "signal_id": source["signal_id"],
        "approval_id": source["approval_id"],
        "request_id": source["request_id"],
        "draft_id": source["draft_id"],
        "sku": source["sku"],
        "status": "APPLICATION_READY_FOR_SEPARATE_STEP",
        "application_ready": True,
        "application_review_complete": True,
        "application_allowed": False,
        "application_started": False,
        "readiness_evidence": evidence,
        "readiness_evidence_count": len(evidence),
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
        "eligibility_id", "preview_id", "authorization_id",
        "authorization_signal_id", "permission_eligibility_id", "permission_signal_id",
    )
    if any(not str(source.get(key) or "").strip() for key in required):
        return "APPLICATION_READINESS_CONTEXT_REQUIRED"

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
    expected_authorization_signal_id = "evidence-application-authorization-signal:" + source["authorization_id"]
    if source["authorization_signal_id"] != expected_authorization_signal_id:
        return "AUTHORIZATION_SIGNAL_ID_MISMATCH"
    expected_permission_eligibility_id = "evidence-application-permission-eligibility:" + source["authorization_signal_id"]
    if source["permission_eligibility_id"] != expected_permission_eligibility_id:
        return "PERMISSION_ELIGIBILITY_ID_MISMATCH"
    expected_permission_signal_id = "evidence-application-permission-signal:" + source["permission_eligibility_id"]
    if source["permission_signal_id"] != expected_permission_signal_id:
        return "PERMISSION_SIGNAL_ID_MISMATCH"

    if source.get("status") != "APPLICATION_PERMISSION_GRANTED":
        return "APPLICATION_PERMISSION_NOT_GRANTED"
    if source.get("decision") != "GRANT":
        return "APPLICATION_PERMISSION_DECISION_MISMATCH"
    if source.get("permission_signal_ready") is not True:
        return "APPLICATION_PERMISSION_SIGNAL_NOT_READY"
    if source.get("permission_granted") is not True:
        return "APPLICATION_PERMISSION_NOT_GRANTED"
    if source.get("permission_rejected") is not False:
        return "APPLICATION_PERMISSION_REJECTED"
    if source.get("application_allowed") is not False or source.get("application_started") is not False:
        return "APPLICATION_BOUNDARY_VIOLATION"
    if source.get("persistent") is not False or source.get("source_freshness_proven") is not False:
        return "PERMISSION_SIGNAL_BOUNDARY_VIOLATION"

    safety_fields = (
        "product_decision_recomputed", "product_decision_mutated", "task_draft_mutated",
        "execution_allowed", "execution_ready", "executed",
    )
    if any(source.get(field) is not False for field in safety_fields):
        return "PERMISSION_SIGNAL_SAFETY_BOUNDARY_VIOLATION"

    evidence = _safe_evidence(source.get("permission_evidence"))
    if not evidence:
        return "PERMISSION_EVIDENCE_REQUIRED"
    if evidence != source.get("permission_evidence"):
        return "PERMISSION_EVIDENCE_UNSAFE"
    if source.get("permission_evidence_count") != len(evidence):
        return "PERMISSION_EVIDENCE_COUNT_MISMATCH"
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
        "application_readiness_id": None,
        "permission_signal_id": source.get("permission_signal_id"),
        "permission_eligibility_id": source.get("permission_eligibility_id"),
        "authorization_signal_id": source.get("authorization_signal_id"),
        "authorization_id": source.get("authorization_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "status": "APPLICATION_READINESS_BLOCKED",
        "application_ready": False,
        "application_review_complete": False,
        "application_allowed": False,
        "application_started": False,
        "readiness_evidence": {},
        "readiness_evidence_count": 0,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
