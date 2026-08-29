from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = {"sales_source_recorded_at", "sales_observed_at", "stock_source_recorded_at", "stock_observed_at", "unit_economics_source_recorded_at", "unit_economics_observed_at"}
SAFETY_FIELDS = ("application_allowed", "application_started", "persistent", "product_decision_recomputed", "product_decision_mutated", "task_draft_mutated", "execution_allowed", "execution_ready", "executed")


def build_application_permission_eligibility(authorization_signal):
    source = deepcopy(authorization_signal or {})
    error = _validate_signal(source)
    if error: return _blocked(source, error)
    evidence = _evidence(source, "authorization_evidence")
    return _base(source, error=False, status="APPLICATION_PERMISSION_ELIGIBLE", permission_eligibility_id="evidence-application-permission-eligibility:" + source["authorization_signal_id"], permission_eligible=True, permission_review_required=True, permission_granted=False, eligible_evidence=evidence, eligible_evidence_count=len(evidence))


def build_application_permission_review(eligibility):
    source = deepcopy(eligibility or {})
    error = _validate_stage(source, "eligibility")
    if error: return _blocked(source, error)
    evidence = _evidence(source, "eligible_evidence")
    return _base(source, error=False, status="APPLICATION_PERMISSION_REVIEW_REQUIRED", permission_review_id="evidence-application-permission-review:" + source["permission_eligibility_id"], permission_eligible=True, permission_review_required=True, permission_granted=False, review_evidence=evidence, review_evidence_count=len(evidence))


def build_application_permission_decision(review, decision):
    source = deepcopy(review or {}); choice = str(decision or "").strip().upper()
    error = _validate_stage(source, "review")
    if error: return _blocked(source, error, decision=choice)
    if choice not in {"PERMIT", "REJECT"}: return _blocked(source, "APPLICATION_PERMISSION_DECISION_INVALID", decision=choice)
    evidence = _evidence(source, "review_evidence"); granted = choice == "PERMIT"
    return _base(source, error=False, status="APPLICATION_PERMISSION_GRANTED" if granted else "APPLICATION_PERMISSION_REJECTED", permission_decision_id="evidence-application-permission-decision:" + source["permission_review_id"], decision=choice, permission_eligible=True, permission_review_required=False, permission_granted=granted, permission_rejected=not granted, permission_evidence=evidence, permission_evidence_count=len(evidence))


def build_application_start_handoff(permission_decision):
    source = deepcopy(permission_decision or {})
    error = _validate_stage(source, "decision")
    if error: return _blocked(source, error)
    if source.get("status") != "APPLICATION_PERMISSION_GRANTED": return _blocked(source, "APPLICATION_PERMISSION_NOT_GRANTED")
    evidence = _evidence(source, "permission_evidence")
    return _base(source, error=False, status="APPLICATION_START_HANDOFF_READY", application_handoff_id="evidence-application-start-handoff:" + source["permission_decision_id"], permission_granted=True, application_handoff_ready=True, handoff_evidence=evidence, handoff_evidence_count=len(evidence))


def build_application_permission_audit(eligibility, review, decision, handoff=None):
    eligible, reviewed, decided = [deepcopy(value or {}) for value in (eligibility, review, decision)]
    if _validate_stage(eligible, "eligibility") or _validate_stage(reviewed, "review"): return _blocked(decided, "APPLICATION_PERMISSION_AUDIT_INPUT_INVALID")
    error = _validate_stage(decided, "decision")
    if error: return _blocked(decided, error)
    if _identity(eligible) != _identity(reviewed) or _identity(reviewed) != _identity(decided): return _blocked(decided, "APPLICATION_PERMISSION_AUDIT_IDENTITY_MISMATCH")
    evidence = _evidence(eligible, "eligible_evidence")
    if evidence != _evidence(reviewed, "review_evidence") or evidence != _evidence(decided, "permission_evidence"): return _blocked(decided, "APPLICATION_PERMISSION_AUDIT_EVIDENCE_MISMATCH")
    granted = decided["permission_granted"] is True
    if granted:
        target = deepcopy(handoff or {})
        if target.get("status") != "APPLICATION_START_HANDOFF_READY" or target.get("application_handoff_ready") is not True: return _blocked(decided, "APPLICATION_START_HANDOFF_REQUIRED")
        if _identity(target) != _identity(decided) or target.get("permission_decision_id") != decided.get("permission_decision_id"): return _blocked(decided, "APPLICATION_START_HANDOFF_MISMATCH")
        if _evidence(target, "handoff_evidence") != evidence or target.get("handoff_evidence_count") != len(evidence) or _unsafe(target): return _blocked(decided, "APPLICATION_START_HANDOFF_MISMATCH")
    elif handoff is not None: return _blocked(decided, "REJECTED_PERMISSION_CANNOT_HAVE_HANDOFF")
    return _base(decided, error=False, status="APPLICATION_PERMISSION_AUDIT_READY", audit_id="evidence-application-permission-audit:" + decided["permission_decision_id"], permission_granted=granted, permission_rejected=not granted, application_handoff_ready=granted, audited_evidence=evidence, audited_evidence_count=len(evidence))


