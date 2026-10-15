from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


class _Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class _Query:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def query(self, **_kwargs):
        self.calls += 1
        return deepcopy(self.result)


def _metric(delta, unit="RUB", current=1500, previous=1000):
    return {
        "unit": unit,
        "current_value": current,
        "current_status": "CONFIRMED",
        "previous_value": previous,
        "previous_status": "CONFIRMED",
        "comparison_status": "COMPARABLE",
        "delta": delta,
        "delta_unit": unit,
    }


def _result():
    summary = {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "revenue": 10000.0,
        "discount_points": 2000.0,
        "revenue_tax_base": 8000.0,
        "net_accrual": 5000.0,
        "product_cost": 2000.0,
        "tax": 500.0,
        "profit": 2500.0,
        "margin_percent": 25.0,
        "units_sold": 10,
        "return_cogs_profit_applied": False,
        "return_cogs_profit_tax_recomputed": False,
    }
    return {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "request": {
            "status": "PERIOD_PROFIT_REQUEST_READY",
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
        },
        "summary": summary,
        "coverage": {"coverage_status": "PARTIAL"},
        "comparison_status": "PERIOD_PROFIT_COMPARISON_READY",
        "comparison_contract": {
            "generated_at": "2026-09-01T10:30:00+00:00",
            "current": {"period": {"date_from": "2026-08-01", "date_to": "2026-08-31"}},
            "previous": {"period": {"date_from": "2026-07-01", "date_to": "2026-07-31"}},
            "profit_bases": {"B": {"status": "CONFIRMED"}},
            "profit_compatibility": {"reason_codes": []},
        },
        "comparison_metrics": {
            "metrics": {
                "revenue": _metric(500),
                "net_accrual": _metric(250),
                "product_cost": _metric(100),
                "tax": _metric(50),
                "profit": _metric(100, current=2500, previous=2400),
                "margin_percent": {
                    **_metric(2.0, "PERCENT", current=25.0, previous=23.0),
                    "delta_unit": "PERCENTAGE_POINT",
                },
                "external_expenses": _metric(0),
                "profit_after_external_expenses": _metric(100),
                "units_sold": _metric(2, "UNIT", current=10, previous=8),
            }
        },
        "profit_bridge": {
            "status": "PERIOD_PROFIT_COMPARISON_BRIDGE_READY",
            "B": {
                "status": "CONFIRMED",
                "authoritative_delta": 100.0,
                "contributions": {
                    "net_accrual_change": 250.0,
                    "product_cost_contribution": -100.0,
                    "return_cogs_contribution": 0.0,
                    "tax_contribution": -50.0,
                    "rounding_adjustment": 0.0,
                },
                "net_accrual_detail": {
                    "status": "CONFIRMED",
                    "revenue_change": 500.0,
                    "other_net_accrual_change": -250.0,
                },
            },
            "E": {"status": "UNAVAILABLE"},
        },
        "sku_contribution": {
            "status": "PERIOD_PROFIT_SKU_CONTRIBUTION_PARTIAL",
            "coverage_status": "PARTIAL",
            "store_profit_delta": 100.0,
            "matched_sku_profit_delta": 70.0,
            "store_minus_sku_delta": 30.0,
            "matched_sku_count": 1,
            "unmatched_current_count": 1,
            "unmatched_previous_count": 0,
            "unmatched_rows_are_zero": False,
            "top_growth": [
                {"sku": "sku-1", "delta": 70.0, "previous_sku": "sku-old", "current_sku": "sku-1"}
            ],
            "top_decline": [],
        },
        "return_cogs_recovery_evidence": {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
            "candidate_records": [],
            "candidate_recovery_units": 0,
            "compensated_records": [],
            "compensated_units": 0,
            "unresolved_units": 0,
            "customer_return_units": 0,
            "unresolved_records": [],
            "return_sample_complete": True,
            "historical_cost_basis_confirmed": False,
            "historical_cost_candidate_record_count": 0,
            "historical_cost_matched_candidate_record_count": 0,
            "candidate_value_at_historical_cost": None,
            "accounting_attribution_evidence_status": "NOT_CONFIRMED",
            "accounting_attribution_evidence_confirmed": False,
            "return_cogs_accounting_recognition_status": "NOT_CONFIRMED",
            "return_cogs_accounting_recognition_evidence_confirmed": False,
            "return_cogs_profit_application_eligibility_status": "NOT_CONFIRMED",
            "return_cogs_profit_application_eligible": False,
            "return_cogs_profit_applied": False,
            "return_cogs_profit_application_amount": None,
            "return_cogs_profit_tax_recomputed": False,
            "read_only": True,
            "executed": False,
        },
    }


