from period_profit_mapping_observability_response import (
    build_period_profit_mapping_observability_response,
)
from period_profit_response import build_period_profit_response
from services.period_profit_mapping_observability_service import (
    PeriodProfitMappingObservabilityService,
)


class Registry:
    def health(self):
        return {
            "health_status": "HEALTHY",
            "schema_version": 1,
            "load_allowed": True,
            "writable": True,
            "issues": [],
            "fail_closed": True,
            "scopes": {
                "RETURN": {
                    "active_revision_id": "return-mapping-r1",
                    "latest_revision_id": "return-mapping-r2",
                    "revision_count": 2,
                    "active_revision_stale": True,
                    "active_mapping_loadable": True,
                },
                "ADVERTISING": {
                    "active_revision_id": "advertising-mapping-r1",
                    "latest_revision_id": "advertising-mapping-r1",
                    "revision_count": 1,
                    "active_revision_stale": False,
                    "active_mapping_loadable": True,
                },
                "STORAGE": {
                    "active_revision_id": None,
                    "latest_revision_id": None,
                    "revision_count": 0,
                    "active_revision_stale": False,
                    "active_mapping_loadable": False,
                },
            },
        }

    def history(self, scope):
        events = []
        if scope == "RETURN":
            events = [{"event": "ACTIVATE", "revision_id": "return-mapping-r1"}]
        return {
            "status": "PERIOD_PROFIT_MAPPING_HISTORY_READY",
            "scope": scope,
            "active_revision_id": self.health()["scopes"][scope]["active_revision_id"],
            "events": events,
        }


def _summary():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-08-01",
        "date_to": "2026-08-07",
        "revenue": 1000,
        "net_accrual": 800,
        "product_cost": 300,
        "tax": 60,
        "profit": 440,
        "margin_percent": 44,
        "fee_components_included": False,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
    }


def test_snapshot_reports_stale_and_loadable_scopes():
    result = PeriodProfitMappingObservabilityService(Registry()).snapshot()
    assert result["stale_scopes"] == ["RETURN"]
    assert result["loadable_scopes"] == ["ADVERTISING", "RETURN"]
    assert result["stale_mapping_warning_required"] is True


def test_audit_summary_is_read_only():
    result = PeriodProfitMappingObservabilityService(Registry()).audit_summary()
    assert result["total_event_count"] == 1
    assert result["read_only"] is True
    assert result["executed"] is False


def test_readiness_warns_on_stale_but_does_not_block_healthy_registry():
    result = PeriodProfitMappingObservabilityService(Registry()).production_readiness()
    assert result["ready"] is True
    assert result["warnings"] == ["STALE_ACTIVE_MAPPING:RETURN"]
    assert result["blocking_issues"] == []
    assert result["profit_adjustment_allowed"] is False


def test_period_profit_response_shows_stale_warning_without_profit_change():
    snapshot = PeriodProfitMappingObservabilityService(Registry()).snapshot()
    result = build_period_profit_response(_summary(), mapping_observability=snapshot)
    assert "Активные mapping revisions не являются последними для: RETURN" in result["text"]
    assert "Прибыль: 440.00 ₽" in result["text"]
    assert "формула прибыли не изменяется" in result["text"]


def test_observability_response_includes_audit_and_readiness():
    service = PeriodProfitMappingObservabilityService(Registry())
    result = build_period_profit_mapping_observability_response(
        service.snapshot(), service.audit_summary(), service.production_readiness()
    )
    assert "Production readiness: READY" in result["text"]
    assert "Audit events: 1" in result["text"]
    assert result["ozon_mutation"] is False
