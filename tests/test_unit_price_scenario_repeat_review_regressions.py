from datetime import datetime

from services.assistant_keyboard_service import AssistantKeyboardService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_unit_price_calculator_runtime_service import (
    TelegramUnitPriceCalculatorRuntimeService,
)
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_scenario_source import UnitPriceScenarioSource


class _Clock:
    def __init__(self, now=0):
        self.now = now

    def __call__(self):
        return self.now


class _Products:
    def load_products(self):
        return [{
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "sku-1",
            "name": "Test product",
        }]


class _CurrentFacts:
    def __init__(self):
        self.calls = 0

    def get(self, **_kwargs):
        self.calls += 1
        return {
            "error": False,
            "seller_price": 500 if self.calls == 1 else 550,
            "commission_rate": 15,
        }


class _Finance:
    def __init__(self):
        self.read_sessions = 0

    def prepare_read_session(self, _start, _end):
        return None

    def begin_read_session(self):
        self.read_sessions += 1

    def get_daily_discount_points_evidence(self, day, sku):
        records = []
        if day == "2026-09-16":
            sale, points = (
                ("300", "50")
                if self.read_sessions == 1
                else ("7", "1")
            )
            records = [{
                "posting_number": "posting-1",
                "sku": sku,
                "sale_amount": sale,
                "discount_points": points,
            }]
        return {"error": False, "complete": True, "records": records}


class _Costs:
    def get_cost(self, product_id):
        return (product_id, "offer-1", "sku-1", 120, "RUB", "2026-10-01")


class _TaxPolicy:
    def get_policy(self):
        return {
            "error": False,
            "configured": True,
            "policy": {
                "mode": "USN_INCOME",
                "tax_rate": 6,
                "minimum_tax_rate": 1,
            },
        }


def _stack(clock):
    current = _CurrentFacts()
    finance = _Finance()
    source = UnitPriceScenarioSource(
        product_service=_Products(),
        current_economics_source=current,
        finance_service=finance,
        cost_service=_Costs(),
        tax_configuration_service=_TaxPolicy(),
        clock=lambda: datetime(2026, 10, 14, 12),
        cache_clock=clock,
        cache_ttl_seconds=600,
    )
    runtime = TelegramUnitPriceCalculatorRuntimeService(
        source=source,
        scenario_service=UnitPriceScenarioService(TaxService()),
        keyboard_service=AssistantKeyboardService(),
        clock=clock,
        session_ttl_seconds=600,
    )
    return source, runtime, current


def _open(runtime):
    runtime.begin_catalog_selection("user-1")
    callback = runtime.build_catalog_product_callback("user-1", "offer-1")
    return runtime.handle_callback(callback, user_id="user-1")


def _edit(runtime, result, field, value):
    scenario_id = result["price_scenario"]["scenario_id"]
    session = runtime._scenarios[scenario_id]
    prompt = runtime.handle_callback(
        f"upc:e:{scenario_id}:{session['version']}:{field}",
        user_id="user-1",
    )
    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    return runtime.handle_text(str(value), user_id="user-1")


def test_complete_weighted_average_survives_source_math_and_runtime_flow():
    clock = _Clock()
    _, runtime, _ = _stack(clock)
    tenant = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = _open(runtime)
        assert result["price_scenario"]["inputs"]["discount_points_rate"]["value"] == (
            16.666666666666668
        )
        for field in (
            "logistics_per_unit",
            "last_mile_per_unit",
            "acquiring_per_unit",
            "advertising_rate",
        ):
            result = _edit(runtime, result, field, 0)
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert result["price_scenario"]["available"] is True
    calculated = result["price_scenario"]["calculated"]
    assert calculated["tax"] == 25
    assert calculated["profit"] == 280
    assert calculated["margin_percent"] == 56
    assert "discount_points_rate" not in result["price_scenario"]["invalid_inputs"]

    tenant = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        scenario_id = result["price_scenario"]["scenario_id"]
        result = _edit(runtime, result, "discount_points_rate", 9)
        scenario_id = result["price_scenario"]["scenario_id"]
        refreshed = runtime.handle_callback(
            f"upc:r:{scenario_id}:{runtime._scenarios[scenario_id]['version']}",
            user_id="user-1",
        )
        assert refreshed["price_scenario"]["inputs"]["discount_points_rate"]["value"] == 9
        scenario_id = refreshed["price_scenario"]["scenario_id"]
        restored = runtime.handle_callback(
            f"upc:b:{scenario_id}:{runtime._scenarios[scenario_id]['version']}",
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert restored["price_scenario"]["available"] is True
    assert restored["price_scenario"]["inputs"]["discount_points_rate"]["value"] == (
        14.285714285714286
    )


def test_cache_hit_does_not_reset_source_age_and_successful_refresh_does():
    clock = _Clock()
    _, runtime, current = _stack(clock)
    tenant = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        original = _open(runtime)
        clock.now = 590
        cached = _open(runtime)
        scenario_id = cached["price_scenario"]["scenario_id"]
        cached = runtime.handle_callback(
            f"upc:z:{scenario_id}:{runtime._scenarios[scenario_id]['version']}",
            user_id="user-1",
        )
        scenario_id = cached["price_scenario"]["scenario_id"]
        touched = runtime.handle_text("покажи расчёт", user_id="user-1")
        assert cached["price_scenario"]["source_freshness"] == {
            "status": "FRESH",
            "age_seconds": 590,
            "ttl_seconds": 600,
        }
        assert touched["price_scenario"]["source_freshness"]["age_seconds"] == 590

        clock.now = 600
        expires_at_ttl = runtime.handle_callback(
            f"upc:v:{scenario_id}:{runtime._scenarios[scenario_id]['version']}",
            user_id="user-1",
        )
        assert expires_at_ttl["price_scenario"]["source_freshness"] == {
            "status": "STALE",
            "age_seconds": 600,
            "ttl_seconds": 600,
        }

        clock.now = 610
        stale = runtime.handle_callback(
            f"upc:v:{scenario_id}:{runtime._scenarios[scenario_id]['version']}",
            user_id="user-1",
        )
        stale_assumptions = runtime.handle_callback(
            f"upc:a:{scenario_id}:{runtime._scenarios[scenario_id]['version']}",
            user_id="user-1",
        )
        assert stale["price_scenario"]["source_freshness"] == {
            "status": "STALE",
            "age_seconds": 610,
            "ttl_seconds": 600,
        }
        assert stale["price_scenario"]["comparison"]["available"] is False
        assert "источники устарели" in stale_assumptions["message"]
        assert current.calls == 1

        refreshed = runtime.handle_callback(
            f"upc:r:{scenario_id}:{runtime._scenarios[scenario_id]['version']}",
            user_id="user-1",
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert original["price_scenario"]["source_freshness"]["age_seconds"] == 0
    assert refreshed["price_scenario"]["source_freshness"] == {
        "status": "FRESH",
        "age_seconds": 0,
        "ttl_seconds": 600,
    }
    assert refreshed["price_scenario"]["comparison"]["price"] == 550
    assert refreshed["price_scenario"]["inputs"]["advertising_rate"]["value"] == 0
    assert current.calls == 2
