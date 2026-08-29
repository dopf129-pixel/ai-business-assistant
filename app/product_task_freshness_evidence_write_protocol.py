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


def build_write_protocol_eligibility(write_handoff, executor_audit, reread_snapshot):
    handoff = deepcopy(write_handoff or {})
    audit = deepcopy(executor_audit or {})
    snapshot = deepcopy(reread_snapshot or {})
    error = _validate_start(handoff, audit, snapshot)
    if error:
        return _blocked(handoff, error)
    return _base(
        handoff,
        error=False,
        status="APPLICATION_WRITE_PROTOCOL_ELIGIBLE",
        write_protocol_eligibility_id="evidence-write-protocol-eligibility:" + handoff["application_write_handoff_id"],
        executor_admission_audit_id=audit["executor_admission_audit_id"],
        write_protocol_eligible=True,
        stale_lineage_check_passed=True,
        target_revision_id=snapshot["target_revision_id"],
        target_version=snapshot["target_version"],
        current_values=_values(snapshot),
        current_value_count=len(_values(snapshot)),
        proposed_changes=deepcopy(handoff["proposed_changes"]),
        proposed_change_count=handoff["proposed_change_count"],
    )


def build_write_request(eligibility):
    source = deepcopy(eligibility or {})
    error = _validate_eligibility(source)
    if error:
        return _blocked(source, error)
    changes = deepcopy(source["proposed_changes"])
    return _base(
        source,
        error=False,
        status="APPLICATION_WRITE_REQUEST_READY",
        write_request_id="evidence-write-request:" + source["write_protocol_eligibility_id"],
        write_protocol_eligible=True,
        write_request_ready=True,
        expected_target_revision_id=source["target_revision_id"],
        expected_target_version=source["target_version"],
        write_operations=changes,
        write_operation_count=len(changes),
        readback_verification_required=True,
    )


def build_write_request_decision(write_request, decision):
    source = deepcopy(write_request or {})
    choice = str(decision or "").strip().upper()
    error = _validate_request(source)
    if error:
        return _blocked(source, error, decision=choice)
    if choice not in {"APPLY", "REJECT"}:
        return _blocked(source, "APPLICATION_WRITE_DECISION_INVALID", decision=choice)
    approved = choice == "APPLY"
    return _base(
        source,
        error=False,
        status="APPLICATION_WRITE_APPROVED" if approved else "APPLICATION_WRITE_REJECTED",
        write_decision_id="evidence-write-decision:" + source["write_request_id"],
        decision=choice,
        write_approved=approved,
        write_rejected=not approved,
        write_adapter_invocation_allowed=False,
        expected_target_revision_id=source["expected_target_revision_id"],
        expected_target_version=source["expected_target_version"],
        write_operations=deepcopy(source["write_operations"]),
        write_operation_count=source["write_operation_count"],
    )


def build_write_adapter_invocation_contract(write_decision):
    source = deepcopy(write_decision or {})
    error = _validate_decision(source)
    if error:
        return _blocked(source, error)
    if source.get("status") != "APPLICATION_WRITE_APPROVED":
        return _blocked(source, "APPLICATION_WRITE_NOT_APPROVED")
    return _base(
        source,
        error=False,
        status="APPLICATION_WRITE_ADAPTER_INVOCATION_CONTRACT_READY",
        write_adapter_contract_id="evidence-write-adapter-contract:" + source["write_decision_id"],
        write_approved=True,
        write_adapter_required=True,
        write_adapter_invocation_allowed=False,
        compare_and_set_required=True,
        readback_verification_required=True,
        expected_target_revision_id=source["expected_target_revision_id"],
        expected_target_version=source["expected_target_version"],
        write_operations=deepcopy(source["write_operations"]),
        write_operation_count=source["write_operation_count"],
    )