def _callback(keyboard, label):
    return next(button["callback"] for button in keyboard["buttons"] if button["text"] == label)


def _utf16_units(text):
    return len(text.encode("utf-16-le")) // 2


def test_period_profit_analytics_views_are_cached_scoped_and_make_no_new_query():
    query = _Query(_result())
    clock = _Clock()
    keyboard = AssistantKeyboardService()
    runtime = AssistantPeriodProfitRuntimeService(query, keyboard_service=keyboard, clock=clock)
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=keyboard,
        period_profit_runtime_service=runtime,
    )
    tenant_token = set_current_tenant_user_id("owner-1::ozon::store-1")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="owner-1")
        report_id = report["report_view_id"]
        assert report["status"] == "PERIOD_PROFIT_QUERY_READY"
        assert len(report_id) == 12
        assert set(button["text"] for button in report["keyboard"]["buttons"]) == {
            "📊 Аналитика периода",
            "🔎 Полнота данных",
        }

        analytics = handler.handle(
            _callback(report["keyboard"], "📊 Аналитика периода"), user_id="owner-1"
        )
        assert analytics["status"] == "PERIOD_PROFIT_ANALYTICS_READY"
        assert "01.08.2026 — 31.08.2026" in analytics["text"]
        assert "01.07.2026 — 31.07.2026" in analytics["text"]
        assert "+100.00 ₽" in analytics["text"]
        assert "Три главных подтверждённых вклада:" in analytics["text"]
        assert len([
            line for line in analytics["text"].splitlines()
            if line.startswith("• ")
        ]) == 3

        details = []
        for label in ("📅 Сравнение периодов", "🧾 Что изменило прибыль", "🛍 Вклад товаров"):
            callback = _callback(analytics["keyboard"], label)
            assert len(callback.encode("utf-8")) <= 64
            details.append(handler.handle(callback, user_id="owner-1"))
        assert details[0]["status"] == "PERIOD_PROFIT_COMPARISON_VIEW_READY"
        assert "Маржа" in details[0]["text"]
        assert "+2.00 п.п." in details[0]["text"]
        assert details[1]["status"] == "PERIOD_PROFIT_BRIDGE_VIEW_READY"
        assert "Выручка внутри начислений" in details[1]["text"]
        assert details[2]["status"] == "PERIOD_PROFIT_SKU_CONTRIBUTION_VIEW_READY"
        assert "Арифметический остаток магазина: +30.00 ₽" in details[2]["text"]
        assert "Отсутствующие строки не объявлены нулём" in details[2]["text"]
        assert _callback(details[2]["keyboard"], "🔎 Выбрать товар") == "period_profit_sku"
        for view in [analytics, *details]:
            assert _utf16_units(view["text"]) <= 3500
            assert view["read_only"] is True
            assert view["executed"] is False
        assert query.calls == 1
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_snapshot_ttl_is_fixed_owner_store_scoped_and_does_not_refresh_on_read():
    query = _Query(_result())
    clock = _Clock()
    runtime = AssistantPeriodProfitRuntimeService(
        query, keyboard_service=AssistantKeyboardService(), clock=clock
    )
    tenant_token = set_current_tenant_user_id("store-A")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="owner-1")
        callback = "period_profit_analytics:" + report["report_view_id"]
        clock.value += 590
        assert runtime.handle_cached_view(callback, user_id="owner-1")["status"] == "PERIOD_PROFIT_ANALYTICS_READY"
        clock.value += 11
        assert runtime.handle_cached_view(callback, user_id="owner-1")["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        assert query.calls == 1

        fresh = runtime.handle_text("прибыль за 28 дней", user_id="owner-1")
        callback = "period_profit_analytics:" + fresh["report_view_id"]
        assert runtime.handle_cached_view(callback, user_id="owner-2")["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        reset_current_tenant_user_id(tenant_token)
        tenant_token = set_current_tenant_user_id("store-B")
        assert runtime.handle_cached_view(callback, user_id="owner-1")["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        assert query.calls == 2
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_report_without_exact_tenant_does_not_create_a_user_only_snapshot():
    query = _Query(_result())
    runtime = AssistantPeriodProfitRuntimeService(query, keyboard_service=AssistantKeyboardService())
    report = runtime.handle_text("прибыль за 28 дней", user_id="owner-1")

    assert report["status"] == "PERIOD_PROFIT_QUERY_READY"
    assert "report_view_id" not in report
    assert "keyboard" not in report


def test_analytics_snapshot_is_compact_and_sku_labels_cannot_inject_long_text():
    result = _result()
    result["sku_contribution"]["top_growth"] = [
        {
            "sku": "😀Товар\nПоддельная строка " + ("X" * 10000),
            "offer_id": "offer-1",
            "delta": 70.0,
            "status": "CONFIRMED",
            "internal_debug_payload": {"must_not_be_cached": True},
        }
    ]
    result["profit_bridge"]["B"]["internal_debug_payload"] = "must_not_be_cached"
    query = _Query(result)
    runtime = AssistantPeriodProfitRuntimeService(
        query,
        keyboard_service=AssistantKeyboardService(),
        clock=_Clock(),
    )
    tenant_token = set_current_tenant_user_id("owner-1::ozon::store-1")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="owner-1")
        snapshot = next(iter(runtime._report_views.values()))["analytics_snapshot"]
        analytics = runtime.handle_cached_view(
            "period_profit_analytics:" + report["report_view_id"],
            user_id="owner-1",
        )
        sku_view = runtime.handle_cached_view(
            "period_profit_sku_contribution:" + report["report_view_id"],
            user_id="owner-1",
        )
        serialized_snapshot = repr(snapshot)

        assert "products" not in snapshot
        assert "return_cogs_recovery_evidence" not in snapshot
        assert "internal_debug_payload" not in serialized_snapshot
        assert len(snapshot["sku_contribution"]["top_growth"]) <= 5
        assert len(snapshot["sku_contribution"]["top_growth"][0]["sku"]) <= 80
        sku_line = next(line for line in sku_view["text"].splitlines() if line.startswith("• 😀Товар"))
        assert "Товар Поддельная строка" in sku_line
        assert len(sku_line) < 160
        assert _utf16_units(sku_view["text"]) <= 3500
        assert _utf16_units(analytics["text"]) <= 3500
        assert query.calls == 1
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_analytics_menu_does_not_claim_unavailable_bridge_contributions():
    result = _result()
    result["profit_bridge"]["B"] = {"status": "UNAVAILABLE"}
    runtime = AssistantPeriodProfitRuntimeService(
        _Query(result),
        keyboard_service=AssistantKeyboardService(),
        clock=_Clock(),
    )
    tenant_token = set_current_tenant_user_id("owner-1::ozon::store-1")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="owner-1")
        analytics = runtime.handle_cached_view(
            "period_profit_analytics:" + report["report_view_id"],
            user_id="owner-1",
        )

        assert "Денежный мост пока не подтверждён." in analytics["text"]
        assert "вкладов, объясняющих" not in analytics["text"].lower()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_production_factory_routes_period_analytics_without_requery(
    monkeypatch, tmp_path
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    monkeypatch.chdir(tmp_path)
    from telegram_assistant_factory import create_telegram_assistant

    runner = create_telegram_assistant()
    runtime = runner.period_profit_runtime_service
    query = _Query(_result())
    runtime.query_service = query
    tenant_token = set_current_tenant_user_id("seller-a")
    try:
        report = runtime.handle_text("прибыль за 28 дней", user_id="seller-a")
        analytics = runner.button_handler.handle(
            _callback(report["keyboard"], "📊 Аналитика периода"),
            user_id="seller-a",
        )

        assert analytics["status"] == "PERIOD_PROFIT_ANALYTICS_READY"
        assert runner.button_handler.period_profit_runtime_service is runtime
        assert runtime.keyboard_service is runner.button_handler.keyboard_service
        assert query.calls == 1
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_cached_read_and_eviction_are_atomic_and_cache_stays_bounded(monkeypatch):
    query = _Query(_result())
    runtime = AssistantPeriodProfitRuntimeService(
        query,
        keyboard_service=AssistantKeyboardService(),
        clock=_Clock(),
    )
    tenant_token = set_current_tenant_user_id("store-A")
    try:
        original = runtime.handle_text("прибыль за 28 дней", user_id="owner-1")
        original_callback = "period_profit_analytics:" + original["report_view_id"]
    finally:
        reset_current_tenant_user_id(tenant_token)

    from services import assistant_period_profit_runtime_service as runtime_module

    copy_entered = Event()
    release_copy = Event()
    writer_started = Event()
    real_deepcopy = runtime_module.deepcopy

    def pause_cached_copy(value):
        if isinstance(value, dict) and "analytics_snapshot" in value:
            copy_entered.set()
            assert release_copy.wait(timeout=5)
        return real_deepcopy(value)

    monkeypatch.setattr(runtime_module, "deepcopy", pause_cached_copy)
    latest_report = []
    outcomes = []

    def read_once():
        token = set_current_tenant_user_id("store-A")
        try:
            outcomes.append(runtime.handle_cached_view(
                original_callback, user_id="owner-1"
            )["status"])
        finally:
            reset_current_tenant_user_id(token)

    def evict_reports():
        token = set_current_tenant_user_id("store-A")
        try:
            writer_started.set()
            for _ in range(runtime.REPORT_VIEW_CACHE_MAX):
                result = runtime.handle_text(
                    "прибыль за 28 дней", user_id="owner-1"
                )
                latest_report[:] = [result]
        finally:
            reset_current_tenant_user_id(token)

    with ThreadPoolExecutor(max_workers=2) as executor:
        reader = executor.submit(read_once)
        assert copy_entered.wait(timeout=5)
        writer = executor.submit(evict_reports)
        assert writer_started.wait(timeout=5)
        release_copy.set()
        reader.result()
        writer.result()

    assert outcomes == ["PERIOD_PROFIT_ANALYTICS_READY"]
    assert len(runtime._report_views) == runtime.REPORT_VIEW_CACHE_MAX == 64
    token = set_current_tenant_user_id("store-A")
    try:
        assert runtime.handle_cached_view(
            original_callback, user_id="owner-1"
        )["status"] == "PERIOD_PROFIT_CACHED_VIEW_EXPIRED"
        latest_callback = "period_profit_analytics:" + latest_report[0]["report_view_id"]
        assert runtime.handle_cached_view(
            latest_callback, user_id="owner-1"
        )["status"] == "PERIOD_PROFIT_ANALYTICS_READY"
    finally:
        reset_current_tenant_user_id(token)
    assert query.calls == runtime.REPORT_VIEW_CACHE_MAX + 1


