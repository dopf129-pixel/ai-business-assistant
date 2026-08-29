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


def _readiness_service():
    return ProductTaskDraftReadinessService(
        freshness_service=ProductTaskDraftFreshnessService(
            clock=lambda: NOW,
        )
    )


def _adapter(result):
    return AssistantTelegramAdapter(
        assistant=None,
        keyboard_service=_KeyboardService(),
        button_handler=_ButtonHandler(result),
    )


def test_observed_only_evidence_is_visible_but_not_freshness_proof():
    readiness = _readiness_service().evaluate({
        "draft_id": "d1",
        "status": "DRAFT",
        "proposal_type": "REVIEW_REPLENISHMENT",
        "decision_recorded_at": "2026-08-29T11:55:00+00:00",
        "current_stock": 20,
        "sales_velocity": 2.0,
        "days_of_stock": 10.0,
        "sales_observed_at": "2026-08-29T11:59:00+00:00",
        "stock_observed_at": "2026-08-29T11:59:00+00:00",
    })

    coverage = readiness["freshness_coverage"]

    assert coverage["counts"] == {
        "SOURCE_PROVEN": 0,
        "OBSERVED_ONLY": 2,
        "NO_EVIDENCE": 0,
    }
    assert coverage["components"]["sales"]["evidence_state"] == (
        "OBSERVED_ONLY"
    )
    assert coverage["components"]["stock"]["evidence_state"] == (
        "OBSERVED_ONLY"
    )
    assert readiness["freshness"]["status"] == "UNKNOWN"
    assert readiness["review_ready"] is False
    assert readiness["execution_ready"] is False
    assert readiness["executed"] is False


def test_source_evidence_takes_precedence_over_observation_metadata():
    readiness = _readiness_service().evaluate({
        "draft_id": "d2",
        "status": "DRAFT",
        "proposal_type": "REVIEW_UNIT_ECONOMICS",
        "decision_recorded_at": "2026-08-29T11:55:00+00:00",
        "profit_per_unit": 30.0,
        "margin_percent": 25.0,
        "economics_basis": "CONFIRMED_RETURNS",
        "unit_economics_source_recorded_at": (
            "2026-08-29T11:50:00+00:00"
        ),
        "unit_economics_observed_at": "2026-08-29T11:59:00+00:00",
    })

    coverage = readiness["freshness_coverage"]
    component = coverage["components"]["unit_economics"]

    assert component["evidence_state"] == "SOURCE_PROVEN"
    assert coverage["source_proven_count"] == 1
    assert coverage["observed_only_count"] == 0
    assert readiness["freshness"]["status"] == "FRESH"
    assert readiness["review_ready"] is True
    assert readiness["execution_ready"] is False


def test_summary_aggregates_component_evidence_coverage():
    summary = _readiness_service().summarize([
        {
            "draft_id": "d1",
            "status": "DRAFT",
            "proposal_type": "REVIEW_REPLENISHMENT",
            "decision_recorded_at": "2026-08-29T11:55:00+00:00",
            "current_stock": 20,
            "sales_velocity": 2.0,
            "days_of_stock": 10.0,
            "sales_observed_at": "2026-08-29T11:59:00+00:00",
        },
        {
            "draft_id": "d2",
            "status": "DRAFT",
            "proposal_type": "REVIEW_MARGIN",
            "decision_recorded_at": "2026-08-29T11:55:00+00:00",
            "profit_per_unit": 30.0,
            "margin_percent": 25.0,
            "unit_economics_source_recorded_at": (
                "2026-08-29T11:50:00+00:00"
            ),
        },
    ])

    assert summary["freshness_coverage_counts"] == {
        "SOURCE_PROVEN": 1,
        "OBSERVED_ONLY": 1,
        "NO_EVIDENCE": 1,
    }
    assert summary["execution_ready_count"] == 0
    assert summary["executed_count"] == 0


def test_telegram_explains_evidence_coverage_without_execution_change():
    result = {
        "error": False,
        "message": "Черновик задачи",
        "readiness": {
            "freshness": {
                "status": "UNKNOWN",
                "decision_snapshot": {"age_seconds": 300.0},
                "reasons": ["SALES_TIMESTAMP_UNKNOWN"],
            },
            "freshness_coverage": {
                "components": {
                    "sales": {
                        "evidence_state": "OBSERVED_ONLY",
                    },
                    "stock": {
                        "evidence_state": "NO_EVIDENCE",
                    },
                }
            },
            "execution_ready": False,
            "executed": False,
        },
        "executed": False,
    }

    response = _adapter(result).handle_button(
        "product_task_draft:view:d1"
    )

    assert "Доказательства по компонентам:" in response["message"]
    assert "Продажи: есть только время наблюдения" in response["message"]
    assert "Остатки: временных доказательств нет" in response["message"]
    assert "время данных продаж неизвестно" in response["message"]
    assert response["executed"] is False
