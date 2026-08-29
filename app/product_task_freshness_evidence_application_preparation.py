from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}
SAFETY_FIELDS = (
    "application_allowed",
    "application_started",
    "persistent",
    "product_decision_recomputed",
    "product_decision_mutated",
    "task_draft_mutated",
    "execution_allowed",
    "execution_ready",
    "executed",
)
IDENTITY_FIELDS = (
    "draft_id",
    "sku",
    "request_id",
    "approval_id",
    "signal_id",
    "eligibility_id",
    "preview_id",
    "authorization_id",
    "authorization_signal_id",
    "permission_eligibility_id",
    "permission_review_id",
    "permission_decision_id",
)


def build_application_preparation_eligibility(handoff, permission_audit):
    source = deepcopy(handoff or {})
    audit = deepcopy(permission_audit or {})
    error = _validate_start_package(source, audit)
    if error:
        return _blocked(source, error)
    evidence = _evidence(source, "handoff_evidence")
    return _base(
        source,
        error=False,
        status="APPLICATION_PREPARATION_ELIGIBLE",
        preparation_eligibility_id=(
            "evidence-application-preparation-eligibility:"
            + source["application_handoff_id"]
        ),
        preparation_eligible=True,
        preparation_review_required=True,
        permission_audit_id=audit["audit_id"],
        preparation_evidence=evidence,
        preparation_evidence_count=len(evidence),
    )


def build_application_preparation_plan(eligibility):
    source = deepcopy(eligibility or {})
    error = _validate_eligibility(source)
    if error:
        return _blocked(source, error)
    evidence = _evidence(source, "preparation_evidence")
    fields = [
        {"field": key, "proposed_value": deepcopy(evidence[key])}
        for key in sorted(evidence)
    ]
    return _base(
        source,
        error=False,
        status="APPLICATION_PREPARATION_PLAN_READY",
        preparation_plan_id=(
            "evidence-application-preparation-plan:"
            + source["preparation_eligibility_id"]
        ),
        preparation_eligible=True,
        preparation_review_required=True,
        preparation_plan_ready=True,
        planned_evidence=evidence,
        planned_evidence_count=len(evidence),
        planned_fields=fields,
        planned_field_count=len(fields),
    )


def build_application_preparation_decision(plan, decision):
    source = deepcopy(plan or {})
    choice = str(decision or "").strip().upper()
    error = _validate_plan(source)
    if error:
        return _blocked(source, error, decision=choice)
    if choice not in {"PREPARE", "REJECT"}:
        return _blocked(source, "APPLICATION_PREPARATION_DECISION_INVALID", decision=choice)
    evidence = _evidence(source, "planned_evidence")
    prepared = choice == "PREPARE"
    return _base(
        source,
        error=False,
        status=(
            "APPLICATION_PREPARATION_APPROVED"
            if prepared
            else "APPLICATION_PREPARATION_REJECTED"
        ),
        preparation_decision_id=(
            "evidence-application-preparation-decision:"
            + source["preparation_plan_id"]
        ),
        decision=choice,
        preparation_eligible=True,
        preparation_review_required=False,
        preparation_plan_ready=True,
        preparation_approved=prepared,
        preparation_rejected=not prepared,
        decision_evidence=evidence,
        decision_evidence_count=len(evidence),
    )


def build_application_execution_handoff(preparation_decision):
    source = deepcopy(preparation_decision or {})
    error = _validate_decision(source)
    if error:
        return _blocked(source, error)
    if source.get("status") != "APPLICATION_PREPARATION_APPROVED":
        return _blocked(source, "APPLICATION_PREPARATION_NOT_APPROVED")
    evidence = _evidence(source, "decision_evidence")
    return _base(
        source,
        error=False,
        status="APPLICATION_EXECUTION_HANDOFF_READY",
        application_execution_handoff_id=(
            "evidence-application-execution-handoff:"
            + source["preparation_decision_id"]
        ),
        preparation_approved=True,
        application_execution_handoff_ready=True,
        application_executor_required=True,
        execution_handoff_evidence=evidence,
        execution_handoff_evidence_count=len(evidence),
    )


