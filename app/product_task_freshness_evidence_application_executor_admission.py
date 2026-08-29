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
    "draft_id", "sku", "request_id", "approval_id", "signal_id", "eligibility_id",
    "preview_id", "authorization_id", "authorization_signal_id", "permission_eligibility_id",
    "permission_review_id", "permission_decision_id", "application_handoff_id",
    "preparation_eligibility_id", "preparation_plan_id", "preparation_decision_id",
)


def build_executor_admission_eligibility(execution_handoff, preparation_audit):
    handoff = deepcopy(execution_handoff or {})
    audit = deepcopy(preparation_audit or {})
    error = _validate_start(handoff, audit)
    if error:
        return _blocked(handoff, error)
    evidence = _evidence(handoff, "execution_handoff_evidence")
    return _base(
        handoff,
        error=False,
        status="APPLICATION_EXECUTOR_ADMISSION_ELIGIBLE",
        executor_admission_eligibility_id="evidence-application-executor-admission-eligibility:" + handoff["application_execution_handoff_id"],
        preparation_audit_id=audit["preparation_audit_id"],
        executor_admission_eligible=True,
        target_snapshot_required=True,
        admission_evidence=evidence,
        admission_evidence_count=len(evidence),
    )


def bind_executor_target_snapshot(eligibility, target_snapshot):
    source = deepcopy(eligibility or {})
    target = deepcopy(target_snapshot or {})
    error = _validate_eligibility(source)
    if error:
        return _blocked(source, error)
    error = _validate_target_snapshot(source, target)
    if error:
        return _blocked(source, error)
    current = _target_values(target)
    return _base(
        source,
        error=False,
        status="APPLICATION_EXECUTOR_TARGET_BOUND",
        executor_target_binding_id="evidence-application-executor-target:" + source["executor_admission_eligibility_id"] + ":" + target["target_revision_id"],
        executor_admission_eligible=True,
        target_snapshot_required=False,
        target_bound=True,
        target_revision_id=target["target_revision_id"],
        target_version=target["target_version"],
        target_values=current,
        target_value_count=len(current),
        admission_evidence=_evidence(source, "admission_evidence"),
        admission_evidence_count=source["admission_evidence_count"],
    )


def build_executor_application_diff(target_binding):
    source = deepcopy(target_binding or {})
    error = _validate_target_binding(source)
    if error:
        return _blocked(source, error)
    evidence = _evidence(source, "admission_evidence")
    current = _target_values(source)
    changes = []
    for field in sorted(evidence):
        before = deepcopy(current.get(field))
        after = deepcopy(evidence[field])
        if before != after:
            changes.append({"field": field, "before": before, "after": after})
    return _base(
        source,
        error=False,
        status="APPLICATION_EXECUTOR_DIFF_READY",
        executor_diff_id="evidence-application-executor-diff:" + source["executor_target_binding_id"],
        target_bound=True,
        target_revision_id=source["target_revision_id"],
        target_version=source["target_version"],
        executor_diff_ready=True,
        proposed_changes=changes,
        proposed_change_count=len(changes),
        no_op=len(changes) == 0,
        admission_evidence=evidence,
        admission_evidence_count=len(evidence),
        target_values=current,
        target_value_count=len(current),
    )


def build_executor_authorization_decision(diff, decision):
    source = deepcopy(diff or {})
    choice = str(decision or "").strip().upper()
    error = _validate_diff(source)
    if error:
        return _blocked(source, error, decision=choice)
    if choice not in {"AUTHORIZE", "REJECT"}:
        return _blocked(source, "APPLICATION_EXECUTOR_DECISION_INVALID", decision=choice)
    granted = choice == "AUTHORIZE"
    return _base(
        source,
        error=False,
        status="APPLICATION_EXECUTOR_AUTHORIZED" if granted else "APPLICATION_EXECUTOR_REJECTED",
        executor_authorization_id="evidence-application-executor-authorization:" + source["executor_diff_id"],
        decision=choice,
        executor_authorized=granted,
        executor_rejected=not granted,
        write_adapter_required=granted,
        target_revision_id=source["target_revision_id"],
        target_version=source["target_version"],
        proposed_changes=deepcopy(source["proposed_changes"]),
        proposed_change_count=source["proposed_change_count"],
        no_op=source["no_op"],
        admission_evidence=_evidence(source, "admission_evidence"),
        admission_evidence_count=source["admission_evidence_count"],
        target_values=_target_values(source),
        target_value_count=source["target_value_count"],
    )


