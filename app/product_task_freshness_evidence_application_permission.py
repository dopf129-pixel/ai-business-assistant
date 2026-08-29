from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_application_permission_eligibility(authorization_signal):
    """v169: validate a granted authorization signal for a separate permission review."""
    source = deepcopy(authorization_signal or {})
    error = _validate_granted_signal(source)
    if error:
        return _blocked(source, error)
    evidence = _safe_evidence(source.get("authorization_evidence"))
    return _base(source, {
        "error": False,
        "status": "APPLICATION_PERMISSION_ELIGIBLE",
        "permission_eligibility_id": "evidence-application-permission-eligibility:" + source["authorization_signal_id"],
        "permission_eligible": True,
        "permission_review_required": True,
        "permission_granted": False,
        "eligible_evidence": evidence,
        "eligible_evidence_count": len(evidence),
    })


def build_application_permission_review(eligibility):
    """v170: produce a read-only human review contract without granting permission."""
    source = deepcopy(eligibility or {})
    error = _validate_eligibility(source)
    if error:
        return _blocked(source, error)
    evidence = _safe_evidence(source.get("eligible_evidence"))
    return _base(source, {
        "error": False,
        "status": "APPLICATION_PERMISSION_REVIEW_REQUIRED",
        "permission_review_id": "evidence-application-permission-review:" + source["permission_eligibility_id"],
        "permission_eligible": True,
        "permission_review_required": True,
        "permission_granted": False,
        "review_evidence": evidence,
        "review_evidence_count": len(evidence),
    })


def build_application_permission_decision(review, decision):
    """v171: record explicit PERMIT/REJECT; PERMIT is still not application execution."""
    source = deepcopy(review or {})
    choice = str(decision or "").strip().upper()
    error = _validate_review(source)
    if error:
        return _blocked(source, error, decision=choice)
    if choice not in {"PERMIT", "REJECT"}:
        return _blocked(source, "APPLICATION_PERMISSION_DECISION_INVALID", decision=choice)
    evidence = _safe_evidence(source.get("review_evidence"))
    permitted = choice == "PERMIT"
    return _base(source, {
        "error": False,
        "status": "APPLICATION_PERMISSION_GRANTED" if permitted else "APPLICATION_PERMISSION_REJECTED",
        "permission_decision_id": "evidence-application-permission-decision:" + source["permission_review_id"],
        "decision": choice,
        "permission_eligible": True,
        "permission_review_required": False,
        "permission_granted": permitted,
        "permission_rejected": not permitted,
        "permission_evidence": evidence,
        "permission_evidence_count": len(evidence),
    })


def build_application_start_handoff(permission_decision):
    """v172: hand off a permitted decision to a future application stage without starting it."""
    source = deepcopy(permission_decision or {})
    error = _validate_permission_decision(source)
    if error:
        return _blocked(source, error)
    evidence = _safe_evidence(source.get("permission_evidence"))
    return _base(source, {
        "error": False,
        "status": "APPLICATION_START_HANDOFF_READY",
        "application_handoff_id": "evidence-application-start-handoff:" + source["permission_decision_id"],
        "permission_granted": True,
        "application_handoff_ready": True,
        "handoff_evidence": evidence,
        "handoff_evidence_count": len(evidence),
    })


