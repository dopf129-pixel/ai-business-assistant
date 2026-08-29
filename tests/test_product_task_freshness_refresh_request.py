from datetime import datetime, timezone

from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)
from app.services.product_task_draft_readiness_service import (
    ProductTaskDraftReadinessService,
)


NOW = datetime(2026, 8, 29, 13, 0, tzinfo=timezone.utc)


def _service():
    return ProductTaskDraftReadinessService(
        freshness_service=ProductTaskDraftFreshnessService(
            max_snapshot_age_seconds=3600,
            clock=lambda: NOW,
        )
    )


def _draft(**values):
    result = {
        "draft_id": "d7",
        "sku": "sku-1",
        "status": "DRAFT",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "2026-08-29T12:30:00+00:00",
        "current_stock": 10,
        "sales_velocity": 1.0,
        "days_of_stock": 10.0,
    }
    result.update(values)
    return result


def test_build_refresh_request_for_missing_source_evidence():
    request = _service().build_refresh_request(
        _draft(
            sales_observed_at="2026-08-29T12:55:00+00:00",
            stock_observed_at="2026-08-29T12:55:00+00:00",
        )
    )

    assert request["request_id"] == "refresh:d7"
    assert request["status"] == "REQUEST_DRAFT"
    assert request["required"] is True
    assert request["target_count"] == 2
    assert {item["component"] for item in request["targets"]} == {
        "sales",
        "stock",
    }
    assert all(
        item["action"] == "SOURCE_TIMESTAMP_REQUIRED"
        for item in request["targets"]
    )
    assert request["persistent"] is False
    assert request["refresh_started"] is False
    assert request["execution_allowed"] is False
    assert request["execution_ready"] is False
    assert request["executed"] is False


def test_no_refresh_request_when_required_sources_are_fresh():
    request = _service().build_refresh_request(
        _draft(
            sales_source_recorded_at="2026-08-29T12:55:00+00:00",
            stock_source_recorded_at="2026-08-29T12:55:00+00:00",
        )
    )

    assert request["request_id"] is None
    assert request["status"] == "NOT_REQUIRED"
    assert request["required"] is False
    assert request["targets"] == []
    assert request["target_count"] == 0
    assert request["refresh_started"] is False
    assert request["executed"] is False


def test_refresh_request_is_deterministic_and_does_not_mutate_draft():
    draft = _draft(
        sales_source_recorded_at="2026-08-29T10:00:00+00:00",
        stock_source_recorded_at="2026-08-29T12:55:00+00:00",
    )
    original = dict(draft)

    first = _service().build_refresh_request(draft)
    second = _service().build_refresh_request(draft)

    assert first == second
    assert draft == original
    assert first["targets"][0]["component"] == "sales"
    assert first["targets"][0]["action"] == "REFRESH_SOURCE_DATA"
    assert first["persistent"] is False


def test_refresh_request_only_targets_components_required_by_proposal():
    draft = {
        "draft_id": "d8",
        "sku": "sku-2",
        "status": "DRAFT",
        "proposal_type": "REVIEW_MARGIN",
        "decision_recorded_at": "2026-08-29T12:30:00+00:00",
        "profit_per_unit": 20.0,
        "margin_percent": 15.0,
        "sales_observed_at": "2026-08-29T12:55:00+00:00",
        "stock_observed_at": "2026-08-29T12:55:00+00:00",
        "unit_economics_observed_at": "2026-08-29T12:55:00+00:00",
    }

    request = _service().build_refresh_request(draft)

    assert request["target_count"] == 1
    assert request["targets"][0]["component"] == "unit_economics"
    assert request["targets"][0]["action"] == "SOURCE_TIMESTAMP_REQUIRED"
