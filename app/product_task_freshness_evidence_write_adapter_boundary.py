from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = (
    "sales_observed_at",
    "sales_source_recorded_at",
    "stock_observed_at",
    "stock_source_recorded_at",
    "unit_economics_observed_at",
    "unit_economics_source_recorded_at",
)
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


def build_write_adapter_capability(descriptor):
    source = deepcopy(descriptor or {})
    adapter_id = source.get("adapter_id")
    if not isinstance(adapter_id, str) or not adapter_id.strip():
        return _blocked(source, "WRITE_ADAPTER_ID_REQUIRED")
    if source.get("target_type") != "TASK_DRAFT_FRESHNESS":
        return _blocked(source, "WRITE_ADAPTER_TARGET_TYPE_UNSUPPORTED")
    if source.get("compare_and_set_supported") is not True:
        return _blocked(source, "WRITE_ADAPTER_CAS_REQUIRED")
    if source.get("readback_supported") is not True:
        return _blocked(source, "WRITE_ADAPTER_READBACK_REQUIRED")
    if source.get("atomic_single_target_supported") is not True:
        return _blocked(source, "WRITE_ADAPTER_ATOMIC_TARGET_REQUIRED")
    fields = source.get("allowed_fields")
    if fields != list(ALLOWED_EVIDENCE_FIELDS):
        return _blocked(source, "WRITE_ADAPTER_ALLOWED_FIELDS_MISMATCH")
    return _base(
        source,
        error=False,
        status="WRITE_ADAPTER_CAPABILITY_READY",
        capability_id="freshness-write-adapter-capability:" + adapter_id,
        adapter_id=adapter_id,
        target_type="TASK_DRAFT_FRESHNESS",
        compare_and_set_supported=True,
        readback_supported=True,
        atomic_single_target_supported=True,
        allowed_fields=list(ALLOWED_EVIDENCE_FIELDS),
        adapter_invocation_allowed=False,
        adapter_invoked=False,
    )


def build_adapter_invocation_eligibility(protocol_audit, adapter_contract, capability):
    audit = deepcopy(protocol_audit or {})
    contract = deepcopy(adapter_contract or {})
    cap = deepcopy(capability or {})
    error = _validate_inputs(audit, contract, cap)
    if error:
        return _blocked(contract, error)
    operations = deepcopy(contract["write_operations"])
    return _base(
        contract,
        error=False,
        status="WRITE_ADAPTER_INVOCATION_ELIGIBLE",
        invocation_eligibility_id="freshness-write-adapter-invocation-eligibility:" + contract["write_adapter_contract_id"],
        capability_id=cap["capability_id"],
        adapter_id=cap["adapter_id"],
        executor_authorization_id=contract["executor_authorization_id"],
        application_write_handoff_id=contract["application_write_handoff_id"],
        write_protocol_eligibility_id=contract["write_protocol_eligibility_id"],
        write_request_id=contract["write_request_id"],
        write_decision_id=contract["write_decision_id"],
        write_adapter_contract_id=contract["write_adapter_contract_id"],
        write_protocol_audit_id=audit["write_protocol_audit_id"],
        expected_target_revision_id=contract["expected_target_revision_id"],
        expected_target_version=contract["expected_target_version"],
        write_operations=operations,
        write_operation_count=len(operations),
        invocation_eligible=True,
        preflight_reread_required=True,
        adapter_invocation_allowed=False,
        adapter_invoked=False,
    )


def build_adapter_execution_envelope(eligibility, preflight_snapshot):
    source = deepcopy(eligibility or {})
    snapshot = deepcopy(preflight_snapshot or {})
    error = _validate_eligibility(source)
    if error:
        return _blocked(source, error)
    error = _validate_preflight(source, snapshot)
    if error:
        return _blocked(source, error)
    expected_values = deepcopy(snapshot["current_values"])
    for operation in source["write_operations"]:
        expected_values[operation["field"]] = deepcopy(operation["after"])
    return _base(
        source,
        error=False,
        status="WRITE_ADAPTER_EXECUTION_ENVELOPE_READY",
        execution_envelope_id="freshness-write-adapter-execution-envelope:" + source["invocation_eligibility_id"],
        invocation_eligible=True,
        preflight_reread_passed=True,
        expected_target_revision_id=source["expected_target_revision_id"],
        expected_target_version=source["expected_target_version"],
        preflight_values=deepcopy(snapshot["current_values"]),
        write_operations=deepcopy(source["write_operations"]),
        write_operation_count=source["write_operation_count"],
        expected_readback_values=expected_values,
        adapter_invocation_allowed=False,
        adapter_invoked=False,
    )