def build_executor_write_handoff(authorization_decision):
    source = deepcopy(authorization_decision or {})
    error = _validate_authorization(source)
    if error:
        return _blocked(source, error)
    if source.get("status") != "APPLICATION_EXECUTOR_AUTHORIZED":
        return _blocked(source, "APPLICATION_EXECUTOR_NOT_AUTHORIZED")
    if source.get("no_op") is True:
        return _blocked(source, "APPLICATION_EXECUTOR_NO_CHANGES")
    return _base(
        source,
        error=False,
        status="APPLICATION_WRITE_ADAPTER_HANDOFF_READY",
        application_write_handoff_id="evidence-application-write-handoff:" + source["executor_authorization_id"],
        executor_authorized=True,
        write_adapter_required=True,
        write_handoff_ready=True,
        stale_lineage_check_required=True,
        readback_verification_required=True,
        target_revision_id=source["target_revision_id"],
        target_version=source["target_version"],
        proposed_changes=deepcopy(source["proposed_changes"]),
        proposed_change_count=source["proposed_change_count"],
    )


def build_executor_admission_audit(eligibility, target_binding, diff, authorization, write_handoff=None):
    eligible, bound, delta, decision = [deepcopy(x or {}) for x in (eligibility, target_binding, diff, authorization)]
    if _validate_eligibility(eligible) or _validate_target_binding(bound) or _validate_diff(delta):
        return _blocked(decision, "APPLICATION_EXECUTOR_AUDIT_INPUT_INVALID")
    error = _validate_authorization(decision)
    if error:
        return _blocked(decision, error)
    if _identity(eligible) != _identity(bound) or _identity(bound) != _identity(delta) or _identity(delta) != _identity(decision):
        return _blocked(decision, "APPLICATION_EXECUTOR_AUDIT_IDENTITY_MISMATCH")
    if eligible.get("preparation_audit_id") != bound.get("preparation_audit_id") or bound.get("preparation_audit_id") != delta.get("preparation_audit_id") or delta.get("preparation_audit_id") != decision.get("preparation_audit_id"):
        return _blocked(decision, "APPLICATION_EXECUTOR_AUDIT_PREPARATION_LINEAGE_MISMATCH")
    if bound.get("target_revision_id") != delta.get("target_revision_id") or delta.get("target_revision_id") != decision.get("target_revision_id"):
        return _blocked(decision, "APPLICATION_EXECUTOR_AUDIT_TARGET_LINEAGE_MISMATCH")
    if bound.get("target_version") != delta.get("target_version") or delta.get("target_version") != decision.get("target_version"):
        return _blocked(decision, "APPLICATION_EXECUTOR_AUDIT_TARGET_LINEAGE_MISMATCH")
    expected_changes = build_executor_application_diff(bound)
    if expected_changes.get("error") or expected_changes.get("proposed_changes") != delta.get("proposed_changes") or expected_changes.get("no_op") != delta.get("no_op"):
        return _blocked(decision, "APPLICATION_EXECUTOR_AUDIT_DIFF_MISMATCH")
    if delta.get("proposed_changes") != decision.get("proposed_changes"):
        return _blocked(decision, "APPLICATION_EXECUTOR_AUDIT_DIFF_MISMATCH")
    authorized = decision.get("executor_authorized") is True
    if authorized and decision.get("no_op") is False:
        target = deepcopy(write_handoff or {})
        error = _validate_write_handoff(target)
        if error:
            return _blocked(decision, error)
        if _identity(target) != _identity(decision) or target.get("executor_authorization_id") != decision.get("executor_authorization_id"):
            return _blocked(decision, "APPLICATION_WRITE_HANDOFF_MISMATCH")
        if target.get("target_revision_id") != decision.get("target_revision_id") or target.get("target_version") != decision.get("target_version"):
            return _blocked(decision, "APPLICATION_WRITE_HANDOFF_MISMATCH")
        if target.get("proposed_changes") != decision.get("proposed_changes"):
            return _blocked(decision, "APPLICATION_WRITE_HANDOFF_MISMATCH")
    elif write_handoff is not None:
        return _blocked(decision, "APPLICATION_WRITE_HANDOFF_FORBIDDEN")
    return _base(
        decision,
        error=False,
        status="APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY",
        executor_admission_audit_id="evidence-application-executor-admission-audit:" + decision["executor_authorization_id"],
        executor_authorized=authorized,
        executor_rejected=decision.get("executor_rejected") is True,
        write_handoff_ready=authorized and decision.get("no_op") is False,
        target_revision_id=decision["target_revision_id"],
        target_version=decision["target_version"],
        proposed_change_count=decision["proposed_change_count"],
        no_op=decision["no_op"],
    )


