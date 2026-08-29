from copy import deepcopy

from app.product_task_freshness_evidence_application_authorization import (
    build_freshness_evidence_application_authorization,
)


def _preview(**values):
    result = {
        "preview_id": "evidence-application-preview:evidence-eligibility:evidence-signal:evidence-approval:d1",
        "eligibility_id": "evidence-eligibility:evidence-signal:evidence-approval:d1",
        "signal_id": "evidence-signal:evidence-approval:d1",
        "approval_id": "evidence-approval:d1",
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "APPLICATION_PREVIEW_READY",
        "preview_only": True,
        "applied_evidence": {
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
            "stock_source_recorded_at": "2026-08-29T11:56:00+00:00",
        },
        "after_freshness": {
            "status": "FRESH",
            "execution_ready": False,
            "executed": False,
        },
        "after_readiness": {
            "review_status": "READY_FOR_REVIEW",
            "review_ready": True,
            "execution_ready": False,
            "executed": False,
        },
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
    result.update(values)
    return result


def test_ready_preview_builds_authorization_required_without_granting_it():
    preview = _preview()
    snapshot = deepcopy(preview)

    result = build_freshness_evidence_application_authorization(preview)

    assert result["status"] == "APPLICATION_AUTHORIZATION_REQUIRED"
    assert result["authorization_ready"] is True
    assert result["authorization_required"] is True
    assert result["authorization_granted"] is False
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert result["executed"] is False
    assert preview == snapshot


def test_non_fresh_after_preview_is_blocked():
    result = build_freshness_evidence_application_authorization(
        _preview(after_freshness={
            "status": "STALE",
            "execution_ready": False,
            "executed": False,
        })
    )
    assert result["code"] == "AFTER_FRESHNESS_NOT_FRESH"
    assert result["authorization_ready"] is False


def test_non_ready_after_preview_is_blocked():
    result = build_freshness_evidence_application_authorization(
        _preview(after_readiness={
            "review_status": "NEEDS_DATA_OR_REFRESH",
            "review_ready": False,
            "execution_ready": False,
            "executed": False,
        })
    )
    assert result["code"] == "AFTER_READINESS_NOT_READY"


def test_unsafe_applied_evidence_is_blocked():
    evidence = deepcopy(_preview()["applied_evidence"])
    evidence["execution_allowed"] = True
    result = build_freshness_evidence_application_authorization(
        _preview(applied_evidence=evidence)
    )
    assert result["code"] == "APPLIED_EVIDENCE_UNSAFE"
    assert result["authorized_evidence"] == {}


def test_forged_preview_id_is_blocked():
    result = build_freshness_evidence_application_authorization(
        _preview(preview_id="evidence-application-preview:wrong")
    )
    assert result["code"] == "PREVIEW_ID_MISMATCH"


def test_request_id_must_bind_to_same_draft():
    result = build_freshness_evidence_application_authorization(
        _preview(request_id="refresh:d2")
    )
    assert result["code"] == "REQUEST_ID_MISMATCH"


def test_preview_that_already_allows_application_is_blocked():
    result = build_freshness_evidence_application_authorization(
        _preview(application_allowed=True)
    )
    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"
    assert result["application_started"] is False


def test_preview_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_authorization(
        _preview(execution_ready=True)
    )
    assert result["code"] == "PREVIEW_SAFETY_BOUNDARY_VIOLATION"


def test_after_freshness_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_authorization(
        _preview(after_freshness={
            "status": "FRESH",
            "execution_ready": True,
            "executed": False,
        })
    )
    assert result["code"] == "AFTER_FRESHNESS_EXECUTION_BOUNDARY_VIOLATION"


def test_after_readiness_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_authorization(
        _preview(after_readiness={
            "review_status": "READY_FOR_REVIEW",
            "review_ready": True,
            "execution_ready": True,
            "executed": False,
        })
    )
    assert result["code"] == "AFTER_READINESS_EXECUTION_BOUNDARY_VIOLATION"
