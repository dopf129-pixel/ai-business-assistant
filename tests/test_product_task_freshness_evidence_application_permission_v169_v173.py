from product_task_freshness_evidence_application_permission import (
    build_application_permission_audit, build_application_permission_decision,
    build_application_permission_eligibility, build_application_permission_review,
    build_application_start_handoff,
)


def _signal(**overrides):
    d="draft-1"; a="evidence-approval:"+d; s="evidence-signal:"+a; e="evidence-eligibility:"+s; p="evidence-application-preview:"+e; z="evidence-application-authorization:"+p
    result={"error":False,"authorization_signal_id":"evidence-application-authorization-signal:"+z,"authorization_id":z,"preview_id":p,"eligibility_id":e,"signal_id":s,"approval_id":a,"request_id":"refresh:"+d,"draft_id":d,"sku":"sku-1","status":"APPLICATION_AUTHORIZATION_GRANTED","decision":"AUTHORIZE","authorization_signal_ready":True,"authorization_granted":True,"authorization_rejected":False,"application_allowed":False,"application_started":False,"authorization_evidence":{"sales_source_recorded_at":"2026-08-29T10:00:00Z"},"authorization_evidence_count":1,"source_freshness_proven":False,"persistent":False,"product_decision_recomputed":False,"product_decision_mutated":False,"task_draft_mutated":False,"execution_allowed":False,"execution_ready":False,"executed":False}
    result.update(overrides); return result


def _flow(choice="PERMIT"):
    eligibility=build_application_permission_eligibility(_signal()); review=build_application_permission_review(eligibility); decision=build_application_permission_decision(review,choice); handoff=build_application_start_handoff(decision) if choice=="PERMIT" else None
    return eligibility,review,decision,handoff


def test_v169_granted_authorization_becomes_permission_eligible_only():
    r=build_application_permission_eligibility(_signal()); assert r["status"]=="APPLICATION_PERMISSION_ELIGIBLE"; assert r["permission_eligible"] is True; assert r["permission_granted"] is False; assert r["application_allowed"] is False; assert r["executed"] is False


def test_v169_rejects_non_granted_or_unsafe_signal():
    r=build_application_permission_eligibility(_signal(status="APPLICATION_AUTHORIZATION_REJECTED",decision="REJECT",authorization_granted=False,authorization_rejected=True)); assert r["error"] is True
    assert build_application_permission_eligibility(_signal(application_allowed=True))["code"]=="APPLICATION_PERMISSION_SAFETY_BOUNDARY_VIOLATION"


def test_v170_review_preserves_identity_without_granting_permission():
    e=build_application_permission_eligibility(_signal()); r=build_application_permission_review(e); assert r["status"]=="APPLICATION_PERMISSION_REVIEW_REQUIRED"; assert r["permission_granted"] is False; assert r["application_started"] is False


def test_v171_permit_and_reject_are_explicit_and_non_executing():
    e=build_application_permission_eligibility(_signal()); r=build_application_permission_review(e); p=build_application_permission_decision(r,"PERMIT"); assert p["permission_granted"] is True; assert p["application_started"] is False; assert p["task_draft_mutated"] is False
    x=build_application_permission_decision(r,"REJECT"); assert x["status"]=="APPLICATION_PERMISSION_REJECTED"; assert x["permission_granted"] is False
    assert build_application_permission_decision(r,"APPLY")["code"]=="APPLICATION_PERMISSION_DECISION_INVALID"


def test_v172_handoff_requires_permit_and_does_not_apply_evidence():
    e,r,p,h=_flow(); assert h["status"]=="APPLICATION_START_HANDOFF_READY"; assert h["application_started"] is False; assert h["persistent"] is False
    rejected=build_application_permission_decision(r,"REJECT"); assert build_application_start_handoff(rejected)["error"] is True


def test_v173_granted_audit_requires_exact_handoff():
    e,r,p,h=_flow(); a=build_application_permission_audit(e,r,p,h); assert a["status"]=="APPLICATION_PERMISSION_AUDIT_READY"; assert a["permission_granted"] is True; assert a["application_started"] is False
    assert build_application_permission_audit(e,r,p)["code"]=="APPLICATION_START_HANDOFF_REQUIRED"


def test_v173_rejected_permission_audits_without_handoff():
    e,r,d,_=_flow("REJECT"); a=build_application_permission_audit(e,r,d); assert a["status"]=="APPLICATION_PERMISSION_AUDIT_READY"; assert a["permission_rejected"] is True; assert a["application_handoff_ready"] is False


def test_forged_identity_evidence_and_decision_fail_closed():
    e,r,p,h=_flow(); assert build_application_permission_decision(dict(r,draft_id="other"),"PERMIT")["error"] is True
    assert build_application_start_handoff(dict(p,permission_evidence={"unknown":"x"}))["error"] is True
    assert build_application_permission_audit(e,r,p,dict(h,handoff_evidence={"stock_observed_at":"x"}))["error"] is True
    forged=dict(p,status="APPLICATION_PERMISSION_GRANTED",decision="REJECT",permission_granted=True,permission_rejected=False)
    assert build_application_permission_audit(e,r,forged,h)["code"]=="APPLICATION_PERMISSION_DECISION_CONTRADICTORY"
    forged_reject=dict(p,status="APPLICATION_PERMISSION_REJECTED",decision="REJECT",permission_granted=True,permission_rejected=True)
    assert build_application_permission_audit(e,r,forged_reject)["code"]=="APPLICATION_PERMISSION_DECISION_CONTRADICTORY"
