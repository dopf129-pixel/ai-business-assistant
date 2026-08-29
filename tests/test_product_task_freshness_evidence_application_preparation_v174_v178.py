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


def _signal(**overrides):
    d = "draft-1"
    a = "evidence-approval:" + d
    s = "evidence-signal:" + a
    e = "evidence-eligibility:" + s
    p = "evidence-application-preview:" + e
    z = "evidence-application-authorization:" + p
    result = {
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
        "application_allowed": False,
        "application_started": False,
        "authorization_evidence": {
            "sales_source_recorded_at": "2026-08-29T10:00:00Z",
            "stock_observed_at": "2026-08-29T10:05:00Z",
        },
        "authorization_evidence_count": 2,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(overrides)
    return result


def _permission_package():
    eligibility = build_application_permission_eligibility(_signal())
    review = build_application_permission_review(eligibility)
    decision = build_application_permission_decision(review, "PERMIT")
    handoff = build_application_start_handoff(decision)
    audit = build_application_permission_audit(eligibility, review, decision, handoff)
    return handoff, audit


def _preparation_flow(choice="PREPARE"):
    handoff, permission_audit = _permission_package()
    eligibility = build_application_preparation_eligibility(handoff, permission_audit)
    plan = build_application_preparation_plan(eligibility)
    decision = build_application_preparation_decision(plan, choice)
    execution_handoff = (
        build_application_execution_handoff(decision)
        if choice == "PREPARE"
        else None
    )
    return eligibility, plan, decision, execution_handoff


def test_v174_start_package_becomes_preparation_eligible_only():
    handoff, permission_audit = _permission_package()
    result = build_application_preparation_eligibility(handoff, permission_audit)
    assert result["status"] == "APPLICATION_PREPARATION_ELIGIBLE"
    assert result["preparation_eligible"] is True
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["persistent"] is False
    assert result["task_draft_mutated"] is False
    assert result["executed"] is False


def test_v174_requires_exact_granted_handoff_and_permission_audit():
    handoff, permission_audit = _permission_package()
    forged = dict(handoff, draft_id="other")
    assert build_application_preparation_eligibility(forged, permission_audit)["error"] is True
    unsafe = dict(permission_audit, application_started=True)
    result = build_application_preparation_eligibility(handoff, unsafe)
    assert result["code"] == "APPLICATION_PREPARATION_SAFETY_BOUNDARY_VIOLATION"


def test_v175_plan_is_deterministic_and_non_mutating():
    handoff, permission_audit = _permission_package()
    eligibility = build_application_preparation_eligibility(handoff, permission_audit)
    result = build_application_preparation_plan(eligibility)
    assert result["status"] == "APPLICATION_PREPARATION_PLAN_READY"
    assert result["planned_fields"] == [
        {
            "field": "sales_source_recorded_at",
            "proposed_value": "2026-08-29T10:00:00Z",
        },
        {
            "field": "stock_observed_at",
            "proposed_value": "2026-08-29T10:05:00Z",
        },
    ]
    assert result["task_draft_mutated"] is False
    assert result["product_decision_recomputed"] is False


def test_v176_prepare_and_reject_are_explicit_without_application_permission():
    handoff, permission_audit = _permission_package()
    eligibility = build_application_preparation_eligibility(handoff, permission_audit)
    plan = build_application_preparation_plan(eligibility)
    prepared = build_application_preparation_decision(plan, "PREPARE")
    assert prepared["status"] == "APPLICATION_PREPARATION_APPROVED"
    assert prepared["preparation_approved"] is True
    assert prepared["application_allowed"] is False
    rejected = build_application_preparation_decision(plan, "REJECT")
    assert rejected["status"] == "APPLICATION_PREPARATION_REJECTED"
    assert rejected["preparation_rejected"] is True
    assert build_application_preparation_decision(plan, "APPLY")["code"] == "APPLICATION_PREPARATION_DECISION_INVALID"


def test_v177_execution_handoff_is_only_a_boundary_not_execution():
    _, _, decision, execution_handoff = _preparation_flow()
    assert decision["preparation_approved"] is True
    assert execution_handoff["status"] == "APPLICATION_EXECUTION_HANDOFF_READY"
    assert execution_handoff["application_execution_handoff_ready"] is True
    assert execution_handoff["application_executor_required"] is True
    assert execution_handoff["application_allowed"] is False
    assert execution_handoff["application_started"] is False
    assert execution_handoff["persistent"] is False
    assert execution_handoff["task_draft_mutated"] is False
    assert execution_handoff["execution_allowed"] is False
    assert execution_handoff["executed"] is False


def test_v177_rejected_preparation_cannot_create_execution_handoff():
    _, _, rejected, _ = _preparation_flow("REJECT")
    result = build_application_execution_handoff(rejected)
    assert result["error"] is True
    assert result["code"] == "APPLICATION_PREPARATION_NOT_APPROVED"


def test_v178_approved_audit_requires_exact_execution_handoff():
    eligibility, plan, decision, execution_handoff = _preparation_flow()
    audit = build_application_preparation_audit(
        eligibility,
        plan,
        decision,
        execution_handoff,
    )
    assert audit["status"] == "APPLICATION_PREPARATION_AUDIT_READY"
    assert audit["preparation_approved"] is True
    assert audit["application_execution_handoff_ready"] is True
    assert audit["application_allowed"] is False
    missing = build_application_preparation_audit(eligibility, plan, decision)
    assert missing["error"] is True


def test_v178_rejected_audit_requires_no_execution_handoff():
    eligibility, plan, decision, _ = _preparation_flow("REJECT")
    audit = build_application_preparation_audit(eligibility, plan, decision)
    assert audit["status"] == "APPLICATION_PREPARATION_AUDIT_READY"
    assert audit["preparation_rejected"] is True
    assert audit["application_execution_handoff_ready"] is False


def test_forged_evidence_plan_decision_and_handoff_fail_closed():
    eligibility, plan, decision, execution_handoff = _preparation_flow()
    forged_plan = dict(plan, planned_evidence={"unknown": "x"})
    assert build_application_preparation_decision(forged_plan, "PREPARE")["error"] is True
    forged_decision = dict(
        decision,
        status="APPLICATION_PREPARATION_APPROVED",
        decision="REJECT",
        preparation_approved=True,
        preparation_rejected=False,
    )
    assert build_application_execution_handoff(forged_decision)["code"] == "APPLICATION_PREPARATION_DECISION_CONTRADICTORY"
    forged_handoff = dict(
        execution_handoff,
        execution_handoff_evidence={"stock_observed_at": "forged"},
    )
    result = build_application_preparation_audit(
        eligibility,
        plan,
        decision,
        forged_handoff,
    )
    assert result["error"] is True
