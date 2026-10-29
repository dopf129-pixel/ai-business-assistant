from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from services.ozon_account_repository import make_store_tenant_scope
from services.period_profit_operation_diagnostics import current_period_profit_trace
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


class _ProductService:
    def load_products(self):
        return [{
            "product_id": "product-q24",
            "offer_id": "offer-q24",
            "sku": "sku-q24",
            "name": "Synthetic product",
        }]


class _ScenarioSource:
    def __init__(self):
        self.product_service = _ProductService()
        self.calls = []

    def load_snapshot(self, sku, user_id, force_refresh=False):
        self.calls.append((sku, user_id, force_refresh))
        return {
            "error": False,
            "snapshot_id": "snapshot-q24",
            "identity": {
                "user_id": user_id,
                "store_id": "store-q24",
                "tenant_scope": make_store_tenant_scope(user_id, "store-q24"),
                "product_id": "product-q24",
                "offer_id": "offer-q24",
                "sku": sku,
            },
            "product": {"name": "Synthetic product", "scheme": "FBO"},
            "suggested_inputs": {
                "price": "100.00", "cost": "20.00", "commission_rate": None,
                "logistics_per_unit": "5.00", "last_mile_per_unit": "0.00",
                "acquiring_per_unit": "0.00", "advertising_rate": "16.5",
                "discount_points_rate": "0", "tax_mode": "NONE",
                "tax_rate": "0", "minimum_tax_rate": "0",
            },
            "input_provenance": {
                "price": "ozon_current_seller_price",
                "cost": "confirmed_store_cost",
                "commission_rate": "unknown",
                "logistics_per_unit": "confirmed_store_average",
                "last_mile_per_unit": "confirmed_store_average",
                "acquiring_per_unit": "confirmed_store_average",
                "advertising_rate": "manual_seller_assumption",
                "discount_points_rate": "weighted_exact_sku_finance_average_28_completed_days",
                "tax_mode": "manual_seller_assumption",
            },
            "source_periods": {
                "seller_price_as_of": datetime.now(ZoneInfo("Europe/Moscow")).isoformat(),
            },
            "source_completeness": {
                "discount_points": {"complete": True, "positive_sale_observations": 1},
            },
            "cache": {"age_seconds": 0, "ttl_seconds": 300},
        }


class _CurrentPointScenarioSource(_ScenarioSource):
    """Read-only fake exposing a confirmed current-price tariff point."""

    def load_snapshot(self, sku, user_id, force_refresh=False):
        snapshot = super().load_snapshot(sku, user_id, force_refresh)
        snapshot["suggested_inputs"]["commission_rate"] = 14.0
        snapshot["input_provenance"]["commission_rate"] = "ozon_current_fbo_rate"
        snapshot["snapshot_id"] = "0123456789abcdef"
        as_of = "2026-10-27T10:00:00+03:00"
        snapshot["source_periods"]["seller_price_as_of"] = as_of
        snapshot["source_periods"]["commission_rate_as_of"] = as_of
        snapshot["source_completeness"].update({
            "seller_price": {"complete": True},
            "commission_rate": {"complete": True},
        })
        return snapshot


class _IncompleteObservationCollector:
    """Synthetic source matching current adapters' intentionally limited contract."""

    def __init__(self):
        self.calls = []

    def collect_window(self, observation_id, *, date_from, date_to):
        self.calls.append((observation_id, date_from, date_to))
        return {
            "error": False,
            "status": "INCOMPARABLE",
            "identity": {
                "store_id": "store-q24", "product_id": "product-q24",
                "offer_id": "offer-q24", "sku": "sku-q24", "sale_schema": "FBO",
            },
            "seller_price_cents": 9_500,
            "window": {
                "from": date_from, "to": date_to,
                "timezone": "Europe/Moscow", "date_basis": "SOURCE_CALENDAR_DATE",
            },
            "sources": [
                {
                    "name": "FINANCE", "status": "COMPLETE", "complete": True,
                    "row_count": 8, "source_date_basis": "SHARED_LOCAL_SALE_DATE",
                    "source_window_start": date_from, "source_window_end": date_to,
                    "timezone": "Europe/Moscow",
                },
                {
                    "name": "PERFORMANCE", "status": "COMPLETE", "complete": True,
                    "row_count": 6, "source_date_basis": "SHARED_LOCAL_SALE_DATE",
                    "source_window_start": date_from, "source_window_end": date_to,
                    "timezone": "Europe/Moscow",
                },
            ],
            "metrics": {
                "gross_seller_revenue": "9500.00", "discount_points": "0.00",
                "discount_points_complete": True, "finance_net": "7000.00",
                "acquiring": "0.00", "commission": "-1140.00",
                "logistics": "-500.00", "other_fees": "-860.00",
                "cpc_spend": "1425.00", "source_row_count": 8,
                "sample_days": 7,
            },
            "warnings": [],
        }


