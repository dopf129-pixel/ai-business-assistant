from product_task_freshness_evidence_write_protocol import (
    build_write_adapter_invocation_contract,
    build_write_protocol_eligibility,
    build_write_request,
    build_write_request_decision,
)


def _safe_flags():
    return {
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


def _eligibility():
    auth = "executor-auth-1"
    handoff_id = "evidence-application-write-handoff:" + auth
    handoff = {
        **_safe_flags(),
        "error": False,
        "status": "APPLICATION_WRITE_ADAPTER_HANDOFF_READY",
        "draft_id": "draft-1",
        "sku": "sku-1",
        "executor_authorization_id": auth,
        "application_write_handoff_id": handoff_id,
        "write_handoff_ready": True,
        "write_adapter_required": True,
        "target_revision_id": "rev-1",
        "target_version": 1,
        "proposed_changes": [{"field": "stock_observed_at", "before": "old", "after": "new"}],
        "proposed_change_count": 1,
    }
    audit = {
        **_safe_flags(),
        "error": False,
        "status": "APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY",
        "executor_admission_audit_id": "evidence-application-executor-admission-audit:" + auth,
        "executor_authorized": True,
        "write_handoff_ready": True,
        "target_revision_id": "rev-1",
        "target_version": 1,
        "proposed_change_count": 1,
    }
    snapshot = {
        "draft_id": "draft-1",
        "sku": "sku-1",
        "target_revision_id": "rev-1",
        "target_version": 1,
        "current_values": {"stock_observed_at": "old"},
    }
    return build_write_protocol_eligibility(handoff, audit, snapshot)


def test_forged_intermediate_lineage_is_rejected_downstream():
    eligibility = _eligibility()
    forged = dict(
        eligibility,
        application_write_handoff_id="evidence-application-write-handoff:forged",
        write_protocol_eligibility_id="evidence-write-protocol-eligibility:evidence-application-write-handoff:forged",
    )
    result = build_write_request(forged)
    assert result["error"] is True
    assert result["code"] == "APPLICATION_WRITE_HANDOFF_ID_MISMATCH"


def test_forged_executor_audit_lineage_is_rejected_before_decision():
    request = build_write_request(_eligibility())
    forged = dict(request, executor_admission_audit_id="evidence-application-executor-admission-audit:forged")
    result = build_write_request_decision(forged, "APPLY")
    assert result["error"] is True
    assert result["code"] == "APPLICATION_WRITE_REQUEST_LINEAGE_MISMATCH"


def test_adapter_contract_cannot_enable_invocation():
    request = build_write_request(_eligibility())
    decision = build_write_request_decision(request, "APPLY")
    contract = build_write_adapter_invocation_contract(decision)
    assert contract["write_adapter_invocation_allowed"] is False
    assert contract["persistent"] is False
    assert contract["task_draft_mutated"] is False
