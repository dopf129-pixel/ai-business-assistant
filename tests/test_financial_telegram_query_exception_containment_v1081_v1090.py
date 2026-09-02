from app.telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)
from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)


class _Assistant:
    def ask(self, text, user_id=None):
        return {
            "error": False,
            "message": "ok",
        }


class _ProductService:
    def __init__(self, products=None, error=None):
        self.products = (
            [{"product_id": "101", "offer_id": "hook-2"}]
            if products is None
            else products
        )
        self.error = error
        self.calls = 0

    def load_products(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.products


class _Keyboard:
    def __init__(self):
        self.unit_calls = 0
        self.returns_calls = 0

    def build_unit_economics_keyboard(self, skus):
        self.unit_calls += 1
        return {
            "buttons": [
                {
                    "text": sku,
                    "callback": "unit_economics:" + sku,
                }
                for sku in skus
            ],
        }

    def build_returns_finance_impact_keyboard(self, skus):
        self.returns_calls += 1
        return {
            "buttons": [
                {
                    "text": sku,
                    "callback": "returns_finance_impact:" + sku,
                }
                for sku in skus
            ],
        }


class _UnitQuery:
    def __init__(
        self,
        result=None,
        query_error=None,
        format_error=None,
        product_error=None,
    ):
        self.result = _unit_success() if result is None else result
        self.query_error = query_error
        self.format_error = format_error
        self.product_service = _ProductService(error=product_error)
        self.query_calls = []
        self.format_calls = 0

    def query(self, sku):
        self.query_calls.append(sku)
        if self.query_error is not None:
            raise self.query_error
        return self.result

    def format_response(self, result):
        self.format_calls += 1
        if self.format_error is not None:
            raise self.format_error
        if result.get("error"):
            return result.get("message") or "Юнит-экономика недоступна"
        return "Unit Economics — " + str(result.get("sku"))


class _ReturnsQuery:
    def __init__(
        self,
        result=None,
        query_error=None,
        product_error=None,
    ):
        self.result = _returns_success() if result is None else result
        self.query_error = query_error
        self.product_service = _ProductService(error=product_error)
        self.query_calls = []

    def query(self, sku):
        self.query_calls.append(sku)
        if self.query_error is not None:
            raise self.query_error
        return self.result


def _unit_success():
    return {
        "error": False,
        "available": True,
        "source": "historical",
        "sku": "hook-2",
        "unit_price": 96.0,
        "cost": 21.0,
        "marketplace_fees": 34.0,
        "tax": 5.76,
        "net_profit_per_unit": 35.1,
        "margin_percent": 36.56,
        "missing_fields": [
            "advertising",
            "storage",
            "returns",
        ],
    }


def _returns_success():
    return {
        "error": False,
        "complete": False,
        "missing_data": [
            "finance_postings_unmatched",
        ],
        "categories": {
            "customer_non_buyout": {
                "label": "Невыкуп",
                "event_posting_count": 1,
                "finance_matched_posting_count": 0,
                "finance_coverage_percent": 0.0,
                "observed_cost_total": None,
                "observed_cost_average": None,
            },
            "customer_return": {
                "label": "Возврат",
                "event_posting_count": 0,
                "finance_matched_posting_count": 0,
                "finance_coverage_percent": 100.0,
                "observed_cost_total": 0.0,
                "observed_cost_average": None,
            },
        },
        "product_id": "101",
        "sku": "hook-2",
        "finance_sku": "3921245627",
        "requested_sku": "hook-2",
        "period_days": 30,
        "period_complete_days": True,
    }


def _handler(unit=None, returns=None):
    keyboard = _Keyboard()
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        keyboard_service=keyboard,
        unit_economics_query=unit,
        returns_finance_impact_query=returns,
    )
    return handler, keyboard


def test_v1081_unit_products_exception_is_contained_without_secret():
    unit = _UnitQuery(
        product_error=RuntimeError("secret unit product source")
    )
    handler, keyboard = _handler(unit=unit)

    result = handler.handle("unit_economics")

    assert result == {
        "error": True,
        "code": "UNIT_ECONOMICS_PRODUCTS_QUERY_FAILED",
        "message": "Юнит-экономика недоступна",
    }
    assert "secret unit product source" not in str(result)
    assert unit.product_service.calls == 1
    assert keyboard.unit_calls == 0


def test_v1082_returns_products_exception_is_contained_without_secret():
    returns = _ReturnsQuery(
        product_error=RuntimeError("secret returns product source")
    )
    handler, keyboard = _handler(returns=returns)

    result = handler.handle("returns_finance_impact")

    assert result == {
        "error": True,
        "code": "RETURNS_FINANCE_IMPACT_PRODUCTS_QUERY_FAILED",
        "message": "Расходы на возвраты недоступны",
    }
    assert "secret returns product source" not in str(result)
    assert returns.product_service.calls == 1
    assert keyboard.returns_calls == 0