def build_write_protocol_audit(eligibility, write_request, decision, adapter_contract=None):
    eligible = deepcopy(eligibility or {})
    request = deepcopy(write_request or {})
    decided = deepcopy(decision or {})
    if _validate_eligibility(eligible) or _validate_request(request):
        return _blocked(decided, "APPLICATION_WRITE_PROTOCOL_AUDIT_INPUT_INVALID")
    error = _validate_decision(decided)
    if error:
        return _blocked(decided, error)
    if eligible.get("write_protocol_eligibility_id") != request.get("write_protocol_eligibility_id"):
        return _blocked(decided, "APPLICATION_WRITE_PROTOCOL_AUDIT_LINEAGE_MISMATCH")
    if request.get("write_request_id") != decided.get("write_request_id"):
        return _blocked(decided, "APPLICATION_WRITE_PROTOCOL_AUDIT_LINEAGE_MISMATCH")
    if request.get("expected_target_revision_id") != decided.get("expected_target_revision_id"):
        return _blocked(decided, "APPLICATION_WRITE_PROTOCOL_AUDIT_TARGET_MISMATCH")
    if request.get("expected_target_version") != decided.get("expected_target_version"):
        return _blocked(decided, "APPLICATION_WRITE_PROTOCOL_AUDIT_TARGET_MISMATCH")
    if request.get("write_operations") != decided.get("write_operations"):
        return _blocked(decided, "APPLICATION_WRITE_PROTOCOL_AUDIT_OPERATIONS_MISMATCH")
    approved = decided.get("write_approved") is True
    if approved:
        contract = deepcopy(adapter_contract or {})
        error = _validate_adapter_contract(contract)
        if error:
            return _blocked(decided, error)
        if contract.get("write_decision_id") != decided.get("write_decision_id"):
            return _blocked(decided, "APPLICATION_WRITE_ADAPTER_CONTRACT_MISMATCH")
        if contract.get("expected_target_revision_id") != decided.get("expected_target_revision_id"):
            return _blocked(decided, "APPLICATION_WRITE_ADAPTER_CONTRACT_MISMATCH")
        if contract.get("expected_target_version") != decided.get("expected_target_version"):
            return _blocked(decided, "APPLICATION_WRITE_ADAPTER_CONTRACT_MISMATCH")
        if contract.get("write_operations") != decided.get("write_operations"):
            return _blocked(decided, "APPLICATION_WRITE_ADAPTER_CONTRACT_MISMATCH")
    elif adapter_contract is not None:
        return _blocked(decided, "REJECTED_WRITE_CANNOT_HAVE_ADAPTER_CONTRACT")
    return _base(
        decided,
        error=False,
        status="APPLICATION_WRITE_PROTOCOL_AUDIT_READY",
        write_protocol_audit_id="evidence-write-protocol-audit:" + decided["write_decision_id"],
        write_approved=approved,
        write_rejected=not approved,
        adapter_contract_ready=approved,
        write_adapter_invocation_allowed=False,
        persistent=False,
        task_draft_mutated=False,
        executed=False,
    )


def _validate_start(handoff, audit, snapshot):
    if handoff.get("error") is not False or audit.get("error") is not False:
        return "APPLICATION_WRITE_PROTOCOL_INPUT_ERROR"
    if handoff.get("status") != "APPLICATION_WRITE_ADAPTER_HANDOFF_READY":
        return "APPLICATION_WRITE_HANDOFF_REQUIRED"
    if handoff.get("write_handoff_ready") is not True or handoff.get("write_adapter_required") is not True:
        return "APPLICATION_WRITE_HANDOFF_REQUIRED"
    if audit.get("status") != "APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY":
        return "APPLICATION_EXECUTOR_AUDIT_REQUIRED"
    if audit.get("executor_authorized") is not True or audit.get("write_handoff_ready") is not True:
        return "APPLICATION_EXECUTOR_AUDIT_NOT_AUTHORIZED"
    if _unsafe(handoff) or _unsafe(audit):
        return "APPLICATION_WRITE_PROTOCOL_SAFETY_BOUNDARY_VIOLATION"
    if not isinstance(handoff.get("application_write_handoff_id"), str) or not handoff["application_write_handoff_id"].strip():
        return "APPLICATION_WRITE_HANDOFF_ID_REQUIRED"
    expected_audit_id = "evidence-application-executor-admission-audit:" + handoff.get("executor_authorization_id", "")
    if audit.get("executor_admission_audit_id") != expected_audit_id:
        return "APPLICATION_EXECUTOR_AUDIT_LINEAGE_MISMATCH"
    if handoff.get("target_revision_id") != audit.get("target_revision_id") or handoff.get("target_version") != audit.get("target_version"):
        return "APPLICATION_WRITE_PROTOCOL_TARGET_LINEAGE_MISMATCH"
    if handoff.get("proposed_change_count") != len(handoff.get("proposed_changes") or []):
        return "APPLICATION_WRITE_PROTOCOL_CHANGE_COUNT_MISMATCH"
    if audit.get("proposed_change_count") != handoff.get("proposed_change_count"):
        return "APPLICATION_WRITE_PROTOCOL_CHANGE_COUNT_MISMATCH"
    return _validate_reread_snapshot(handoff, snapshot)


