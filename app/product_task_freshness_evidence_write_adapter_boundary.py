from copy import deepcopy

ALLOWED_EVIDENCE_FIELDS = (
    "sales_observed_at", "sales_source_recorded_at", "stock_observed_at",
    "stock_source_recorded_at", "unit_economics_observed_at",
    "unit_economics_source_recorded_at",
)
SAFETY_FIELDS = (
    "application_allowed", "application_started", "persistent",
    "product_decision_recomputed", "product_decision_mutated",
    "task_draft_mutated", "execution_allowed", "execution_ready", "executed",
)


def build_write_adapter_capability(descriptor):
    s = deepcopy(descriptor or {})
    adapter_id = s.get("adapter_id")
    if not isinstance(adapter_id, str) or not adapter_id.strip(): return _blocked(s, "WRITE_ADAPTER_ID_REQUIRED")
    if s.get("target_type") != "TASK_DRAFT_FRESHNESS": return _blocked(s, "WRITE_ADAPTER_TARGET_TYPE_UNSUPPORTED")
    if s.get("compare_and_set_supported") is not True: return _blocked(s, "WRITE_ADAPTER_CAS_REQUIRED")
    if s.get("readback_supported") is not True: return _blocked(s, "WRITE_ADAPTER_READBACK_REQUIRED")
    if s.get("atomic_single_target_supported") is not True: return _blocked(s, "WRITE_ADAPTER_ATOMIC_TARGET_REQUIRED")
    if s.get("allowed_fields") != list(ALLOWED_EVIDENCE_FIELDS): return _blocked(s, "WRITE_ADAPTER_ALLOWED_FIELDS_MISMATCH")
    return _base(s, error=False, status="WRITE_ADAPTER_CAPABILITY_READY",
        capability_id="freshness-write-adapter-capability:" + adapter_id,
        adapter_id=adapter_id, target_type="TASK_DRAFT_FRESHNESS",
        compare_and_set_supported=True, readback_supported=True,
        atomic_single_target_supported=True, allowed_fields=list(ALLOWED_EVIDENCE_FIELDS),
        adapter_invocation_allowed=False, adapter_invoked=False)


def build_adapter_invocation_eligibility(protocol_audit, adapter_contract, capability):
    audit, contract, cap = map(lambda x: deepcopy(x or {}), (protocol_audit, adapter_contract, capability))
    error = _validate_inputs(audit, contract, cap)
    if error: return _blocked(contract, error)
    ops = deepcopy(contract["write_operations"])
    return _base(contract, error=False, status="WRITE_ADAPTER_INVOCATION_ELIGIBLE",
        invocation_eligibility_id="freshness-write-adapter-invocation-eligibility:" + contract["write_adapter_contract_id"],
        capability_id=cap["capability_id"], adapter_id=cap["adapter_id"],
        write_protocol_audit_id=audit["write_protocol_audit_id"],
        expected_target_revision_id=contract["expected_target_revision_id"],
        expected_target_version=contract["expected_target_version"],
        write_operations=ops, write_operation_count=len(ops), invocation_eligible=True,
        preflight_reread_required=True, adapter_invocation_allowed=False, adapter_invoked=False)


def build_adapter_execution_envelope(eligibility, preflight_snapshot):
    s, snapshot = deepcopy(eligibility or {}), deepcopy(preflight_snapshot or {})
    error = _validate_eligibility(s)
    if error: return _blocked(s, error)
    error = _validate_preflight(s, snapshot)
    if error: return _blocked(s, error)
    expected = deepcopy(snapshot["current_values"])
    for op in s["write_operations"]: expected[op["field"]] = deepcopy(op["after"])
    return _base(s, error=False, status="WRITE_ADAPTER_EXECUTION_ENVELOPE_READY",
        execution_envelope_id="freshness-write-adapter-execution-envelope:" + s["invocation_eligibility_id"],
        invocation_eligible=True, preflight_reread_passed=True,
        expected_target_revision_id=s["expected_target_revision_id"], expected_target_version=s["expected_target_version"],
        preflight_values=deepcopy(snapshot["current_values"]), write_operations=deepcopy(s["write_operations"]),
        write_operation_count=s["write_operation_count"], expected_readback_values=expected,
        adapter_invocation_allowed=False, adapter_invoked=False)