def _validate_start(handoff, audit):
    if handoff.get("error") is not False or audit.get("error") is not False:
        return "APPLICATION_EXECUTOR_INPUT_ERROR"
    if handoff.get("status") != "APPLICATION_EXECUTION_HANDOFF_READY" or handoff.get("application_execution_handoff_ready") is not True or handoff.get("application_executor_required") is not True:
        return "APPLICATION_EXECUTION_HANDOFF_REQUIRED"
    if audit.get("status") != "APPLICATION_PREPARATION_AUDIT_READY" or audit.get("preparation_approved") is not True or audit.get("application_execution_handoff_ready") is not True:
        return "APPLICATION_PREPARATION_AUDIT_REQUIRED"
    if _ids_error(handoff) or _ids_error(audit) or _identity(handoff) != _identity(audit):
        return "APPLICATION_EXECUTOR_IDENTITY_MISMATCH"
    expected_handoff = "evidence-application-execution-handoff:" + handoff["preparation_decision_id"]
    if handoff.get("application_execution_handoff_id") != expected_handoff:
        return "APPLICATION_EXECUTION_HANDOFF_ID_MISMATCH"
    expected_audit = "evidence-application-preparation-audit:" + audit["preparation_decision_id"]
    if audit.get("preparation_audit_id") != expected_audit:
        return "APPLICATION_PREPARATION_AUDIT_ID_MISMATCH"
    h_evidence = _evidence(handoff, "execution_handoff_evidence")
    a_evidence = _evidence(audit, "audited_evidence")
    if not h_evidence or h_evidence != handoff.get("execution_handoff_evidence") or h_evidence != a_evidence:
        return "APPLICATION_EXECUTOR_EVIDENCE_MISMATCH"
    if handoff.get("execution_handoff_evidence_count") != len(h_evidence) or audit.get("audited_evidence_count") != len(a_evidence):
        return "APPLICATION_EXECUTOR_EVIDENCE_COUNT_MISMATCH"
    if _unsafe(handoff) or _unsafe(audit):
        return "APPLICATION_EXECUTOR_SAFETY_BOUNDARY_VIOLATION"
    return None