def _validate_reread_snapshot(handoff, snapshot):
    if snapshot.get("draft_id") != handoff.get("draft_id") or snapshot.get("sku") != handoff.get("sku"):
        return "APPLICATION_WRITE_REREAD_IDENTITY_MISMATCH"
    if snapshot.get("target_revision_id") != handoff.get("target_revision_id"):
        return "APPLICATION_WRITE_STALE_REVISION"
    if snapshot.get("target_version") != handoff.get("target_version"):
        return "APPLICATION_WRITE_STALE_VERSION"
    values = snapshot.get("current_values")
    if not isinstance(values, dict) or any(key not in ALLOWED_EVIDENCE_FIELDS for key in values):
        return "APPLICATION_WRITE_REREAD_VALUES_UNSAFE"
    for change in handoff.get("proposed_changes") or []:
        if not isinstance(change, dict) or set(change) != {"field", "before", "after"}:
            return "APPLICATION_WRITE_CHANGE_SCHEMA_INVALID"
        field = change.get("field")
        if field not in ALLOWED_EVIDENCE_FIELDS:
            return "APPLICATION_WRITE_CHANGE_FIELD_UNSAFE"
        if values.get(field) != change.get("before"):
            return "APPLICATION_WRITE_STALE_CURRENT_VALUE"
    return None