def build_adapter_readback_contract(execution_envelope):
    s = deepcopy(execution_envelope or {})
    error = _validate_envelope(s)
    if error: return _blocked(s, error)
    return _base(s, error=False, status="WRITE_ADAPTER_READBACK_CONTRACT_READY",
        readback_contract_id="freshness-write-adapter-readback-contract:" + s["execution_envelope_id"],
        expected_target_revision_id=s["expected_target_revision_id"], expected_target_version=s["expected_target_version"],
        expected_readback_values=deepcopy(s["expected_readback_values"]), exact_field_readback_required=True,
        post_write_version_evidence_required=True, mutation_success_claim_allowed=False,
        adapter_invocation_allowed=False, adapter_invoked=False)


def build_write_adapter_boundary_audit(capability, eligibility, envelope, readback_contract):
    cap, eligible, env, readback = map(lambda x: deepcopy(x or {}), (capability, eligibility, envelope, readback_contract))
    if _validate_capability(cap): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_CAPABILITY_INVALID")
    if _validate_eligibility(eligible): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_ELIGIBILITY_INVALID")
    if _validate_envelope(env): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_ENVELOPE_INVALID")
    if _validate_readback_contract(readback): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_READBACK_INVALID")
    for item in (eligible, env, readback):
        if item.get("capability_id") != cap.get("capability_id") or item.get("adapter_id") != cap.get("adapter_id"):
            return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_CAPABILITY_MISMATCH")
        if item.get("expected_target_revision_id") != eligible.get("expected_target_revision_id") or item.get("expected_target_version") != eligible.get("expected_target_version"):
            return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_TARGET_MISMATCH")
    if env.get("invocation_eligibility_id") != eligible.get("invocation_eligibility_id"): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_LINEAGE_MISMATCH")
    if readback.get("execution_envelope_id") != env.get("execution_envelope_id"): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_LINEAGE_MISMATCH")
    if env.get("write_operations") != eligible.get("write_operations"): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_OPERATIONS_MISMATCH")
    if readback.get("expected_readback_values") != env.get("expected_readback_values"): return _blocked(eligible, "WRITE_ADAPTER_BOUNDARY_AUDIT_READBACK_MISMATCH")
    return _base(eligible, error=False, status="WRITE_ADAPTER_BOUNDARY_AUDIT_READY",
        boundary_audit_id="freshness-write-adapter-boundary-audit:" + readback["readback_contract_id"],
        capability_id=cap["capability_id"], adapter_id=cap["adapter_id"], invocation_eligible=True,
        execution_envelope_ready=True, readback_contract_ready=True, mutation_success_claim_allowed=False,
        adapter_invocation_allowed=False, adapter_invoked=False)


def _validate_inputs(audit, contract, capability):
    error = _validate_capability(capability)
    if error: return error
    if audit.get("error") is not False or audit.get("status") != "APPLICATION_WRITE_PROTOCOL_AUDIT_READY": return "WRITE_PROTOCOL_AUDIT_REQUIRED"
    if audit.get("write_approved") is not True or audit.get("adapter_contract_ready") is not True: return "WRITE_PROTOCOL_AUDIT_NOT_APPROVED"
    if contract.get("error") is not False or contract.get("status") != "APPLICATION_WRITE_ADAPTER_INVOCATION_CONTRACT_READY": return "WRITE_ADAPTER_INVOCATION_CONTRACT_REQUIRED"
    if contract.get("write_approved") is not True or contract.get("compare_and_set_required") is not True or contract.get("readback_verification_required") is not True: return "WRITE_ADAPTER_INVOCATION_CONTRACT_GUARDS_REQUIRED"
    if contract.get("write_adapter_invocation_allowed") is not False or _unsafe(audit) or _unsafe(contract): return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    expected = _expected_lineage(contract.get("executor_authorization_id", ""))
    if any(contract.get(k) != v for k, v in expected.items() if k != "write_protocol_audit_id"): return "WRITE_ADAPTER_UPSTREAM_LINEAGE_MISMATCH"
    if audit.get("write_protocol_audit_id") != expected["write_protocol_audit_id"] or audit.get("write_decision_id") != expected["write_decision_id"]: return "WRITE_ADAPTER_PROTOCOL_AUDIT_LINEAGE_MISMATCH"
    if audit.get("expected_target_revision_id") != contract.get("expected_target_revision_id") or audit.get("expected_target_version") != contract.get("expected_target_version"): return "WRITE_ADAPTER_TARGET_LINEAGE_MISMATCH"
    return _validate_operations(contract.get("write_operations"), contract.get("write_operation_count"))


