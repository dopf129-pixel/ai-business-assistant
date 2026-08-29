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


def _canonical():
    d="draft-1"; a="evidence-approval:"+d; s="evidence-signal:"+a; e="evidence-eligibility:"+s; p="evidence-application-preview:"+e; z="evidence-application-authorization:"+p
    signal={"error":False,"authorization_signal_id":"evidence-application-authorization-signal:"+z,"authorization_id":z,"preview_id":p,"eligibility_id":e,"signal_id":s,"approval_id":a,"request_id":"refresh:"+d,"draft_id":d,"sku":"sku-1","status":"APPLICATION_AUTHORIZATION_GRANTED","decision":"AUTHORIZE","authorization_signal_ready":True,"authorization_granted":True,"authorization_rejected":False,"authorization_evidence":{"sales_source_recorded_at":"2026-08-29T10:00:00Z"},"authorization_evidence_count":1,"source_freshness_proven":False,"application_allowed":False,"application_started":False,"persistent":False,"product_decision_recomputed":False,"product_decision_mutated":False,"task_draft_mutated":False,"execution_allowed":False,"execution_ready":False,"executed":False}
    pe=build_application_permission_eligibility(signal); pr=build_application_permission_review(pe); pd=build_application_permission_decision(pr,"PERMIT"); ph=build_application_start_handoff(pd); pa=build_application_permission_audit(pe,pr,pd,ph)
    e1=build_application_preparation_eligibility(ph,pa); plan=build_application_preparation_plan(e1); d1=build_application_preparation_decision(plan,"PREPARE"); h1=build_application_execution_handoff(d1); a1=build_application_preparation_audit(e1,plan,d1,h1)
    e2=build_executor_admission_eligibility(h1,a1)
    b=bind_executor_target_snapshot(e2,{"draft_id":"draft-1","sku":"sku-1","target_revision_id":"rev-1","target_version":1,"target_values":{}})
    diff=build_executor_application_diff(b); auth=build_executor_authorization_decision(diff,"AUTHORIZE"); wh=build_executor_write_handoff(auth)
    return h1,a1,e2,b,diff,auth,wh


def test_intermediate_upstream_id_forgery_fails_closed():
    handoff,audit,_,_,_,_,_=_canonical()
    forged_handoff=dict(handoff, approval_id="evidence-approval:forged")
    forged_audit=dict(audit, approval_id="evidence-approval:forged")
    result=build_executor_admission_eligibility(forged_handoff,forged_audit)
    assert result["error"] is True
    assert result["code"]=="APPLICATION_EXECUTOR_IDENTITY_MISMATCH"


def test_preparation_audit_reference_must_be_canonical_at_every_stage():
    _,_,eligibility,binding,diff,auth,handoff=_canonical()
    forged_eligibility=dict(eligibility,preparation_audit_id="forged")
    assert bind_executor_target_snapshot(forged_eligibility,{"draft_id":"draft-1","sku":"sku-1","target_revision_id":"rev-1","target_version":1,"target_values":{}})["error"] is True
    forged_binding=dict(binding,preparation_audit_id="forged")
    assert build_executor_application_diff(forged_binding)["error"] is True
    forged_diff=dict(diff,preparation_audit_id="forged")
    assert build_executor_authorization_decision(forged_diff,"AUTHORIZE")["error"] is True
    forged_auth=dict(auth,preparation_audit_id="forged")
    assert build_executor_write_handoff(forged_auth)["error"] is True
    assert build_executor_admission_audit(eligibility,binding,diff,auth,handoff)["error"] is False
