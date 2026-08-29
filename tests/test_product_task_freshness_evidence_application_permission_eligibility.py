from copy import deepcopy

from app.product_task_freshness_evidence_application_permission_eligibility import (
    build_freshness_evidence_application_permission_eligibility,
)


def _signal(**values):
    result = {
        "authorization_signal_id": "evidence-application-authorization-signal:evidence-application-authorization:evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "authorization_id": "evidence-application-authorization:evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "preview_id": "evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "eligibility_id": "evidence-eligibility:evidence-signal:evidence-approval:d1",
        "signal_id": "evidence-signal:evidence-approval:d1",
        "approval_id": "evidence-approval:d1",
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "APPLICATION_AUTHORIZATION_GRANTED",
        "decision": "AUTHORIZE",
        "authorization_signal_ready": True,
        "authorization_granted": True,
        "authorization_rejected": False,
        "application_allowed": False,
        "application_started": False,
        "authorization_evidence": {
            "sales_source_recorded_at": "2026-08-29T12:10:00+00:00",
            "stock_source_recorded_at": "2026-08-29T12:11:00+00:00",
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
    result.update(values)
    return result


def test_granted_signal_becomes_permission_review_eligible_without_permission():
    source = _signal()
    snapshot = deepcopy(source)
    result = build_freshness_evidence_application_permission_eligibility(source)
    assert result["status"] == "APPLICATION_PERMISSION_REVIEW_REQUIRED"
    assert result["permission_eligible"] is True
    assert result["permission_review_required"] is True
    assert result["permission_granted"] is False
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert source == snapshot


def test_rejected_authorization_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(
        _signal(status="APPLICATION_AUTHORIZATION_REJECTED", authorization_granted=False, authorization_rejected=True, decision="REJECT")
    )
    assert result["code"] == "APPLICATION_AUTHORIZATION_NOT_GRANTED"


def test_forged_authorization_signal_id_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(
        _signal(authorization_signal_id="evidence-application-authorization-signal:wrong")
    )
    assert result["code"] == "AUTHORIZATION_SIGNAL_ID_MISMATCH"


def test_decision_mismatch_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(_signal(decision="REJECT"))
    assert result["code"] == "APPLICATION_AUTHORIZATION_DECISION_MISMATCH"


def test_not_ready_signal_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(_signal(authorization_signal_ready=False))
    assert result["code"] == "APPLICATION_AUTHORIZATION_SIGNAL_NOT_READY"


def test_application_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(_signal(application_allowed=True))
    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(_signal(execution_ready=True))
    assert result["code"] == "AUTHORIZATION_SIGNAL_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_evidence_is_blocked():
    evidence = deepcopy(_signal()["authorization_evidence"])
    evidence["application_allowed"] = True
    result = build_freshness_evidence_application_permission_eligibility(
        _signal(authorization_evidence=evidence, authorization_evidence_count=3)
    )
    assert result["code"] == "AUTHORIZATION_EVIDENCE_UNSAFE"


def test_evidence_count_mismatch_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(_signal(authorization_evidence_count=1))
    assert result["code"] == "AUTHORIZATION_EVIDENCE_COUNT_MISMATCH"


def test_missing_context_is_blocked():
    result = build_freshness_evidence_application_permission_eligibility(_signal(sku=""))
    assert result["code"] == "APPLICATION_PERMISSION_ELIGIBILITY_CONTEXT_REQUIRED"