def _validate_eligibility(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_EXECUTOR_ADMISSION_ELIGIBLE":
        return "APPLICATION_EXECUTOR_NOT_ELIGIBLE"
    if source.get("executor_admission_eligible") is not True or source.get("target_snapshot_required") is not True:
        return "APPLICATION_EXECUTOR_NOT_ELIGIBLE"
    if _ids_error(source) or not _valid_executor_eligibility_id(source):
        return "APPLICATION_EXECUTOR_LINEAGE_MISMATCH"
    return _payload_error(source, "admission_evidence", "admission_evidence_count")


def _validate_target_snapshot(source, target):
    if not isinstance(target.get("target_revision_id"), str) or not target["target_revision_id"].strip():
        return "APPLICATION_TARGET_REVISION_REQUIRED"
    if not isinstance(target.get("target_version"), int) or isinstance(target.get("target_version"), bool) or target["target_version"] < 1:
        return "APPLICATION_TARGET_VERSION_REQUIRED"
    if target.get("draft_id") != source.get("draft_id") or target.get("sku") != source.get("sku"):
        return "APPLICATION_TARGET_IDENTITY_MISMATCH"
    values = target.get("target_values")
    if not isinstance(values, dict):
        return "APPLICATION_TARGET_VALUES_REQUIRED"
    if any(key not in ALLOWED_EVIDENCE_FIELDS for key in values):
        return "APPLICATION_TARGET_VALUES_UNSAFE"
    return None


def _validate_target_binding(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_EXECUTOR_TARGET_BOUND" or source.get("target_bound") is not True:
        return "APPLICATION_TARGET_BINDING_REQUIRED"
    if _ids_error(source) or not _valid_executor_eligibility_id(source):
        return "APPLICATION_EXECUTOR_LINEAGE_MISMATCH"
    if not isinstance(source.get("target_revision_id"), str) or not source["target_revision_id"].strip():
        return "APPLICATION_TARGET_REVISION_REQUIRED"
    if not isinstance(source.get("target_version"), int) or isinstance(source.get("target_version"), bool) or source["target_version"] < 1:
        return "APPLICATION_TARGET_VERSION_REQUIRED"
    expected = "evidence-application-executor-target:" + source["executor_admission_eligibility_id"] + ":" + source["target_revision_id"]
    if source.get("executor_target_binding_id") != expected:
        return "APPLICATION_TARGET_BINDING_ID_MISMATCH"
    error = _payload_error(source, "admission_evidence", "admission_evidence_count")
    if error:
        return error
    values = source.get("target_values")
    if not isinstance(values, dict) or any(key not in ALLOWED_EVIDENCE_FIELDS for key in values) or source.get("target_value_count") != len(values):
        return "APPLICATION_TARGET_VALUES_UNSAFE"
    return None


def _validate_diff(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_EXECUTOR_DIFF_READY" or source.get("executor_diff_ready") is not True:
        return "APPLICATION_EXECUTOR_DIFF_REQUIRED"
    if _ids_error(source) or not _valid_executor_eligibility_id(source):
        return "APPLICATION_EXECUTOR_LINEAGE_MISMATCH"
    expected_binding = "evidence-application-executor-target:" + source["executor_admission_eligibility_id"] + ":" + source["target_revision_id"]
    if source.get("executor_target_binding_id") != expected_binding:
        return "APPLICATION_TARGET_BINDING_ID_MISMATCH"
    if source.get("executor_diff_id") != "evidence-application-executor-diff:" + expected_binding:
        return "APPLICATION_EXECUTOR_DIFF_ID_MISMATCH"
    expected = build_executor_application_diff(dict(source, status="APPLICATION_EXECUTOR_TARGET_BOUND", target_bound=True, executor_diff_ready=False))
    if expected.get("error") is True:
        return expected.get("code", "APPLICATION_EXECUTOR_DIFF_INVALID")
    if source.get("proposed_changes") != expected.get("proposed_changes") or source.get("proposed_change_count") != expected.get("proposed_change_count") or source.get("no_op") is not expected.get("no_op"):
        return "APPLICATION_EXECUTOR_DIFF_MISMATCH"
    return None


def _validate_authorization(source):
    if _validate_diff(dict(source, status="APPLICATION_EXECUTOR_DIFF_READY", executor_diff_ready=True)):
        return "APPLICATION_EXECUTOR_AUTHORIZATION_INPUT_INVALID"
    if source.get("executor_authorization_id") != "evidence-application-executor-authorization:" + source["executor_diff_id"]:
        return "APPLICATION_EXECUTOR_AUTHORIZATION_ID_MISMATCH"
    if source.get("status") == "APPLICATION_EXECUTOR_AUTHORIZED":
        if source.get("decision") != "AUTHORIZE" or source.get("executor_authorized") is not True or source.get("executor_rejected") is not False or source.get("write_adapter_required") is not True:
            return "APPLICATION_EXECUTOR_AUTHORIZATION_CONTRADICTORY"
    elif source.get("status") == "APPLICATION_EXECUTOR_REJECTED":
        if source.get("decision") != "REJECT" or source.get("executor_authorized") is not False or source.get("executor_rejected") is not True or source.get("write_adapter_required") is not False:
            return "APPLICATION_EXECUTOR_AUTHORIZATION_CONTRADICTORY"
    else:
        return "APPLICATION_EXECUTOR_AUTHORIZATION_REQUIRED"
    if _unsafe(source):
        return "APPLICATION_EXECUTOR_SAFETY_BOUNDARY_VIOLATION"
    return None


def _validate_write_handoff(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_WRITE_ADAPTER_HANDOFF_READY":
        return "APPLICATION_WRITE_HANDOFF_REQUIRED"
    if source.get("executor_authorized") is not True or source.get("write_adapter_required") is not True or source.get("write_handoff_ready") is not True:
        return "APPLICATION_WRITE_HANDOFF_REQUIRED"
    if source.get("stale_lineage_check_required") is not True or source.get("readback_verification_required") is not True:
        return "APPLICATION_WRITE_SAFETY_REQUIREMENTS_MISSING"
    if _unsafe(source):
        return "APPLICATION_EXECUTOR_SAFETY_BOUNDARY_VIOLATION"
    expected = "evidence-application-write-handoff:" + source.get("executor_authorization_id", "")
    if source.get("application_write_handoff_id") != expected:
        return "APPLICATION_WRITE_HANDOFF_ID_MISMATCH"
    return None


def _valid_executor_eligibility_id(source):
    handoff_id = source.get("application_execution_handoff_id")
    if not isinstance(handoff_id, str) or not handoff_id:
        return False
    return source.get("executor_admission_eligibility_id") == "evidence-application-executor-admission-eligibility:" + handoff_id


def _ids_error(source):
    return any(not isinstance(source.get(field), str) or not source[field].strip() for field in IDENTITY_FIELDS)


def _payload_error(source, field, count):
    if _unsafe(source):
        return "APPLICATION_EXECUTOR_SAFETY_BOUNDARY_VIOLATION"
    evidence = _evidence(source, field)
    if not evidence or evidence != source.get(field):
        return "APPLICATION_EXECUTOR_EVIDENCE_UNSAFE"
    if source.get(count) != len(evidence):
        return "APPLICATION_EXECUTOR_EVIDENCE_COUNT_MISMATCH"
    return None


def _evidence(source, field):
    values = source.get(field)
    if not isinstance(values, dict):
        return {}
    return {k: deepcopy(v) for k, v in values.items() if k in ALLOWED_EVIDENCE_FIELDS and v not in (None, "")}


def _target_values(source):
    values = source.get("target_values")
    if not isinstance(values, dict):
        return {}
    return {k: deepcopy(v) for k, v in values.items() if k in ALLOWED_EVIDENCE_FIELDS}


def _unsafe(source):
    return any(source.get(field) is not False for field in SAFETY_FIELDS) or source.get("source_freshness_proven") is not False


def _identity(source):
    return tuple(source.get(field) for field in IDENTITY_FIELDS)


def _base(source, **additions):
    carry = IDENTITY_FIELDS + (
        "application_execution_handoff_id", "preparation_audit_id",
        "executor_admission_eligibility_id", "executor_target_binding_id", "executor_diff_id",
        "executor_authorization_id",
    )
    result = {field: deepcopy(source.get(field)) for field in carry if source.get(field) is not None}
    result.update({field: False for field in SAFETY_FIELDS})
    result["source_freshness_proven"] = False
    result.update(additions)
    return result


def _blocked(source, code, decision=None):
    return _base(
        source,
        error=True,
        code=code,
        status="APPLICATION_EXECUTOR_ADMISSION_BLOCKED",
        decision=decision,
        executor_admission_eligible=False,
        executor_authorized=False,
        executor_rejected=False,
        write_adapter_required=False,
        write_handoff_ready=False,
    )
