from datetime import datetime, timedelta, timezone

from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.seller_attention_summary_service import SellerAttentionSummaryService
from services.tenant_context import (
    get_current_tenant_user_id,
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
FRESH = NOW.isoformat().replace("+00:00", "Z")


class Query:
    def __init__(self, decisions):
        self.decisions = decisions
        self.calls = 0

    def query_all(self):
        self.calls += 1
        return {
            "error": False,
            "total": len(self.decisions),
            "decisions": self.decisions,
        }

    def query_catalog_group(self, offset=0, limit=20):
        rows = []
        for index, decision in enumerate(self.decisions):
            sku = decision["sku"]
            rows.append({
                "selector": sku,
                "identity": {
                    "product_id": str(decision.get("product_id") or index + 1),
                    "offer_id": str(decision.get("offer_id") or sku),
                    "catalog_sku": sku,
                },
                "status": "READY" if not decision.get("error") else "SOURCE_UNAVAILABLE",
                "code": decision.get("code"),
                "decision": decision,
            })
        selected = rows[offset : offset + limit]
        return {
            "error": False,
            "rows": selected,
            "selection_scope": {
                "mode": "FIRST_SORTED_CATALOG_GROUP",
                "sort_by": "offer_id_then_catalog_sku",
                "selected_count": len(selected),
                "catalog_identity_count": len(rows),
                "offset": offset,
                "has_previous_group": offset > 0,
                "has_next_group": offset + len(selected) < len(rows),
                "limit": limit,
            },
        }


def _decision(
    sku,
    decision_type="REPLENISH_HIGH_PRIORITY",
    priority="CRITICAL",
    reasons=None,
    missing_data=None,
    **overrides,
):
    value = {
        "error": False,
        "sku": sku,
        "decision_type": decision_type,
        "priority": priority,
        "reasons": reasons or ["DAYS_OF_STOCK_CRITICAL", "POSITIVE_UNIT_PROFIT"],
        "missing_data": missing_data or [],
        "current_stock": 4,
        "days_of_stock": 2.0,
        "stock_priority": "CRITICAL",
        "decision_profit_per_unit": 50.0,
        "decision_margin_percent": 12.5,
        "sales_observed_at": FRESH,
        "stock_observed_at": FRESH,
        "unit_economics_observed_at": FRESH,
    }
    value.update(overrides)
    return value


def _service(decisions, **overrides):
    query = Query(decisions)
    service = SellerAttentionSummaryService(
        query,
        keyboard_service=AssistantKeyboardService(),
        clock=lambda: NOW,
        **overrides,
    )
    return service, query


def test_summary_orders_existing_priorities_and_includes_evidence_and_links():
    service, _query = _service([
        _decision("SKU-B"),
        _decision(
            "SKU-A",
            reasons=["NEGATIVE_UNIT_PROFIT", "DAYS_OF_STOCK_CRITICAL"],
            decision_profit_per_unit=-10.0,
            decision_margin_percent=-2.0,
        ),
        _decision(
            "SKU-C",
            decision_type="HOLD_STOCK",
            priority="LOW",
            reasons=["POSITIVE_UNIT_PROFIT"],
            stock_priority="NO_SALES",
            sales_velocity=0,
        ),
    ])

    result = service.build(user_id="telegram-1")

    assert result["status"] == "SELLER_ATTENTION_SUMMARY_READY"
    assert result["priority_count"] == 3
    assert result["message"].index("SKU-A") < result["message"].index("SKU-B")
    assert "Приоритет: Критический" in result["message"]
    assert "CRITICAL" not in result["message"]
    assert "отрицательная прибыль с единицы" in result["message"]
    assert "остаток 4 шт." in result["message"]
    assert "есть остаток, продаж в периоде нет" in result["message"]
    assert "не рассчитываются без подтверждённых расходов" in result["message"]
    callbacks = [button["callback"] for button in result["keyboard"]["buttons"]]
    assert "product_decision:SKU-A" in callbacks
    assert "product_decision:SKU-C" in callbacks
    assert "period_profit" in callbacks
    assert result["read_only"] is True
    assert result["executed"] is False


def test_stale_or_unknown_sources_are_moved_to_needs_data_not_current_risks():
    stale = (NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    service, _query = _service([
        _decision("SKU-STALE", sales_source_recorded_at=stale),
        _decision(
            "SKU-UNKNOWN",
            sales_observed_at=None,
            stock_observed_at=None,
            unit_economics_observed_at=None,
        ),
        _decision(
            "SKU-MISSING",
            decision_type="INSUFFICIENT_DATA",
            priority="NONE",
            reasons=["ECONOMICS_INCOMPLETE"],
            missing_data=["cost", "advertising", "returns"],
            current_stock=None,
            days_of_stock=None,
            stock_priority=None,
            decision_profit_per_unit=None,
            decision_margin_percent=None,
            sales_observed_at=None,
            stock_observed_at=None,
            unit_economics_observed_at=None,
        ),
    ])

    result = service.build(user_id="telegram-1")

    assert result["priority_count"] == 0
    assert result["missing_data_count"] == 3
    assert "данные старше одного часа" in result["message"]
    assert "время источника неизвестно" in result["message"]
    assert "себестоимость" in result["message"]
    assert "реклама" in result["message"]
    assert "возвраты" in result["message"]
    assert "подтверждённых актуальных приоритетов" in result["message"]


def test_summary_caps_priorities_at_five_and_aggregates_the_rest():
    decisions = [_decision("SKU-" + str(index)) for index in range(7)]
    service, _query = _service(decisions)

    result = service.build(user_id="telegram-1")

    assert result["priority_count"] == 5
    assert "первые 5 из 7 приоритетов" in result["message"]
    assert len([
        button for button in result["keyboard"]["buttons"]
        if button["callback"].startswith("product_decision:")
    ]) == 5


def test_summary_accepts_unicode_sku_values_and_keeps_telegram_callbacks_bounded():
    service, _query = _service([
        _decision("offer.①/товар"),
        _decision("x" * 60),
    ])

    result = service.build(user_id="telegram-1")

    assert result["status"] == "SELLER_ATTENTION_SUMMARY_READY"
    assert "offer.①/товар" in result["message"]
    assert ("product_decision:offer.①/товар" in [
        button["callback"] for button in result["keyboard"]["buttons"]
    ])
    assert all(
        len(button["callback"].encode("utf-8")) <= 64
        for button in result["keyboard"]["buttons"]
    )


def test_long_summary_uses_compact_telegram_safe_message():
    decisions = []
    for index in range(8):
        sku = str(index) + ("😀" * 127)
        if index < 5:
            decisions.append(_decision(sku, missing_data=[
                "advertising", "storage", "returns", "returns_finance",
                "tax", "cost", "profit_per_unit", "margin_percent",
                "sales_velocity", "sales_trend", "current_stock",
                "days_of_stock", "stock_priority", "unit_economics",
                "decision", "external_expenses",
            ]))
        else:
            decisions.append(_decision(
                sku,
                decision_type="INSUFFICIENT_DATA",
                priority="NONE",
                reasons=["ECONOMICS_INCOMPLETE"],
                missing_data=[
                    "advertising", "storage", "returns", "returns_finance",
                    "tax", "cost", "profit_per_unit", "margin_percent",
                    "sales_velocity", "sales_trend", "current_stock",
                    "days_of_stock", "stock_priority", "unit_economics",
                    "decision", "external_expenses",
                ],
                current_stock=None,
                days_of_stock=None,
                stock_priority=None,
                decision_profit_per_unit=None,
                decision_margin_percent=None,
                sales_observed_at=None,
                stock_observed_at=None,
                unit_economics_observed_at=None,
            ))
    service, _query = _service(decisions)

    result = service.build(user_id="telegram-1")

    assert result["status"] == "SELLER_ATTENTION_SUMMARY_READY"
    assert "Короткий формат" in result["message"]
    assert "ДРР/ROAS не рассчитываются" in result["message"]
    assert "Return COGS" in result["message"]
    assert service._utf16_units(result["message"]) <= 3500


def test_button_handler_reuses_bounded_summary_and_scopes_it_by_user_and_store():
    service, query = _service([_decision("SKU-1")])
    keyboard = AssistantKeyboardService()
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=keyboard,
        seller_attention_summary_service=service,
    )
    token = set_current_tenant_user_id("store-A")
    try:
        first = handler.handle("seller_attention", user_id="telegram-1")
        second = handler.handle("seller_attention", user_id="telegram-1")
        other_user = handler.handle("seller_attention", user_id="telegram-2")

        assert first["message"] == second["message"]
        assert other_user["status"] == "SELLER_ATTENTION_SUMMARY_READY"
        assert query.calls == 2
    finally:
        reset_current_tenant_user_id(token)


def test_summary_cache_is_isolated_by_store_for_the_same_telegram_user():
    class StoreQuery:
        def __init__(self):
            self.calls = 0

        def query_all(self):
            self.calls += 1
            sku = "SKU-A" if get_current_tenant_user_id() == "store-A" else "SKU-B"
            return {"error": False, "total": 1, "decisions": [_decision(sku)]}

    query = StoreQuery()
    service = SellerAttentionSummaryService(query, clock=lambda: NOW)
    store_a = set_current_tenant_user_id("store-A")
    try:
        first = service.build(user_id="telegram-1")
    finally:
        reset_current_tenant_user_id(store_a)

    store_b = set_current_tenant_user_id("store-B")
    try:
        second = service.build(user_id="telegram-1")
    finally:
        reset_current_tenant_user_id(store_b)

    assert "SKU-A" in first["message"]
    assert "SKU-B" in second["message"]
    assert query.calls == 2


def test_summary_cache_is_bounded_by_configured_entry_count():
    service, query = _service([_decision("SKU-1")], cache_max_entries=1)

    service.build(user_id="telegram-1")
    service.build(user_id="telegram-2")

    assert len(service._cache) == 1
    assert query.calls == 2


def test_summary_cache_expires_when_source_freshness_deadline_passes():
    clock = [NOW]
    query = Query([_decision("SKU-1")])
    service = SellerAttentionSummaryService(query, clock=lambda: clock[0])

    first = service.build(user_id="telegram-1")
    clock[0] = NOW + timedelta(hours=1, seconds=1)
    second = service.build(user_id="telegram-1")

    assert first["priority_count"] == 1
    assert second["priority_count"] == 0
    assert "данные старше одного часа" in second["message"]
    assert query.calls == 2


def test_main_keyboard_exposes_on_demand_attention_summary():
    callbacks = {
        item["callback"]
        for item in AssistantKeyboardService().build_main_keyboard()["buttons"]
    }

    assert "seller_attention" in callbacks


def test_production_telegram_factory_wires_attention_summary_to_main_handler(monkeypatch):
    import telegram_assistant_factory as factory

    class Dummy:
        def __init__(self, *args, **kwargs):
            pass

    query = Query([_decision("SKU-1")])
    system = {
        "core": object(),
        "storage": object(),
        "context": object(),
        "task_context": object(),
        "period_profit_runtime_service": None,
    }
    monkeypatch.setattr(factory, "create_telegram_core", lambda: system)
    monkeypatch.setattr(
        factory, "create_current_unit_economics_query", lambda **_kwargs: object()
    )
    monkeypatch.setattr(factory, "create_product_decision_history", lambda: object())
    monkeypatch.setattr(
        factory, "create_product_business_decision_query", lambda **_kwargs: query
    )
    monkeypatch.setattr(
        factory, "create_product_returns_finance_impact_query", lambda **_kwargs: object()
    )
    for name in (
        "AssistantTelegramMemoryService",
        "AssistantMemoryCommandService",
        "AssistantHistoryService",
        "ProductDecisionPersistenceVerificationService",
        "ExpenseRepository",
        "TelegramExternalExpenseRuntimeService",
        "PeriodProfitEffectiveCostService",
        "PeriodProfitSkuAdvertisingService",
        "TelegramSellerCostUpdateService",
        "ProductService",
        "TelegramReturnInventoryConfirmationService",
        "ReturnInventoryRecoveryRepository",
        "TelegramOnboardingService",
        "OzonAccountService",
        "TaxConfigurationService",
        "OzonPerformanceAccountService",
        "AssistantTelegramAdapter",
        "TelegramCommandService",
        "TelegramBotService",
    ):
        monkeypatch.setattr(factory, name, Dummy)

    runner = factory.create_telegram_assistant()

    assert isinstance(runner.seller_attention_summary_service, SellerAttentionSummaryService)
    assert runner.seller_attention_summary_service.product_decision_query is query
    assert runner.product_overview_service.decision_query is query
    assert runner.product_overview_service.snapshot_store is (
        runner.scoped_transient_snapshot_store
    )
    assert runner.button_handler.product_overview_service is (
        runner.product_overview_service
    )
    tenant = set_current_tenant_user_id("owner-1::ozon::store-1")
    try:
        overview = runner.button_handler.handle(
            "product_overview", user_id="owner-1"
        )
    finally:
        reset_current_tenant_user_id(tenant)
    assert overview["error"] is False
    assert "SKU-1" in overview["message"]
    assert (
        runner.button_handler.seller_attention_summary_service
        is runner.seller_attention_summary_service
    )