def build_application_permission_audit(eligibility, review, decision, handoff=None):
    """v173: deterministic audit receipt for the permission lifecycle."""
    eligible = deepcopy(eligibility or {})
    reviewed = deepcopy(review or {})
    decided = deepcopy(decision or {})
    if _validate_eligibility(eligible) or _validate_review(reviewed):
        return _blocked(decided, "APPLICATION_PERMISSION_AUDIT_INPUT_INVALID")
    if _identity(eligible) != _identity(reviewed) or _identity(reviewed) != _identity(decided):
        return _blocked(decided, "APPLICATION_PERMISSION_AUDIT_IDENTITY_MISMATCH")
    if decided.get("status") not in {"APPLICATION_PERMISSION_GRANTED", "APPLICATION_PERMISSION_REJECTED"}:
        return _blocked(decided, "APPLICATION_PERMISSION_DECISION_REQUIRED")
    evidence = _safe_evidence(eligible.get("eligible_evidence"))
    if evidence != _safe_evidence(reviewed.get("review_evidence")) or evidence != _safe_evidence(decided.get("permission_evidence")):
        return _blocked(decided, "APPLICATION_PERMISSION_AUDIT_EVIDENCE_MISMATCH")
    granted = decided.get("permission_granted") is True
    if granted:
        target = deepcopy(handoff or {})
        if target.get("status") != "APPLICATION_START_HANDOFF_READY" or target.get("application_handoff_ready") is not True:
            return _blocked(decided, "APPLICATION_START_HANDOFF_REQUIRED")
        if _identity(target) != _identity(decided) or _safe_evidence(target.get("handoff_evidence")) != evidence:
            return _blocked(decided, "APPLICATION_START_HANDOFF_MISMATCH")
    elif handoff is not None:
        return _blocked(decided, "REJECTED_PERMISSION_CANNOT_HAVE_HANDOFF")
    return _base(decided, {
        "error": False,
        "status": "APPLICATION_PERMISSION_AUDIT_READY",
        "audit_id": "evidence-application-permission-audit:" + decided["permission_decision_id"],
        "permission_granted": granted,
        "permission_rejected": not granted,
        "application_handoff_ready": granted,
        "audited_evidence": evidence,
        "audited_evidence_count": len(evidence),
    })


def _validate_granted_signal(source):
    error = _identity_error(source, through="authorization_signal")
    if error:
        return error
    if source.get("status") != "APPLICATION_AUTHORIZATION_GRANTED" or source.get("decision") != "AUTHORIZE":
        return "APPLICATION_AUTHORIZATION_NOT_GRANTED"
    if source.get("authorization_signal_ready") is not True or source.get("authorization_granted") is not True:
        return "APPLICATION_AUTHORIZATION_NOT_GRANTED"
    if source.get("authorization_rejected") is not False:
        return "APPLICATION_AUTHORIZATION_CONTRADICTORY"
    return _safety_and_evidence_error(source, "authorization_evidence", "authorization_evidence_count")


def _validate_eligibility(source):
    error = _identity_error(source, through="permission_eligibility")
    if error:
        return error
    if source.get("status") != "APPLICATION_PERMISSION_ELIGIBLE" or source.get("permission_eligible") is not True:
        return "APPLICATION_PERMISSION_NOT_ELIGIBLE"
    if source.get("permission_review_required") is not True or source.get("permission_granted") is not False:
        return "APPLICATION_PERMISSION_ELIGIBILITY_BOUNDARY_VIOLATION"
    return _safety_and_evidence_error(source, "eligible_evidence", "eligible_evidence_count")


def _validate_review(source):
    error = _identity_error(source, through="permission_review")
    if error:
        return error
    if source.get("status") != "APPLICATION_PERMISSION_REVIEW_REQUIRED":
        return "APPLICATION_PERMISSION_REVIEW_NOT_READY"
    if source.get("permission_review_required") is not True or source.get("permission_granted") is not False:
        return "APPLICATION_PERMISSION_REVIEW_BOUNDARY_VIOLATION"
    return _safety_and_evidence_error(source, "review_evidence", "review_evidence_count")


def _validate_permission_decision(source):
    error = _identity_error(source, through="permission_decision")
    if error:
        return error
    if source.get("status") != "APPLICATION_PERMISSION_GRANTED" or source.get("decision") != "PERMIT":
        return "APPLICATION_PERMISSION_NOT_GRANTED"
    if source.get("permission_granted") is not True or source.get("permission_rejected") is not False:
        return "APPLICATION_PERMISSION_NOT_GRANTED"
    return _safety_and_evidence_error(source, "permission_evidence", "permission_evidence_count")