def test_v1083_unit_query_exception_is_one_shot_and_unformatted():
    unit = _UnitQuery(
        query_error=OSError("private unit economics backend")
    )
    handler, _ = _handler(unit=unit)

    result = handler.handle("unit_economics:hook-2")

    assert result["error"] is True
    assert result["code"] == "UNIT_ECONOMICS_QUERY_FAILED"
    assert result["message"] == "Юнит-экономика недоступна"
    assert "private unit economics backend" not in str(result)
    assert unit.query_calls == ["hook-2"]
    assert unit.format_calls == 0


def test_v1084_returns_query_exception_is_one_shot():
    returns = _ReturnsQuery(
        query_error=OSError("private returns finance backend")
    )
    handler, _ = _handler(returns=returns)

    result = handler.handle("returns_finance_impact:hook-2")

    assert result["error"] is True
    assert result["code"] == "RETURNS_FINANCE_IMPACT_QUERY_FAILED"
    assert result["message"] == "Расходы на возвраты недоступны"
    assert "private returns finance backend" not in str(result)
    assert returns.query_calls == ["hook-2"]


def test_v1085_unit_formatter_exception_is_contained_locally():
    unit = _UnitQuery(
        format_error=ValueError("private formatter detail")
    )
    handler, _ = _handler(unit=unit)

    result = handler.handle("unit_economics:hook-2")

    assert result == {
        "error": True,
        "code": "UNIT_ECONOMICS_FORMAT_FAILED",
        "message": "Юнит-экономика недоступна",
    }
    assert "private formatter detail" not in str(result)
    assert unit.query_calls == ["hook-2"]
    assert unit.format_calls == 1


def test_v1086_unit_typeerror_is_not_retried():
    unit = _UnitQuery(
        query_error=TypeError("internal unit type error")
    )
    handler, _ = _handler(unit=unit)

    result = handler.handle("unit_economics:hook-2")

    assert result["code"] == "UNIT_ECONOMICS_QUERY_FAILED"
    assert unit.query_calls == ["hook-2"]


def test_v1087_returns_typeerror_is_not_retried():
    returns = _ReturnsQuery(
        query_error=TypeError("internal returns type error")
    )
    handler, _ = _handler(returns=returns)

    result = handler.handle("returns_finance_impact:hook-2")

    assert result["code"] == "RETURNS_FINANCE_IMPACT_QUERY_FAILED"
    assert returns.query_calls == ["hook-2"]


def test_v1088_financial_domain_failure_reaches_adapter_unchanged():
    unit = _UnitQuery(
        query_error=RuntimeError("secret adapter unit error")
    )
    handler, keyboard = _handler(unit=unit)
    adapter = AssistantTelegramAdapter(
        assistant=_Assistant(),
        keyboard_service=keyboard,
        button_handler=handler,
    )

    result = adapter.handle_button(
        "unit_economics:hook-2",
        user_id=1001,
    )

    assert result["code"] == "UNIT_ECONOMICS_QUERY_FAILED"
    assert result["message"] == "Юнит-экономика недоступна"
    assert result["message"] != "TELEGRAM_BUTTON_DISPATCH_FAILED"
    assert unit.query_calls == ["hook-2"]


def test_v1089_valid_unit_menu_and_detail_remain_compatible():
    unit = _UnitQuery()
    handler, keyboard = _handler(unit=unit)

    menu = handler.handle("unit_economics")
    detail = handler.handle("unit_economics:hook-2")

    assert menu["error"] is False
    assert menu["message"] == "Выберите товар:"
    assert keyboard.unit_calls == 1
    assert detail["error"] is False
    assert detail["unit_economics"] is unit.result
    assert detail["message"] == "Unit Economics — hook-2"
    assert unit.query_calls == ["hook-2"]
    assert unit.format_calls == 1


def test_v1090_valid_returns_menu_and_detail_remain_compatible():
    returns = _ReturnsQuery()
    handler, keyboard = _handler(returns=returns)

    menu = handler.handle("returns_finance_impact")
    detail = handler.handle("returns_finance_impact:hook-2")

    assert menu["error"] is False
    assert menu["message"] == "Выберите товар:"
    assert keyboard.returns_calls == 1
    assert detail["error"] is False
    assert detail["returns_finance_impact"] is returns.result
    assert "Данные неполные" in detail["message"]
    assert returns.query_calls == ["hook-2"]