def _validate_eligibility(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_WRITE_PROTOCOL_ELIGIBLE":
        return "APPLICATION_WRITE_PROTOCOL_NOT_ELIGIBLE"
    if source.get("write_protocol_eligible") is not True or source.get("stale_lineage_check_passed") is not True:
        return "APPLICATION_WRITE_PROTOCOL_NOT_ELIGIBLE"
    if source.get("write_protocol_eligibility_id") != "evidence-write-protocol-eligibility:" + source.get("application_write_handoff_id", ""):
        return "APPLICATION_WRITE_PROTOCOL_ELIGIBILITY_ID_MISMATCH"
    if _unsafe(source):
        return "APPLICATION_WRITE_PROTOCOL_SAFETY_BOUNDARY_VIOLATION"
    if not isinstance(source.get("target_version"), int) or isinstance(source.get("target_version"), bool) or source["target_version"] < 1:
        return "APPLICATION_WRITE_TARGET_VERSION_INVALID"
    if source.get("proposed_change_count") != len(source.get("proposed_changes") or []):
        return "APPLICATION_WRITE_PROTOCOL_CHANGE_COUNT_MISMATCH"
    return None


def _validate_request(source):
    if source.get("error") is not False or source.get("status") != "APPLICATION_WRITE_REQUEST_READY":
        return "APPLICATION_WRITE_REQUEST_REQUIRED"
    if source.get("write_request_ready") is not True:
        return "APPLICATION_WRITE_REQUEST_REQUIRED"
    if source.get("write_request_id") != "evidence-write-request:" + source.get("write_protocol_eligibility_id", ""):
        return "APPLICATION_WRITE_REQUEST_ID_MISMATCH"
    if source.get("expected_target_revision_id") != source.get("target_revision_id"):
        return "APPLICATION_WRITE_REQUEST_TARGET_MISMATCH"
    if source.get("expected_target_version") != source.get("target_version"):
        return "APPLICATION_WRITE_REQUEST_TARGET_MISMATCH"
    if source.get("write_operations") != source.get("proposed_changes"):
        return "APPLICATION_WRITE_REQUEST_OPERATIONS_MISMATCH"
    if source.get("write_operation_count") != len(source.get("write_operations") or []):
        return "APPLICATION_WRITE_REQUEST_OPERATION_COUNT_MISMATCH"
    if _unsafe(source):
        return "APPLICATION_WRITE_PROTOCOL_SAFETY_BOUNDARY_VIOLATION"
    return None


def _validate_decision(source):
    request_view = dict(source)
    request_view["status"] = "APPLICATION_WRITE_REQUEST_READY"
    request_view["write_request_ready"] = True
    if _validate_request(request_view):
        return "APPLICATION_WRITE_DECISION_INPUT_INVALID"
    expected_id = "evidence-write-decision:" + source.get("write_request_id", "")
    if source.get("write_decision_id") != expected_id:
        return "APPLICATION_WRITE_DECISION_ID_MISMATCH"
    if source.get("status") == "APPLICATION_WRITE_APPROVED":
        if source.get("decision") != "APPLY" or source.get("write_approved") is not True or source.get("write_rejected") is not False:
            return "APPLICATION_WRITE_DECISION_CONTRADICTORY"
    elif source.get("status") == "APPLICATION_WRITE_REJECTED":
        if source.get("decision") != "REJECT" or source.get("write_approved") is not False or source.get("write_rejected") is not True:
            return "APPLICATION_WRITE_DECISION_CONTRADICTORY"
    else:
        return "APPLICATION_WRITE_DECISION_REQUIRED"
    if source.get("write_adapter_invocation_allowed") is not False:
        return "APPLICATION_WRITE_ADAPTER_INVOCATION_BOUNDARY_VIOLATION"
    return None


def _validate_adapter_contract(source):
    decision_view = dict(source)
    decision_view["status"] = "APPLICATION_WRITE_APPROVED"
    decision_view["decision"] = "APPLY"
    decision_view["write_approved"] = True
    decision_view["write_rejected"] = False
    decision_view["write_adapter_invocation_allowed"] = False
    if _validate_decision(decision_view):
        return "APPLICATION_WRITE_ADAPTER_CONTRACT_INPUT_INVALID"
    if source.get("status") != "APPLICATION_WRITE_ADAPTER_INVOCATION_CONTRACT_READY":
        return "APPLICATION_WRITE_ADAPTER_CONTRACT_REQUIRED"
    if source.get("write_adapter_contract_id") != "evidence-write-adapter-contract:" + source.get("write_decision_id", ""):
        return "APPLICATION_WRITE_ADAPTER_CONTRACT_ID_MISMATCH"
    if source.get("compare_and_set_required") is not True or source.get("readback_verification_required") is not True:
        return "APPLICATION_WRITE_ADAPTER_CONTRACT_GUARD_REQUIRED"
    if source.get("write_adapter_invocation_allowed") is not False:
        return "APPLICATION_WRITE_ADAPTER_INVOCATION_BOUNDARY_VIOLATION"
    if _unsafe(source):
        return "APPLICATION_WRITE_PROTOCOL_SAFETY_BOUNDARY_VIOLATION"
    return None


def _values(snapshot):
    values = snapshot.get("current_values")
    if not isinstance(values, dict):
        return {}
    return {key: deepcopy(value) for key, value in values.items() if key in ALLOWED_EVIDENCE_FIELDS}


def _unsafe(source):
    return any(source.get(field) is not False for field in SAFETY_FIELDS) or source.get("source_freshness_proven") is not False


def _base(source, **additions):
    carry = (
        "draft_id", "sku", "executor_authorization_id", "application_write_handoff_id",
        "write_protocol_eligibility_id", "write_request_id", "write_decision_id",
        "target_revision_id", "target_version", "proposed_changes", "proposed_change_count",
        "expected_target_revision_id", "expected_target_version", "write_operations", "write_operation_count",
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
        status="APPLICATION_WRITE_PROTOCOL_BLOCKED",
        decision=decision,
        write_protocol_eligible=False,
        write_request_ready=False,
        write_approved=False,
        write_rejected=False,
        write_adapter_required=False,
        write_adapter_invocation_allowed=False,
        adapter_contract_ready=False,
    )