def build_adapter_readback_contract(execution_envelope):
    source = deepcopy(execution_envelope or {})
    error = _validate_envelope(source)
    if error:
        return _blocked(source, error)
    return _base(
        source,
        error=False,
        status="WRITE_ADAPTER_READBACK_CONTRACT_READY",
        readback_contract_id="freshness-write-adapter-readback-contract:" + source["execution_envelope_id"],
        expected_target_revision_id=source["expected_target_revision_id"],
        expected_target_version=source["expected_target_version"],
        expected_readback_values=deepcopy(source["expected_readback_values"]),
        exact_field_readback_required=True,
        post_write_version_evidence_required=True,
        mutation_success_claim_allowed=False,
        adapter_invocation_allowed=False,
        adapter_invoked=False,
    )


def build_write_adapter_boundary_audit(capability, eligibility, envelope, readback_contract):
    cap = deepcopy(capability or {})
    eligible = deepcopy(eligibility or {})
    env = deepcopy(envelope or {})
    readback = deepcopy(readback_contract or {})
    if _validate_capability(cap):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_CAPABILITY_INVALID")
    if _validate_eligibility(eligible):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_ELIGIBILITY_INVALID")
    if _validate_envelope(env):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_ENVELOPE_INVALID")
    if _validate_readback_contract(readback):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_READBACK_INVALID")
    if eligible.get("capability_id") != cap.get("capability_id") or eligible.get("adapter_id") != cap.get("adapter_id"):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_CAPABILITY_MISMATCH")
    if env.get("invocation_eligibility_id") != eligible.get("invocation_eligibility_id"):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_LINEAGE_MISMATCH")
    if readback.get("execution_envelope_id") != env.get("execution_envelope_id"):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_LINEAGE_MISMATCH")
    for item in (eligible, env, readback):
        if item.get("expected_target_revision_id") != eligible.get("expected_target_revision_id"):
            return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_TARGET_MISMATCH")
        if item.get("expected_target_version") != eligible.get("expected_target_version"):
            return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_TARGET_MISMATCH")
    if env.get("write_operations") != eligible.get("write_operations"):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_OPERATIONS_MISMATCH")
    if readback.get("expected_readback_values") != env.get("expected_readback_values"):
        return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_READBACK_MISMATCH")
    return _base(
        eligible,
        error=False,
        status="WRITE_ADAPTER_BOUNDARY_AUDIT_READY",
        boundary_audit_id="freshness-write-adapter-boundary-audit:" + readback["readback_contract_id"],
        capability_id=cap["capability_id"],
        adapter_id=cap["adapter_id"],
        invocation_eligible=True,
        execution_envelope_ready=True,
        readback_contract_ready=True,
        mutation_success_claim_allowed=False,
        adapter_invocation_allowed=False,
        adapter_invoked=False,
    )


def _validate_inputs(audit, contract, capability):
    error = _validate_capability(capability)
    if error:
        return error
    if audit.get("error") is not False or audit.get("status") != "APPLICATION_WRITE_PROTOCOL_AUDIT_READY":
        return "WRITE_PROTOCOL_AUDIT_REQUIRED"
    if audit.get("write_approved") is not True or audit.get("adapter_contract_ready") is not True:
        return "WRITE_PROTOCOL_AUDIT_NOT_APPROVED"
    if contract.get("error") is not False or contract.get("status") != "APPLICATION_WRITE_ADAPTER_INVOCATION_CONTRACT_READY":
        return "WRITE_ADAPTER_INVOCATION_CONTRACT_REQUIRED"
    if contract.get("write_approved") is not True or contract.get("compare_and_set_required") is not True or contract.get("readback_verification_required") is not True:
        return "WRITE_ADAPTER_INVOCATION_CONTRACT_GUARDS_REQUIRED"
    if contract.get("write_adapter_invocation_allowed") is not False:
        return "WRITE_ADAPTER_INVOCATION_BOUNDARY_VIOLATION"
    if _unsafe(audit) or _unsafe(contract):
        return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    expected_handoff = "evidence-application-write-handoff:" + contract.get("executor_authorization_id", "")
    expected_eligibility = "evidence-write-protocol-eligibility:" + expected_handoff
    expected_request = "evidence-write-request:" + expected_eligibility
    expected_decision = "evidence-write-decision:" + expected_request
    expected_contract = "evidence-write-adapter-contract:" + expected_decision
    expected_audit = "evidence-write-protocol-audit:" + expected_decision
    expected = (
        ("application_write_handoff_id", expected_handoff),
        ("write_protocol_eligibility_id", expected_eligibility),
        ("write_request_id", expected_request),
        ("write_decision_id", expected_decision),
        ("write_adapter_contract_id", expected_contract),
    )
    if any(contract.get(field) != value for field, value in expected):
        return "WRITE_ADAPTER_UPSTREAM_LINEAGE_MISMATCH"
    if audit.get("write_protocol_audit_id") != expected_audit:
        return "WRITE_ADAPTER_PROTOCOL_AUDIT_LINEAGE_MISMATCH"
    if audit.get("write_decision_id") != contract.get("write_decision_id"):
        return "WRITE_ADAPTER_PROTOCOL_AUDIT_LINEAGE_MISMATCH"
    if audit.get("expected_target_revision_id") != contract.get("expected_target_revision_id"):
        return "WRITE_ADAPTER_TARGET_LINEAGE_MISMATCH"
    if audit.get("expected_target_version") != contract.get("expected_target_version"):
        return "WRITE_ADAPTER_TARGET_LINEAGE_MISMATCH"
    return _validate_operations(contract.get("write_operations"), contract.get("write_operation_count"))