class _ObservationFinance:
    def prepare_read_session(self, date_from, date_to):
        self.period = (date_from, date_to)

    def begin_read_session(self):
        return None

    def get_daily_finance(self, day, *, sku):
        reservation = current_period_profit_trace().reserve_ozon_request("q30-finance")
        if reservation["error"]:
            return {"error": True, "code": reservation["code"]}
        return {
            "error": False, "date": day, "sku": sku, "operations": 1,
            "gross_sales": "1000.00", "discount_points": "0.00",
            "net_accrual": "500.00", "commission": "-100.00",
            "logistics": "-200.00", "acquiring": "-10.00",
            "other_fees": "-190.00", "fee_components_included": True,
            "accrual_type_breakdown": {},
        }


class _ObservationAdvertising:
    def load(self, date_from, date_to, accepted_skus):
        reservation = current_period_profit_trace().reserve_ozon_request("q30-performance")
        if reservation["error"]:
            return {"error": True, "code": reservation["code"]}
        return {
            "error": False, "configured": True, "complete": True,
            "expense": "100.00", "matched_row_count": 2,
        }


class _ObservationReturns:
    def __init__(self):
        self.calls = []

    def get(self, sku, since, to):
        self.calls.append((sku, since, to))
        trace = current_period_profit_trace()
        for _ in range(2):
            reservation = trace.reserve_ozon_request("q30-returns")
            if reservation["error"]:
                return {"error": True, "code": reservation["code"]}
        incomplete = len(self.calls) == 1
        return {
            "error": False, "sku": sku, "since": since, "to": to,
            "posting_count": 5, "total_units": 5,
            "delivered_units": 4, "cancelled_units": 1,
            "ambiguous_cancelled_units": 1 if incomplete else 0,
            "customer_non_buyout_units": 0 if incomplete else 1,
            "customer_return_units": 0 if incomplete else 1, "customer_cancelled_units": 0,
            "delivery_failure_units": 0, "unknown_return_units": 1 if incomplete else 0,
            "postings_complete": True, "returns_available": True,
            "returns_complete": True,
            "postings": [
                {"posting_number": f"q30-private-{index}",
                 "status": "delivered" if index < 4 else "cancelled", "quantity": 1}
                for index in range(5)
            ],
            "return_events": [],
        }


def _button(result, label):
    return next(button for button in result["keyboard"]["buttons"] if button["text"] == label)


