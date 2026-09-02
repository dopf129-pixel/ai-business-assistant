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


class _Keyboard:
    def __init__(self):
        self.overview_calls = 0
        self.feedback_calls = 0

    def build_product_decisions_keyboard(
        self,
        items,
        **kwargs,
    ):
        self.overview_calls += 1
        return {
            "buttons": [
                {
                    "text": item["text"],
                    "callback": "product_decision:" + item["sku"],
                }
                for item in items
            ],
        }

    def build_product_decision_feedback_keyboard(
        self,
        sku,
        proposal=None,
    ):
        self.feedback_calls += 1
        return {"buttons": []}


class _Query:
    def __init__(
        self,
        overview=None,
        detail=None,
        overview_error=None,
        detail_error=None,
    ):
        self.overview = (
            _valid_overview()
            if overview is None
            else overview
        )
        self.detail = (
            _valid_detail()
            if detail is None
            else detail
        )
        self.overview_error = overview_error
        self.detail_error = detail_error
        self.overview_calls = 0
        self.detail_calls = []
        self.decision_history_service = None
        self.action_proposal_confirmation_service = None
        self.action_task_draft_service = None
        self.task_draft_readiness_service = None

    def query_all(self):
        self.overview_calls += 1
        if self.overview_error is not None:
            raise self.overview_error
        return self.overview

    def query(self, sku):
        self.detail_calls.append(sku)
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail


def _valid_overview():
    return {
        "error": False,
        "code": None,
        "total": 1,
        "counts": {
            "REPLENISH_NORMAL": 1,
        },
        "proposal_counts": {},
        "actionable_proposals_count": 0,
        "decisions": [
            {
                "error": False,
                "sku": "hook-2",
                "decision_type": "REPLENISH_NORMAL",
                "priority": "HIGH",
            },
        ],
    }


def _valid_detail():
    return {
        "error": False,
        "code": None,
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "REPLENISH_NORMAL",
        "priority": "HIGH",
        "reasons": ["DAYS_OF_STOCK_LOW"],
        "confidence": "HIGH",
        "missing_data": [],
        "decision_history_available": False,
    }


def _handler(query):
    keyboard = _Keyboard()
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        keyboard_service=keyboard,
        product_business_decision_query=query,
    )
    return handler, keyboard


def test_v1071_overview_runtime_exception_is_contained_locally():
    query = _Query(
        overview_error=RuntimeError("secret overview detail")
    )
    handler, keyboard = _handler(query)

    result = handler.handle("product_decisions")

    assert result == {
        "error": True,
        "code": "PRODUCT_DECISION_QUERY_FAILED",
        "message": "Не удалось получить решения по товарам",
    }
    assert "secret overview detail" not in str(result)
    assert query.overview_calls == 1
    assert keyboard.overview_calls == 0


def test_v1072_overview_typeerror_is_not_retried():
    query = _Query(
        overview_error=TypeError("internal overview type error")
    )
    handler, _ = _handler(query)

    result = handler.handle("product_decisions")

    assert result["error"] is True
    assert result["code"] == "PRODUCT_DECISION_QUERY_FAILED"
    assert query.overview_calls == 1


def test_v1073_detail_runtime_exception_is_contained_locally():
    query = _Query(
        detail_error=RuntimeError("secret detail path")
    )
    handler, keyboard = _handler(query)

    result = handler.handle("product_decision:hook-2")

    assert result == {
        "error": True,
        "code": "PRODUCT_DECISION_QUERY_FAILED",
        "message": "Не удалось получить решение по товару",
    }
    assert "secret detail path" not in str(result)
    assert query.detail_calls == ["hook-2"]
    assert keyboard.feedback_calls == 0


def test_v1074_detail_typeerror_is_not_retried():
    query = _Query(
        detail_error=TypeError("internal detail type error")
    )
    handler, _ = _handler(query)

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is True
    assert result["code"] == "PRODUCT_DECISION_QUERY_FAILED"
    assert query.detail_calls == ["hook-2"]


def test_v1075_overview_domain_failure_reaches_adapter_unchanged():
    query = _Query(
        overview_error=OSError("private backend detail")
    )
    handler, keyboard = _handler(query)
    adapter = AssistantTelegramAdapter(
        assistant=_Assistant(),
        keyboard_service=keyboard,
        button_handler=handler,
    )

    result = adapter.handle_button(
        "product_decisions",
        user_id=1001,
    )

    assert result["code"] == "PRODUCT_DECISION_QUERY_FAILED"
    assert result["message"] == "Не удалось получить решения по товарам"
    assert result["message"] != "TELEGRAM_BUTTON_DISPATCH_FAILED"
    assert query.overview_calls == 1


def test_v1076_detail_domain_failure_reaches_adapter_unchanged():
    query = _Query(
        detail_error=OSError("private product detail")
    )
    handler, keyboard = _handler(query)
    adapter = AssistantTelegramAdapter(
        assistant=_Assistant(),
        keyboard_service=keyboard,
        button_handler=handler,
    )

    result = adapter.handle_button(
        "product_decision:hook-2",
        user_id=1001,
    )

    assert result["code"] == "PRODUCT_DECISION_QUERY_FAILED"
    assert result["message"] == "Не удалось получить решение по товару"
    assert result["message"] != "TELEGRAM_BUTTON_DISPATCH_FAILED"
    assert query.detail_calls == ["hook-2"]


def test_v1077_explicit_overview_failure_semantics_are_preserved():
    explicit = {
        "error": True,
        "code": "PRODUCT_DECISION_SOURCE_UNAVAILABLE",
    }
    query = _Query(overview=explicit)
    handler, keyboard = _handler(query)

    result = handler.handle("product_decisions")

    assert result["error"] is True
    assert result["code"] == "PRODUCT_DECISION_SOURCE_UNAVAILABLE"
    assert result["message"] == "Не удалось получить решения по товарам"
    assert query.overview_calls == 1
    assert keyboard.overview_calls == 0


def test_v1078_valid_overview_is_unchanged():
    overview = _valid_overview()
    query = _Query(overview=overview)
    handler, keyboard = _handler(query)

    result = handler.handle("product_decisions")

    assert result["error"] is False
    assert result["overview"] is overview
    assert query.overview_calls == 1
    assert keyboard.overview_calls == 1


def test_v1079_explicit_detail_failure_semantics_are_preserved():
    explicit = {
        "error": True,
        "code": "SKU_NOT_FOUND",
        "product_id": None,
        "sku": "missing",
        "decision_type": "INSUFFICIENT_DATA",
        "priority": "NONE",
        "reasons": [],
        "confidence": "LOW",
        "missing_data": ["sku"],
    }
    query = _Query(detail=explicit)
    handler, keyboard = _handler(query)

    result = handler.handle("product_decision:missing")

    assert result["error"] is True
    assert result["decision"] is explicit
    assert result["message"] == "Товар не найден"
    assert query.detail_calls == ["missing"]
    assert keyboard.feedback_calls == 0


def test_v1080_valid_detail_is_unchanged_and_read_only():
    detail = _valid_detail()
    query = _Query(detail=detail)
    handler, keyboard = _handler(query)

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert result["decision"] == detail
    assert "Решение по товару" in result["message"]
    assert query.detail_calls == ["hook-2"]
    assert keyboard.feedback_calls == 0