def _validate_capability(source):
    if source.get("error") is not False or source.get("status") != "WRITE_ADAPTER_CAPABILITY_READY":
        return "WRITE_ADAPTER_CAPABILITY_REQUIRED"
    adapter_id = source.get("adapter_id")
    if not isinstance(adapter_id, str) or not adapter_id.strip():
        return "WRITE_ADAPTER_ID_REQUIRED"
    if source.get("capability_id") != "freshness-write-adapter-capability:" + adapter_id:
        return "WRITE_ADAPTER_CAPABILITY_ID_MISMATCH"
    if source.get("target_type") != "TASK_DRAFT_FRESHNESS":
        return "WRITE_ADAPTER_TARGET_TYPE_UNSUPPORTED"
    if source.get("compare_and_set_supported") is not True or source.get("readback_supported") is not True or source.get("atomic_single_target_supported") is not True:
        return "WRITE_ADAPTER_CAPABILITY_INSUFFICIENT"
    if source.get("allowed_fields") != list(ALLOWED_EVIDENCE_FIELDS):
        return "WRITE_ADAPTER_ALLOWED_FIELDS_MISMATCH"
    if source.get("adapter_invocation_allowed") is not False or source.get("adapter_invoked") is not False:
        return "WRITE_ADAPTER_INVOCATION_BOUNDARY_VIOLATION"
    return None


def _validate_eligibility(source):
    if source.get("error") is not False or source.get("status") != "WRITE_ADAPTER_INVOCATION_ELIGIBLE" or source.get("invocation_eligible") is not True:
        return "WRITE_ADAPTER_INVOCATION_NOT_ELIGIBLE"
    if _unsafe(source) or source.get("adapter_invocation_allowed") is not False or source.get("adapter_invoked") is not False:
        return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    expected_contract = "evidence-write-adapter-contract:" + source.get("write_decision_id", "")
    if source.get("write_adapter_contract_id") != expected_contract:
        return "WRITE_ADAPTER_CONTRACT_LINEAGE_MISMATCH"
    if source.get("invocation_eligibility_id") != "freshness-write-adapter-invocation-eligibility:" + expected_contract:
        return "WRITE_ADAPTER_INVOCATION_ELIGIBILITY_ID_MISMATCH"
    return _validate_operations(source.get("write_operations"), source.get("write_operation_count"))


def _validate_preflight(source, snapshot):
    if snapshot.get("draft_id") != source.get("draft_id") or snapshot.get("sku") != source.get("sku"):
        return "WRITE_ADAPTER_PREFLIGHT_IDENTITY_MISMATCH"
    if snapshot.get("target_revision_id") != source.get("expected_target_revision_id"):
        return "WRITE_ADAPTER_PREFLIGHT_STALE_REVISION"
    if snapshot.get("target_version") != source.get("expected_target_version"):
        return "WRITE_ADAPTER_PREFLIGHT_STALE_VERSION"
    values = snapshot.get("current_values")
    if not isinstance(values, dict) or any(field not in ALLOWED_EVIDENCE_FIELDS for field in values):
        return "WRITE_ADAPTER_PREFLIGHT_VALUES_UNSAFE"
    for operation in source["write_operations"]:
        if values.get(operation["field"]) != operation["before"]:
            return "WRITE_ADAPTER_PREFLIGHT_STALE_CURRENT_VALUE"
    return None