def _validate_capability(s):
    if s.get("error") is not False or s.get("status") != "WRITE_ADAPTER_CAPABILITY_READY": return "WRITE_ADAPTER_CAPABILITY_REQUIRED"
    adapter_id = s.get("adapter_id")
    if not isinstance(adapter_id, str) or not adapter_id.strip(): return "WRITE_ADAPTER_ID_REQUIRED"
    if s.get("capability_id") != "freshness-write-adapter-capability:" + adapter_id: return "WRITE_ADAPTER_CAPABILITY_ID_MISMATCH"
    if s.get("target_type") != "TASK_DRAFT_FRESHNESS": return "WRITE_ADAPTER_TARGET_TYPE_UNSUPPORTED"
    if s.get("compare_and_set_supported") is not True or s.get("readback_supported") is not True or s.get("atomic_single_target_supported") is not True: return "WRITE_ADAPTER_CAPABILITY_INSUFFICIENT"
    if s.get("allowed_fields") != list(ALLOWED_EVIDENCE_FIELDS): return "WRITE_ADAPTER_ALLOWED_FIELDS_MISMATCH"
    if s.get("adapter_invocation_allowed") is not False or s.get("adapter_invoked") is not False: return "WRITE_ADAPTER_INVOCATION_BOUNDARY_VIOLATION"
    return None


def _validate_local_lineage(s):
    adapter_id = s.get("adapter_id")
    if not isinstance(adapter_id, str) or not adapter_id.strip(): return "WRITE_ADAPTER_ID_REQUIRED"
    if s.get("capability_id") != "freshness-write-adapter-capability:" + adapter_id: return "WRITE_ADAPTER_CAPABILITY_LINEAGE_MISMATCH"
    expected = _expected_lineage(s.get("executor_authorization_id", ""))
    for field in ("application_write_handoff_id", "write_protocol_eligibility_id", "write_request_id", "write_decision_id", "write_adapter_contract_id", "write_protocol_audit_id"):
        if s.get(field) != expected[field]: return "WRITE_ADAPTER_UPSTREAM_LINEAGE_MISMATCH"
    if s.get("invocation_eligibility_id") != "freshness-write-adapter-invocation-eligibility:" + expected["write_adapter_contract_id"]: return "WRITE_ADAPTER_INVOCATION_ELIGIBILITY_ID_MISMATCH"
    return None


def _validate_eligibility(s):
    if s.get("error") is not False or s.get("status") != "WRITE_ADAPTER_INVOCATION_ELIGIBLE" or s.get("invocation_eligible") is not True: return "WRITE_ADAPTER_INVOCATION_NOT_ELIGIBLE"
    if _unsafe(s) or s.get("adapter_invocation_allowed") is not False or s.get("adapter_invoked") is not False: return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    error = _validate_local_lineage(s)
    if error: return error
    return _validate_operations(s.get("write_operations"), s.get("write_operation_count"))


def _validate_preflight(s, snapshot):
    if snapshot.get("draft_id") != s.get("draft_id") or snapshot.get("sku") != s.get("sku"): return "WRITE_ADAPTER_PREFLIGHT_IDENTITY_MISMATCH"
    if snapshot.get("target_revision_id") != s.get("expected_target_revision_id"): return "WRITE_ADAPTER_PREFLIGHT_STALE_REVISION"
    if snapshot.get("target_version") != s.get("expected_target_version"): return "WRITE_ADAPTER_PREFLIGHT_STALE_VERSION"
    values = snapshot.get("current_values")
    if not isinstance(values, dict) or any(k not in ALLOWED_EVIDENCE_FIELDS for k in values): return "WRITE_ADAPTER_PREFLIGHT_VALUES_UNSAFE"
    for op in s["write_operations"]:
        if values.get(op["field"]) != op["before"]: return "WRITE_ADAPTER_PREFLIGHT_STALE_CURRENT_VALUE"
    return None