def _validate_signal(source):
    error = _ids(source, "signal")
    if error: return error
    if source.get("status") != "APPLICATION_AUTHORIZATION_GRANTED" or source.get("decision") != "AUTHORIZE" or source.get("authorization_signal_ready") is not True or source.get("authorization_granted") is not True or source.get("authorization_rejected") is not False: return "APPLICATION_AUTHORIZATION_NOT_GRANTED"
    return _payload_error(source, "authorization_evidence", "authorization_evidence_count")


def _validate_stage(source, stage):
    error = _ids(source, stage)
    if error: return error
    expected = {"eligibility": ("APPLICATION_PERMISSION_ELIGIBLE", "eligible_evidence", "eligible_evidence_count"), "review": ("APPLICATION_PERMISSION_REVIEW_REQUIRED", "review_evidence", "review_evidence_count"), "decision": (None, "permission_evidence", "permission_evidence_count")}[stage]
    if stage == "eligibility" and (source.get("status") != expected[0] or source.get("permission_eligible") is not True or source.get("permission_review_required") is not True or source.get("permission_granted") is not False): return "APPLICATION_PERMISSION_NOT_ELIGIBLE"
    if stage == "review" and (source.get("status") != expected[0] or source.get("permission_eligible") is not True or source.get("permission_review_required") is not True or source.get("permission_granted") is not False): return "APPLICATION_PERMISSION_REVIEW_NOT_READY"
    if stage == "decision":
        if source.get("permission_eligible") is not True or source.get("permission_review_required") is not False: return "APPLICATION_PERMISSION_DECISION_BOUNDARY_VIOLATION"
        if source.get("status") == "APPLICATION_PERMISSION_GRANTED":
            if source.get("decision") != "PERMIT" or source.get("permission_granted") is not True or source.get("permission_rejected") is not False: return "APPLICATION_PERMISSION_DECISION_CONTRADICTORY"
        elif source.get("status") == "APPLICATION_PERMISSION_REJECTED":
            if source.get("decision") != "REJECT" or source.get("permission_granted") is not False or source.get("permission_rejected") is not True: return "APPLICATION_PERMISSION_DECISION_CONTRADICTORY"
        else: return "APPLICATION_PERMISSION_DECISION_REQUIRED"
    return _payload_error(source, expected[1], expected[2])


def _ids(source, stage):
    fields = ("draft_id", "sku", "request_id", "approval_id", "signal_id", "eligibility_id", "preview_id", "authorization_id", "authorization_signal_id")
    if any(not isinstance(source.get(f), str) or not source[f].strip() for f in fields): return "APPLICATION_PERMISSION_CONTEXT_REQUIRED"
    d = source["draft_id"]
    expected = {"request_id": "refresh:" + d, "approval_id": "evidence-approval:" + d, "signal_id": "evidence-signal:" + source["approval_id"], "eligibility_id": "evidence-eligibility:" + source["signal_id"], "preview_id": "evidence-application-preview:" + source["eligibility_id"], "authorization_id": "evidence-application-authorization:" + source["preview_id"], "authorization_signal_id": "evidence-application-authorization-signal:" + source["authorization_id"]}
    for field, value in expected.items():
        if source.get(field) != value: return field.upper() + "_MISMATCH"
    if stage in {"eligibility", "review", "decision"} and source.get("permission_eligibility_id") != "evidence-application-permission-eligibility:" + source["authorization_signal_id"]: return "PERMISSION_ELIGIBILITY_ID_MISMATCH"
    if stage in {"review", "decision"} and source.get("permission_review_id") != "evidence-application-permission-review:" + source["permission_eligibility_id"]: return "PERMISSION_REVIEW_ID_MISMATCH"
    if stage == "decision" and source.get("permission_decision_id") != "evidence-application-permission-decision:" + source["permission_review_id"]: return "PERMISSION_DECISION_ID_MISMATCH"
    return None


def _payload_error(source, field, count):
    if _unsafe(source): return "APPLICATION_PERMISSION_SAFETY_BOUNDARY_VIOLATION"
    evidence = _evidence(source, field)
    if not evidence or evidence != source.get(field): return "APPLICATION_PERMISSION_EVIDENCE_UNSAFE"
    if source.get(count) != len(evidence): return "APPLICATION_PERMISSION_EVIDENCE_COUNT_MISMATCH"
    return None


def _unsafe(source):
    return any(source.get(field) is not False for field in SAFETY_FIELDS) or source.get("source_freshness_proven") is not False


def _evidence(source, field):
    values = source.get(field)
    if not isinstance(values, dict): return {}
    return {key: deepcopy(value) for key, value in values.items() if key in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")}


def _identity(source):
    return tuple(source.get(field) for field in ("draft_id", "sku", "request_id", "approval_id", "signal_id", "eligibility_id", "preview_id", "authorization_id", "authorization_signal_id"))


def _base(source, **additions):
    result = {field: source.get(field) for field in ("authorization_signal_id", "authorization_id", "preview_id", "eligibility_id", "signal_id", "approval_id", "request_id", "draft_id", "sku", "permission_eligibility_id", "permission_review_id", "permission_decision_id")}
    result.update({field: False for field in SAFETY_FIELDS}); result["source_freshness_proven"] = False; result.update(additions); return result


def _blocked(source, code, decision=None):
    return _base(source, error=True, code=code, status="APPLICATION_PERMISSION_BLOCKED", decision=decision, permission_eligible=False, permission_review_required=False, permission_granted=False, permission_rejected=False, application_handoff_ready=False)
