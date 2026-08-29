from copy import deepcopy

from app.product_task_freshness_evidence_application_permission_signal import (
    build_freshness_evidence_application_permission_signal,
)


def _eligibility(**values):
    result = {
        "permission_eligibility_id": "evidence-application-permission-eligibility:evidence-application-authorization-signal:evidence-application-authorization:evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "authorization_signal_id": "evidence-application-authorization-signal:evidence-application-authorization:evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "authorization_id": "evidence-application-authorization:evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "preview_id": "evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "eligibility_id": "evidence-eligibility:evidence-signal:evidence-approval:d1",
        "signal_id": "evidence-signal:evidence-approval:d1",
        "approval_id": "evidence-approval:d1",
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "APPLICATION_PERMISSION_REVIEW_REQUIRED",
        "permission_eligible": True,
        "permission_review_required": True,
        "permission_granted": False,
        "application_allowed": False,
        "application_started": False,
        "permission_evidence": {
            "sales_source_recorded_at": "2026-08-29T12:20:00+00:00",
            "stock_source_recorded_at": "2026-08-29T12:21:00+00:00",
        },
        "permission_evidence_count": 2,
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


def test_grant_builds_permission_signal_without_allowing_application():
    source = _eligibility()
    snapshot = deepcopy(source)
    result = build_freshness_evidence_application_permission_signal(source, "GRANT")
    assert result["status"] == "APPLICATION_PERMISSION_GRANTED"
    assert result["permission_granted"] is True
    assert result["permission_rejected"] is False
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert source == snapshot


def test_reject_builds_rejection_signal():
    result = build_freshness_evidence_application_permission_signal(_eligibility(), "REJECT")
    assert result["status"] == "APPLICATION_PERMISSION_REJECTED"
    assert result["permission_granted"] is False
    assert result["permission_rejected"] is True


def test_invalid_decision_is_blocked():
    result = build_freshness_evidence_application_permission_signal(_eligibility(), "YES")
    assert result["code"] == "APPLICATION_PERMISSION_DECISION_INVALID"


def test_forged_permission_eligibility_id_is_blocked():
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(permission_eligibility_id="evidence-application-permission-eligibility:wrong"), "GRANT"
    )
    assert result["code"] == "PERMISSION_ELIGIBILITY_ID_MISMATCH"


def test_not_eligible_is_blocked():
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(permission_eligible=False), "GRANT"
    )
    assert result["code"] == "APPLICATION_PERMISSION_NOT_ELIGIBLE"


def test_pregranted_permission_is_blocked():
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(permission_granted=True), "GRANT"
    )
    assert result["code"] == "APPLICATION_PERMISSION_ALREADY_DECIDED"


def test_application_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(application_allowed=True), "GRANT"
    )
    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(execution_ready=True), "GRANT"
    )
    assert result["code"] == "PERMISSION_ELIGIBILITY_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_evidence_is_blocked():
    evidence = deepcopy(_eligibility()["permission_evidence"])
    evidence["application_allowed"] = True
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(permission_evidence=evidence, permission_evidence_count=3), "GRANT"
    )
    assert result["code"] == "PERMISSION_EVIDENCE_UNSAFE"


def test_evidence_count_mismatch_is_blocked():
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(permission_evidence_count=1), "GRANT"
    )
    assert result["code"] == "PERMISSION_EVIDENCE_COUNT_MISMATCH"


def test_persistence_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_permission_signal(
        _eligibility(persistent=True), "GRANT"
    )
    assert result["code"] == "PERMISSION_ELIGIBILITY_BOUNDARY_VIOLATION"
