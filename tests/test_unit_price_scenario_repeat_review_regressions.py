from datetime import date, datetime, timedelta
from decimal import Decimal

from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.finance_service import FinanceService
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
    def __init__(self, seller_price=500, refreshed_price=550):
        self.calls = 0
        self.seller_price = seller_price
        self.refreshed_price = refreshed_price

    def get(self, **_kwargs):
        self.calls += 1
        return {
            "error": False,
            "seller_price": (
                self.seller_price if self.calls == 1 else self.refreshed_price
            ),
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


class _RawFinanceEvidence(FinanceService):
    def __init__(self, responses):
        self.responses = responses
        self._daily_accrual_cache = {}

    def _get_accruals_by_day(self, accrual_date):
        return self.responses[str(accrual_date)]


class _Costs:
    def __init__(self, cost=120):
        self.cost = cost

    def get_cost(self, product_id):
        return (product_id, "offer-1", "sku-1", self.cost, "RUB", "2026-10-01")


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


def _stack(clock, cost=120, seller_price=500, finance=None):
    current = _CurrentFacts(seller_price=seller_price)
    finance = finance or _Finance()
    source = UnitPriceScenarioSource(
        product_service=_Products(),
        current_economics_source=current,
        finance_service=finance,
        cost_service=_Costs(cost=cost),
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


def _handler(runtime, source):
    query = type("Query", (), {"product_service": source.product_service})()
    return AssistantButtonHandlerService(
        assistant=object(),
        keyboard_service=AssistantKeyboardService(),
        unit_economics_query=query,
        unit_price_calculator_runtime_service=runtime,
    )


def _select_through_handler(handler):
    picker = handler.handle("upc:m", user_id="user-1")
    assert picker["keyboard"]["buttons"]
    return handler.handle(
        picker["keyboard"]["buttons"][0]["callback"],
        user_id="user-1",
    )


def _edit_through_handler(handler, runtime, result, field, value):
    scenario = result["price_scenario"]
    session = runtime._scenarios[scenario["scenario_id"]]
    prompt = handler.handle(
        f"upc:e:{scenario['scenario_id']}:{session['version']}:{field}",
        user_id="user-1",
    )
    assert prompt["status"] == "UNIT_PRICE_SCENARIO_INPUT_PENDING"
    return handler.handle_text(str(value), user_id="user-1")


def _complete_manual_costs(handler, runtime, result):
    for field in (
        "logistics_per_unit",
        "last_mile_per_unit",
        "acquiring_per_unit",
        "advertising_rate",
    ):
        result = _edit_through_handler(handler, runtime, result, field, 0)
    return result


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


def test_unresolved_raw_sku_keeps_average_unknown_until_manual_fallback():
    start = date(2026, 9, 16)
    responses = {
        (start + timedelta(days=index)).isoformat(): {
            "error": False,
            "last_id": "",
            "pages_loaded": 1,
            "accruals": [],
        }
        for index in range(28)
    }
    responses["2026-10-13"]["accruals"] = [
        {
            "accrued_category": "POSTING",
            "unit_number": "known-sale",
            "posting": {
                "products": [{
                    "sku": "sku-1",
                    "commission": {
                        "sale_amount": {"amount": "100"},
                        "bonus": {"amount": "20"},
                    },
                }],
            },
        },
        {
            "accrued_category": "POSTING",
            "unit_number": "unresolved-sale",
            "posting": {
                "products": [{
                    "commission": {
                        "sale_amount": {"amount": "900"},
                        "bonus": {"amount": "0"},
                    },
                }],
            },
        },
    ]
    finance = _RawFinanceEvidence(responses)
    clock = _Clock()
    source, runtime, _ = _stack(clock, finance=finance)
    handler = _handler(runtime, source)

    tenant = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = _select_through_handler(handler)

        scenario = result["price_scenario"]
        assert result["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
        assert scenario["inputs"]["discount_points_rate"]["value"] is None
        assert scenario["inputs"]["discount_points_rate"]["provenance"] == "unknown"
        assert scenario["source_completeness"]["discount_points"]["complete"] is False
        assert scenario["calculated"]["profit"] is None

        result = _edit_through_handler(
            handler, runtime, result, "discount_points_rate", 20
        )
        for field in (
            "logistics_per_unit",
            "last_mile_per_unit",
            "acquiring_per_unit",
            "advertising_rate",
        ):
            result = _edit_through_handler(handler, runtime, result, field, 0)
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert result["price_scenario"]["available"] is True
    assert result["price_scenario"]["calculated"]["profit"] == 281
    assert result["price_scenario"]["inputs"]["discount_points_rate"]["provenance"] == (
        "manual_seller_assumption"
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


def test_unsupported_saved_cost_stays_editable_through_public_handler():
    clock = _Clock()
    source, runtime, _ = _stack(clock, cost=1e100)
    handler = _handler(runtime, source)
    tenant = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = _select_through_handler(handler)
        assert result.get("error") is False, result
        assert result["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
        assert result["keyboard"]["buttons"]
        assert result["price_scenario"]["inputs"]["cost"]["value"] is None
        assert result["price_scenario"]["inputs"]["cost"]["provenance"] == "unknown"
        assert result["price_scenario"]["source_completeness"]["cost"]["complete"] is False
        assert result["price_scenario"]["source_periods"]["cost_as_of"] is None
        assert result["price_scenario"]["calculated"]["profit"] is None
        assert "cost" in result["price_scenario"]["missing_inputs"]

        # Defensive presentation remains safe even if an old/injected session
        # still carries the unsupported raw amount before the user edits it.
        scenario_id = result["price_scenario"]["scenario_id"]
        session = runtime._scenarios[scenario_id]
        session["inputs"]["cost"] = 1e100
        shown = handler.handle_text("покажи расчёт", user_id="user-1")
        assert shown["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
        assert shown["keyboard"]["buttons"]
        assert "Себестоимость: не задано" in shown["message"]

        result = _edit_through_handler(handler, runtime, result, "cost", 120)
        result = _complete_manual_costs(handler, runtime, result)
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert result["price_scenario"]["available"] is True
    assert result["price_scenario"]["calculated"]["profit"] == 280
    assert source.cost_service.cost == 1e100


def test_unsupported_source_seller_price_can_be_replaced_manually():
    clock = _Clock()
    source, runtime, _ = _stack(clock, seller_price=1e100)
    handler = _handler(runtime, source)
    tenant = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = _select_through_handler(handler)
        assert result.get("error") is False, result
        assert result["status"] == "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
        assert result["keyboard"]["buttons"]
        assert result["price_scenario"]["inputs"]["price"]["value"] is None
        assert result["price_scenario"]["inputs"]["price"]["provenance"] == "unknown"
        assert result["price_scenario"]["source_completeness"]["seller_price"]["complete"] is False
        assert result["price_scenario"]["calculated"]["profit"] is None
        assert "price" in result["price_scenario"]["missing_inputs"]

        result = _edit_through_handler(handler, runtime, result, "price", 500)
        result = _complete_manual_costs(handler, runtime, result)
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["status"] == "UNIT_PRICE_SCENARIO_READY"
    assert result["price_scenario"]["available"] is True
    assert result["price_scenario"]["inputs"]["price"]["value"] == 500
    assert result["price_scenario"]["calculated"]["profit"] == 280


def test_formatters_fail_closed_for_unrepresentable_money_and_percent():
    _, runtime, _ = _stack(_Clock())

    assert runtime._money(Decimal("1e100")) == "не задано"
    assert runtime._money(Decimal("-1e100")) == "не задано"
    assert runtime._percent(Decimal("1e100")) == "не задано"
    assert runtime._percent("16.66666666666666666666666667") == "16,67%"