def _identity_error(source, through):
    draft_id = _text(source.get("draft_id"))
    sku = _text(source.get("sku"))
    request_id = _text(source.get("request_id"))
    approval_id = _text(source.get("approval_id"))
    signal_id = _text(source.get("signal_id"))
    eligibility_id = _text(source.get("eligibility_id"))
    preview_id = _text(source.get("preview_id"))
    authorization_id = _text(source.get("authorization_id"))
    authorization_signal_id = _text(source.get("authorization_signal_id"))
    if not all((draft_id, sku, request_id, approval_id, signal_id, eligibility_id, preview_id, authorization_id, authorization_signal_id)):
        return "APPLICATION_PERMISSION_CONTEXT_REQUIRED"
    expected = {
        "request_id": "refresh:" + draft_id,
        "approval_id": "evidence-approval:" + draft_id,
        "signal_id": "evidence-signal:" + approval_id,
        "eligibility_id": "evidence-eligibility:" + signal_id,
        "preview_id": "evidence-application-preview:" + eligibility_id,
        "authorization_id": "evidence-application-authorization:" + preview_id,
        "authorization_signal_id": "evidence-application-authorization-signal:" + authorization_id,
    }
    for field, value in expected.items():
        if source.get(field) != value:
            return field.upper() + "_MISMATCH"
    if through in {"permission_eligibility", "permission_review", "permission_decision"}:
        pid = _text(source.get("permission_eligibility_id"))
        if not pid or pid != "evidence-application-permission-eligibility:" + authorization_signal_id:
            return "PERMISSION_ELIGIBILITY_ID_MISMATCH"
    if through in {"permission_review", "permission_decision"}:
        rid = _text(source.get("permission_review_id"))
        if not rid or rid != "evidence-application-permission-review:" + source["permission_eligibility_id"]:
            return "PERMISSION_REVIEW_ID_MISMATCH"
    if through == "permission_decision":
        did = _text(source.get("permission_decision_id"))
        if not did or did != "evidence-application-permission-decision:" + source["permission_review_id"]:
            return "PERMISSION_DECISION_ID_MISMATCH"
    return None


def _safety_and_evidence_error(source, evidence_field, count_field):
    if any(source.get(field) is not False for field in (
        "application_allowed", "application_started", "persistent",
        "product_decision_recomputed", "product_decision_mutated", "task_draft_mutated",
        "execution_allowed", "execution_ready", "executed",
    )):
        return "APPLICATION_PERMISSION_SAFETY_BOUNDARY_VIOLATION"
    if source.get("source_freshness_proven") is not False:
        return "SOURCE_FRESHNESS_BOUNDARY_VIOLATION"
    evidence = _safe_evidence(source.get(evidence_field))
    if not evidence or evidence != source.get(evidence_field):
        return "APPLICATION_PERMISSION_EVIDENCE_UNSAFE"
    if source.get(count_field) != len(evidence):
        return "APPLICATION_PERMISSION_EVIDENCE_COUNT_MISMATCH"
    return None


def _identity(source):
    return tuple(source.get(field) for field in (
        "draft_id", "sku", "request_id", "approval_id", "signal_id", "eligibility_id",
        "preview_id", "authorization_id", "authorization_signal_id",
    ))


def _safe_evidence(values):
    if not isinstance(values, dict):
        return {}
    return {field: deepcopy(value) for field, value in values.items() if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")}


def _base(source, additions):
    result = {
        "authorization_signal_id": source.get("authorization_signal_id"),
        "authorization_id": source.get("authorization_id"),
        "preview_id": source.get("preview_id"),
        "eligibility_id": source.get("eligibility_id"),
        "signal_id": source.get("signal_id"),
        "approval_id": source.get("approval_id"),
        "request_id": source.get("request_id"),
        "draft_id": source.get("draft_id"),
        "sku": source.get("sku"),
        "permission_eligibility_id": source.get("permission_eligibility_id"),
        "permission_review_id": source.get("permission_review_id"),
        "permission_decision_id": source.get("permission_decision_id"),
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
    result.update(additions)
    return result


def _blocked(source, code, decision=None):
    return _base(source, {
        "error": True,
        "code": code,
        "status": "APPLICATION_PERMISSION_BLOCKED",
        "decision": decision,
        "permission_eligible": False,
        "permission_review_required": False,
        "permission_granted": False,
        "permission_rejected": False,
        "application_handoff_ready": False,
    })


def _text(value):
    return value.strip() if isinstance(value, str) else ""
