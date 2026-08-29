from product_task_freshness_evidence_application_permission import (
    build_application_permission_audit,
    build_application_permission_decision,
    build_application_permission_eligibility,
    build_application_permission_review,
    build_application_start_handoff,
)


def _signal(**overrides):
    draft = "draft-1"
    approval = "evidence-approval:" + draft
    signal = "evidence-signal:" + approval
    eligibility = "evidence-eligibility:" + signal
    preview = "evidence-application-preview:" + eligibility
    authorization = "evidence-application-authorization:" + preview
    result = {
        "error": False,
        "authorization_signal_id": "evidence-application-authorization-signal:" + authorization,
        "authorization_id": authorization,
        "preview_id": preview,
        "eligibility_id": eligibility,
        "signal_id": signal,
        "approval_id": approval,
        "request_id": "refresh:" + draft,
        "draft_id": draft,
        "sku": "sku-1",
        "status": "APPLICATION_AUTHORIZATION_GRANTED",
        "decision": "AUTHORIZE",
        "authorization_signal_ready": True,
        "authorization_granted": True,
        "authorization_rejected": False,
        "application_allowed": False,
        "application_started": False,
        "authorization_evidence": {"sales_source_recorded_at": "2026-08-29T10:00:00Z"},
        "authorization_evidence_count": 1,
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


def _flow():
    eligibility = build_application_permission_eligibility(_signal())
    review = build_application_permission_review(eligibility)
    decision = build_application_permission_decision(review, "PERMIT")
    handoff = build_application_start_handoff(decision)
    return eligibility, review, decision, handoff


def test_v169_granted_authorization_becomes_permission_eligible_only():
    result = build_application_permission_eligibility(_signal())
    assert result["status"] == "APPLICATION_PERMISSION_ELIGIBLE"
    assert result["permission_eligible"] is True
    assert result["permission_review_required"] is True
    assert result["permission_granted"] is False
    assert result["application_allowed"] is False
    assert result["executed"] is False


def test_v169_rejects_non_granted_or_unsafe_signal():
    rejected = build_application_permission_eligibility(_signal(status="APPLICATION_AUTHORIZATION_REJECTED", decision="REJECT", authorization_granted=False, authorization_rejected=True))
    assert rejected["error"] is True
    unsafe = build_application_permission_eligibility(_signal(application_allowed=True))
    assert unsafe["code"] == "APPLICATION_PERMISSION_SAFETY_BOUNDARY_VIOLATION"


def test_v170_review_preserves_exact_identity_and_no_application_permission():
    eligibility = build_application_permission_eligibility(_signal())
    review = build_application_permission_review(eligibility)
    assert review["status"] == "APPLICATION_PERMISSION_REVIEW_REQUIRED"
    assert review["permission_review_id"].endswith(eligibility["permission_eligibility_id"])
    assert review["permission_granted"] is False
    assert review["application_started"] is False


def test_v171_permit_is_explicit_but_still_does_not_start_application():
    eligibility = build_application_permission_eligibility(_signal())
    review = build_application_permission_review(eligibility)
    decision = build_application_permission_decision(review, "PERMIT")
    assert decision["status"] == "APPLICATION_PERMISSION_GRANTED"
    assert decision["permission_granted"] is True
    assert decision["application_allowed"] is False
    assert decision["application_started"] is False
    assert decision["task_draft_mutated"] is False


def test_v171_reject_and_invalid_decision_fail_safe():
    eligibility = build_application_permission_eligibility(_signal())
    review = build_application_permission_review(eligibility)
    rejected = build_application_permission_decision(review, "REJECT")
    assert rejected["status"] == "APPLICATION_PERMISSION_REJECTED"
    assert rejected["permission_granted"] is False
    invalid = build_application_permission_decision(review, "APPLY")
    assert invalid["code"] == "APPLICATION_PERMISSION_DECISION_INVALID"


def test_v172_handoff_requires_permit_and_does_not_apply_evidence():
    eligibility = build_application_permission_eligibility(_signal())
    review = build_application_permission_review(eligibility)
    permitted = build_application_permission_decision(review, "PERMIT")
    handoff = build_application_start_handoff(permitted)
    assert handoff["status"] == "APPLICATION_START_HANDOFF_READY"
    assert handoff["application_handoff_ready"] is True
    assert handoff["application_started"] is False
    assert handoff["persistent"] is False
    rejected = build_application_permission_decision(review, "REJECT")
    assert build_application_start_handoff(rejected)["error"] is True


def test_v173_audit_requires_matching_handoff_for_granted_permission():
    eligibility, review, decision, handoff = _flow()
    audit = build_application_permission_audit(eligibility, review, decision, handoff)
    assert audit["status"] == "APPLICATION_PERMISSION_AUDIT_READY"
    assert audit["permission_granted"] is True
    assert audit["application_handoff_ready"] is True
    assert audit["application_started"] is False
    assert build_application_permission_audit(eligibility, review, decision)["code"] == "APPLICATION_START_HANDOFF_REQUIRED"


def test_v173_rejected_permission_audits_without_handoff():
    eligibility = build_application_permission_eligibility(_signal())
    review = build_application_permission_review(eligibility)
    decision = build_application_permission_decision(review, "REJECT")
    audit = build_application_permission_audit(eligibility, review, decision)
    assert audit["status"] == "APPLICATION_PERMISSION_AUDIT_READY"
    assert audit["permission_rejected"] is True
    assert audit["application_handoff_ready"] is False


def test_forged_identity_and_evidence_fail_closed():
    eligibility, review, decision, handoff = _flow()
    forged_review = dict(review, draft_id="other")
    assert build_application_permission_decision(forged_review, "PERMIT")["error"] is True
    forged_decision = dict(decision, permission_evidence={"unknown": "x"})
    assert build_application_start_handoff(forged_decision)["error"] is True
    forged_handoff = dict(handoff, handoff_evidence={"stock_observed_at": "x"})
    assert build_application_permission_audit(eligibility, review, decision, forged_handoff)["error"] is True