def build_application_preparation_audit(
    eligibility,
    plan,
    decision,
    execution_handoff=None,
):
    eligible = deepcopy(eligibility or {})
    planned = deepcopy(plan or {})
    decided = deepcopy(decision or {})
    if _validate_eligibility(eligible) or _validate_plan(planned):
        return _blocked(decided, "APPLICATION_PREPARATION_AUDIT_INPUT_INVALID")
    error = _validate_decision(decided)
    if error:
        return _blocked(decided, error)
    if _identity(eligible) != _identity(planned) or _identity(planned) != _identity(decided):
        return _blocked(decided, "APPLICATION_PREPARATION_AUDIT_IDENTITY_MISMATCH")
    if eligible.get("preparation_eligibility_id") != planned.get("preparation_eligibility_id"):
        return _blocked(decided, "APPLICATION_PREPARATION_AUDIT_LINEAGE_MISMATCH")
    if planned.get("preparation_plan_id") != decided.get("preparation_plan_id"):
        return _blocked(decided, "APPLICATION_PREPARATION_AUDIT_LINEAGE_MISMATCH")
    evidence = _evidence(eligible, "preparation_evidence")
    if evidence != _evidence(planned, "planned_evidence") or evidence != _evidence(decided, "decision_evidence"):
        return _blocked(decided, "APPLICATION_PREPARATION_AUDIT_EVIDENCE_MISMATCH")
    approved = decided.get("preparation_approved") is True
    if approved:
        target = deepcopy(execution_handoff or {})
        error = _validate_execution_handoff(target)
        if error:
            return _blocked(decided, error)
        if _identity(target) != _identity(decided):
            return _blocked(decided, "APPLICATION_EXECUTION_HANDOFF_MISMATCH")
        if target.get("preparation_decision_id") != decided.get("preparation_decision_id"):
            return _blocked(decided, "APPLICATION_EXECUTION_HANDOFF_MISMATCH")
        if _evidence(target, "execution_handoff_evidence") != evidence:
            return _blocked(decided, "APPLICATION_EXECUTION_HANDOFF_MISMATCH")
    elif execution_handoff is not None:
        return _blocked(decided, "REJECTED_PREPARATION_CANNOT_HAVE_EXECUTION_HANDOFF")
    return _base(
        decided,
        error=False,
        status="APPLICATION_PREPARATION_AUDIT_READY",
        preparation_audit_id=(
            "evidence-application-preparation-audit:"
            + decided["preparation_decision_id"]
        ),
        preparation_approved=approved,
        preparation_rejected=not approved,
        application_execution_handoff_ready=approved,
        audited_evidence=evidence,
        audited_evidence_count=len(evidence),
    )


def _validate_start_package(handoff, audit):
    if handoff.get("error") is not False or audit.get("error") is not False:
        return "APPLICATION_PREPARATION_INPUT_ERROR"
    if handoff.get("status") != "APPLICATION_START_HANDOFF_READY":
        return "APPLICATION_START_HANDOFF_REQUIRED"
    if audit.get("status") != "APPLICATION_PERMISSION_AUDIT_READY":
        return "APPLICATION_PERMISSION_AUDIT_REQUIRED"
    if handoff.get("permission_granted") is not True or handoff.get("application_handoff_ready") is not True:
        return "APPLICATION_START_HANDOFF_NOT_READY"
    if audit.get("permission_granted") is not True or audit.get("application_handoff_ready") is not True:
        return "APPLICATION_PERMISSION_AUDIT_NOT_GRANTED"
    if _ids_error(handoff) or _ids_error(audit):
        return "APPLICATION_PREPARATION_CONTEXT_REQUIRED"
    if _identity(handoff) != _identity(audit):
        return "APPLICATION_PREPARATION_IDENTITY_MISMATCH"
    expected_handoff_id = "evidence-application-start-handoff:" + handoff["permission_decision_id"]
    if handoff.get("application_handoff_id") != expected_handoff_id:
        return "APPLICATION_START_HANDOFF_ID_MISMATCH"
    expected_audit_id = "evidence-application-permission-audit:" + audit["permission_decision_id"]
    if audit.get("audit_id") != expected_audit_id:
        return "APPLICATION_PERMISSION_AUDIT_ID_MISMATCH"
    handoff_evidence = _evidence(handoff, "handoff_evidence")
    audited_evidence = _evidence(audit, "audited_evidence")
    if not handoff_evidence or handoff_evidence != handoff.get("handoff_evidence"):
        return "APPLICATION_PREPARATION_EVIDENCE_UNSAFE"
    if handoff_evidence != audited_evidence:
        return "APPLICATION_PREPARATION_EVIDENCE_MISMATCH"
    if handoff.get("handoff_evidence_count") != len(handoff_evidence):
        return "APPLICATION_PREPARATION_EVIDENCE_COUNT_MISMATCH"
    if audit.get("audited_evidence_count") != len(audited_evidence):
        return "APPLICATION_PREPARATION_EVIDENCE_COUNT_MISMATCH"
    if _unsafe(handoff) or _unsafe(audit):
        return "APPLICATION_PREPARATION_SAFETY_BOUNDARY_VIOLATION"
    return None