def test_production_factory_connects_price_planning_observation_and_next_variant(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    monkeypatch.chdir(tmp_path)

    from telegram_assistant_factory import create_telegram_assistant

    runner = create_telegram_assistant()
    handler = runner.button_handler
    calculator = runner.unit_price_calculator_runtime_service
    observation_runtime = runner.unit_price_observation_runtime_service
    assert handler.unit_price_calculator_runtime_service is calculator
    assert handler.unit_price_observation_runtime_service is observation_runtime
    assert runner.saved_planning_plan_runtime_service.unit_price_observation_runtime_service is observation_runtime
    from services.returns_buyout_facts_source import ReturnsBuyoutFactsSource
    wired_buyout_source = observation_runtime.collection_service.returns_buyout_source
    assert isinstance(wired_buyout_source, ReturnsBuyoutFactsSource)
    assert wired_buyout_source.ozon_client is calculator.source.current_economics_source.ozon_client

    source = _ScenarioSource()
    collector = _IncompleteObservationCollector()
    calculator.source = source
    observation_runtime.collection_service = collector

    user_id = "q24-owner"
    store_id = "store-q24"
    scope = make_store_tenant_scope(user_id, store_id)
    tenant = set_current_tenant_user_id(scope)
    try:
        entry = calculator.build_product_entry_button(user_id, "sku-q24")
        scenario = handler.handle(entry["callback"], user_id=user_id)
        assert scenario["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"

        tariff_prompt = handler.handle(
            _button(scenario, "Указать тариф комиссии")["callback"], user_id=user_id,
        )
        assert tariff_prompt["status"] == "UNIT_PRICE_TARIFF_INPUT"
        invalid_tariff = handler.handle_text("это не тариф", user_id=user_id)
        assert invalid_tariff["status"] == "UNIT_PRICE_TARIFF_INPUT"
        assert "Укажите комиссию Ozon" in invalid_tariff["message"]

        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        tariff_effective = today - timedelta(days=20)
        tariff_text = (
            f"Действует с: {tariff_effective.isoformat()}\n"
            "0,01–99,99 ₽ = 12%\n100–199,99 ₽ = 14%"
        )
        tariff_preview = handler.handle_text(tariff_text, user_id=user_id)
        assert tariff_preview["status"] == "UNIT_PRICE_TARIFF_PREVIEW"
        scenario = handler.handle(
            _button(tariff_preview, "✅ Сохранить для SKU")["callback"],
            user_id=user_id,
        )
        assert scenario["price_scenario"]["tariff_resolution"]["commission_rate"] == "14"

        price_prompt = handler.handle(
            _button(scenario, "Сравнить цены")["callback"], user_id=user_id,
        )
        assert price_prompt["stage"] == "price_options"
        invalid_prices = handler.handle_text("95", user_id=user_id)
        assert invalid_prices["stage"] == "price_options"
        initial_comparison = handler.handle_text("95; 100", user_id=user_id)
        assert initial_comparison["status"] == "UNIT_PRICE_PRICE_COMPARISON_RESULT"
        per_price_drr_prompt = handler.handle(
            _button(initial_comparison, "Указать ДРР для каждой цены")["callback"],
            user_id=user_id,
        )
        invalid_drr = handler.handle_text("15", user_id=user_id)
        assert invalid_drr["stage"] == "comparison_per_price_drr"
        comparison = handler.handle_text("15; 16,5", user_id=user_id)
        assert comparison["status"] == "UNIT_PRICE_PRICE_COMPARISON_RESULT"
        rows = comparison["price_planning_result"]["rows"]
        assert [row["commission_rate"] for row in rows] == ["12", "14"]
        assert all(row.get("available") is True and row.get("profit") is not None for row in rows), rows

        applied = handler.handle(
            _button(comparison, "Подставить вариант 1")["callback"], user_id=user_id,
        )
        assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
        assert applied["price_scenario"]["inputs"]["price"]["value"] == 95.0
        assert applied["price_scenario"]["inputs"]["commission_rate"]["value"] == 12.0

        save_prompt = handler.handle(
            _button(applied, "💾 Сохранить план")["callback"], user_id=user_id,
        )
        assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
        invalid_title = handler.handle_text("   ", user_id=user_id)
        assert invalid_title["status"] == "PLANNING_TITLE_INVALID"
        saved = handler.handle_text("Q24 candidate 95", user_id=user_id)
        assert saved["status"] == "PLANNING_DOCUMENT_SAVED"

        plan_list = handler.handle("upp:m", user_id=user_id)
        plan_action = next(
            button["callback"] for button in plan_list["keyboard"]["buttons"]
            if button["text"].startswith("Q24 candidate 95")
        )
        plan_detail = handler.handle(plan_action, user_id=user_id)
        observation_prompt = handler.handle(
            _button(plan_detail, "Наблюдать цену · SKU sku-q24")["callback"],
            user_id=user_id,
        )
        assert observation_prompt["status"] == "SELLER_PRICE_INPUT_REQUIRED"
        assert handler.handle_text("95", user_id=user_id)["status"] == "EFFECTIVE_TIME_INPUT_REQUIRED"
        installed_at = datetime.combine(
            tariff_effective, time(10), tzinfo=ZoneInfo("Europe/Moscow"),
        ).isoformat()
        observation_preview = handler.handle_text(installed_at, user_id=user_id)
        assert observation_preview["status"] == "OBSERVATION_START_PREVIEW"
        observation_card = handler.handle(
            _button(observation_preview, "Подтвердить наблюдение")["callback"],
            user_id=user_id,
        )
        collect_prompt = handler.handle(
            _button(observation_card, "Собрать данные за период")["callback"],
            user_id=user_id,
        )
        assert collect_prompt["status"] == "OBSERVATION_WINDOW_INPUT_REQUIRED"
        invalid_window = handler.handle_text("не даты", user_id=user_id)
        assert invalid_window["status"] == "OBSERVATION_WINDOW_INPUT_REQUIRED"
        window_end = today - timedelta(days=8)
        window_start = window_end - timedelta(days=6)
        collected = handler.handle_text(
            f"{window_start.isoformat()} - {window_end.isoformat()}", user_id=user_id,
        )
        assert collected["status"] == "OBSERVATION_CARD_READY"

        ranking = handler.handle(
            _button(collected, "Сравнить прибыль по наблюдениям SKU")["callback"],
            user_id=user_id,
        )
        assert ranking["status"] == "OBSERVATION_RANKING_NOT_READY"
        assert "Рейтинг пока не готов" in ranking["message"]
        assert "минимум 2 сопоставимых варианта" in ranking["message"]
        assert "SUCCESSFUL_UNIT_DENOMINATOR_UNCONFIRMED" not in ranking["message"]
        next_variant = _button(ranking, "Мои планы · следующий вариант цены")
        next_plan_list = handler.handle(next_variant["callback"], user_id=user_id)
        assert next_plan_list["status"] == "PLANNING_DOCUMENT_LIST"
        next_plan_action = next(
            button["callback"] for button in next_plan_list["keyboard"]["buttons"]
            if button["text"].startswith("Q24 candidate 95")
        )
        reopened_plan = handler.handle(next_plan_action, user_id=user_id)
        edit_scenario = handler.handle(
            _button(reopened_plan, "Продолжить по сохранённым допущениям")["callback"],
            user_id=user_id,
        )
        price_edit = next(
            button for button in edit_scenario["keyboard"]["buttons"]
            if button["text"] == "Цена"
        )
        handler.handle(price_edit["callback"], user_id=user_id)
        next_price_scenario = handler.handle_text("100", user_id=user_id)
        assert next_price_scenario["price_scenario"]["inputs"]["commission_rate"]["value"] == 14.0

        observations = observation_runtime.repository.list_unit_price_observations(
            owner_id=user_id, store_id=store_id,
        )
        assert len(observations["items"]) == 1
        result = observation_runtime.repository.get_unit_price_observation(
            observations["items"][0]["observation_id"], owner_id=user_id,
            store_id=store_id,
        )["result"]["payload"]
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["metrics"].get("profit_per_unit") is None
        assert source.calls == [("sku-q24", user_id, False)]
        assert len(collector.calls) == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_production_public_route_uses_confirmed_current_tariff_point_and_exports_snapshot(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    monkeypatch.chdir(tmp_path)

    from telegram_assistant_factory import create_telegram_assistant

    runner = create_telegram_assistant()
    source = _CurrentPointScenarioSource()
    runner.unit_price_calculator_runtime_service.source = source
    user_id = "q30-current-point-owner"
    store_id = "store-q24"
    tenant = set_current_tenant_user_id(make_store_tenant_scope(user_id, store_id))
    try:
        entry = runner.unit_price_calculator_runtime_service.build_product_entry_button(
            user_id, "sku-q24",
        )
        result = runner.button_handler.handle(entry["callback"], user_id=user_id)
        assert result["status"] == "UNIT_PRICE_SCENARIO_READY", (
            result["status"],
            (result.get("price_scenario") or {}).get("missing_inputs"),
            (result.get("price_scenario") or {}).get("invalid_inputs"),
            result.get("code"),
        )
        tariff = result["price_scenario"]["tariff_resolution"]
        assert tariff["status"] == "CURRENT_PRICE_POINT_ONLY"
        assert float(tariff["commission_rate"]) == 14.0
        assert source.calls == [("sku-q24", user_id, False)]

        active = runner.unit_price_calculator_runtime_service.active_scenario_identity(user_id)
        scenario_id = active["scenario_id"]
        version = active["version"]
        assumptions = runner.button_handler.handle(
            f"upc:a:{scenario_id}:{version}", user_id=user_id,
        )
        profile = runner.button_handler.handle(
            _button(assumptions, "Профиль комиссии")["callback"], user_id=user_id,
        )
        assert profile["status"] == "UNIT_PRICE_TARIFF_SNAPSHOT_READY"
        exported = runner.button_handler.handle(
            _button(profile, "Скачать JSON")["callback"], user_id=user_id,
        )
        assert exported["export_kind"] == "unit_price_tariff_profile"
        assert b"CURRENT_PRICE_POINT" in exported["file_content"]
        # Only the injected read-only snapshot source was reachable in this public route.
        assert source.calls == [("sku-q24", user_id, False)]
    finally:
        reset_current_tenant_user_id(tenant)


def test_manual_tariff_survives_store_switch_restart_and_public_export(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    monkeypatch.chdir(tmp_path)

    from telegram_assistant_factory import create_telegram_assistant

    first_runner = create_telegram_assistant()
    first_source = _ScenarioSource()
    first_runner.unit_price_calculator_runtime_service.source = first_source
    handler = first_runner.button_handler
    user_id = "q30-restart-owner"
    store_id = "store-q24"

    tenant = set_current_tenant_user_id(make_store_tenant_scope(user_id, store_id))
    try:
        entry = first_runner.unit_price_calculator_runtime_service.build_product_entry_button(
            user_id, "sku-q24",
        )
        scenario = handler.handle(entry["callback"], user_id=user_id)
        prompt = handler.handle(
            _button(scenario, "Указать тариф комиссии")["callback"], user_id=user_id,
        )
        assert prompt["status"] == "UNIT_PRICE_TARIFF_INPUT"
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        effective = (today - timedelta(days=20)).isoformat()
        preview = handler.handle_text(
            f"Действует с: {effective}\n0,01–99,99 ₽ = 12%\n100–199,99 ₽ = 14%",
            user_id=user_id,
        )
        assert preview["status"] == "UNIT_PRICE_TARIFF_PREVIEW"
        save_callback = _button(preview, "✅ Сохранить для SKU")["callback"]
        saved = handler.handle(save_callback, user_id=user_id)
        assert saved["status"] == "UNIT_PRICE_SCENARIO_READY"
        active = first_runner.unit_price_calculator_runtime_service.active_scenario_identity(user_id)
        scenario_id = active["scenario_id"]
        version = active["version"]
        profile_callback = _button(
            handler.handle(f"upc:a:{scenario_id}:{version}", user_id=user_id),
            "Профиль комиссии",
        )["callback"]
        export_callback = _button(
            handler.handle(profile_callback, user_id=user_id), "Скачать JSON",
        )["callback"]
    finally:
        reset_current_tenant_user_id(tenant)

    switched = set_current_tenant_user_id(
        make_store_tenant_scope(user_id, "store-q30-other"),
    )
    try:
        stale_export = handler.handle(export_callback, user_id=user_id)
        assert stale_export.get("error") is True
        other_store_profiles = handler.unit_price_tariff_profile_runtime_service.repository.list_tariff_profiles(
            owner_id=user_id, store_id="store-q30-other",
        )
        assert other_store_profiles["error"] is False
        assert other_store_profiles["items"] == []
    finally:
        reset_current_tenant_user_id(switched)

    # A fresh production composition reads the persisted manual profile from the same temp root.
    second_runner = create_telegram_assistant()
    second_source = _ScenarioSource()
    second_runner.unit_price_calculator_runtime_service.source = second_source
    second_tenant = set_current_tenant_user_id(
        make_store_tenant_scope(user_id, store_id),
    )
    try:
        entry = second_runner.unit_price_calculator_runtime_service.build_product_entry_button(
            user_id, "sku-q24",
        )
        reopened = second_runner.button_handler.handle(entry["callback"], user_id=user_id)
        assert reopened["status"] == "UNIT_PRICE_SCENARIO_READY"
        assert reopened["price_scenario"]["tariff_resolution"]["commission_rate"] == "14"
        assert second_source.calls == [("sku-q24", user_id, False)]

        active = second_runner.unit_price_calculator_runtime_service.active_scenario_identity(user_id)
        scenario_id = active["scenario_id"]
        version = active["version"]
        assumptions = second_runner.button_handler.handle(
            f"upc:a:{scenario_id}:{version}", user_id=user_id,
        )
        profile = second_runner.button_handler.handle(
            _button(assumptions, "Профиль комиссии")["callback"], user_id=user_id,
        )
        exported = second_runner.button_handler.handle(
            _button(profile, "Скачать JSON")["callback"], user_id=user_id,
        )
        assert exported["export_kind"] == "unit_price_tariff_profile"
        assert b"MANUAL_SELLER_ASSUMPTION" in exported["file_content"]
        assert second_source.calls == [("sku-q24", user_id, False)]
    finally:
        reset_current_tenant_user_id(second_tenant)


def test_public_flow_incomplete_buyout_then_modelled_rate_and_comparison(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    monkeypatch.chdir(tmp_path)

    from telegram_assistant_factory import create_telegram_assistant
    from services.unit_price_observation_collection_service import (
        UnitPriceObservationCollectionService,
    )

    runner = create_telegram_assistant()
    calculator = runner.unit_price_calculator_runtime_service
    runtime = runner.unit_price_observation_runtime_service
    handler = runner.button_handler
    scenario_source = _ScenarioSource()
    calculator.source = scenario_source
    returns_source = _ObservationReturns()
    runtime.collection_service = UnitPriceObservationCollectionService(
        repository=runtime.repository,
        finance_service=_ObservationFinance(),
        advertising_service=_ObservationAdvertising(),
        returns_buyout_source=returns_source,
        clock=lambda: datetime.now(ZoneInfo("UTC")),
    )

    user_id = "q30-buyout-owner"
    store_id = "store-q24"
    tenant = set_current_tenant_user_id(make_store_tenant_scope(user_id, store_id))
    try:
        entry = calculator.build_product_entry_button(user_id, "sku-q24")
        scenario = handler.handle(entry["callback"], user_id=user_id)
        tariff_prompt = handler.handle(
            _button(scenario, "Указать тариф комиссии")["callback"], user_id=user_id,
        )
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        tariff_start = today - timedelta(days=40)
        tariff_preview = handler.handle_text(
            f"Действует с: {tariff_start.isoformat()}\n"
            "0,01–99,99 ₽ = 12%\n100–199,99 ₽ = 14%",
            user_id=user_id,
        )
        assert tariff_prompt["status"] == "UNIT_PRICE_TARIFF_INPUT"
        scenario = handler.handle(
            _button(tariff_preview, "✅ Сохранить для SKU")["callback"], user_id=user_id,
        )
        save_prompt = handler.handle(
            _button(scenario, "💾 Сохранить план")["callback"], user_id=user_id,
        )
        assert handler.handle_text("Q30 buyout base 100", user_id=user_id)["status"] == "PLANNING_DOCUMENT_SAVED"

        plan_list = handler.handle("upp:m", user_id=user_id)
        base_action = next(
            button["callback"] for button in plan_list["keyboard"]["buttons"]
            if button["text"].startswith("Q30 buyout base 100")
        )
        base_plan = handler.handle(base_action, user_id=user_id)
        editable = handler.handle(
            _button(base_plan, "Продолжить по сохранённым допущениям")["callback"],
            user_id=user_id,
        )
        handler.handle(_button(editable, "Цена")["callback"], user_id=user_id)
        lower_price = handler.handle_text("95", user_id=user_id)
        assert lower_price["price_scenario"]["inputs"]["price"]["value"] == 95.0
        save_prompt = handler.handle(
            _button(lower_price, "💾 Сохранить план")["callback"], user_id=user_id,
        )
        assert save_prompt["status"] == "PLANNING_TITLE_REQUIRED"
        assert handler.handle_text("Q30 buyout lower 95", user_id=user_id)["status"] == "PLANNING_DOCUMENT_SAVED"

        first_start = today - timedelta(days=28)
        first_end = first_start + timedelta(days=6)
        second_start = first_end + timedelta(days=1)
        second_end = second_start + timedelta(days=6)

        def start_and_collect(title, price, effective_date, date_from, date_to):
            plans = handler.handle("upp:m", user_id=user_id)
            action = next(
                button["callback"] for button in plans["keyboard"]["buttons"]
                if button["text"].startswith(title)
            )
            detail = handler.handle(action, user_id=user_id)
            observation_prompt = handler.handle(
                _button(detail, "Наблюдать цену · SKU sku-q24")["callback"],
                user_id=user_id,
            )
            assert observation_prompt["status"] == "SELLER_PRICE_INPUT_REQUIRED"
            assert handler.handle_text(str(price), user_id=user_id)["status"] == "EFFECTIVE_TIME_INPUT_REQUIRED"
            effective = datetime.combine(
                effective_date, time(12), tzinfo=ZoneInfo("Europe/Moscow"),
            ).isoformat()
            preview = handler.handle_text(effective, user_id=user_id)
            card = handler.handle(
                _button(preview, "Подтвердить наблюдение")["callback"], user_id=user_id,
            )
            prompt = handler.handle(
                _button(card, "Собрать данные за период")["callback"], user_id=user_id,
            )
            assert prompt["status"] == "OBSERVATION_WINDOW_INPUT_REQUIRED"
            collected = handler.handle_text(
                f"{date_from.isoformat()} - {date_to.isoformat()}", user_id=user_id,
            )
            assert collected.get("status") == "OBSERVATION_CARD_READY", collected
            return collected

        base_card = start_and_collect(
            "Q30 buyout base 100", 100, first_start - timedelta(days=1),
            first_start, first_end,
        )
        base_observations = runtime.repository.list_unit_price_observations(
            owner_id=user_id, store_id=store_id,
        )
        base_observation = next(
            item for item in base_observations["items"]
            if item["seller_price_cents"] == 10_000
        )
        first_result = runtime.repository.get_unit_price_observation(
            base_observation["observation_id"], owner_id=user_id, store_id=store_id,
        )["result"]["payload"]
        assert first_result["status"] == "INSUFFICIENT_DATA"
        assert first_result["metrics"].get("profit_per_unit") is None

        retry_prompt = handler.handle(
            _button(base_card, "Собрать данные за период")["callback"], user_id=user_id,
        )
        retry_card = handler.handle_text(
            f"{first_start.isoformat()} - {first_end.isoformat()}", user_id=user_id,
        )
        assert retry_prompt["status"] == "OBSERVATION_WINDOW_INPUT_REQUIRED"
        base_result_detail = handler.handle(
            _button(retry_card, "История результатов")["callback"], user_id=user_id,
        )
        base_result_action = next(
            button["callback"] for button in base_result_detail["keyboard"]["buttons"]
            if button["text"] == "Открыть результат #2"
        )
        base_detail = handler.handle(base_result_action, user_id=user_id)
        assert "Наблюдаемый выкуп SKU: 80.00%" in base_detail["message"]
        assert "Модельная прибыль:" in base_detail["message"]
        assert "Возвраты в окне: 1 шт." in base_detail["message"]
        assert "расходы не вычтены из модельной прибыли/шт." in base_detail["message"]
        recovered_base = runtime.repository.get_unit_price_observation(
            base_observation["observation_id"], result_revision=2,
            owner_id=user_id, store_id=store_id,
        )["result"]["payload"]
        assert recovered_base["status"] == "AVAILABLE"
        assert recovered_base["metrics"]["successful_sale_units"] == 4
        assert recovered_base["metrics"]["weighted_ad_spend_numerator"] == "100.00"
        assert recovered_base["metrics"]["profit_per_unit"] == "36.00"

        finished_base = handler.handle(
            _button(base_card, "Завершить наблюдение")["callback"],
            user_id=user_id,
        )
        assert finished_base["status"] == "OBSERVATION_CARD_READY"
        assert "Наблюдение завершено." in finished_base["message"]

        lower_card = start_and_collect(
            "Q30 buyout lower 95", 95, second_start - timedelta(days=1),
            second_start, second_end,
        )
        lower_history = handler.handle(
            _button(lower_card, "История результатов")["callback"], user_id=user_id,
        )
        lower_result_callback = next(
            button["callback"] for button in lower_history["keyboard"]["buttons"]
            if button["text"] == "Открыть результат #1"
        )
        lower_result = handler.handle(lower_result_callback, user_id=user_id)
        lower_observation_id = lower_result_callback.split(":")[2]
        modeled_lower = runtime.repository.get_unit_price_observation(
            lower_observation_id, result_revision=1,
            owner_id=user_id, store_id=store_id,
        )["result"]["payload"]
        assert modeled_lower["status"] == "AVAILABLE"
        assert modeled_lower["metrics"]["successful_sale_units"] == 4
        assert modeled_lower["metrics"]["weighted_ad_spend_numerator"] == "100.00"
        assert modeled_lower["metrics"]["profit_per_unit"] == "33.60"
        comparison = handler.handle(
            _button(lower_result, "Сравнить прибыль по наблюдениям SKU")["callback"],
            user_id=user_id,
        )
        assert comparison["status"] == "OBSERVATION_RANKING_READY", comparison["message"]
        assert "Модель при сохранённых допущениях" in comparison["message"]
        assert "не доказывает" in comparison["message"]
        assert len(returns_source.calls) == 3
    finally:
        reset_current_tenant_user_id(tenant)
