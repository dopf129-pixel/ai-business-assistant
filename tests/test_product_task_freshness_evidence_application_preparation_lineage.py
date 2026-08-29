from product_task_freshness_evidence_application_permission import (
    build_application_permission_audit,
    build_application_permission_decision,
    build_application_permission_eligibility,
    build_application_permission_review,
    build_application_start_handoff,
)
from product_task_freshness_evidence_application_preparation import (
    build_application_preparation_audit,
    build_application_preparation_decision,
    build_application_preparation_eligibility,
    build_application_preparation_plan,
)


def _package():
    d = "draft-lineage"
    approval = "evidence-approval:" + d
    signal = "evidence-signal:" + approval
    eligibility_id = "evidence-eligibility:" + signal
    preview = "evidence-application-preview:" + eligibility_id
    authorization = "evidence-application-authorization:" + preview
    authorization_signal = "evidence-application-authorization-signal:" + authorization
    source = {
        "error": False,
        "authorization_signal_id": authorization_signal,
        "authorization_id": authorization,
        "preview_id": preview,
        "eligibility_id": eligibility_id,
        "signal_id": signal,
        "approval_id": approval,
        "request_id": "refresh:" + d,
        "draft_id": d,
        "sku": "sku-lineage",
        "status": "APPLICATION_AUTHORIZATION_GRANTED",
        "decision": "AUTHORIZE",
        "authorization_signal_ready": True,
        "authorization_granted": True,
        "authorization_rejected": False,
        "authorization_evidence": {"stock_observed_at": "2026-08-30T00:00:00Z"},
        "authorization_evidence_count": 1,
        "application_allowed": False,
        "application_started": False,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    permission_eligibility = build_application_permission_eligibility(source)
    review = build_application_permission_review(permission_eligibility)
    decision = build_application_permission_decision(review, "PERMIT")
    handoff = build_application_start_handoff(decision)
    permission_audit = build_application_permission_audit(
        permission_eligibility, review, decision, handoff
    )
    preparation_eligibility = build_application_preparation_eligibility(
        handoff, permission_audit
    )
    plan = build_application_preparation_plan(preparation_eligibility)
    preparation_decision = build_application_preparation_decision(plan, "REJECT")
    return preparation_eligibility, plan, preparation_decision


def test_v178_rejects_forged_permission_audit_lineage():
    eligibility, plan, decision = _package()
    forged_plan = dict(plan, permission_audit_id="forged-audit")
    result = build_application_preparation_audit(
        eligibility, forged_plan, decision
    )
    assert result["error"] is True
    assert result["code"] == "APPLICATION_PREPARATION_AUDIT_LINEAGE_MISMATCH"
