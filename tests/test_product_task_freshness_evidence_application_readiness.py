from copy import deepcopy

from app.product_task_freshness_evidence_application_readiness import (
    build_freshness_evidence_application_readiness,
)


def _permission_signal(**values):
    result = {
        "permission_signal_id": "evidence-application-permission-signal:evidence-application-permission-eligibility:evidence-application-authorization-signal:evidence-application-authorization:evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
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
        "status": "APPLICATION_PERMISSION_GRANTED",
        "decision": "GRANT",
        "permission_signal_ready": True,
        "permission_granted": True,
        "permission_rejected": False,
        "application_allowed": False,
        "application_started": False,
        "permission_evidence": {
            "sales_source_recorded_at": "2026-08-29T12:30:00+00:00",
            "stock_source_recorded_at": "2026-08-29T12:31:00+00:00",
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


def test_granted_permission_becomes_ready_without_allowing_application():
    source = _permission_signal()
    snapshot = deepcopy(source)
    result = build_freshness_evidence_application_readiness(source)
    assert result["status"] == "APPLICATION_READY_FOR_SEPARATE_STEP"
    assert result["application_ready"] is True
    assert result["application_review_complete"] is True
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert source == snapshot


def test_rejected_permission_is_blocked():
    result = build_freshness_evidence_application_readiness(
        _permission_signal(status="APPLICATION_PERMISSION_REJECTED", decision="REJECT", permission_granted=False, permission_rejected=True)
    )
    assert result["code"] == "APPLICATION_PERMISSION_NOT_GRANTED"


def test_forged_permission_signal_id_is_blocked():
    result = build_freshness_evidence_application_readiness(
        _permission_signal(permission_signal_id="evidence-application-permission-signal:wrong")
    )
    assert result["code"] == "PERMISSION_SIGNAL_ID_MISMATCH"


def test_decision_mismatch_is_blocked():
    result = build_freshness_evidence_application_readiness(_permission_signal(decision="REJECT"))
    assert result["code"] == "APPLICATION_PERMISSION_DECISION_MISMATCH"


def test_not_ready_permission_signal_is_blocked():
    result = build_freshness_evidence_application_readiness(_permission_signal(permission_signal_ready=False))
    assert result["code"] == "APPLICATION_PERMISSION_SIGNAL_NOT_READY"


def test_application_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_readiness(_permission_signal(application_allowed=True))
    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"


def test_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_readiness(_permission_signal(execution_ready=True))
    assert result["code"] == "PERMISSION_SIGNAL_SAFETY_BOUNDARY_VIOLATION"


def test_persistence_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_readiness(_permission_signal(persistent=True))
    assert result["code"] == "PERMISSION_SIGNAL_BOUNDARY_VIOLATION"


def test_unsafe_evidence_is_blocked():
    evidence = deepcopy(_permission_signal()["permission_evidence"])
    evidence["application_allowed"] = True
    result = build_freshness_evidence_application_readiness(
        _permission_signal(permission_evidence=evidence, permission_evidence_count=3)
    )
    assert result["code"] == "PERMISSION_EVIDENCE_UNSAFE"


def test_evidence_count_mismatch_is_blocked():
    result = build_freshness_evidence_application_readiness(_permission_signal(permission_evidence_count=1))
    assert result["code"] == "PERMISSION_EVIDENCE_COUNT_MISMATCH"


def test_missing_context_is_blocked():
    result = build_freshness_evidence_application_readiness(_permission_signal(sku=""))
    assert result["code"] == "APPLICATION_READINESS_CONTEXT_REQUIRED"
