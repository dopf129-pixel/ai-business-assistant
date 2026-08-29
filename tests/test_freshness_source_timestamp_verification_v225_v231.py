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
        "decision_recorded_at": "2026-08-29T11:50:00+00:00",
        "current_stock": 10,
        "sales_velocity": 1.0,
        "days_of_stock": 10.0,
    }
    result.update(values)
    return result


class _ButtonHandler:
    def __init__(self, result):
        self.result = result

    def handle(self, callback, user_id=None):
        return self.result


class _KeyboardService:
    def build_main_keyboard(self):
        return []


def _adapter(result):
    return AssistantTelegramAdapter(
        assistant=None,
        keyboard_service=_KeyboardService(),
        button_handler=_ButtonHandler(result),
    )


def test_v225_fresh_source_timestamp_is_verified():
    result = _readiness().evaluate(_draft(
        sales_source_recorded_at="2026-08-29T11:55:00+00:00",
        stock_source_recorded_at="2026-08-29T11:55:00+00:00",
    ))

    coverage = result["freshness_coverage"]
    assert coverage["components"]["sales"]["source_timestamp_state"] == (
        "VERIFIED"
    )
    assert coverage["components"]["stock"]["source_timestamp_state"] == (
        "VERIFIED"
    )
    assert coverage["source_timestamp_counts"] == {
        "VERIFIED": 2,
        "UNVERIFIED": 0,
        "ABSENT": 0,
    }
    assert result["execution_ready"] is False
    assert result["executed"] is False


def test_v226_stale_but_parseable_source_timestamp_is_verified():
    result = _readiness().evaluate(_draft(
        sales_source_recorded_at="2026-08-29T09:00:00+00:00",
        stock_source_recorded_at="2026-08-29T11:55:00+00:00",
    ))

    sales = result["freshness_coverage"]["components"]["sales"]
    assert sales["freshness_status"] == "STALE"
    assert sales["source_timestamp_state"] == "VERIFIED"
    guidance = result["freshness_refresh_guidance"]["targets"]
    sales_target = next(
        item for item in guidance if item["component"] == "sales"
    )
    assert sales_target["action"] == "REFRESH_SOURCE_DATA"


def test_v227_future_source_timestamp_is_unverified():
    result = _readiness().evaluate(_draft(
        sales_source_recorded_at="2026-08-29T12:30:00+00:00",
        stock_source_recorded_at="2026-08-29T11:55:00+00:00",
    ))

    sales = result["freshness_coverage"]["components"]["sales"]
    assert sales["freshness_status"] == "UNKNOWN"
    assert sales["evidence_state"] == "SOURCE_PROVEN"
    assert sales["source_timestamp_state"] == "UNVERIFIED"

    sales_target = next(
        item
        for item in result["freshness_refresh_guidance"]["targets"]
        if item["component"] == "sales"
    )
    assert sales_target["action"] == "VERIFY_SOURCE_TIMESTAMP"


def test_v227_malformed_source_timestamp_is_unverified():
    result = _readiness().evaluate(_draft(
        sales_source_recorded_at="not-a-timestamp",
        stock_source_recorded_at="2026-08-29T11:55:00+00:00",
    ))

    sales = result["freshness_coverage"]["components"]["sales"]
    assert sales["freshness_status"] == "UNKNOWN"
    assert sales["source_timestamp_state"] == "UNVERIFIED"


def test_v228_observed_only_has_absent_source_timestamp_state():
    result = _readiness().evaluate(_draft(
        sales_observed_at="2026-08-29T11:59:00+00:00",
        stock_observed_at="2026-08-29T11:59:00+00:00",
    ))

    coverage = result["freshness_coverage"]
    assert coverage["components"]["sales"]["evidence_state"] == (
        "OBSERVED_ONLY"
    )
    assert coverage["components"]["sales"]["source_timestamp_state"] == (
        "ABSENT"
    )
    assert coverage["source_timestamp_counts"] == {
        "VERIFIED": 0,
        "UNVERIFIED": 0,
        "ABSENT": 2,
    }


def test_v230_summary_aggregates_timestamp_verification_counts():
    summary = _readiness().summarize([
        _draft(
            draft_id="d1",
            sales_source_recorded_at="2026-08-29T11:55:00+00:00",
            stock_source_recorded_at="2026-08-29T11:55:00+00:00",
        ),
        _draft(
            draft_id="d2",
            sales_source_recorded_at="not-a-timestamp",
            stock_observed_at="2026-08-29T11:59:00+00:00",
        ),
    ])

    assert summary["freshness_source_timestamp_counts"] == {
        "VERIFIED": 2,
        "UNVERIFIED": 1,
        "ABSENT": 1,
    }
    assert summary["execution_ready_count"] == 0
    assert summary["executed_count"] == 0


def test_v231_telegram_distinguishes_verified_and_unverified_source_fields():
    verified = _readiness().evaluate(_draft(
        sales_source_recorded_at="2026-08-29T11:55:00+00:00",
        stock_source_recorded_at="2026-08-29T11:55:00+00:00",
    ))
    response = _adapter({
        "error": False,
        "message": "Черновик",
        "readiness": verified,
        "executed": False,
    }).handle_button("product_task_draft:view:d1")

    assert "Продажи: timestamp источника проверен" in response["message"]
    assert response["executed"] is False

    unverified = _readiness().evaluate(_draft(
        sales_source_recorded_at="not-a-timestamp",
        stock_source_recorded_at="2026-08-29T11:55:00+00:00",
    ))
    response = _adapter({
        "error": False,
        "message": "Черновик",
        "readiness": unverified,
        "executed": False,
    }).handle_button("product_task_draft:view:d1")

    assert (
        "Продажи: timestamp источника требует проверки"
        in response["message"]
    )
    assert response["executed"] is False