def _validate_envelope(s):
    if s.get("error") is not False or s.get("status") != "WRITE_ADAPTER_EXECUTION_ENVELOPE_READY": return "WRITE_ADAPTER_EXECUTION_ENVELOPE_REQUIRED"
    if s.get("preflight_reread_passed") is not True or s.get("invocation_eligible") is not True: return "WRITE_ADAPTER_EXECUTION_ENVELOPE_INVALID"
    if s.get("execution_envelope_id") != "freshness-write-adapter-execution-envelope:" + s.get("invocation_eligibility_id", ""): return "WRITE_ADAPTER_EXECUTION_ENVELOPE_ID_MISMATCH"
    if _unsafe(s) or s.get("adapter_invocation_allowed") is not False or s.get("adapter_invoked") is not False: return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    error = _validate_local_lineage(s)
    if error: return error
    error = _validate_operations(s.get("write_operations"), s.get("write_operation_count"))
    if error: return error
    expected = deepcopy(s.get("preflight_values") or {})
    for op in s["write_operations"]: expected[op["field"]] = deepcopy(op["after"])
    if s.get("expected_readback_values") != expected: return "WRITE_ADAPTER_EXPECTED_READBACK_MISMATCH"
    return None


def _validate_readback_contract(s):
    if s.get("error") is not False or s.get("status") != "WRITE_ADAPTER_READBACK_CONTRACT_READY": return "WRITE_ADAPTER_READBACK_CONTRACT_REQUIRED"
    if s.get("readback_contract_id") != "freshness-write-adapter-readback-contract:" + s.get("execution_envelope_id", ""): return "WRITE_ADAPTER_READBACK_CONTRACT_ID_MISMATCH"
    if s.get("exact_field_readback_required") is not True or s.get("post_write_version_evidence_required") is not True: return "WRITE_ADAPTER_READBACK_GUARDS_REQUIRED"
    if s.get("mutation_success_claim_allowed") is not False: return "WRITE_ADAPTER_SUCCESS_CLAIM_BOUNDARY_VIOLATION"
    if _unsafe(s) or s.get("adapter_invocation_allowed") is not False or s.get("adapter_invoked") is not False: return "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"
    error = _validate_local_lineage(s)
    if error: return error
    return None


def _validate_operations(ops, count):
    if not isinstance(ops, list) or not ops or count != len(ops): return "WRITE_ADAPTER_OPERATIONS_INVALID"
    seen, order = set(), []
    for op in ops:
        if not isinstance(op, dict) or set(op) != {"field", "before", "after"}: return "WRITE_ADAPTER_OPERATION_SCHEMA_INVALID"
        field = op.get("field")
        if field not in ALLOWED_EVIDENCE_FIELDS or field in seen: return "WRITE_ADAPTER_OPERATION_FIELD_INVALID"
        if op.get("before") == op.get("after"): return "WRITE_ADAPTER_OPERATION_NOOP"
        seen.add(field); order.append(field)
    if order != sorted(order): return "WRITE_ADAPTER_OPERATION_ORDER_INVALID"
    return None


def _expected_lineage(auth):
    handoff = "evidence-application-write-handoff:" + auth
    eligibility = "evidence-write-protocol-eligibility:" + handoff
    request = "evidence-write-request:" + eligibility
    decision = "evidence-write-decision:" + request
    contract = "evidence-write-adapter-contract:" + decision
    return {"application_write_handoff_id": handoff, "write_protocol_eligibility_id": eligibility,
        "write_request_id": request, "write_decision_id": decision, "write_adapter_contract_id": contract,
        "write_protocol_audit_id": "evidence-write-protocol-audit:" + decision}


def _unsafe(s):
    return any(s.get(f) is not False for f in SAFETY_FIELDS) or s.get("source_freshness_proven") is not False


def _base(s, **additions):
    carry = ("draft_id", "sku", "executor_authorization_id", "application_write_handoff_id",
        "write_protocol_eligibility_id", "write_request_id", "write_decision_id", "write_adapter_contract_id",
        "write_protocol_audit_id", "capability_id", "adapter_id", "invocation_eligibility_id",
        "execution_envelope_id", "readback_contract_id", "expected_target_revision_id", "expected_target_version",
        "write_operations", "write_operation_count")
    result = {f: deepcopy(s.get(f)) for f in carry if s.get(f) is not None}
    result.update({f: False for f in SAFETY_FIELDS}); result["source_freshness_proven"] = False
    result.update(additions); return result


def _blocked(s, code):
    return _base(s, error=True, code=code, status="WRITE_ADAPTER_BOUNDARY_BLOCKED",
        invocation_eligible=False, preflight_reread_passed=False, mutation_success_claim_allowed=False,
        adapter_invocation_allowed=False, adapter_invoked=False)
