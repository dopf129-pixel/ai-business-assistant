from copy import deepcopy

from app.product_task_freshness_evidence_application_authorization_signal import (
    build_freshness_evidence_application_authorization_signal,
)


def _contract(**values):
    result = {
        "authorization_id": "evidence-application-authorization:evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "preview_id": "evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "eligibility_id": "evidence-eligibility:evidence-signal:evidence-approval:d1",
        "signal_id": "evidence-signal:evidence-approval:d1",
        "approval_id": "evidence-approval:d1",
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "APPLICATION_AUTHORIZATION_REQUIRED",
        "authorization_ready": True,
        "authorization_required": True,
        "authorization_granted": False,
        "application_allowed": False,
        "application_started": False,
        "authorization_evidence": {
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
            "stock_source_recorded_at": "2026-08-29T11:56:00+00:00",
        },
        "authorization_evidence_count": 2,
        "validated_freshness_status": "FRESH",
        "validated_review_status": "READY_FOR_REVIEW",
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


def test_authorize_builds_signal_without_allowing_application():
    source = _contract()
    snapshot = deepcopy(source)
    result = build_freshness_evidence_application_authorization_signal(source, "AUTHORIZE")
    assert result["status"] == "APPLICATION_AUTHORIZATION_GRANTED"
    assert result["authorization_granted"] is True
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["execution_allowed"] is False
    assert source == snapshot


def test_reject_builds_rejection_signal():
    result = build_freshness_evidence_application_authorization_signal(_contract(), "REJECT")
    assert result["status"] == "APPLICATION_AUTHORIZATION_REJECTED"
    assert result["authorization_granted"] is False
    assert result["authorization_rejected"] is True


def test_invalid_decision_is_blocked():
    result = build_freshness_evidence_application_authorization_signal(_contract(), "YES")
    assert result["code"] == "APPLICATION_AUTHORIZATION_DECISION_INVALID"


def test_forged_authorization_id_is_blocked():
    result = build_freshness_evidence_application_authorization_signal(
        _contract(authorization_id="evidence-application-authorization:wrong"), "AUTHORIZE"
    )
    assert result["code"] == "AUTHORIZATION_ID_MISMATCH"


def test_pregranted_authorization_is_blocked():
    result = build_freshness_evidence_application_authorization_signal(
        _contract(authorization_granted=True), "AUTHORIZE"
    )
    assert result["code"] == "APPLICATION_AUTHORIZATION_ALREADY_DECIDED"


def test_application_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_authorization_signal(
        _contract(application_allowed=True), "AUTHORIZE"
    )
    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_authorization_signal(
        _contract(execution_ready=True), "AUTHORIZE"
    )
    assert result["code"] == "AUTHORIZATION_SAFETY_BOUNDARY_VIOLATION"


def test_unsafe_evidence_is_blocked():
    evidence = deepcopy(_contract()["authorization_evidence"])
    evidence["execution_allowed"] = True
    result = build_freshness_evidence_application_authorization_signal(
        _contract(authorization_evidence=evidence, authorization_evidence_count=3), "AUTHORIZE"
    )
    assert result["code"] == "AUTHORIZATION_EVIDENCE_UNSAFE"


def test_evidence_count_mismatch_is_blocked():
    result = build_freshness_evidence_application_authorization_signal(
        _contract(authorization_evidence_count=1), "AUTHORIZE"
    )
    assert result["code"] == "AUTHORIZATION_EVIDENCE_COUNT_MISMATCH"


def test_non_fresh_validation_is_blocked():
    result = build_freshness_evidence_application_authorization_signal(
        _contract(validated_freshness_status="STALE"), "AUTHORIZE"
    )
    assert result["code"] == "VALIDATED_FRESHNESS_NOT_FRESH"
