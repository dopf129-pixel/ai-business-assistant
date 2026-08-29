from product_task_freshness_evidence_write_adapter_boundary import (
    build_adapter_execution_envelope,
    build_adapter_invocation_eligibility,
    build_adapter_readback_contract,
    build_write_adapter_boundary_audit,
    build_write_adapter_capability,
)


ALLOWED = [
    "sales_observed_at",
    "sales_source_recorded_at",
    "stock_observed_at",
    "stock_source_recorded_at",
    "unit_economics_observed_at",
    "unit_economics_source_recorded_at",
]


def _capability(**overrides):
    result = {
        "adapter_id": "adapter-1",
        "target_type": "TASK_DRAFT_FRESHNESS",
        "compare_and_set_supported": True,
        "readback_supported": True,
        "atomic_single_target_supported": True,
        "allowed_fields": ALLOWED,
    }
    result.update(overrides)
    return result


def _contract(**overrides):
    auth = "auth-1"
    handoff = "evidence-application-write-handoff:" + auth
    eligibility = "evidence-write-protocol-eligibility:" + handoff
    request = "evidence-write-request:" + eligibility
    decision = "evidence-write-decision:" + request
    result = {
        "error": False,
        "status": "APPLICATION_WRITE_ADAPTER_INVOCATION_CONTRACT_READY",
        "draft_id": "draft-1",
        "sku": "sku-1",
        "executor_authorization_id": auth,
        "application_write_handoff_id": handoff,
        "write_protocol_eligibility_id": eligibility,
        "write_request_id": request,
        "write_decision_id": decision,
        "write_adapter_contract_id": "evidence-write-adapter-contract:" + decision,
        "write_approved": True,
        "compare_and_set_required": True,
        "readback_verification_required": True,
        "expected_target_revision_id": "rev-9",
        "expected_target_version": 9,
        "write_operations": [
            {"field": "stock_observed_at", "before": "old", "after": "new"},
        ],
        "write_operation_count": 1,
        "write_adapter_invocation_allowed": False,
        "application_allowed": False,
        "application_started": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
        "source_freshness_proven": False,
    }
    result.update(overrides)
    return result


def _audit(**overrides):
    contract = _contract()
    result = {
        "error": False,
        "status": "APPLICATION_WRITE_PROTOCOL_AUDIT_READY",
        "write_protocol_audit_id": "evidence-write-protocol-audit:" + contract["write_decision_id"],
        "write_decision_id": contract["write_decision_id"],
        "write_approved": True,
        "adapter_contract_ready": True,
        "expected_target_revision_id": "rev-9",
        "expected_target_version": 9,
        "application_allowed": False,
        "application_started": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
        "source_freshness_proven": False,
    }
    result.update(overrides)
    return result


def _snapshot(**overrides):
    result = {
        "draft_id": "draft-1",
        "sku": "sku-1",
        "target_revision_id": "rev-9",
        "target_version": 9,
        "current_values": {"stock_observed_at": "old"},
    }
    result.update(overrides)
    return result


def _flow():
    cap = build_write_adapter_capability(_capability())
    eligibility = build_adapter_invocation_eligibility(_audit(), _contract(), cap)
    envelope = build_adapter_execution_envelope(eligibility, _snapshot())
    readback = build_adapter_readback_contract(envelope)
    return cap, eligibility, envelope, readback


def test_v189_builds_strict_non_invoking_capability():
    cap = build_write_adapter_capability(_capability())
    assert cap["status"] == "WRITE_ADAPTER_CAPABILITY_READY"
    assert cap["compare_and_set_supported"] is True
    assert cap["readback_supported"] is True
    assert cap["adapter_invocation_allowed"] is False
    assert cap["adapter_invoked"] is False


def test_v189_rejects_incomplete_or_wrong_field_capability():
    assert build_write_adapter_capability(_capability(compare_and_set_supported=False))["code"] == "WRITE_ADAPTER_CAS_REQUIRED"
    assert build_write_adapter_capability(_capability(allowed_fields=list(reversed(ALLOWED))))["code"] == "WRITE_ADAPTER_ALLOWED_FIELDS_MISMATCH"


def test_v190_requires_exact_protocol_and_contract_lineage():
    cap = build_write_adapter_capability(_capability())
    result = build_adapter_invocation_eligibility(_audit(), _contract(), cap)
    assert result["status"] == "WRITE_ADAPTER_INVOCATION_ELIGIBLE"
    assert result["invocation_eligible"] is True
    assert result["adapter_invocation_allowed"] is False
    forged = _contract(write_request_id="forged")
    assert build_adapter_invocation_eligibility(_audit(), forged, cap)["code"] == "WRITE_ADAPTER_UPSTREAM_LINEAGE_MISMATCH"


def test_v191_rechecks_revision_version_and_current_values():
    _, eligibility, envelope, _ = _flow()
    assert envelope["status"] == "WRITE_ADAPTER_EXECUTION_ENVELOPE_READY"
    assert envelope["preflight_reread_passed"] is True
    assert envelope["expected_readback_values"]["stock_observed_at"] == "new"
    assert build_adapter_execution_envelope(eligibility, _snapshot(target_version=10))["code"] == "WRITE_ADAPTER_PREFLIGHT_STALE_VERSION"
    assert build_adapter_execution_envelope(eligibility, _snapshot(current_values={"stock_observed_at": "changed"}))["code"] == "WRITE_ADAPTER_PREFLIGHT_STALE_CURRENT_VALUE"


def test_v192_builds_readback_contract_without_success_claim():
    _, _, _, readback = _flow()
    assert readback["status"] == "WRITE_ADAPTER_READBACK_CONTRACT_READY"
    assert readback["exact_field_readback_required"] is True
    assert readback["post_write_version_evidence_required"] is True
    assert readback["mutation_success_claim_allowed"] is False
    assert readback["adapter_invoked"] is False


def test_v193_audits_exact_boundary_without_invocation():
    cap, eligibility, envelope, readback = _flow()
    audit = build_write_adapter_boundary_audit(cap, eligibility, envelope, readback)
    assert audit["status"] == "WRITE_ADAPTER_BOUNDARY_AUDIT_READY"
    assert audit["execution_envelope_ready"] is True
    assert audit["readback_contract_ready"] is True
    assert audit["adapter_invocation_allowed"] is False
    assert audit["adapter_invoked"] is False
    assert audit["persistent"] is False


def test_forged_readback_and_unsafe_flags_fail_closed():
    cap, eligibility, envelope, readback = _flow()
    forged = dict(readback, expected_readback_values={"stock_observed_at": "forged"})
    assert build_write_adapter_boundary_audit(cap, eligibility, envelope, forged)["code"] == "WRITE_ADAPTER_BOUNDARY_AUDIT_READBACK_MISMATCH"
    unsafe = dict(envelope, persistent=True)
    assert build_adapter_readback_contract(unsafe)["code"] == "WRITE_ADAPTER_SAFETY_BOUNDARY_VIOLATION"


def test_duplicate_unordered_and_noop_operations_fail_closed():
    cap = build_write_adapter_capability(_capability())
    duplicate = _contract(write_operations=[
        {"field": "stock_observed_at", "before": "a", "after": "b"},
        {"field": "stock_observed_at", "before": "b", "after": "c"},
    ], write_operation_count=2)
    assert build_adapter_invocation_eligibility(_audit(), duplicate, cap)["error"] is True
    noop = _contract(write_operations=[
        {"field": "stock_observed_at", "before": "a", "after": "a"},
    ])
    assert build_adapter_invocation_eligibility(_audit(), noop, cap)["code"] == "WRITE_ADAPTER_OPERATION_NOOP"
