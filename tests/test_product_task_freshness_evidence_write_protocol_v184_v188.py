from product_task_freshness_evidence_write_protocol import (
    build_write_adapter_invocation_contract,
    build_write_protocol_audit,
    build_write_protocol_eligibility,
    build_write_request,
    build_write_request_decision,
)


def _handoff(**overrides):
    auth = "executor-auth-1"
    result = {
        "error": False,
        "status": "APPLICATION_WRITE_ADAPTER_HANDOFF_READY",
        "draft_id": "draft-1",
        "sku": "sku-1",
        "executor_authorization_id": auth,
        "application_write_handoff_id": "evidence-application-write-handoff:" + auth,
        "write_handoff_ready": True,
        "write_adapter_required": True,
        "stale_lineage_check_required": True,
        "readback_verification_required": True,
        "target_revision_id": "rev-7",
        "target_version": 7,
        "proposed_changes": [{"field": "stock_observed_at", "before": "old", "after": "new"}],
        "proposed_change_count": 1,
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
    result = {
        "error": False,
        "status": "APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY",
        "executor_admission_audit_id": "evidence-application-executor-admission-audit:executor-auth-1",
        "executor_authorized": True,
        "write_handoff_ready": True,
        "target_revision_id": "rev-7",
        "target_version": 7,
        "proposed_change_count": 1,
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
        "draft_id": "draft-1", "sku": "sku-1", "target_revision_id": "rev-7", "target_version": 7,
        "current_values": {"stock_observed_at": "old"},
    }
    result.update(overrides)
    return result


def _flow(choice="APPLY"):
    eligibility = build_write_protocol_eligibility(_handoff(), _audit(), _snapshot())
    request = build_write_request(eligibility)
    decision = build_write_request_decision(request, choice)
    contract = build_write_adapter_invocation_contract(decision) if choice == "APPLY" else None
    return eligibility, request, decision, contract


def test_v184_requires_exact_reread_revision_version_and_before_values():
    result = build_write_protocol_eligibility(_handoff(), _audit(), _snapshot())
    assert result["status"] == "APPLICATION_WRITE_PROTOCOL_ELIGIBLE"
    assert result["stale_lineage_check_passed"] is True
    assert result["persistent"] is False
    assert build_write_protocol_eligibility(_handoff(), _audit(), _snapshot(target_version=8))["code"] == "APPLICATION_WRITE_STALE_VERSION"
    assert build_write_protocol_eligibility(_handoff(), _audit(), _snapshot(current_values={"stock_observed_at": "changed"}))["code"] == "APPLICATION_WRITE_STALE_CURRENT_VALUE"


def test_v184_recomputes_handoff_lineage_and_rejects_duplicate_fields():
    forged = _handoff(application_write_handoff_id="forged")
    assert build_write_protocol_eligibility(forged, _audit(), _snapshot())["code"] == "APPLICATION_WRITE_HANDOFF_ID_MISMATCH"
    duplicate = _handoff(proposed_changes=[
        {"field": "stock_observed_at", "before": "old", "after": "new"},
        {"field": "stock_observed_at", "before": "old", "after": "newer"},
    ], proposed_change_count=2)
    assert build_write_protocol_eligibility(duplicate, _audit(proposed_change_count=2), _snapshot())["code"] == "APPLICATION_WRITE_DUPLICATE_FIELD"


def test_v185_builds_canonical_non_executing_write_request():
    eligibility, request, _, _ = _flow()
    assert eligibility["write_protocol_eligible"] is True
    assert request["status"] == "APPLICATION_WRITE_REQUEST_READY"
    assert request["expected_target_revision_id"] == "rev-7"
    assert request["expected_target_version"] == 7
    assert request["write_operations"] == _handoff()["proposed_changes"]
    assert request["task_draft_mutated"] is False


def test_v186_apply_and_reject_are_explicit_but_do_not_invoke_adapter():
    _, request, decision, _ = _flow()
    assert decision["status"] == "APPLICATION_WRITE_APPROVED"
    assert decision["decision"] == "APPLY"
    assert decision["write_adapter_invocation_allowed"] is False
    rejected = build_write_request_decision(request, "REJECT")
    assert rejected["status"] == "APPLICATION_WRITE_REJECTED"
    assert rejected["write_rejected"] is True
    assert build_write_request_decision(request, "AUTHORIZE")["code"] == "APPLICATION_WRITE_DECISION_INVALID"


def test_v187_contract_requires_cas_and_readback_but_never_invokes_write():
    _, _, _, contract = _flow()
    assert contract["status"] == "APPLICATION_WRITE_ADAPTER_INVOCATION_CONTRACT_READY"
    assert contract["compare_and_set_required"] is True
    assert contract["readback_verification_required"] is True
    assert contract["write_adapter_invocation_allowed"] is False
    assert contract["persistent"] is False
    assert contract["executed"] is False


def test_v188_audit_requires_exact_contract_for_approved_write():
    eligibility, request, decision, contract = _flow()
    audit = build_write_protocol_audit(eligibility, request, decision, contract)
    assert audit["status"] == "APPLICATION_WRITE_PROTOCOL_AUDIT_READY"
    assert audit["adapter_contract_ready"] is True
    assert audit["persistent"] is False
    assert build_write_protocol_audit(eligibility, request, decision)["error"] is True


def test_rejected_write_audits_without_adapter_contract():
    eligibility, request, decision, _ = _flow("REJECT")
    audit = build_write_protocol_audit(eligibility, request, decision)
    assert audit["status"] == "APPLICATION_WRITE_PROTOCOL_AUDIT_READY"
    assert audit["write_rejected"] is True
    assert audit["adapter_contract_ready"] is False


def test_forged_request_decision_and_contract_fail_closed():
    eligibility, request, decision, contract = _flow()
    forged_request = dict(request, write_operations=[{"field": "stock_observed_at", "before": "x", "after": "new"}])
    assert build_write_request_decision(forged_request, "APPLY")["error"] is True
    forged_decision = dict(decision, decision="REJECT", write_approved=True, write_rejected=False)
    assert build_write_adapter_invocation_contract(forged_decision)["code"] == "APPLICATION_WRITE_DECISION_CONTRADICTORY"
    forged_contract = dict(contract, expected_target_version=8)
    assert build_write_protocol_audit(eligibility, request, decision, forged_contract)["code"] == "APPLICATION_WRITE_ADAPTER_CONTRACT_MISMATCH"


def test_unknown_fields_noops_and_unsafe_flags_fail_closed():
    bad = _handoff(proposed_changes=[{"field": "unknown", "before": None, "after": "x"}])
    assert build_write_protocol_eligibility(bad, _audit(), _snapshot())["code"] == "APPLICATION_WRITE_CHANGE_FIELD_UNSAFE"
    noop = _handoff(proposed_changes=[{"field": "stock_observed_at", "before": "old", "after": "old"}])
    assert build_write_protocol_eligibility(noop, _audit(), _snapshot())["code"] == "APPLICATION_WRITE_NOOP_OPERATION"
    assert build_write_protocol_eligibility(_handoff(persistent=True), _audit(), _snapshot())["code"] == "APPLICATION_WRITE_PROTOCOL_SAFETY_BOUNDARY_VIOLATION"
