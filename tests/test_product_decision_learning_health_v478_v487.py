from pathlib import Path

from product_decision_learning_health import (
    build_product_decision_learning_health,
)
from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)
from services.assistant_keyboard_service import (
    AssistantKeyboardService,
)


ROOT = Path(__file__).resolve().parents[1]


class _Assistant:
    def ask(self, message, user_id=None):
        return {"error": False, "message": message}


class _History:
    def __init__(self, summary):
        self._summary = dict(summary)

    def learning_summary(self):
        return dict(self._summary)


class _Query:
    def __init__(self, history):
        self.decision_history_service = history
        self.action_proposal_confirmation_service = None
        self.action_task_draft_service = None
        self.task_draft_readiness_service = None
        self.product_service = type(
            "_Products",
            (),
            {
                "load_products": lambda self: [{
                    "product_id": "1",
                    "offer_id": "sku-1",
                    "sku": "1001",
                }]
            },
        )()

    def query_all(self):
        return {
            "error": False,
            "total": 1,
            "counts": {"HOLD_STOCK": 1},
            "actionable_proposals_count": 0,
            "decisions": [{
                "error": False,
                "sku": "sku-1",
                "decision_type": "HOLD_STOCK",
                "priority": "LOW",
            }],
        }


def _summary(
    *,
    products=0,
    snapshots=0,
    useful=0,
    not_relevant=0,
    decreased=0,
    increased=0,
    changed=0,
):
    return {
        "error": False,
        "products_count": products,
        "decision_snapshots_count": snapshots,
        "feedback_count": useful + not_relevant,
        "feedback_counts": {
            "USEFUL": useful,
            "NOT_RELEVANT": not_relevant,
        },
        "outcome_count": decreased + increased + changed,
        "outcome_counts": {
            "PRIORITY_DECREASED": decreased,
            "PRIORITY_INCREASED": increased,
            "DECISION_CHANGED": changed,
        },
    }


def _handler(summary, builder=build_product_decision_learning_health):
    return AssistantButtonHandlerService(
        assistant=_Assistant(),
        keyboard_service=AssistantKeyboardService(),
        product_business_decision_query=_Query(_History(summary)),
        product_decision_learning_health_builder=builder,
    )


def test_v478_no_feedback_history_has_no_feedback_evidence_state():
    result = build_product_decision_learning_health(
        _summary(products=2, snapshots=4)
    )

    assert result["status"] == "PRODUCT_DECISION_LEARNING_HEALTH_READY"
    assert result["health_state"] == "NO_FEEDBACK_EVIDENCE"
    assert result["next_action"] == "COLLECT_USER_FEEDBACK"
    assert result["feedback_count"] == 0
    assert result["outcome_count"] == 0


def test_v479_feedback_without_later_outcomes_is_feedback_only():
    result = build_product_decision_learning_health(
        _summary(
            products=2,
            snapshots=5,
            useful=2,
            not_relevant=1,
        )
    )

    assert result["health_state"] == "FEEDBACK_ONLY"
    assert result["next_action"] == (
        "WAIT_FOR_LATER_DECISION_OBSERVATIONS"
    )
    assert result["feedback_count"] == 3
    assert result["outcome_count"] == 0


def test_v480_early_and_multi_product_samples_are_descriptive_only():
    early = build_product_decision_learning_health(
        _summary(
            products=1,
            snapshots=4,
            useful=2,
            decreased=1,
        )
    )
    mature = build_product_decision_learning_health(
        _summary(
            products=3,
            snapshots=10,
            useful=4,
            not_relevant=2,
            decreased=1,
            increased=1,
            changed=1,
        )
    )

    assert early["health_state"] == "EARLY_POST_FEEDBACK_SAMPLE"
    assert mature["health_state"] == (
        "MULTI_PRODUCT_DESCRIPTIVE_SAMPLE"
    )
    assert mature["next_action"] == "REVIEW_DESCRIPTIVE_PATTERNS"
    assert mature["causal_claim_allowed"] is False
    assert mature["success_rate_claim_allowed"] is False
    assert mature["profitability_claim_allowed"] is False