def _validate_envelope(source):
    if source.get("error") is not False or source.get("status") != "WRITE_ADAPTER_EXECUTION_ENVELOPE_READY":
        return "WRITE_ADAPTER_EXECUTION_ENVELOPE_REQUIRED"
    if source.get("preflight_reread_passed") is not True or source.get("invocation_eligible") is not True:
        return "WRITE_ADAPTER_EXECUTION_ENVELOPE_INVALID"
    if source.get("execution_envelope_id") != "freshness-write-adapter-execution-envelope:" + source.get("invocation_eligibility_id", ""):
        return "WRITE_ADAPTER_EXECUTION_ENVELOPE_ID_MISMATCH"
    if _unsafe(source) or source.get("adapter_invocation_allowed") is not False or source.get("adapter_invoked") is not False:
        return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    error = _validate_operations(source.get("write_operations"), source.get("write_operation_count"))
    if error:
        return error
    expected = deepcopy(source.get("preflight_values") or {})
    for operation in source["write_operations"]:
        expected[operation["field"]] = deepcopy(operation["after"])
    if source.get("expected_readback_values") != expected:
        return "WRITE_ADAPTER_EXPECTED_READBACK_MISMATCH"
    return None


def _validate_readback_contract(source):
    if source.get("error") is not False or source.get("status") != "WRITE_ADAPTER_READBACK_CONTRACT_READY":
        return "WRITE_ADAPTER_READBACK_CONTRACT_REQUIRED"
    if source.get("readback_contract_id") != "freshness-write-adapter-readback-contract:" + source.get("execution_envelope_id", ""):
        return "WRITE_ADAPTER_READBACK_CONTRACT_ID_MISMATCH"
    if source.get("exact_field_readback_required") is not True or source.get("post_write_version_evidence_required") is not True:
        return "WRITE_ADAPTER_READBACK_GUARDS_REQUIRED"
    if source.get("mutation_success_claim_allowed") is not False:
        return "WRITE_ADAPTER_SUCCESS_CLAIM_BOUNDARY_VIOLATION"
    if _unsafe(source) or source.get("adapter_invocation_allowed") is not False or source.get("adapter_invoked") is not False:
        return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    return None


def _validate_operations(operations, count):
    if not isinstance(operations, list) or not operations or count != len(operations):
        return "WRITE_ADAPTER_OPERATIONS_INVALID"
    seen = set()
    ordered = []
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != {"field", "before", "after"}:
            return "WRITE_ADAPTER_OPERATION_SCHEMA_INVALID"
        field = operation.get("field")
        if field not in ALLOWED_EVIDENCE_FIELDS or field in seen:
            return "WRITE_ADAPTER_OPERATION_FIELD_INVALID"
        if operation.get("before") == operation.get("after"):
            return "WRITE_ADAPTER_OPERATION_NOOP"
        seen.add(field)
        ordered.append(field)
    if ordered != sorted(ordered):
        return "WRITE_ADAPTER_OPERATION_ORDER_INVALID"
    return None


def _unsafe(source):
    return any(source.get(field) is not False for field in SAFETY_FIELDS) or source.get("source_freshness_proven") is not False


def _base(source, **additions):
    carry = (
        "draft_id", "sku", "executor_authorization_id", "application_write_handoff_id",
        "write_protocol_eligibility_id", "write_request_id", "write_decision_id",
        "write_adapter_contract_id", "write_protocol_audit_id", "capability_id", "adapter_id",
        "invocation_eligibility_id", "execution_envelope_id", "readback_contract_id",
        "expected_target_revision_id", "expected_target_version", "write_operations", "write_operation_count",
    )
    result = {field: deepcopy(source.get(field)) for field in carry if source.get(field) is not None}
    result.update({field: False for field in SAFETY_FIELDS})
    result["source_freshness_proven"] = False
    result.update(additions)
    return result


def _blocked(source, code):
    return _base(
        source,
        error=True,
        code=code,
        status="WRITE_ADAPTER_BOUNDARY_BLOCKED",
        invocation_eligible=False,
        preflight_reread_passed=False,
        mutation_success_claim_allowed=False,
        adapter_invocation_allowed=False,
        adapter_invoked=False,
    )
