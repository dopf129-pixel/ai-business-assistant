from copy import deepcopy
from threading import Event, Thread

from services.assistant_keyboard_service import AssistantKeyboardService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_unit_price_calculator_runtime_service import (
    TelegramUnitPriceCalculatorRuntimeService,
)
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter
from services.unit_price_advertising_cap_service import UnitPriceAdvertisingCapService
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService


class _ProductService:
    def __init__(self):
        self.products = [{
            "product_id": "p1",
            "offer_id": "hook-2",
            "sku": "3921245627",
            "name": "Самоклеящийся крючок",
        }]

    def load_products(self):
        return deepcopy(self.products)


class _Source:
    def __init__(self):
        self.product_service = _ProductService()
        self.calls = []

    def load_snapshot(self, sku, user_id, force_refresh=False):
        self.calls.append((sku, user_id, force_refresh))
        return {
            "error": False,
            "snapshot_id": "snapshot-1",
            "identity": {
                "user_id": user_id,
                "store_id": "store-1",
                "tenant_scope": f"{user_id}::ozon::store-1",
                "product_id": "p1",
                "offer_id": "hook-2",
                "sku": sku,
            },
            "product": {"name": "Самоклеящийся крючок", "scheme": "FBO"},
            "suggested_inputs": {
                "price": 500,
                "cost": 120,
                "commission_rate": 15,
                "logistics_per_unit": 40,
                "last_mile_per_unit": 10,
                "acquiring_per_unit": 5,
                "advertising_rate": None,
                "discount_points_rate": "20",
                "tax_mode": "USN_INCOME",
                "tax_rate": 6,
                "minimum_tax_rate": 1,
            },
            "input_provenance": {
                "price": "ozon_current_seller_price",
                "cost": "confirmed_store_cost",
                "commission_rate": "ozon_current_fbo_rate",
                "discount_points_rate": "weighted_exact_sku_finance_average_28_completed_days",
            },
            "source_periods": {
                "discount_points": {
                    "from": "2026-09-16",
                    "to": "2026-10-13",
                    "calendar_days": 28,
                },
                "seller_price_as_of": "2026-10-14T09:00:00+03:00",
            },
            "source_completeness": {
                "discount_points": {
                    "complete": True,
                    "positive_sale_observations": 12,
                }
            },
        }


def _runtime(clock=None, **kwargs):
    source = _Source()
    scenario_service = UnitPriceScenarioService(TaxService())
    kwargs.setdefault(
        "target_planning_service",
        UnitPriceTargetPlanningService(scenario_service),
    )
    kwargs.setdefault("advertising_cap_service", UnitPriceAdvertisingCapService(scenario_service))
    runtime = TelegramUnitPriceCalculatorRuntimeService(
        source=source,
        scenario_service=scenario_service,
        keyboard_service=AssistantKeyboardService(),
        clock=clock,
        **kwargs,
    )
    return runtime, source


def _mark_fixed_rate_assumption(source):
    """Keep legacy what-if fixtures explicit when testing multiple prices."""
    original_load_snapshot = source.load_snapshot

    def load_snapshot(*args, **kwargs):
        snapshot = original_load_snapshot(*args, **kwargs)
        snapshot["input_provenance"]["commission_rate"] = "fixed_rate_assumption"
        return snapshot

    source.load_snapshot = load_snapshot


def _activate(store="store-1"):
    return set_current_tenant_user_id(f"user-1::ozon::{store}")


def test_active_scenario_identity_supports_explicit_replacement_guard():
    runtime, _source = _runtime()
    tenant = _activate()
    try:
        button = runtime.build_product_entry_button("user-1", "3921245627")
        created = runtime.handle_callback(button["callback"], user_id="user-1")
        identity = runtime.active_scenario_identity("user-1")
        wrong_user = runtime.active_scenario_identity("user-2")
    finally:
        reset_current_tenant_user_id(tenant)

    assert created["error"] is False
    assert identity["scenario_id"]
    assert identity["version"] == 1
    assert identity["tenant_scope"] == "user-1::ozon::store-1"
    assert wrong_user is None


