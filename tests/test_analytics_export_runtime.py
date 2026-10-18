from services.analytics_export_service import AnalyticsExportService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_period_profit_runtime_service import AssistantPeriodProfitRuntimeService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


class _Query:
    def __init__(self):
        self.calls = 0


def _snapshot():
    return {
        "schema_version": 1,
        "periods": {"current": {"date_from": "2026-08-01", "date_to": "2026-08-31"}},
        "comparison_metrics": {},
        "profit_bridge": {},
        "sku_contribution": {},
    }


def test_period_snapshot_export_reader_is_tenant_scoped_fixed_ttl_and_copy_isolated():
    now = [100.0]
    query = _Query()
    runtime = AssistantPeriodProfitRuntimeService(query, clock=lambda: now[0])
    tenant = set_current_tenant_user_id("owner-1::ozon::store-1")
    view_id = "abcdef123456"
    key = (*runtime._report_view_scope("owner-1"), view_id)
    runtime._report_views[key] = {
        "analytics_snapshot": _snapshot(), "expires_at": 200.0, "created_at": 100.0,
    }
    try:
        first = runtime.get_analytics_snapshot_for_export(view_id, user_id="owner-1")
        first["snapshot"]["mutated"] = True
        second = runtime.get_analytics_snapshot_for_export(view_id, user_id="owner-1")
        foreign = runtime.get_analytics_snapshot_for_export(view_id, user_id="owner-2")
        now[0] = 200.0
        expired = runtime.get_analytics_snapshot_for_export(view_id, user_id="owner-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert first["error"] is False
    assert second["snapshot"] == _snapshot()
    assert foreign["error"] is False and foreign["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
    assert expired["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
    assert query.calls == 0


def test_public_period_export_callback_returns_file_from_cached_snapshot_only():
    now = [100.0]
    runtime = AssistantPeriodProfitRuntimeService(_Query(), clock=lambda: now[0])
    tenant = set_current_tenant_user_id("owner-1::ozon::store-1")
    view_id = "123456abcdef"
    key = (*runtime._report_view_scope("owner-1"), view_id)
    runtime._report_views[key] = {
        "analytics_snapshot": _snapshot(), "expires_at": 200.0, "created_at": 100.0,
    }
    handler = AssistantButtonHandlerService(
        assistant=None,
        period_profit_runtime_service=runtime,
        analytics_export_service=AnalyticsExportService(),
    )
    try:
        result = handler.handle(
            "period_profit_export:json:" + view_id, user_id="owner-1"
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["error"] is False
    assert result["document_kind"] == "analytics_export"
    assert result["export_kind"] == "period_profit"
    assert runtime.query_service.calls == 0
