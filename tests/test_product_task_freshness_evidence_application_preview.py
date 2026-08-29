from copy import deepcopy
from datetime import datetime, timezone

from app.product_task_freshness_evidence_application_preview import (
    build_freshness_evidence_application_preview,
)
from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)
from app.services.product_task_draft_readiness_service import (
    ProductTaskDraftReadinessService,
)


def _clock():
    return datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _draft(**values):
    result = {
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "DRAFT",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "2026-08-29T11:50:00+00:00",
        "current_stock": 10,
        "sales_velocity": 2.0,
        "days_of_stock": 5.0,
        "sales_source_recorded_at": "2026-08-29T09:00:00+00:00",
        "stock_source_recorded_at": "2026-08-29T09:00:00+00:00",
    }
    result.update(values)
    return result


def _eligibility(**values):
    result = {
        "eligibility_id": "evidence-eligibility:evidence-signal:evidence-approval:d1",
        "signal_id": "evidence-signal:evidence-approval:d1",
        "approval_id": "evidence-approval:d1",
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "ELIGIBLE_FOR_APPLICATION_REVIEW",
        "application_eligible": True,
        "application_review_required": True,
        "application_allowed": False,
        "application_started": False,
        "approved_evidence": {
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
            "stock_source_recorded_at": "2026-08-29T11:56:00+00:00",
        },
        "approved_evidence_count": 2,
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


def _services():
    freshness = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=_clock,
    )
    readiness = ProductTaskDraftReadinessService(freshness_service=freshness)
    return freshness, readiness


def test_preview_applies_evidence_only_to_copy_and_rechecks_freshness_readiness():
    draft = _draft()
    eligibility = _eligibility()
    draft_snapshot = deepcopy(draft)
    eligibility_snapshot = deepcopy(eligibility)
    freshness, readiness = _services()

    result = build_freshness_evidence_application_preview(
        draft, eligibility, freshness, readiness
    )

    assert result["status"] == "APPLICATION_PREVIEW_READY"
    assert result["before_freshness"]["status"] == "STALE"
    assert result["after_freshness"]["status"] == "FRESH"
    assert result["before_readiness"]["review_ready"] is False
    assert result["after_readiness"]["review_ready"] is True
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert draft == draft_snapshot
    assert eligibility == eligibility_snapshot


def test_observation_only_evidence_does_not_prove_source_freshness():
    freshness, readiness = _services()
    eligibility = _eligibility(
        approved_evidence={
            "sales_observed_at": "2026-08-29T11:55:00+00:00",
            "stock_observed_at": "2026-08-29T11:56:00+00:00",
        },
        approved_evidence_count=2,
    )

    result = build_freshness_evidence_application_preview(
        _draft(), eligibility, freshness, readiness
    )

    assert result["after_freshness"]["status"] == "STALE"
    assert result["source_freshness_proven"] is False


def test_cross_draft_context_is_blocked():
    freshness, readiness = _services()
    result = build_freshness_evidence_application_preview(
        _draft(), _eligibility(draft_id="d2"), freshness, readiness
    )
    assert result["code"] == "DRAFT_ID_MISMATCH"
    assert result["applied_evidence"] == {}


def test_forged_request_id_is_blocked():
    freshness, readiness = _services()
    result = build_freshness_evidence_application_preview(
        _draft(), _eligibility(request_id="refresh:d2"), freshness, readiness
    )
    assert result["code"] == "REQUEST_ID_MISMATCH"


def test_forged_eligibility_id_is_blocked():
    freshness, readiness = _services()
    result = build_freshness_evidence_application_preview(
        _draft(), _eligibility(eligibility_id="evidence-eligibility:wrong"), freshness, readiness
    )
    assert result["code"] == "ELIGIBILITY_ID_MISMATCH"


def test_unsafe_evidence_is_blocked():
    evidence = deepcopy(_eligibility()["approved_evidence"])
    evidence["execution_allowed"] = True
    freshness, readiness = _services()

    result = build_freshness_evidence_application_preview(
        _draft(),
        _eligibility(approved_evidence=evidence, approved_evidence_count=3),
        freshness,
        readiness,
    )

    assert result["code"] == "APPROVED_EVIDENCE_UNSAFE"
    assert result["execution_allowed"] is False


def test_evidence_count_mismatch_is_blocked():
    freshness, readiness = _services()
    result = build_freshness_evidence_application_preview(
        _draft(), _eligibility(approved_evidence_count=1), freshness, readiness
    )
    assert result["code"] == "APPROVED_EVIDENCE_COUNT_MISMATCH"


def test_missing_freshness_service_is_blocked():
    _, readiness = _services()
    result = build_freshness_evidence_application_preview(
        _draft(), _eligibility(), None, readiness
    )
    assert result["code"] == "FRESHNESS_SERVICE_REQUIRED"


def test_missing_readiness_service_is_blocked():
    freshness, _ = _services()
    result = build_freshness_evidence_application_preview(
        _draft(), _eligibility(), freshness, None
    )
    assert result["code"] == "READINESS_SERVICE_REQUIRED"


def test_eligibility_that_already_allows_application_is_blocked():
    freshness, readiness = _services()
    result = build_freshness_evidence_application_preview(
        _draft(), _eligibility(application_allowed=True), freshness, readiness
    )
    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"
    assert result["application_started"] is False