def test_advertising_cap_requires_explicit_target_and_applies_only_to_current_local_version():
    runtime, source = _runtime()
    tenant = _activate()
    try:
        opened = _select_catalog_product(runtime)
        ad_button = next(
            item for item in opened["keyboard"]["buttons"]
            if str(item.get("callback", "")).endswith(":advertising_rate")
        )
        prompt = runtime.handle_callback(ad_button["callback"], user_id="user-1")
        scenario = runtime.handle_text("10", user_id="user-1")
        cap_button = _find_button(scenario, "Сколько можно тратить на рекламу?")
        target_prompt = runtime.handle_callback(cap_button["callback"], user_id="user-1")
        cap = runtime.handle_text("25", user_id="user-1")
        target_button = _find_button(cap, "Подставить предел целевой маржи")
        applied = runtime.handle_callback(target_button["callback"], user_id="user-1")
        new_identity = runtime.active_scenario_identity("user-1")
        stale_apply = runtime.handle_callback(target_button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert target_prompt["status"] == "UNIT_PRICE_ADVERTISING_CAP_TARGET_REQUIRED"
    assert cap["status"] == "UNIT_PRICE_ADVERTISING_CAP_RESULT"
    target_cap = cap["advertising_cap_result"]["target"]
    assert target_cap["available"] is True
    assert "запас" in cap["message"]
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert applied["price_scenario"]["inputs"]["advertising_rate"]["value"] == float(target_cap["advertising_rate"])
    assert new_identity["version"] == 5
    assert stale_apply["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert len(source.calls) == 1


def test_advertising_cap_reuses_the_tariff_resolved_for_the_current_candidate_price():
    tariff = _FrozenRangeTariffRuntime()
    tariff.profile["bands"] = [
        {"price_from_cents": 1, "price_to_cents": 50_000, "commission_rate": "11"},
        {"price_from_cents": 50_001, "price_to_cents": 60_000, "commission_rate": "22"},
    ]
    runtime, source = _runtime(tariff_profile_runtime_service=tariff)
    token = _activate()
    try:
        opened = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(opened, "Реклама 0%")["callback"], user_id="user-1",
        )
        price_button = next(
            button for button in scenario["keyboard"]["buttons"]
            if str(button.get("callback", "")).endswith(":price")
        )
        price_prompt = runtime.handle_callback(
            price_button["callback"], user_id="user-1",
        )
        changed = runtime.handle_text("500.01", user_id="user-1")
        cap_prompt = runtime.handle_callback(
            _find_button(changed, "Сколько можно тратить на рекламу?")["callback"],
            user_id="user-1",
        )
        cap = runtime.handle_text("25", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert price_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert changed["price_scenario"]["inputs"]["commission_rate"]["value"] == 22
    assert cap_prompt["status"] == "UNIT_PRICE_ADVERTISING_CAP_TARGET_REQUIRED"
    assert cap["status"] == "UNIT_PRICE_ADVERTISING_CAP_RESULT"
    assert cap["advertising_cap_result"]["commission_rate"] == "22"
    assert cap["advertising_cap_result"]["commission_origin"] == "manual_seller_assumption"
    assert "Комиссия на этой цене: 22%" in cap["message"]
    expected_inputs = deepcopy(changed["price_scenario"]["effective_scenario_inputs"])
    expected_inputs.update(commission_rate="22", advertising_rate="0")
    expected = runtime.advertising_cap_service.solve(
        expected_inputs, "25",
        identity=changed["price_scenario"]["identity"],
        provenance={"commission_rate": "manual_seller_assumption"},
        sources=changed["price_scenario"].get("sources") or {},
    )
    assert cap["advertising_cap_result"]["target"] == expected["target"]
    assert len(source.calls) == 1


def _find_button(result, text):
    return next(
        item for item in result["keyboard"]["buttons"]
        if item["text"] == text
    )


def _select_catalog_product(runtime, reference="hook-2"):
    pending = runtime.begin_catalog_selection("user-1")
    assert pending["status"] == "UNIT_PRICE_SCENARIO_CATALOG_SELECTION_PENDING"
    callback = runtime.build_catalog_product_callback("user-1", reference)
    return runtime.handle_callback(callback, user_id="user-1")


def _add_cross_docking_evidence(source, cross_docking):
    original_load = source.load_snapshot

    def load_snapshot(*args, **kwargs):
        snapshot = original_load(*args, **kwargs)
        snapshot["cross_docking"] = deepcopy(cross_docking)
        snapshot["suggested_inputs"]["cross_docking_per_unit"] = 12.0
        snapshot["input_provenance"]["cross_docking_per_unit"] = "ozon_cross_docking_sku_average"
        snapshot["source_completeness"]["cross_docking"] = {
            "complete": True,
            "status": "SKU_SUPPLY_PERIOD_AVERAGE",
        }
        snapshot["source_periods"]["cross_docking"] = {
            "from": "2026-08-24",
            "to": "2026-10-18",
            "calendar_days": 56,
        }
        return snapshot

    source.load_snapshot = load_snapshot


class _FrozenRangeTariffRuntime:
    def __init__(self):
        self.calls = []
        self.profile = {
            "profile_id": "manual-range-1", "revision": 1, "state_revision": 1,
            "owner_id": "user-1", "store_id": "store-1",
            "identity": {"product_id": "p1", "offer_id": "hook-2", "sku": "3921245627"},
            "sale_schema": "FBO", "price_basis": "SELLER_PRICE_RUB", "currency": "RUB",
            "origin": "MANUAL_SELLER_ASSUMPTION", "source_ref": "synthetic-runtime-test",
            "recorded_at": "2026-10-27T10:00:00+00:00", "observed_at": None,
            "effective_from": "2026-10-01", "effective_to": None,
            "confirmed_by_owner": True,
            "bands": [
                {"price_from_cents": 1, "price_to_cents": 10_000, "commission_rate": "11"},
                {"price_from_cents": 10_001, "price_to_cents": 30_000, "commission_rate": "22"},
                {"price_from_cents": 30_001, "price_to_cents": 100_000, "commission_rate": "15"},
            ],
        }

    def get_session_profile(self, scenario_id, user_id=None):
        return None

    def resolve_for_scenario(self, scenario_id, version, seller_price, user_id=None,
                             *, session_profile_only=False):
        self.calls.append((scenario_id, version, str(seller_price), user_id))
        cents = UnitPriceTariffSnapshotAdapter.price_to_cents(seller_price)
        resolution = UnitPriceTariffResolver().resolve(
            seller_price_cents=cents,
            identity={
                "owner_id": "user-1", "store_id": "store-1", "product_id": "p1",
                "offer_id": "hook-2", "sku": "3921245627",
            },
            sale_schema="FBO", effective_date="2026-10-14", profiles=[self.profile],
        )
        return {
            **resolution,
            "effective_date": "2026-10-14",
            "selected_profile": deepcopy(self.profile) if resolution.get("available") is True else None,
            "candidate_profiles": [deepcopy(self.profile)],
        }


def test_catalog_selection_uses_exact_sku_and_initially_requires_manual_advertising():
    runtime, source = _runtime()
    token = _activate()
    try:
        result = _select_catalog_product(runtime)
    finally:
        reset_current_tenant_user_id(token)

    assert source.calls == [("3921245627", "user-1", False)]
    assert result["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
    assert result["price_scenario"]["missing_inputs"] == ["advertising_rate"]
    assert "Реклама" in result["message"]
    assert "Кросс-докинг не включён" in result["message"]
    assert all(len(button["callback"].encode("utf-8")) <= 64 for button in result["keyboard"]["buttons"])


def test_price_calculator_shows_cross_docking_formula_and_uses_it_in_profit():
    runtime, source = _runtime()
    _mark_fixed_rate_assumption(source)
    cross_docking = {
        "status": "SKU_SUPPLY_PERIOD_AVERAGE",
        "reason": None,
        "evidence_complete": True,
        "applicable_to_sku": True,
        "method": "sku_accrual_cost_per_delivered_crossdock_unit",
        "cross_docking_per_unit": "12.00",
        "expense_by_sku": "1200.00",
        "signed_accrual_by_sku": "-1200.00",
        "supplied_units_sku": 100,
        "days_complete": 56,
        "days_expected": 56,
        "date_from": "2026-08-24",
        "date_to": "2026-10-18",
        "as_of": "2026-10-19T12:00:00+00:00",
        "supply_status": "COMPLETE",
        "sku": "must-not-be-exposed",
        "supply_id": "must-not-be-exposed",
    }
    _add_cross_docking_evidence(source, cross_docking)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        ready = runtime.handle_callback(
            f"upc:z:{scenario['price_scenario']['scenario_id']}:1",
            user_id="user-1",
        )
        details = runtime.handle_callback(
            _find_button(ready, "Подробности расчёта")["callback"], user_id="user-1"
        )
        assumptions = runtime.handle_callback(
            _find_button(ready, "Допущения и источники")['callback'], user_id="user-1"
        )
        target_prompt = runtime.handle_callback(
            _find_button(ready, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        target = runtime.handle_text("20", user_id="user-1")
        compare_prompt = runtime.handle_callback(
            _find_button(target, "Сравнить другие цены")["callback"],
            user_id="user-1",
        )
        comparison = runtime.handle_text("499,90; 549,90", user_id="user-1")
        cap_runtime, cap_source = _runtime()
        _mark_fixed_rate_assumption(cap_source)
        _add_cross_docking_evidence(cap_source, cross_docking)
        cap_scenario = _select_catalog_product(cap_runtime)
        cap_ready = cap_runtime.handle_callback(
            f"upc:z:{cap_scenario['price_scenario']['scenario_id']}:1",
            user_id="user-1",
        )
        cap_prompt = cap_runtime.handle_callback(
            _find_button(cap_ready, "Сколько можно тратить на рекламу?")["callback"],
            user_id="user-1",
        )
        cap = cap_runtime.handle_text("25", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert ready["price_scenario"]["calculated"]["cross_docking"] == 12.0
    assert ready["price_scenario"]["calculated"]["profit"] == 214.0
    assert "Кросс-докинг учтён: 12,00 ₽/шт." in ready["message"]
    assert "Кросс-докинг: 12,00 ₽ на фактически поставленную единицу (по расходам этого SKU)" in details["message"]
    assert "начисления 1 200,00 ₽ / принято 100 шт." in details["message"]
    assert "начисления Ozon с корректировками -1 200,00 ₽" in details["message"]
    assert "покрытие 56/56 дней" in details["message"]
    assert "поставки: COMPLETE" in details["message"]
    assert "снимок: 2026-10-19T12:00:00Z" in details["message"]
    assert "must-not-be-exposed" not in details["message"]
    assert "Кросс-докинг: 12,00 ₽" in assumptions["message"]
    assert target_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert "Кросс-докинг учтён: 12,00 ₽ на одну плановую успешную продажу." in target["message"]
    assert compare_prompt["stage"] == "price_options"
    assert "Кросс-докинг учтён: 12,00 ₽ на одну плановую успешную продажу." in comparison["message"]
    assert cap_prompt["status"] == "UNIT_PRICE_ADVERTISING_CAP_TARGET_REQUIRED"
    assert "Кросс-докинг: 12,00 ₽ на фактически поставленную единицу" in cap["message"]


def test_target_price_result_labels_missing_cross_docking_evidence_instead_of_excluding_it_generically():
    runtime, source = _runtime()
    original_load = source.load_snapshot

    def load_snapshot(*args, **kwargs):
        snapshot = original_load(*args, **kwargs)
        snapshot["suggested_inputs"]["cross_docking_per_unit"] = None
        snapshot["input_provenance"]["cross_docking_per_unit"] = "unknown"
        snapshot["source_completeness"]["cross_docking"] = {
            "complete": False,
            "status": "WINDOW_INCOMPLETE",
            "reason": "FINANCE_WINDOW_INCOMPLETE",
        }
        return snapshot

    source.load_snapshot = load_snapshot
    tenant = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("20", user_id="user-1")
        applied = runtime.handle_callback(
            _find_button(result, "Подставить цену для цели")["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert prompt["stage"] == "target_margin"
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert "Кросс-докинг не включён: подтверждённой ставки для SKU нет (FINANCE_WINDOW_INCOMPLETE)." in result["message"]


def test_legacy_saved_v1_target_result_says_cross_docking_is_not_included():
    runtime, _source = _runtime()
    tenant = _activate()
    try:
        current = _select_catalog_product(runtime)
        identity = current["price_scenario"]["identity"]
        capture = runtime.get_saved_plan_capture(
            current["price_scenario"]["scenario_id"],
            identity["scenario_version"],
            user_id="user-1",
        )
        payload = capture["payload"]
        payload["schema_version"] = 1
        payload["calculation_version"] = 1
        item = payload["items"][0]
        item["inputs"].pop("cross_docking_per_unit", None)
        item["provenance"].pop("cross_docking_per_unit", None)
        item["sources"].pop("cross_docking", None)
        item["sources"].get("completeness", {}).pop("cross_docking", None)
        item["projection"].pop("cross_docking", None)
        restored = runtime.restore_saved_plan(payload, user_id="user-1")
        restored = runtime.handle_callback(
            _find_button(restored, "Реклама 0%")["callback"], user_id="user-1"
        )
        prompt = runtime.handle_callback(
            _find_button(restored, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("20", user_id="user-1")
    finally:
        reset_current_tenant_user_id(tenant)

    assert identity["sku"] == "3921245627"
    assert prompt["stage"] == "target_margin"
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert "Сохранённый план v1: кросс-докинг не учтён; исходная версия не содержит ставки." in result["message"]


def test_price_edit_accepts_comma_decimal_and_stale_buttons_fail_closed():
    runtime, _ = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        sid = scenario["price_scenario"]["scenario_id"]
        old_edit = f"upc:e:{sid}:1:price"
        prompt = runtime.handle_callback(old_edit, user_id="user-1")
        old_zero_ad = f"upc:z:{sid}:1"
        invalid = runtime.handle_text("-1", user_id="user-1")
        valid = runtime.handle_text("600,50", user_id="user-1")
        stale = runtime.handle_callback(old_zero_ad, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert invalid["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert valid["price_scenario"]["inputs"]["price"]["value"] == 600.5
    assert valid["price_scenario"]["available"] is False
    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"


def test_manual_zero_advertising_completes_scenario_and_reports_comparison():
    runtime, _ = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        sid = scenario["price_scenario"]["scenario_id"]
        result = runtime.handle_callback(f"upc:z:{sid}:1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert result["price_scenario"]["calculated"]["profit"] == 226.0
    assert result["price_scenario"]["comparison"]["available"] is True
    assert result["message"].index("Прибыль:") < result["message"].index("Комиссия:")
    assert "Прибыль: 226,00 ₽/шт." in result["message"]
    assert "Выручка для налога" not in result["message"]
    assert len(result["message"]) < 1200
    assert "При текущей цене 500,00 ₽" in result["message"]
    assert "Оценка одной успешной продажи FBO" in result["message"]
    assert "FBS не поддержан" in result["message"]
    assert "Не включены хранение, постоянные расходы и возвраты." in result["message"]

    token = _activate()
    try:
        details = runtime.handle_callback(
            _find_button(result, "Подробности расчёта")["callback"], user_id="user-1"
        )
        short = runtime.handle_callback(
            _find_button(details, "Краткий итог")["callback"], user_id="user-1"
        )
    finally:
        reset_current_tenant_user_id(token)
    assert details["status"] == "UNIT_PRICE_SCENARIO_DETAILS_READY"
    assert "Цена продавца: 500,00 ₽" in details["message"]
    assert "Выручка для налога:" in details["message"]
    assert "Налог:" in details["message"]
    assert "Краткий итог" in [item["text"] for item in details["keyboard"]["buttons"]]
    assert short["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert "Прибыль: 226,00 ₽/шт." in short["message"]


def test_target_margin_input_retries_then_shows_verified_price_without_changing_scenario():
    runtime, source = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        price_before = scenario["price_scenario"]["inputs"]["price"]["value"]
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        invalid = runtime.handle_text("120", user_id="user-1")
        result = runtime.handle_text("20", user_id="user-1")
        returned = runtime.handle_callback(
            _find_button(result, "Назад к расчёту")["callback"], user_id="user-1"
        )
    finally:
        reset_current_tenant_user_id(token)

    target = result["price_planning_result"]["target"]
    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert invalid["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert "Некорректный процент" in invalid["message"]
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert target["status"] == "FOUND"
    assert target["goal_reached"] is True
    assert "Цена для цели" in result["message"]
    assert "цель 20,00% достигнута" in result["message"]
    assert result["price_planning_result"]["read_only"] is True
    assert result["price_planning_result"]["executed"] is False
    assert price_before == 500
    assert returned["price_scenario"]["inputs"]["price"]["value"] == 500
    assert source.calls == [("3921245627", "user-1", False)]
    assert len(result["message"]) < 3500
    assert all(len(item["callback"].encode("utf-8")) <= 64 for item in result["keyboard"]["buttons"])


def test_target_margin_runtime_uses_frozen_tariff_segments_and_discloses_coverage_gaps():
    tariff = _FrozenRangeTariffRuntime()
    runtime, source = _runtime(tariff_profile_runtime_service=tariff)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("20", user_id="user-1")
        applied = runtime.handle_callback(
            _find_button(result, "Подставить цену для цели")["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    plan = result["price_planning_result"]
    target = plan["target"]
    assert prompt["stage"] == "target_margin"
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert target["status"] == "FOUND"
    assert target["commission_rate"] == "15"
    assert target["commission_origin"] == "MANUAL_SELLER_ASSUMPTION"
    assert plan["tariff_search"]["covered_segment_count"] == 3
    assert plan["tariff_search"]["coverage_complete"] is False
    assert plan["tariff_search"]["global_minimum_claimed"] is False
    assert "Минимум ищется только среди рассчитанных тарифных диапазонов" in result["message"]
    assert "Комиссия не определена для цен:" in result["message"]
    assert "Цена основного сценария не изменена" in result["message"]
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert applied["price_scenario"]["inputs"]["price"]["value"] == float(target["price"])
    assert applied["price_scenario"]["inputs"]["commission_rate"]["value"] == float(target["commission_rate"])
    assert len(result["message"]) < 3500
    assert source.calls == [("3921245627", "user-1", False)]


def test_target_margin_can_be_found_without_a_source_price():
    runtime, source = _runtime()
    original_load_snapshot = source.load_snapshot

    def load_snapshot(sku, user_id, force_refresh=False):
        snapshot = original_load_snapshot(sku, user_id, force_refresh)
        snapshot["suggested_inputs"].update({
            "price": None,
            "cost": "0",
            "commission_rate": "50",
            "logistics_per_unit": "0",
            "last_mile_per_unit": "0",
            "acquiring_per_unit": "0",
            "advertising_rate": "0.01",
            "discount_points_rate": "0",
            "tax_mode": "NONE",
            "tax_rate": None,
            "minimum_tax_rate": None,
        })
        snapshot["input_provenance"].pop("price", None)
        return snapshot

    source.load_snapshot = load_snapshot
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("49,99", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    target = result["price_planning_result"]["target"]
    assert prompt["stage"] == "target_margin"
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert target["status"] == "FOUND"
    assert target["price"] == "0.02"
    assert target["goal_reached"] is True
    assert result["price_planning_result"]["read_only"] is True
    assert result["price_planning_result"]["executed"] is False
    assert source.calls == [("3921245627", "user-1", False)]


def test_target_margin_prefers_a_smaller_verified_price_than_current_price():
    runtime, source = _runtime()
    original_load_snapshot = source.load_snapshot

    def load_snapshot(sku, user_id, force_refresh=False):
        snapshot = original_load_snapshot(sku, user_id, force_refresh)
        snapshot["suggested_inputs"].update({
            "price": "500",
            "cost": "0",
            "commission_rate": "50",
            "logistics_per_unit": "0",
            "last_mile_per_unit": "0",
            "acquiring_per_unit": "0",
            "advertising_rate": "0",
            "discount_points_rate": "0",
            "tax_mode": "NONE",
            "tax_rate": None,
            "minimum_tax_rate": None,
        })
        snapshot["input_provenance"]["commission_rate"] = "fixed_rate_assumption"
        return snapshot

    source.load_snapshot = load_snapshot
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("50", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    target = result["price_planning_result"]["target"]
    assert prompt["stage"] == "target_margin"
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert target["status"] == "FOUND"
    assert target["price"] == "0.02"
    assert target["goal_reached"] is True
    assert "Подставить цену для цели" in [
        button["text"] for button in result["keyboard"]["buttons"]
    ]
    assert source.calls == [("3921245627", "user-1", False)]


def test_target_margin_treats_trailing_zero_price_input_as_same_cent_value():
    runtime, source = _runtime()
    original_load_snapshot = source.load_snapshot

    def load_snapshot(sku, user_id, force_refresh=False):
        snapshot = original_load_snapshot(sku, user_id, force_refresh)
        snapshot["suggested_inputs"].update({
            "price": "11.11",
            "cost": "0",
            "commission_rate": "68.18",
            "logistics_per_unit": "0",
            "last_mile_per_unit": "0",
            "acquiring_per_unit": "0",
            "advertising_rate": "31.81",
            "discount_points_rate": "0",
            "tax_mode": "NONE",
            "tax_rate": None,
            "minimum_tax_rate": None,
        })
        snapshot["input_provenance"]["commission_rate"] = "fixed_rate_assumption"
        return snapshot

    source.load_snapshot = load_snapshot
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        sid = scenario["price_scenario"]["scenario_id"]
        prompt = runtime.handle_callback(
            f"upc:e:{sid}:1:price", user_id="user-1"
        )
        edited = runtime.handle_text("11.110", user_id="user-1")
        target_prompt = runtime.handle_callback(
            _find_button(edited, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("0.01", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    target = result["price_planning_result"]["target"]
    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert edited["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert edited["price_scenario"]["inputs"]["price"]["value"] == 11.11
    assert edited["price_scenario"]["calculated"]["profit"] == 0.01
    assert target_prompt["stage"] == "target_margin"
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert target["status"] == "FOUND"
    # The current solver evaluates the canonical rounded per-unit fees at each
    # cent. In this deliberately extreme 99.99% variable-rate case, the first
    # cent-exact price that yields a positive kopeck is 0.11 RUB.
    assert target["price"] == "0.11"
    assert target["goal_reached"] is True
    assert target["previous_cent_goal_reached"] is False
    assert source.calls == [("3921245627", "user-1", False)]


def test_compare_prices_rejects_entire_invalid_list_then_compares_same_scenario():
    runtime, source = _runtime()
    _mark_fixed_rate_assumption(source)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        price_before = scenario["price_scenario"]["inputs"]["price"]["value"]
        target_prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"], user_id="user-1"
        )
        target_result = runtime.handle_text("20", user_id="user-1")
        prompt = runtime.handle_callback(
            _find_button(target_result, "Сравнить другие цены")["callback"],
            user_id="user-1",
        )
        invalid = runtime.handle_text("499,90; 499.90; nope", user_id="user-1")
        result = runtime.handle_text("499,90; 549,90; 599,90", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["stage"] == "price_options"
    assert invalid["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert "Список не принят целиком" in invalid["message"]
    assert result["status"] == "UNIT_PRICE_PRICE_COMPARISON_RESULT"
    rows = result["price_planning_result"]["rows"]
    assert [row["price"] for row in rows] == ["499.90", "549.90", "599.90"]
    assert all(row["available"] is True for row in rows)
    assert len({row["profit"] for row in rows}) == 3
    assert all(row["goal_reached"] is True for row in rows)
    assert "цель 20,00% достигнута" in result["message"]
    assert "налог" in result["message"]
    assert price_before == 500
    assert source.calls == [("3921245627", "user-1", False)]


def test_tariff_aware_comparison_uses_frozen_per_price_rate_and_no_extra_source_reads():
    tariff = _FrozenRangeTariffRuntime()
    runtime, source = _runtime(tariff_profile_runtime_service=tariff)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        target_prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        target_result = runtime.handle_text("20", user_id="user-1")
        prompt = runtime.handle_callback(
            _find_button(target_result, "Сравнить другие цены")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("99,99; 100; 100,01", user_id="user-1")
        selected = runtime.handle_callback(
            _find_button(result, "Подставить вариант 3")["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    comparison = result["price_planning_result"]
    assert target_prompt["stage"] == "target_margin"
    assert prompt["stage"] == "price_options"
    assert comparison["target_margin_percent"] == "20"
    assert [row["commission_rate"] for row in comparison["rows"]] == ["11", "11", "22"]
    assert [row["commission"] for row in comparison["rows"]] == [11.0, 11.0, 22.0]
    assert comparison["baseline"]["price"] == "500.00"
    assert comparison["baseline"]["available"] is True
    assert comparison["best_prices"] == ["100.00"]
    assert "Максимальная прибыль среди рассчитанных вариантов" in result["message"]
    assert "Реклама для вариантов: одинаковая ДРР 0,00%" in result["message"]
    assert selected["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert selected["price_scenario"]["inputs"]["price"]["value"] == 100.01
    assert selected["price_scenario"]["inputs"]["commission_rate"]["value"] == 22.0
    assert len(source.calls) == 1
    assert len(tariff.calls) == 1


def test_public_comparison_flow_accepts_per_price_drr_and_applies_selected_rate_locally():
    runtime, source = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        ad_button = next(button for button in scenario["keyboard"]["buttons"]
                         if str(button.get("callback", "")).endswith(":advertising_rate"))
        ad_prompt = runtime.handle_callback(ad_button["callback"], user_id="user-1")
        scenario = runtime.handle_text("16.5", user_id="user-1")
        compare_button = next(button for button in scenario["keyboard"]["buttons"]
                              if str(button.get("callback", "")).startswith("upc:q:"))
        comparison_prompt = runtime.handle_callback(compare_button["callback"], user_id="user-1")
        initial = runtime.handle_text("450; 500", user_id="user-1")
        drr_button = next(button for button in initial["keyboard"]["buttons"]
                          if str(button.get("callback", "")).startswith("upc:d:"))
        drr_prompt = runtime.handle_callback(drr_button["callback"], user_id="user-1")
        invalid = runtime.handle_text("12", user_id="user-1")
        result = runtime.handle_text("16.5; 8", user_id="user-1")
        apply_button = next(button for button in result["keyboard"]["buttons"]
                            if str(button.get("callback", "")).startswith("upc:u:")
                            and str(button.get("callback", "")).endswith(":1"))
        applied = runtime.handle_callback(apply_button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert ad_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert comparison_prompt["stage"] == "price_options"
    assert drr_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert invalid["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    result_data = result["price_planning_result"]
    assert result_data["advertising_basis"]["mode"] == "PER_PRICE_DRR"
    assert result_data["advertising_basis"]["rates"] == ["16.5", "8"]
    assert result_data["rows"][1]["compensation_thresholds"]["strictly_better"]["available"] is True
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert applied["price_scenario"]["inputs"]["price"]["value"] == 500
    assert applied["price_scenario"]["inputs"]["advertising_rate"]["value"] == 8
    assert len(source.calls) == 1


def test_public_comparison_flow_uses_total_spend_over_successful_sales_denominator():
    runtime, source = _runtime()
    _mark_fixed_rate_assumption(source)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        ad_button = next(button for button in scenario["keyboard"]["buttons"]
                         if str(button.get("callback", "")).endswith(":advertising_rate"))
        ad_prompt = runtime.handle_callback(ad_button["callback"], user_id="user-1")
        scenario = runtime.handle_text("10", user_id="user-1")
        compare_button = next(button for button in scenario["keyboard"]["buttons"]
                              if str(button.get("callback", "")).startswith("upc:q:"))
        comparison_prompt = runtime.handle_callback(compare_button["callback"], user_id="user-1")
        initial = runtime.handle_text("450; 500", user_id="user-1")
        cost_button = next(button for button in initial["keyboard"]["buttons"]
                           if str(button.get("callback", "")).startswith("upc:h:"))
        cost_prompt = runtime.handle_callback(cost_button["callback"], user_id="user-1")
        result = runtime.handle_text("200; 40", user_id="user-1")
        apply_button = next(button for button in result["keyboard"]["buttons"]
                            if str(button.get("callback", "")).startswith("upc:u:")
                            and str(button.get("callback", "")).endswith(":0"))
        applied = runtime.handle_callback(apply_button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    basis = result["price_planning_result"]["advertising_basis"]
    assert ad_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert comparison_prompt["stage"] == "price_options"
    assert cost_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert basis["mode"] == "MANUAL_COST_PER_SUCCESSFUL_UNIT"
    assert basis["denominator"] == "SUCCESSFUL_UNITS"
    assert basis["successful_units"] == 40
    assert basis["total_spend"] == "200.00"
    assert basis["amount_per_unit"] == "5.00"
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    applied_inputs = applied["price_scenario"]["inputs"]
    assert applied_inputs["advertising_mode"]["value"] == "ABSOLUTE_PER_SUCCESSFUL_UNIT"
    assert applied_inputs["advertising_cost_per_unit"]["value"] == 5.0
    assert "advertising_rate" not in applied_inputs
    assert applied["price_scenario"]["calculated"]["advertising"] == 5.0
    assert len(source.calls) == 1


def test_advertising_mode_can_switch_between_percentage_and_fixed_rubles_per_unit():
    runtime, _source = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        fixed_button = _find_button(scenario, "Реклама, ₽/успешную продажу")
        fixed_prompt = runtime.handle_callback(fixed_button["callback"], user_id="user-1")
        fixed = runtime.handle_text("600", user_id="user-1")

        percent_button = _find_button(fixed, "Реклама, %")
        percent_prompt = runtime.handle_callback(percent_button["callback"], user_id="user-1")
        percent = runtime.handle_text("7", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert fixed_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert fixed["price_scenario"]["inputs"]["advertising_mode"]["value"] == (
        "ABSOLUTE_PER_SUCCESSFUL_UNIT"
    )
    assert fixed["price_scenario"]["inputs"]["advertising_cost_per_unit"]["value"] == 600.0
    assert "advertising_rate" not in fixed["price_scenario"]["inputs"]
    assert fixed["price_scenario"]["calculated"]["advertising"] == 600.0
    assert percent_prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert percent["price_scenario"]["inputs"]["advertising_rate"]["value"] == 7.0
    assert "advertising_mode" not in percent["price_scenario"]["inputs"]
    assert "advertising_cost_per_unit" not in percent["price_scenario"]["inputs"]
    assert percent["price_scenario"]["calculated"]["advertising"] == 35.0


def test_public_price_grid_is_bounded_paged_and_calculates_compensation_only_for_selected_price():
    tariff = _FrozenRangeTariffRuntime()
    runtime, source = _runtime(tariff_profile_runtime_service=tariff)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        prompt = runtime.handle_callback(
            _find_button(scenario, "Исследовать диапазон цены")["callback"],
            user_id="user-1",
        )
        invalid = runtime.handle_text("2;1;0.01", user_id="user-1")
        result = runtime.handle_text("1;2;0.01", user_id="user-1")
        next_page_button = next(
            button for button in result["keyboard"]["buttons"]
            if str(button.get("callback", "")).startswith("upc:w:")
        )
        second_page = runtime.handle_callback(next_page_button["callback"], user_id="user-1")
        apply_button = _find_button(result, "Подставить вариант 1")
        applied = runtime.handle_callback(apply_button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    grid = result["price_planning_result"]
    assert prompt["stage"] == "price_grid"
    assert invalid["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert "начало; конец; шаг" in invalid["message"]
    assert result["status"] == "UNIT_PRICE_PRICE_COMPARISON_RESULT"
    assert len(grid["rows"]) == 101
    assert len(grid["rows"]) <= grid["price_grid"]["candidate_limit"] == 200
    assert grid["evaluation_count"] <= grid["evaluation_limit"] == 1_024
    assert grid["global_optimum_claimed"] is False
    assert all("forward_result" not in row for row in grid["rows"])
    assert all(row["compensation_thresholds"]["status"] == "DEFERRED_UNTIL_CANDIDATE_SELECTED"
               for row in grid["rows"])
    assert "не глобальный максимум" in result["message"]
    assert "варианты 1–10" in result["message"]
    assert "варианты 11–20" in second_page["message"]
    second_page_buttons = second_page["keyboard"]["buttons"]
    assert any(button["text"] == "Подставить вариант 11" for button in second_page_buttons)
    assert not any(button["text"] == "Подставить вариант 1" for button in second_page_buttons)
    assert all(len(button["callback"].encode("utf-8")) <= 64 for button in second_page_buttons)
    stale_keyboard = AssistantKeyboardService().build_unit_price_planning_result_keyboard(
        "scenario-1", 1, "price_grid", planning_result=grid,
        allow_apply=False, page=1,
    )
    assert any(button["text"].startswith("◀ Предыдущие") for button in stale_keyboard["buttons"])
    assert not any(button["text"].startswith("Подставить") for button in stale_keyboard["buttons"])
    assert len(result["message"].encode("utf-16-le")) // 2 <= 4096
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert "Порог рекламы для выбранной цены относительно базы" in applied["message"]
    assert applied["price_scenario"]["inputs"]["price"]["value"] == 1
    assert source.calls == [("3921245627", "user-1", False)]
    assert len(tariff.calls) == 1


def test_target_margin_reports_missing_assumptions_instead_of_zeroing_them():
    runtime, _ = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("20", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert result["price_planning_result"]["target"]["status"] == "MISSING_INPUTS"
    assert "заполните Реклама" in result["message"]
    assert "Цена основного сценария не изменена" in result["message"]
    assert not any(
        item["text"].startswith("Подставить")
        for item in result["keyboard"]["buttons"]
    )


def test_cancel_price_planning_text_keeps_existing_assumptions():
    runtime, _ = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        sid = scenario["price_scenario"]["scenario_id"]
        prompt = runtime.handle_callback(
            _find_button(scenario, "Сравнить цены")["callback"], user_id="user-1"
        )
        cancelled = runtime.handle_callback(
            _find_button(prompt, "Отмена")["callback"], user_id="user-1"
        )
    finally:
        reset_current_tenant_user_id(token)

    assert sid == cancelled["price_scenario"]["scenario_id"]
    assert cancelled["price_scenario"]["inputs"]["price"]["value"] == 500
    assert cancelled["price_scenario"]["inputs"]["advertising_rate"]["value"] is None


def test_price_comparison_message_stays_within_telegram_utf16_limit():
    runtime, source = _runtime()
    original_load = source.load_snapshot

    def load_long_labels(sku, user_id, force_refresh=False):
        result = original_load(sku, user_id, force_refresh)
        result["identity"]["store_name"] = "Магазин" * 500
        result["product"]["name"] = "Товар" * 500
        return result

    source.load_snapshot = load_long_labels
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        runtime.handle_callback(
            _find_button(scenario, "Сравнить цены")["callback"], user_id="user-1"
        )
        result = runtime.handle_text("499; 549; 599; 649; 699", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "UNIT_PRICE_PRICE_COMPARISON_RESULT"
    assert len(result["message"].encode("utf-16-le")) // 2 <= 4096
    assert len(result["message"]) < 3500
    assert "Магазин" * 20 not in result["message"]


def test_target_price_applies_only_from_current_verified_result_and_old_button_stales():
    runtime, source = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("20", user_id="user-1")
        apply_button = _find_button(result, "Подставить цену для цели")
        applied = runtime.handle_callback(apply_button["callback"], user_id="user-1")
        stale = runtime.handle_callback(apply_button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    candidate = result["price_planning_result"]["target"]["price"]
    assert prompt["stage"] == "target_margin"
    assert candidate not in apply_button["callback"]
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert applied["price_scenario"]["inputs"]["price"]["value"] == float(candidate)
    assert applied["price_scenario"]["inputs"]["price"]["provenance"] == "manual_seller_assumption"
    assert "подставлена только в текущий сценарий" in applied["message"]
    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert source.calls == [("3921245627", "user-1", False)]


def test_comparison_applies_only_the_selected_saved_row():
    runtime, source = _runtime()
    _mark_fixed_rate_assumption(source)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        prompt = runtime.handle_callback(
            _find_button(scenario, "Сравнить цены")["callback"], user_id="user-1"
        )
        result = runtime.handle_text("499; 549; 599", user_id="user-1")
        selected_button = _find_button(result, "Подставить вариант 2")
        tampered_callback = selected_button["callback"].rsplit(":", 1)[0] + ":549"
        tampered = runtime.handle_callback(tampered_callback, user_id="user-1")
        applied = runtime.handle_callback(selected_button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["stage"] == "price_options"
    assert "549" not in selected_button["callback"]
    assert tampered["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert applied["price_scenario"]["inputs"]["price"]["value"] == 549
    assert applied["price_scenario"]["inputs"]["price"]["provenance"] == "manual_seller_assumption"
    assert source.calls == [("3921245627", "user-1", False)]


def test_apply_callback_is_invalidated_after_manual_scenario_change():
    runtime, _ = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        prompt = runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = runtime.handle_text("20", user_id="user-1")
        apply_callback = _find_button(result, "Подставить цену для цели")["callback"]
        returned = runtime.handle_callback(
            _find_button(result, "Назад к расчёту")["callback"], user_id="user-1"
        )
        edit = runtime.handle_callback(
            _find_button(returned, "Цена")["callback"], user_id="user-1"
        )
        changed = runtime.handle_text("700", user_id="user-1")
        stale = runtime.handle_callback(apply_callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert prompt["stage"] == "target_margin"
    assert edit["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    assert changed["price_scenario"]["inputs"]["price"]["value"] == 700
    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"


def test_apply_callback_fails_closed_for_another_store():
    runtime, source = _runtime()
    token = _activate("store-1")
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"], user_id="user-1"
        )
        result = runtime.handle_text("20", user_id="user-1")
        apply_callback = _find_button(result, "Подставить цену для цели")["callback"]
    finally:
        reset_current_tenant_user_id(token)

    other_store = _activate("store-2")
    try:
        stale = runtime.handle_callback(apply_callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(other_store)

    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert source.calls == [("3921245627", "user-1", False)]


def test_apply_callback_expires_when_source_snapshot_becomes_stale():
    class Clock:
        now = 0

        def __call__(self):
            return self.now

    clock = Clock()
    runtime, source = _runtime(clock=clock, session_ttl_seconds=600)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"], user_id="user-1"
        )
        result = runtime.handle_text("20", user_id="user-1")
        apply_callback = _find_button(result, "Подставить цену для цели")["callback"]
        clock.now = 600
        rejected = runtime.handle_callback(apply_callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert rejected["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert "снимок источников устарел" in rejected["message"].lower()
    assert "не подставил" in rejected["message"].lower()
    assert rejected["price_scenario"]["inputs"]["price"]["value"] == 500
    assert source.calls == [("3921245627", "user-1", False)]


def test_apply_callback_cannot_survive_source_refresh_or_new_sku():
    runtime, source = _runtime()
    source.product_service.products.append({
        "product_id": "p2",
        "offer_id": "hook-3",
        "sku": "3921245628",
        "name": "Другой товар",
    })
    original_load = source.load_snapshot

    def load_both_products(sku, user_id, force_refresh=False):
        snapshot = original_load(sku, user_id, force_refresh)
        if sku == "3921245628":
            snapshot["identity"].update({"product_id": "p2", "offer_id": "hook-3"})
            snapshot["product"]["name"] = "Другой товар"
        return snapshot

    source.load_snapshot = load_both_products
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"], user_id="user-1"
        )
        result = runtime.handle_text("20", user_id="user-1")
        apply_callback = _find_button(result, "Подставить цену для цели")["callback"]
        sid = result["price_planning_result"]["identity"]["scenario_id"]
        version = result["keyboard"]["buttons"][0]["callback"].split(":")[3]
        refreshed = runtime.handle_callback(f"upc:r:{sid}:{version}", user_id="user-1")
        stale_after_refresh = runtime.handle_callback(apply_callback, user_id="user-1")
        other_product = runtime.build_product_entry_button("user-1", "hook-3")
        selected_other = runtime.handle_callback(other_product["callback"], user_id="user-1")
        stale_after_sku_change = runtime.handle_callback(apply_callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert refreshed["price_scenario"]["inputs"]["price"]["value"] == 500
    assert stale_after_refresh["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert selected_other["price_scenario"]["identity"]["sku"] == "3921245628"
    assert stale_after_sku_change["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert source.calls == [
        ("3921245627", "user-1", False),
        ("3921245627", "user-1", True),
        ("3921245628", "user-1", False),
    ]


def test_expiring_calculator_session_releases_saved_price_planning_result():
    class Clock:
        now = 0

        def __call__(self):
            return self.now

    clock = Clock()
    runtime, source = _runtime(clock=clock, session_ttl_seconds=600)
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"], user_id="user-1"
        )
        result = runtime.handle_text("20", user_id="user-1")
        callback = _find_button(result, "Подставить цену для цели")["callback"]
        sid = result["price_planning_result"]["identity"]["scenario_id"]
        clock.now = 601
        stale = runtime.handle_callback(callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert sid not in runtime._scenarios
    assert ("user-1", "user-1::ozon::store-1") not in runtime._active
    assert source.calls == [("3921245627", "user-1", False)]


def test_late_apply_cannot_overwrite_scenario_after_return_to_editor():
    runtime, _ = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        scenario = runtime.handle_callback(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        runtime.handle_callback(
            _find_button(scenario, "Цена для целевой маржи")["callback"], user_id="user-1"
        )
        result = runtime.handle_text("20", user_id="user-1")
        callback = _find_button(result, "Подставить цену для цели")["callback"]
        proposed_price = result["price_planning_result"]["target"]["price"]
    finally:
        reset_current_tenant_user_id(token)

    calculating = Event()
    release = Event()
    original_calculate = runtime.scenario_service.calculate

    def blocked_calculate(inputs, **kwargs):
        if str(inputs.get("price")) == proposed_price:
            calculating.set()
            assert release.wait(5)
        return original_calculate(inputs, **kwargs)

    runtime.scenario_service.calculate = blocked_calculate
    late_result = {}

    def apply_late():
        thread_token = _activate()
        try:
            late_result["value"] = runtime.handle_callback(callback, user_id="user-1")
        finally:
            reset_current_tenant_user_id(thread_token)

    thread = Thread(target=apply_late)
    thread.start()
    assert calculating.wait(5)
    editor_token = _activate()
    try:
        returned = runtime.handle_callback(
            _find_button(result, "Назад к расчёту")["callback"], user_id="user-1"
        )
    finally:
        reset_current_tenant_user_id(editor_token)
        release.set()
    thread.join(5)
    assert not thread.is_alive()

    assert returned["price_scenario"]["inputs"]["price"]["value"] == 500
    assert late_result["value"]["status"] == "UNIT_PRICE_SCENARIO_STALE"
    final_token = _activate()
    try:
        active = runtime.handle_text("ignored", user_id="user-1")
    finally:
        reset_current_tenant_user_id(final_token)
    assert active["price_scenario"]["inputs"]["price"]["value"] == 500


def test_manual_inputs_survive_source_refresh_and_auto_points_can_be_restored():
    runtime, source = _runtime()
    token = _activate()
    try:
        result = _select_catalog_product(runtime)
        sid = result["price_scenario"]["scenario_id"]
        result = runtime.handle_callback(f"upc:e:{sid}:1:advertising_rate", user_id="user-1")
        result = runtime.handle_text("8", user_id="user-1")
        sid = result["price_scenario"]["scenario_id"]
        result = runtime.handle_callback(f"upc:e:{sid}:3:discount_points_rate", user_id="user-1")
        result = runtime.handle_text("10", user_id="user-1")
        sid = result["price_scenario"]["scenario_id"]
        refreshed = runtime.handle_callback(f"upc:r:{sid}:5", user_id="user-1")
        sid = refreshed["price_scenario"]["scenario_id"]
        restored = runtime.handle_callback(
            _find_button(refreshed, "Вернуть среднее баллов")["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert source.calls[-1] == ("3921245627", "user-1", True)
    assert refreshed["price_scenario"]["inputs"]["advertising_rate"]["value"] == 8.0
    assert refreshed["price_scenario"]["inputs"]["discount_points_rate"]["value"] == 10.0
    assert restored["price_scenario"]["inputs"]["discount_points_rate"]["value"] == 20.0
    assert "ручные допущения сохранены" in refreshed["message"]


def test_old_product_entry_button_cannot_cross_store_scope():
    runtime, source = _runtime()
    token = _activate("store-1")
    try:
        button = runtime.build_product_entry_button("user-1", "hook-2")
    finally:
        reset_current_tenant_user_id(token)
    other_token = _activate("store-2")
    try:
        stale = runtime.handle_callback(button["callback"], user_id="user-1")
    finally:
        reset_current_tenant_user_id(other_token)

    assert stale["status"] == "UNIT_PRICE_SCENARIO_STALE"
    assert source.calls == []


def test_catalog_selection_mode_is_bounded_and_store_scoped():
    runtime, source = _runtime(max_catalog_selections=1)
    token = _activate("store-1")
    try:
        runtime.begin_catalog_selection("user-1")
    finally:
        reset_current_tenant_user_id(token)

    other_user_token = set_current_tenant_user_id("user-2::ozon::store-2")
    try:
        runtime.begin_catalog_selection("user-2")
    finally:
        reset_current_tenant_user_id(other_user_token)

    first_user_token = _activate("store-1")
    try:
        assert runtime.has_catalog_selection("user-1") is False
        assert runtime.handle_catalog_selection("hook-2", user_id="user-1") is None
    finally:
        reset_current_tenant_user_id(first_user_token)

    assert source.calls == []


def test_leaving_calculator_clears_pending_text_stage():
    runtime, _ = _runtime()
    token = _activate()
    try:
        scenario = _select_catalog_product(runtime)
        sid = scenario["price_scenario"]["scenario_id"]
        runtime.handle_callback(f"upc:e:{sid}:1:price", user_id="user-1")
        runtime.clear_pending("user-1")
        text_result = runtime.handle_text("600", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert text_result is None


def test_current_unit_economics_detail_has_entry_to_same_calculator_runtime():
    from services.assistant_button_handler_service import AssistantButtonHandlerService

    class _Query:
        product_service = _Source().product_service

        def query(self, sku):
            return {
                "error": False,
                "available": True,
                "source": "current",
                "sku": sku,
                "missing_fields": [],
            }

        def format_response(self, _result):
            return "unit economics detail"

    runtime, _ = _runtime()
    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=_Query(),
        unit_price_calculator_runtime_service=runtime,
    )
    token = _activate()
    try:
        result = handler.handle("unit_economics:hook-2", user_id="user-1")
        scenario = handler.handle(
            result["keyboard"]["buttons"][0]["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["keyboard"]["buttons"][0]["text"] == "🧮 Планировать цену"
    assert result["keyboard"]["buttons"][0]["callback"].startswith("upc:p:")
    assert "Базовый режим" in result["message"]
    assert "допущений" in result["message"]
    assert scenario["price_scenario"]["identity"]["sku"] == "3921245627"


def test_opening_calculator_clears_pending_period_and_expense_text_stages():
    from services.assistant_button_handler_service import AssistantButtonHandlerService

    class _PendingFlow:
        def __init__(self):
            self.cleared = []

        def clear_pending_custom_period_input(self, user_id):
            self.cleared.append(("period", user_id))

        def clear_pending(self, user_id):
            self.cleared.append(("expense", user_id))

    runtime, _ = _runtime()
    query = type("Query", (), {})()
    query.product_service = _Source().product_service
    pending = _PendingFlow()
    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=query,
        unit_price_calculator_runtime_service=runtime,
        period_profit_runtime_service=pending,
        external_expense_runtime_service=pending,
    )
    token = _activate()
    try:
        result = handler.handle("unit_price_calculator", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert "Расширенная плановая экономика" in result["message"]
    assert "не меняет данные на Ozon" in result["message"]
    assert result["keyboard"]["buttons"] == [{
        "text": "hook-2",
        "callback": result["keyboard"]["buttons"][0]["callback"],
    }]
    assert result["keyboard"]["buttons"][0]["callback"].startswith("upc:s:")
    assert pending.cleared == [("period", "user-1"), ("expense", "user-1")]


def test_existing_unit_economics_menu_discoverably_opens_calculator():
    from services.assistant_button_handler_service import AssistantButtonHandlerService

    query = type("Query", (), {})()
    query.product_service = _Source().product_service
    runtime, _ = _runtime()
    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=query,
        unit_price_calculator_runtime_service=runtime,
    )
    token = _activate()
    try:
        menu = handler.handle("unit_economics", user_id="user-1")
        calculator_picker = handler.handle(
            menu["keyboard"]["buttons"][0]["callback"],
            user_id="user-1",
        )
        scenario = handler.handle(
            calculator_picker["keyboard"]["buttons"][0]["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert menu["keyboard"]["buttons"][0] == {
        "text": "🧮 Плановая экономика",
        "callback": "upc:m",
    }
    assert "Расширенная плановая экономика" in calculator_picker["message"]
    assert calculator_picker["keyboard"]["buttons"] == [{
        "text": "hook-2",
        "callback": calculator_picker["keyboard"]["buttons"][0]["callback"],
    }]
    assert calculator_picker["keyboard"]["buttons"][0]["callback"].startswith("upc:s:")
    assert scenario["price_scenario"]["identity"]["sku"] == "3921245627"


def test_factory_leaves_optional_calculator_disabled_when_sources_are_unavailable():
    from unit_price_scenario_factory import create_unit_price_scenario_runtime

    assert create_unit_price_scenario_runtime(
        core_components={},
        unit_economics_query=object(),
        keyboard_service=AssistantKeyboardService(),
    ) is None


def test_factory_wires_price_planner_to_same_forward_scenario_service():
    from unit_price_scenario_factory import create_unit_price_scenario_runtime

    query = type("Query", (), {})()
    query.product_service = object()
    query.current_economics_source = object()
    query.cost_service = object()
    runtime = create_unit_price_scenario_runtime(
        core_components={},
        unit_economics_query=query,
        keyboard_service=AssistantKeyboardService(),
    )

    assert isinstance(runtime.target_planning_service, UnitPriceTargetPlanningService)
    assert runtime.target_planning_service.scenario_service is runtime.scenario_service


def test_target_price_apply_works_through_public_assistant_handler():
    from services.assistant_button_handler_service import AssistantButtonHandlerService

    runtime, source = _runtime()

    class _Query:
        product_service = source.product_service

        def query(self, sku):
            return {
                "error": False,
                "available": True,
                "source": "current",
                "sku": sku,
                "missing_fields": [],
            }

        def format_response(self, _result):
            return "unit economics detail"

    handler = AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=_Query(),
        unit_price_calculator_runtime_service=runtime,
    )
    token = _activate()
    try:
        detail = handler.handle("unit_economics:hook-2", user_id="user-1")
        scenario = handler.handle(
            detail["keyboard"]["buttons"][0]["callback"], user_id="user-1"
        )
        scenario = handler.handle(
            _find_button(scenario, "Реклама 0%")["callback"], user_id="user-1"
        )
        handler.handle(
            _find_button(scenario, "Цена для целевой маржи")["callback"],
            user_id="user-1",
        )
        result = handler.handle_text("20", user_id="user-1")
        applied = handler.handle(
            _find_button(result, "Подставить цену для цели")["callback"],
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "UNIT_PRICE_TARGET_MARGIN_RESULT"
    assert applied["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert applied["price_scenario"]["inputs"]["price"]["provenance"] == "manual_seller_assumption"
    assert source.calls == [("3921245627", "user-1", False)]