def _validate_eligibility(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_PREPARATION_ELIGIBLE":
        return "APPLICATION_PREPARATION_NOT_ELIGIBLE"
    if source.get("preparation_eligible") is not True or source.get("preparation_review_required") is not True:
        return "APPLICATION_PREPARATION_NOT_ELIGIBLE"
    if _ids_error(source) or not _valid_preparation_eligibility_id(source):
        return "APPLICATION_PREPARATION_LINEAGE_MISMATCH"
    return _payload_error(source, "preparation_evidence", "preparation_evidence_count")


def _validate_plan(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_PREPARATION_PLAN_READY":
        return "APPLICATION_PREPARATION_PLAN_REQUIRED"
    if source.get("preparation_plan_ready") is not True or source.get("preparation_review_required") is not True:
        return "APPLICATION_PREPARATION_PLAN_REQUIRED"
    if _ids_error(source) or not _valid_preparation_eligibility_id(source):
        return "APPLICATION_PREPARATION_LINEAGE_MISMATCH"
    expected_plan_id = "evidence-application-preparation-plan:" + source["preparation_eligibility_id"]
    if source.get("preparation_plan_id") != expected_plan_id:
        return "APPLICATION_PREPARATION_PLAN_ID_MISMATCH"
    error = _payload_error(source, "planned_evidence", "planned_evidence_count")
    if error:
        return error
    expected_fields = [
        {"field": key, "proposed_value": deepcopy(source["planned_evidence"][key])}
        for key in sorted(source["planned_evidence"])
    ]
    if source.get("planned_fields") != expected_fields or source.get("planned_field_count") != len(expected_fields):
        return "APPLICATION_PREPARATION_PLAN_FIELDS_MISMATCH"
    return None


def _validate_decision(source):
    if _ids_error(source) or not _valid_preparation_eligibility_id(source):
        return "APPLICATION_PREPARATION_LINEAGE_MISMATCH"
    expected_plan_id = "evidence-application-preparation-plan:" + source["preparation_eligibility_id"]
    if source.get("preparation_plan_id") != expected_plan_id:
        return "APPLICATION_PREPARATION_PLAN_ID_MISMATCH"
    expected_decision_id = "evidence-application-preparation-decision:" + expected_plan_id
    if source.get("preparation_decision_id") != expected_decision_id:
        return "APPLICATION_PREPARATION_DECISION_ID_MISMATCH"
    if source.get("preparation_review_required") is not False or source.get("preparation_plan_ready") is not True:
        return "APPLICATION_PREPARATION_DECISION_BOUNDARY_VIOLATION"
    if source.get("status") == "APPLICATION_PREPARATION_APPROVED":
        if source.get("decision") != "PREPARE" or source.get("preparation_approved") is not True or source.get("preparation_rejected") is not False:
            return "APPLICATION_PREPARATION_DECISION_CONTRADICTORY"
    elif source.get("status") == "APPLICATION_PREPARATION_REJECTED":
        if source.get("decision") != "REJECT" or source.get("preparation_approved") is not False or source.get("preparation_rejected") is not True:
            return "APPLICATION_PREPARATION_DECISION_CONTRADICTORY"
    else:
        return "APPLICATION_PREPARATION_DECISION_REQUIRED"
    return _payload_error(source, "decision_evidence", "decision_evidence_count")


def _validate_execution_handoff(source):
    error = _validate_decision(source)
    if error:
        return error
    if source.get("status") != "APPLICATION_EXECUTION_HANDOFF_READY":
        return "APPLICATION_EXECUTION_HANDOFF_REQUIRED"
    if source.get("preparation_approved") is not True or source.get("application_execution_handoff_ready") is not True:
        return "APPLICATION_EXECUTION_HANDOFF_REQUIRED"
    if source.get("application_executor_required") is not True:
        return "APPLICATION_EXECUTOR_BOUNDARY_REQUIRED"
    expected = "evidence-application-execution-handoff:" + source["preparation_decision_id"]
    if source.get("application_execution_handoff_id") != expected:
        return "APPLICATION_EXECUTION_HANDOFF_ID_MISMATCH"
    return _payload_error(source, "execution_handoff_evidence", "execution_handoff_evidence_count")


def _valid_preparation_eligibility_id(source):
    handoff_id = source.get("application_handoff_id")
    if not isinstance(handoff_id, str) or not handoff_id:
        return False
    expected = "evidence-application-preparation-eligibility:" + handoff_id
    return source.get("preparation_eligibility_id") == expected


def _ids_error(source):
    if any(not isinstance(source.get(field), str) or not source[field].strip() for field in IDENTITY_FIELDS):
        return True
    d = source["draft_id"]
    expected = {
        "request_id": "refresh:" + d,
        "approval_id": "evidence-approval:" + d,
        "signal_id": "evidence-signal:" + source["approval_id"],
        "eligibility_id": "evidence-eligibility:" + source["signal_id"],
        "preview_id": "evidence-application-preview:" + source["eligibility_id"],
        "authorization_id": "evidence-application-authorization:" + source["preview_id"],
        "authorization_signal_id": "evidence-application-authorization-signal:" + source["authorization_id"],
        "permission_eligibility_id": "evidence-application-permission-eligibility:" + source["authorization_signal_id"],
        "permission_review_id": "evidence-application-permission-review:" + source["permission_eligibility_id"],
        "permission_decision_id": "evidence-application-permission-decision:" + source["permission_review_id"],
    }
    return any(source.get(field) != value for field, value in expected.items())


def _payload_error(source, field, count):
    if _unsafe(source):
        return "APPLICATION_PREPARATION_SAFETY_BOUNDARY_VIOLATION"
    evidence = _evidence(source, field)
    if not evidence or evidence != source.get(field):
        return "APPLICATION_PREPARATION_EVIDENCE_UNSAFE"
    if source.get(count) != len(evidence):
        return "APPLICATION_PREPARATION_EVIDENCE_COUNT_MISMATCH"
    return None


def _unsafe(source):
    return any(source.get(field) is not False for field in SAFETY_FIELDS) or source.get("source_freshness_proven") is not False


def _evidence(source, field):
    values = source.get(field)
    if not isinstance(values, dict):
        return {}
    return {
        key: deepcopy(value)
        for key, value in values.items()
        if key in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
    }


def _identity(source):
    return tuple(source.get(field) for field in IDENTITY_FIELDS)


def _base(source, **additions):
    carried = IDENTITY_FIELDS + (
        "application_handoff_id",
        "permission_audit_id",
        "preparation_eligibility_id",
        "preparation_plan_id",
        "preparation_decision_id",
    )
    result = {field: source.get(field) for field in carried}
    result.update({field: False for field in SAFETY_FIELDS})
    result["source_freshness_proven"] = False
    result.update(additions)
    return result


def _blocked(source, code, decision=None):
    return _base(
        source,
        error=True,
        code=code,
        status="APPLICATION_PREPARATION_BLOCKED",
        decision=decision,
        preparation_eligible=False,
        preparation_review_required=False,
        preparation_plan_ready=False,
        preparation_approved=False,
        preparation_rejected=False,
        application_execution_handoff_ready=False,
        application_executor_required=False,
    )
