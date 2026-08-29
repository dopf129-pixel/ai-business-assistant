from product_task_freshness_evidence_write_adapter_boundary import (
    build_adapter_execution_envelope,
    build_adapter_invocation_eligibility,
    build_adapter_readback_contract,
    build_write_adapter_boundary_audit,
    build_write_adapter_capability,
)


FLAGS = {
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


def _inputs():
    auth = "auth-1"
    handoff = "evidence-application-write-handoff:" + auth
    eligibility = "evidence-write-protocol-eligibility:" + handoff
    request = "evidence-write-request:" + eligibility
    decision = "evidence-write-decision:" + request
    contract_id = "evidence-write-adapter-contract:" + decision
    contract = dict(FLAGS, error=False, status="APPLICATION_WRITE_ADAPTER_INVOCATION_CONTRACT_READY",
        draft_id="draft-1", sku="sku-1", executor_authorization_id=auth,
        application_write_handoff_id=handoff, write_protocol_eligibility_id=eligibility,
        write_request_id=request, write_decision_id=decision, write_adapter_contract_id=contract_id,
        write_approved=True, compare_and_set_required=True, readback_verification_required=True,
        expected_target_revision_id="rev-1", expected_target_version=1,
        write_operations=[{"field":"stock_observed_at","before":"a","after":"b"}],
        write_operation_count=1, write_adapter_invocation_allowed=False)
    audit = dict(FLAGS, error=False, status="APPLICATION_WRITE_PROTOCOL_AUDIT_READY",
        write_protocol_audit_id="evidence-write-protocol-audit:" + decision,
        write_decision_id=decision, write_approved=True, adapter_contract_ready=True,
        expected_target_revision_id="rev-1", expected_target_version=1)
    capability = build_write_adapter_capability({
        "adapter_id":"adapter-1", "target_type":"TASK_DRAFT_FRESHNESS",
        "compare_and_set_supported":True, "readback_supported":True,
        "atomic_single_target_supported":True,
        "allowed_fields":["sales_observed_at","sales_source_recorded_at","stock_observed_at","stock_source_recorded_at","unit_economics_observed_at","unit_economics_source_recorded_at"],
    })
    return audit, contract, capability


def test_forged_capability_identity_fails_across_envelope_and_readback():
    audit, contract, capability = _inputs()
    eligibility = build_adapter_invocation_eligibility(audit, contract, capability)
    forged_eligibility = dict(eligibility, adapter_id="other-adapter")
    assert build_adapter_execution_envelope(forged_eligibility, {
        "draft_id":"draft-1", "sku":"sku-1", "target_revision_id":"rev-1",
        "target_version":1, "current_values":{"stock_observed_at":"a"},
    })["code"] == "WRITE_ADAPTER_CAPABILITY_LINEAGE_MISMATCH"

    envelope = build_adapter_execution_envelope(eligibility, {
        "draft_id":"draft-1", "sku":"sku-1", "target_revision_id":"rev-1",
        "target_version":1, "current_values":{"stock_observed_at":"a"},
    })
    forged_envelope = dict(envelope, capability_id="freshness-write-adapter-capability:other-adapter")
    assert build_adapter_readback_contract(forged_envelope)["code"] == "WRITE_ADAPTER_CAPABILITY_LINEAGE_MISMATCH"


def test_boundary_audit_rejects_capability_identity_changed_only_downstream():
    audit, contract, capability = _inputs()
    eligibility = build_adapter_invocation_eligibility(audit, contract, capability)
    envelope = build_adapter_execution_envelope(eligibility, {
        "draft_id":"draft-1", "sku":"sku-1", "target_revision_id":"rev-1",
        "target_version":1, "current_values":{"stock_observed_at":"a"},
    })
    readback = build_adapter_readback_contract(envelope)
    forged = dict(readback, adapter_id="other-adapter")
    result = build_write_adapter_boundary_audit(capability, eligibility, envelope, forged)
    assert result["error"] is True
