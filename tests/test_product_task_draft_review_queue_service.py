from app.services.product_task_draft_review_queue_service import (
    ProductTaskDraftReviewQueueService,
)


def _draft(**overrides):
    result = {
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "DRAFT",
        "priority": "HIGH",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "created_at": "2026-08-28T10:00:00+00:00",
        "execution_allowed": False,
        "executed": False,
    }
    result.update(overrides)
    return result


def test_review_queue_prioritizes_current_critical_replenishment():
    service = ProductTaskDraftReviewQueueService()

    result = service.prioritize([
        _draft(
            draft_id="d-low",
            sku="low",
            status="STALE",
            priority="LOW",
            proposal_type="REVIEW_MARGIN",
        ),
        _draft(
            draft_id="d-urgent",
            sku="urgent",
            priority="CRITICAL",
        ),
    ])

    assert [item["sku"] for item in result["items"]] == [
        "urgent", "low"
    ]
    urgent = result["items"][0]
    assert urgent["review_score"] == 155
    assert urgent["review_priority"] == "URGENT"
    assert urgent["review_reasons"] == [
        "CURRENT_DRAFT",
        "SOURCE_PRIORITY_CRITICAL",
        "REPLENISHMENT_REVIEW",
    ]


def test_review_queue_excludes_closed_drafts_and_never_executes():
    service = ProductTaskDraftReviewQueueService()

    result = service.prioritize([
        _draft(status="ARCHIVED"),
        _draft(status="DISMISSED", draft_id="d2"),
        _draft(status="DRAFT", draft_id="d3"),
    ])

    assert result["total_reviewable"] == 1
    assert result["executed_count"] == 0
    assert result["items"][0]["execution_allowed"] is False
    assert result["items"][0]["executed"] is False


def test_review_queue_uses_stable_oldest_first_tie_breaker_and_limit():
    service = ProductTaskDraftReviewQueueService()

    result = service.prioritize([
        _draft(sku="new", created_at="2026-08-28T12:00:00+00:00"),
        _draft(sku="old", created_at="2026-08-28T09:00:00+00:00"),
    ], limit=1)

    assert result["total_reviewable"] == 2
    assert len(result["items"]) == 1
    assert result["items"][0]["sku"] == "old"


def test_priority_counts_cover_full_queue_before_limit():
    service = ProductTaskDraftReviewQueueService()

    result = service.prioritize([
        _draft(priority="CRITICAL"),
        _draft(draft_id="d2", priority="HIGH"),
        _draft(draft_id="d3", status="STALE", priority="HIGH"),
    ], limit=1)

    assert result["priority_counts"] == {
        "URGENT": 1,
        "HIGH": 1,
        "NORMAL": 0,
        "LOW": 1,
    }