def test_v481_malformed_or_inconsistent_history_aggregates_fail_closed():
    mismatch = _summary(
        products=2,
        snapshots=5,
        useful=2,
    )
    mismatch["feedback_count"] = 3

    rejected = build_product_decision_learning_health(mismatch)

    assert rejected["error"] is True
    assert rejected["code"] == "LEARNING_HEALTH_FEEDBACK_TOTAL_MISMATCH"

    impossible = _summary(
        products=4,
        snapshots=2,
    )
    rejected_impossible = build_product_decision_learning_health(
        impossible
    )
    assert rejected_impossible["error"] is True
    assert rejected_impossible["code"] == (
        "LEARNING_HEALTH_HISTORY_COUNTS_INCONSISTENT"
    )


def test_v482_health_contract_never_exposes_success_rate_or_execution():
    result = build_product_decision_learning_health(
        _summary(
            products=3,
            snapshots=8,
            useful=3,
            not_relevant=1,
            changed=2,
        )
    )

    assert "human_reported_usefulness_rate" not in result
    assert "success_rate" not in result
    assert result["evidence_scope"] == (
        "DESCRIPTIVE_DECISION_HISTORY_ONLY"
    )
    assert result["decision_rule_update_allowed"] is False
    assert result["automatic_execution_allowed"] is False
    assert result["executed"] is False


def test_v483_handler_without_builder_remains_backward_compatible():
    handler = _handler(
        _summary(products=1, snapshots=1),
        builder=None,
    )

    menu = handler.handle("product_decisions")
    callbacks = [
        item["callback"]
        for item in menu["keyboard"]["buttons"]
    ]

    assert "product_decision_learning_summary" in callbacks
    assert "product_decision_learning_health" not in callbacks

    unavailable = handler.handle(
        "product_decision_learning_health"
    )
    assert unavailable["error"] is True
    assert unavailable["message"] == (
        "Качество данных обучения недоступно"
    )


def test_v484_menu_exposes_learning_health_only_when_builder_is_available():
    handler = _handler(
        _summary(products=2, snapshots=4)
    )

    menu = handler.handle("product_decisions")
    callbacks = [
        item["callback"]
        for item in menu["keyboard"]["buttons"]
    ]

    assert "product_decision_learning_summary" in callbacks
    assert "product_decision_learning_health" in callbacks


def test_v485_learning_health_callback_formats_counts_and_noncausal_warning():
    handler = _handler(
        _summary(
            products=3,
            snapshots=10,
            useful=4,
            not_relevant=2,
            decreased=1,
            increased=1,
            changed=1,
        )
    )

    response = handler.handle(
        "product_decision_learning_health"
    )
    message = response["message"]

    assert response["error"] is False
    assert response["executed"] is False
    assert "🩺 Качество данных обучения" in message
    assert "Товаров в истории: 3" in message
    assert "Оценок пользователя: 6" in message
    assert "👍 Полезно: 4" in message
    assert "👎 Неактуально: 2" in message
    assert "Наблюдений после оценок: 3" in message
    assert "Описательная выборка по нескольким товарам" in message
    assert "не доказывает причинность" in message
    assert "корректность решения" in message
    assert "прибыльность" in message


def test_v486_handler_rejects_forged_builder_that_enables_rule_update():
    def forged_builder(summary):
        result = build_product_decision_learning_health(summary)
        result["decision_rule_update_allowed"] = True
        return result

    handler = _handler(
        _summary(products=1, snapshots=1),
        builder=forged_builder,
    )

    response = handler.handle(
        "product_decision_learning_health"
    )

    assert response["error"] is True
    assert response["message"] == (
        "Качество данных обучения недоступно"
    )


def test_v487_telegram_factory_wires_canonical_learning_health_builder():
    text = (
        ROOT
        / "app"
        / "telegram_assistant_factory.py"
    ).read_text(encoding="utf-8")

    assert (
        "build_product_decision_learning_health"
        in text
    )
    assert (
        "product_decision_learning_health_builder="
        in text
    )
