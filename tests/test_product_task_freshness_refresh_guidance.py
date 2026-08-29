from datetime import datetime, timezone

from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)
from app.services.product_task_draft_readiness_service import (
    ProductTaskDraftReadinessService,
)
from app.telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


class _ButtonHandler:
    def __init__(self, result):
        self.result = result

    def handle(self, callback, user_id=None):
        return self.result


class _KeyboardService:
    def build_main_keyboard(self):
        return []


def _readiness():
    return ProductTaskDraftReadinessService(
        freshness_service=ProductTaskDraftFreshnessService(
            max_snapshot_age_seconds=3600,
            clock=lambda: NOW,
        )
    )


def _draft(**values):
    result = {
        "draft_id": "d1",
        "status": "DRAFT",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "2026-08-29T11:30:00+00:00",
        "current_stock": 10,
        "sales_velocity": 1.0,
        "days_of_stock": 10.0,
    }
    result.update(values)
    return result


def test_observed_only_unknown_requires_source_timestamp():
    result = _readiness().evaluate(
        _draft(
            sales_observed_at="2026-08-29T11:55:00+00:00",
            stock_observed_at="2026-08-29T11:55:00+00:00",
        )
    )

    guidance = result["freshness_refresh_guidance"]

    assert guidance["required"] is True
    assert guidance["counts"]["SOURCE_TIMESTAMP_REQUIRED"] == 2
    assert {
        item["component"] for item in guidance["targets"]
    } == {"sales", "stock"}
    assert all(
        item["action"] == "SOURCE_TIMESTAMP_REQUIRED"
        for item in guidance["targets"]
    )
    assert result["execution_ready"] is False
    assert result["executed"] is False


def test_unknown_source_timestamp_that_is_present_requires_verification():
    result = _readiness().evaluate(
        _draft(
            sales_source_recorded_at="2026-08-29T12:30:00+00:00",
            stock_source_recorded_at="2026-08-29T11:55:00+00:00",
        )
    )

    targets = result["freshness_refresh_guidance"]["targets"]
    sales = next(item for item in targets if item["component"] == "sales")

    assert sales["freshness_status"] == "UNKNOWN"
    assert sales["evidence_state"] == "SOURCE_PROVEN"
    assert sales["action"] == "VERIFY_SOURCE_TIMESTAMP"


def test_stale_source_data_requires_refresh():
    result = _readiness().evaluate(
        _draft(
            sales_source_recorded_at="2026-08-29T09:00:00+00:00",
            stock_source_recorded_at="2026-08-29T11:55:00+00:00",
        )
    )

    targets = result["freshness_refresh_guidance"]["targets"]
    sales = next(item for item in targets if item["component"] == "sales")

    assert sales["freshness_status"] == "STALE"
    assert sales["action"] == "REFRESH_SOURCE_DATA"
    assert result["review_ready"] is False


def test_summary_aggregates_refresh_actions():
    summary = _readiness().summarize([
        _draft(
            draft_id="d1",
            sales_observed_at="2026-08-29T11:55:00+00:00",
            stock_source_recorded_at="2026-08-29T11:55:00+00:00",
        ),
        _draft(
            draft_id="d2",
            sales_source_recorded_at="2026-08-29T09:00:00+00:00",
            stock_source_recorded_at="2026-08-29T12:30:00+00:00",
        ),
    ])

    counts = summary["freshness_refresh_counts"]

    assert counts["SOURCE_TIMESTAMP_REQUIRED"] == 1
    assert counts["VERIFY_SOURCE_TIMESTAMP"] == 1
    assert counts["REFRESH_SOURCE_DATA"] == 1
    assert summary["execution_ready_count"] == 0
    assert summary["executed_count"] == 0


def test_telegram_detail_shows_guidance_without_execution_control():
    readiness = _readiness().evaluate(
        _draft(
            sales_observed_at="2026-08-29T11:55:00+00:00",
            stock_source_recorded_at="2026-08-29T09:00:00+00:00",
        )
    )
    adapter = AssistantTelegramAdapter(
        assistant=None,
        keyboard_service=_KeyboardService(),
        button_handler=_ButtonHandler({
            "error": False,
            "message": "Черновик задачи",
            "readiness": readiness,
            "executed": False,
        }),
    )

    response = adapter.handle_button("product_task_draft:view:d1")

    assert "Что требуется:" in response["message"]
    assert "Продажи: нужен достоверный timestamp источника" in response["message"]
    assert "Остатки: обновить данные из источника" in response["message"]
    assert response["executed"] is False
