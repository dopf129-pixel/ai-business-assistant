from product_task_freshness_evidence_application_permission import (
    build_application_permission_audit,
    build_application_permission_decision,
    build_application_permission_eligibility,
    build_application_permission_review,
    build_application_start_handoff,
)
from product_task_freshness_evidence_application_preparation import (
    build_application_execution_handoff,
    build_application_preparation_audit,
    build_application_preparation_decision,
    build_application_preparation_eligibility,
    build_application_preparation_plan,
)
from product_task_freshness_evidence_application_executor_admission import (
    bind_executor_target_snapshot,
    build_executor_admission_audit,
    build_executor_admission_eligibility,
    build_executor_application_diff,
    build_executor_authorization_decision,
    build_executor_write_handoff,
)


def _signal():
    d = "draft-1"
    a = "evidence-approval:" + d
    s = "evidence-signal:" + a
    e = "evidence-eligibility:" + s
    p = "evidence-application-preview:" + e
    z = "evidence-application-authorization:" + p
    return {
        "error": False,
        "authorization_signal_id": "evidence-application-authorization-signal:" + z,
        "authorization_id": z,
        "preview_id": p,
        "eligibility_id": e,
        "signal_id": s,
        "approval_id": a,
        "request_id": "refresh:" + d,
        "draft_id": d,
        "sku": "sku-1",
        "status": "APPLICATION_AUTHORIZATION_GRANTED",
        "decision": "AUTHORIZE",
        "authorization_signal_ready": True,
        "authorization_granted": True,
        "authorization_rejected": False,
        "authorization_evidence": {
            "sales_source_recorded_at": "2026-08-29T10:00:00Z",
            "stock_observed_at": "2026-08-29T11:00:00Z",
        },
        "authorization_evidence_count": 2,
        "source_freshness_proven": False,
        "application_allowed": False,
        "application_started": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _prior_flow():
    permission_eligibility = build_application_permission_eligibility(_signal())
    permission_review = build_application_permission_review(permission_eligibility)
    permission_decision = build_application_permission_decision(permission_review, "PERMIT")
    permission_handoff = build_application_start_handoff(permission_decision)
    permission_audit = build_application_permission_audit(
        permission_eligibility, permission_review, permission_decision, permission_handoff
    )
    preparation_eligibility = build_application_preparation_eligibility(permission_handoff, permission_audit)
    preparation_plan = build_application_preparation_plan(preparation_eligibility)
    preparation_decision = build_application_preparation_decision(preparation_plan, "PREPARE")
    execution_handoff = build_application_execution_handoff(preparation_decision)
    preparation_audit = build_application_preparation_audit(
        preparation_eligibility, preparation_plan, preparation_decision, execution_handoff
    )
    return execution_handoff, preparation_audit


def _executor_flow(current=None):
    execution_handoff, preparation_audit = _prior_flow()
    eligibility = build_executor_admission_eligibility(execution_handoff, preparation_audit)
    target = {
        "draft_id": "draft-1",
        "sku": "sku-1",
        "target_revision_id": "rev-7",
        "target_version": 7,
        "target_values": current if current is not None else {
            "sales_source_recorded_at": "2026-08-28T10:00:00Z",
            "stock_observed_at": "2026-08-29T11:00:00Z",
        },
    }
    binding = bind_executor_target_snapshot(eligibility, target)
    diff = build_executor_application_diff(binding)
    decision = build_executor_authorization_decision(diff, "AUTHORIZE")
    handoff = build_executor_write_handoff(decision) if not diff.get("no_op") else None
    return eligibility, binding, diff, decision, handoff


def test_v179_requires_exact_execution_handoff_and_preparation_audit():
    handoff, audit = _prior_flow()
    result = build_executor_admission_eligibility(handoff, audit)
    assert result["status"] == "APPLICATION_EXECUTOR_ADMISSION_ELIGIBLE"
    assert result["executor_admission_eligible"] is True
    assert result["target_snapshot_required"] is True
    assert result["application_allowed"] is False
    assert result["executed"] is False
    forged = dict(audit, preparation_decision_id="forged")
    assert build_executor_admission_eligibility(handoff, forged)["error"] is True


def test_v180_binds_only_versioned_exact_target_snapshot():
    eligibility, binding, _, _, _ = _executor_flow()
    assert binding["status"] == "APPLICATION_EXECUTOR_TARGET_BOUND"
    assert binding["target_revision_id"] == "rev-7"
    assert binding["target_version"] == 7
    bad = bind_executor_target_snapshot(eligibility, {
        "draft_id": "draft-1", "sku": "sku-1", "target_revision_id": "", "target_version": 7, "target_values": {}
    })
    assert bad["code"] == "APPLICATION_TARGET_REVISION_REQUIRED"
    wrong = bind_executor_target_snapshot(eligibility, {
        "draft_id": "other", "sku": "sku-1", "target_revision_id": "rev-7", "target_version": 7, "target_values": {}
    })
    assert wrong["code"] == "APPLICATION_TARGET_IDENTITY_MISMATCH"


def test_v180_rejects_unknown_target_fields():
    handoff, audit = _prior_flow()
    eligibility = build_executor_admission_eligibility(handoff, audit)
    result = bind_executor_target_snapshot(eligibility, {
        "draft_id": "draft-1", "sku": "sku-1", "target_revision_id": "rev-7", "target_version": 7,
        "target_values": {"unknown": "x"},
    })
    assert result["code"] == "APPLICATION_TARGET_VALUES_UNSAFE"


def test_v181_builds_exact_sorted_change_set_without_writing():
    _, _, diff, _, _ = _executor_flow()
    assert diff["status"] == "APPLICATION_EXECUTOR_DIFF_READY"
    assert diff["proposed_changes"] == [{
        "field": "sales_source_recorded_at",
        "before": "2026-08-28T10:00:00Z",
        "after": "2026-08-29T10:00:00Z",
    }]
    assert diff["persistent"] is False
    assert diff["task_draft_mutated"] is False


def test_v181_detects_noop_exactly():
    current = {
        "sales_source_recorded_at": "2026-08-29T10:00:00Z",
        "stock_observed_at": "2026-08-29T11:00:00Z",
    }
    _, _, diff, decision, handoff = _executor_flow(current=current)
    assert diff["no_op"] is True
    assert diff["proposed_change_count"] == 0
    assert decision["executor_authorized"] is True
    assert handoff is None
    assert build_executor_write_handoff(decision)["code"] == "APPLICATION_EXECUTOR_NO_CHANGES"


def test_v182_authorize_and_reject_are_explicit_but_non_mutating():
    _, _, diff, authorized, _ = _executor_flow()
    assert authorized["status"] == "APPLICATION_EXECUTOR_AUTHORIZED"
    assert authorized["write_adapter_required"] is True
    assert authorized["application_allowed"] is False
    rejected = build_executor_authorization_decision(diff, "REJECT")
    assert rejected["status"] == "APPLICATION_EXECUTOR_REJECTED"
    assert rejected["write_adapter_required"] is False
    assert build_executor_authorization_decision(diff, "APPLY")["code"] == "APPLICATION_EXECUTOR_DECISION_INVALID"


def test_v183_write_handoff_requires_authorization_and_stays_non_executing():
    _, _, _, decision, handoff = _executor_flow()
    assert handoff["status"] == "APPLICATION_WRITE_ADAPTER_HANDOFF_READY"
    assert handoff["stale_lineage_check_required"] is True
    assert handoff["readback_verification_required"] is True
    assert handoff["persistent"] is False
    assert handoff["application_started"] is False
    assert handoff["executed"] is False
    rejected = dict(decision, status="APPLICATION_EXECUTOR_REJECTED", decision="REJECT", executor_authorized=False, executor_rejected=True, write_adapter_required=False)
    assert build_executor_write_handoff(rejected)["code"] == "APPLICATION_EXECUTOR_NOT_AUTHORIZED"


def test_v183_audit_recomputes_diff_and_requires_matching_write_handoff():
    eligibility, binding, diff, decision, handoff = _executor_flow()
    audit = build_executor_admission_audit(eligibility, binding, diff, decision, handoff)
    assert audit["status"] == "APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY"
    assert audit["write_handoff_ready"] is True
    forged_diff = dict(diff, proposed_changes=[])
    assert build_executor_admission_audit(eligibility, binding, forged_diff, decision, handoff)["error"] is True
    forged_handoff = dict(handoff, target_revision_id="rev-8")
    assert build_executor_admission_audit(eligibility, binding, diff, decision, forged_handoff)["code"] == "APPLICATION_WRITE_HANDOFF_MISMATCH"


def test_rejected_authorization_audits_without_write_handoff():
    eligibility, binding, diff, _, _ = _executor_flow()
    rejected = build_executor_authorization_decision(diff, "REJECT")
    audit = build_executor_admission_audit(eligibility, binding, diff, rejected)
    assert audit["status"] == "APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY"
    assert audit["executor_rejected"] is True
    assert audit["write_handoff_ready"] is False


def test_all_new_stages_preserve_execution_and_mutation_safety_flags():
    eligibility, binding, diff, decision, handoff = _executor_flow()
    execution_handoff, preparation_audit = _prior_flow()
    audit = build_executor_admission_audit(eligibility, binding, diff, decision, handoff)
    for artifact in (eligibility, binding, diff, decision, handoff, audit):
        assert artifact["application_allowed"] is False
        assert artifact["application_started"] is False
        assert artifact["persistent"] is False
        assert artifact["task_draft_mutated"] is False
        assert artifact["product_decision_mutated"] is False
        assert artifact["execution_allowed"] is False
        assert artifact["execution_ready"] is False
        assert artifact["executed"] is False
