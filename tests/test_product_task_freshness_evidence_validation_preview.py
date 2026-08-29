from copy import deepcopy
from datetime import datetime, timezone

from app.product_task_freshness_evidence_validation_preview import (
    build_freshness_evidence_validation_preview,
)
from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _service():
    return ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=lambda: NOW,
    )


def _draft(**values):
    result = {
        "draft_id": "d1",
        "sku": "hook-2",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "2026-08-29T11:30:00+00:00",
    }
    result.update(values)
    return result


def _candidate(**evidence):
    return {
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "evidence_update": evidence,
        "persistent": False,
        "task_draft_mutated": False,
        "executed": False,
    }


def test_fresh_source_candidate_can_preview_unknown_to_fresh_without_mutation():
    draft = _draft()
    candidate = _candidate(
        sales_source_recorded_at="2026-08-29T11:55:00+00:00",
        stock_source_recorded_at="2026-08-29T11:56:00+00:00",
    )
    draft_snapshot = deepcopy(draft)
    candidate_snapshot = deepcopy(candidate)

    result = build_freshness_evidence_validation_preview(
        draft,
        candidate,
        _service(),
    )

    assert result["before"]["status"] == "UNKNOWN"
    assert result["after"]["status"] == "FRESH"
    assert result["preview_freshness_status"] == "FRESH"
    assert result["preview_freshness_validated"] is True
    assert result["source_freshness_proven"] is False
    assert result["changed_component_count"] == 2
    assert result["task_draft_mutated"] is False
    assert result["persistent"] is False
    assert draft == draft_snapshot
    assert candidate == candidate_snapshot


def test_stale_source_candidate_previews_stale_and_does_not_claim_freshness():
    result = build_freshness_evidence_validation_preview(
        _draft(),
        _candidate(
            sales_source_recorded_at="2026-08-29T09:00:00+00:00",
            stock_source_recorded_at="2026-08-29T11:55:00+00:00",
        ),
        _service(),
    )

    assert result["after"]["status"] == "STALE"
    assert result["preview_freshness_validated"] is False
    assert result["source_freshness_proven"] is False
    assert result["after"]["components"]["sales"]["status"] == "STALE"


def test_future_source_candidate_stays_unknown_after_guard_validation():
    result = build_freshness_evidence_validation_preview(
        _draft(),
        _candidate(
            sales_source_recorded_at="2026-08-29T12:30:00+00:00",
            stock_source_recorded_at="2026-08-29T11:55:00+00:00",
        ),
        _service(),
    )

    assert result["after"]["status"] == "UNKNOWN"
    assert "SALES_TIMESTAMP_IN_FUTURE" in result["after"]["reasons"]
    assert result["preview_freshness_validated"] is False


def test_observation_only_candidate_does_not_change_guard_status():
    result = build_freshness_evidence_validation_preview(
        _draft(),
        _candidate(
            sales_observed_at="2026-08-29T11:59:00+00:00",
            stock_observed_at="2026-08-29T11:59:00+00:00",
        ),
        _service(),
    )

    assert result["before"]["status"] == "UNKNOWN"
    assert result["after"]["status"] == "UNKNOWN"
    assert result["overall_status_changed"] is False
    assert result["changed_component_count"] == 0
    assert result["applied_evidence_count"] == 2


def test_unexpected_candidate_fields_are_ignored_and_execution_stays_blocked():
    result = build_freshness_evidence_validation_preview(
        _draft(),
        _candidate(
            sales_source_recorded_at="2026-08-29T11:55:00+00:00",
            stock_source_recorded_at="2026-08-29T11:55:00+00:00",
            updated_at="2026-08-29T12:00:00+00:00",
            execution_allowed=True,
        ),
        _service(),
    )

    assert "updated_at" not in result["applied_evidence"]
    assert "execution_allowed" not in result["applied_evidence"]
    assert result["preview_freshness_status"] == "FRESH"
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False


def test_mismatched_draft_candidate_is_blocked_before_evidence_application():
    candidate = _candidate(
        sales_source_recorded_at="2026-08-29T11:55:00+00:00",
    )
    candidate["draft_id"] = "d2"

    result = build_freshness_evidence_validation_preview(
        _draft(),
        candidate,
        _service(),
    )

    assert result["status"] == "PREVIEW_BLOCKED"
    assert result["code"] == "EVIDENCE_CANDIDATE_DRAFT_MISMATCH"
    assert result["applied_evidence"] == {}
    assert result["preview_freshness_status"] is None
    assert result["executed"] is False


def test_missing_freshness_service_blocks_preview_without_applying_candidate():
    result = build_freshness_evidence_validation_preview(
        _draft(),
        _candidate(sales_source_recorded_at="2026-08-29T11:55:00+00:00"),
        None,
    )

    assert result["status"] == "PREVIEW_BLOCKED"
    assert result["code"] == "FRESHNESS_SERVICE_REQUIRED"
    assert result["applied_evidence"] == {}
    assert result["source_freshness_proven"] is False
    assert result["executed"] is False
