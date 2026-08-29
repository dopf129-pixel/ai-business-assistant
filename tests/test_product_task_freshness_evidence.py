from datetime import datetime, timezone

from app.services.product_action_task_draft_service import (
    ProductActionTaskDraftService,
)
from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)


def _decision(**overrides):
    result = {
        "sku": "hook-2",
        "recorded_at": "2026-08-29T09:30:00+00:00",
        "decision_type": "REPLENISH",
        "priority": "HIGH",
        "current_stock": 8,
        "sales_velocity": 4.0,
        "days_of_stock": 2.0,
        "profit_per_unit": 35.1,
        "margin_percent": 36.5,
        "economics_basis": "ESTIMATED_RETURNS",
    }
    result.update(overrides)
    return result


def _proposal():
    return {
        "proposal_type": "REVIEW_REPLENISHMENT",
        "action_required": True,
    }


def _clock():
    return "2026-08-29T10:00:00+00:00"


def _freshness_clock():
    return datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)


def test_draft_persists_real_source_timestamps_from_decision():
    service = ProductActionTaskDraftService(clock=_clock)

    result = service.create_from_confirmation(
        _decision(
            sales_source_recorded_at="2026-08-29T09:45:00+00:00",
            stock_source_recorded_at="2026-08-29T09:50:00+00:00",
            unit_economics_source_recorded_at="2026-08-29T09:40:00+00:00",
        ),
        _proposal(),
    )

    draft = result["task_draft"]
    assert draft["sales_source_recorded_at"] == "2026-08-29T09:45:00+00:00"
    assert draft["stock_source_recorded_at"] == "2026-08-29T09:50:00+00:00"
    assert draft["unit_economics_source_recorded_at"] == "2026-08-29T09:40:00+00:00"


def test_draft_keeps_observed_time_separate_from_source_time():
    service = ProductActionTaskDraftService(clock=_clock)

    result = service.create_from_confirmation(
        _decision(
            stock_source_recorded_at=None,
            stock_observed_at="2026-08-29T09:59:00+00:00",
        ),
        _proposal(),
    )

    draft = result["task_draft"]
    assert draft["stock_source_recorded_at"] is None
    assert draft["stock_observed_at"] == "2026-08-29T09:59:00+00:00"
    assert draft["created_at"] == "2026-08-29T10:00:00+00:00"


def test_observed_time_does_not_make_missing_source_timestamp_fresh():
    draft_service = ProductActionTaskDraftService(clock=_clock)
    freshness = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=_freshness_clock,
    )

    draft = draft_service.create_from_confirmation(
        _decision(
            sales_observed_at="2026-08-29T09:59:00+00:00",
            stock_observed_at="2026-08-29T09:59:00+00:00",
        ),
        _proposal(),
    )["task_draft"]
    result = freshness.evaluate(draft)

    assert result["components"]["sales"]["status"] == "UNKNOWN"
    assert result["components"]["stock"]["status"] == "UNKNOWN"
    assert "SALES_TIMESTAMP_UNKNOWN" in result["reasons"]
    assert "STOCK_TIMESTAMP_UNKNOWN" in result["reasons"]
    assert result["status"] == "UNKNOWN"


def test_real_source_timestamps_can_prove_freshness():
    draft_service = ProductActionTaskDraftService(clock=_clock)
    freshness = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=3600,
        clock=_freshness_clock,
    )

    draft = draft_service.create_from_confirmation(
        _decision(
            sales_source_recorded_at="2026-08-29T09:45:00+00:00",
            stock_source_recorded_at="2026-08-29T09:50:00+00:00",
            sales_observed_at="2026-08-29T09:59:00+00:00",
            stock_observed_at="2026-08-29T09:59:00+00:00",
        ),
        _proposal(),
    )["task_draft"]
    result = freshness.evaluate(draft)

    assert result["components"]["sales"]["status"] == "FRESH"
    assert result["components"]["stock"]["status"] == "FRESH"
    assert result["status"] == "FRESH"


def test_missing_evidence_fields_remain_absent_for_legacy_sources():
    service = ProductActionTaskDraftService(clock=_clock)

    draft = service.create_from_confirmation(
        _decision(),
        _proposal(),
    )["task_draft"]

    assert "sales_source_recorded_at" not in draft
    assert "stock_source_recorded_at" not in draft
    assert "unit_economics_source_recorded_at" not in draft
    assert "sales_observed_at" not in draft
    assert "stock_observed_at" not in draft
    assert "unit_economics_observed_at" not in draft
