from datetime import datetime, timezone

from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)
from app.services.product_task_draft_readiness_service import (
    ProductTaskDraftReadinessService,
)


def _draft(**overrides):
    result = {
        "draft_id": "d1",
        "status": "DRAFT",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "2026-08-29T09:30:00+00:00",
        "current_stock": 8,
        "sales_velocity": 4.0,
        "days_of_stock": 2.0,
        "profit_per_unit": 35.1,
        "margin_percent": 36.5,
        "economics_basis": "ESTIMATED_RETURNS",
    }
    result.update(overrides)
    return result


def _clock():
    return datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)


def test_freshness_uses_real_decision_snapshot_timestamp():
    service = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=_clock,
    )

    result = service.evaluate(_draft())

    assert result["decision_snapshot"]["status"] == "FRESH"
    assert result["decision_snapshot"]["age_seconds"] == 1800.0
    assert result["components"]["sales"]["status"] == "UNKNOWN"
    assert result["components"]["stock"]["status"] == "UNKNOWN"
    assert result["components"]["unit_economics"]["status"] == "UNKNOWN"
    assert result["status"] == "UNKNOWN"
    assert result["execution_ready"] is False
    assert result["executed"] is False


def test_old_decision_snapshot_is_stale():
    service = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=_clock,
    )

    result = service.evaluate(_draft(
        decision_recorded_at="2026-08-29T08:00:00+00:00"
    ))

    assert result["status"] == "STALE"
    assert result["decision_snapshot"]["age_seconds"] == 7200.0
    assert "DECISION_SNAPSHOT_STALE" in result["reasons"]


def test_invalid_or_missing_timestamp_is_unknown_not_fresh():
    service = ProductTaskDraftFreshnessService(clock=_clock)

    missing = service.evaluate(_draft(decision_recorded_at=None))
    invalid = service.evaluate(_draft(decision_recorded_at="not-a-time"))

    assert missing["decision_snapshot"]["status"] == "UNKNOWN"
    assert invalid["decision_snapshot"]["status"] == "UNKNOWN"
    assert "DECISION_SNAPSHOT_TIMESTAMP_UNKNOWN" in missing["reasons"]


def test_component_source_timestamps_are_used_only_when_supplied():
    service = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=_clock,
    )

    result = service.evaluate(_draft(
        sales_source_recorded_at="2026-08-29T09:45:00+00:00",
        stock_source_recorded_at="2026-08-29T07:00:00+00:00",
        unit_economics_source_recorded_at="2026-08-29T09:50:00+00:00",
    ))

    assert result["components"]["sales"]["status"] == "FRESH"
    assert result["components"]["stock"]["status"] == "STALE"
    assert result["components"]["unit_economics"]["status"] == "FRESH"
    assert result["status"] == "STALE"
    assert "STOCK_DATA_STALE" in result["reasons"]


def test_readiness_requires_freshness_when_guard_is_connected():
    freshness = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=_clock,
    )
    readiness = ProductTaskDraftReadinessService(
        freshness_service=freshness
    )

    unknown = readiness.evaluate(_draft())
    fresh = readiness.evaluate(_draft(
        sales_source_recorded_at="2026-08-29T09:45:00+00:00",
        stock_source_recorded_at="2026-08-29T09:45:00+00:00",
        unit_economics_source_recorded_at="2026-08-29T09:45:00+00:00",
    ))

    assert unknown["review_ready"] is False
    assert "SOURCE_DATA_NOT_FRESH" in unknown["review_blockers"]
    assert unknown["freshness"]["status"] == "UNKNOWN"
    assert fresh["review_ready"] is True
    assert fresh["freshness"]["status"] == "FRESH"
    assert fresh["execution_ready"] is False
