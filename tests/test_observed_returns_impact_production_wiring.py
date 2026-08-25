from datetime import datetime, timezone

from product_returns_finance_impact_factory import (
    create_product_returns_finance_impact_query,
)
from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)
from services.assistant_keyboard_service import (
    AssistantKeyboardService,
)


class StubProductService:
    def load_products(self):
        return [{
            "product_id": "1",
            "offer_id": "hook-2",
            "sku": "3921245627",
        }]


class StubUnitEconomicsQuery:
    product_service = StubProductService()


class StubOzonClient:
    pass


class StubAttributionQuery:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


class FakeAssistant:
    pass


def _impact_result(complete=False):
    return {
        "error": False,
        "requested_sku": "hook-2",
        "period_days": 30,
        "complete": complete,
        "categories": {
            "customer_non_buyout": {
                "label": "Невыкуп",
                "event_posting_count": 93,
                "finance_matched_posting_count": 82,
                "finance_coverage_percent": 88.17,
                "observed_cost_total": 4668.6,
                "observed_cost_average": 56.93,
            },
            "customer_return": {
                "label": "Возврат покупателя",
                "event_posting_count": 2,
                "finance_matched_posting_count": 2,
                "finance_coverage_percent": 100.0,
                "observed_cost_total": 108.73,
                "observed_cost_average": 54.36,
            },
        },
    }


def test_factory_builds_product_query_from_production_dependencies():
    query = create_product_returns_finance_impact_query(
        core_components={
            "unit_economics_query": StubUnitEconomicsQuery(),
        },
        ozon_client=StubOzonClient(),
        period_days=14,
        now_provider=lambda: datetime(
            2026, 8, 25, tzinfo=timezone.utc
        ),
    )

    assert query.product_service is StubUnitEconomicsQuery.product_service
    assert query.period_days == 14
    assert (
        query.attribution_query_service
        .facts_source
        .ozon_client
        .__class__
        is StubOzonClient
    )


def test_factory_rejects_missing_product_wiring():
    try:
        create_product_returns_finance_impact_query(
            core_components={},
            ozon_client=StubOzonClient(),
        )
    except RuntimeError as error:
        assert "Unit Economics" in str(error)
    else:
        raise AssertionError("RuntimeError expected")


def test_menu_lists_products_and_selects_impact_query():
    query = type("Query", (), {})()
    query.product_service = StubProductService()
    query.calls = []
    query.query = lambda sku: (
        query.calls.append(sku) or _impact_result()
    )
    handler = AssistantButtonHandlerService(
        assistant=FakeAssistant(),
        keyboard_service=AssistantKeyboardService(),
        returns_finance_impact_query=query,
    )

    menu = handler.handle("returns_finance_impact")
    result = handler.handle(
        "returns_finance_impact:hook-2"
    )

    assert menu["keyboard"]["buttons"] == [{
        "text": "3921245627",
        "callback": (
            "returns_finance_impact:3921245627"
        ),
    }]
    assert query.calls == ["hook-2"]
    assert result["error"] is False
    assert "Наблюдаемые расходы: 4668.60 ₽" in result["message"]


def test_incomplete_impact_never_claims_adjusted_profit():
    query = type("Query", (), {})()
    query.product_service = StubProductService()
    query.query = lambda sku: _impact_result(
        complete=False
    )
    handler = AssistantButtonHandlerService(
        assistant=FakeAssistant(),
        keyboard_service=AssistantKeyboardService(),
        returns_finance_impact_query=query,
    )

    result = handler.handle(
        "returns_finance_impact:hook-2"
    )

    assert "Скорректированная прибыль:\n—" in result["message"]
    assert "Данные неполные" in result["message"]
    assert "экстраполяция" in result["message"]


def test_unknown_cost_is_rendered_as_dash():
    result = _impact_result()
    result["categories"][
        "customer_non_buyout"
    ]["observed_cost_total"] = None

    query = type("Query", (), {})()
    query.product_service = StubProductService()
    query.query = lambda sku: result
    handler = AssistantButtonHandlerService(
        assistant=FakeAssistant(),
        keyboard_service=AssistantKeyboardService(),
        returns_finance_impact_query=query,
    )

    response = handler.handle(
        "returns_finance_impact:hook-2"
    )

    assert "Наблюдаемые расходы: —" in response["message"]
