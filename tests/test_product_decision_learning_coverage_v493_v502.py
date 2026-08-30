from pathlib import Path

from product_decision_learning_coverage_queue import (
    build_product_decision_learning_coverage_queue,
)
from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)
from services.assistant_keyboard_service import (
    AssistantKeyboardService,
)


ROOT = Path(__file__).resolve().parents[1]


def _record(
    sku,
    *,
    feedback=None,
    outcome=None,
    decision_type="HOLD_STOCK",
):
    return {
        "sku": sku,
        "decision_type": decision_type,
        "priority": "LOW",
        "feedback": feedback,
        "outcome": outcome,
    }


def _rows():
    return [
        {
            "sku": "sku-feedback",
            "history": [
                _record("sku-feedback", feedback=None),
            ],
        },
        {
            "sku": "sku-empty",
            "history": [],
        },
        {
            "sku": "sku-wait",
            "history": [
                _record("sku-wait", feedback="USEFUL"),
                _record(
                    "sku-wait",
                    feedback="USEFUL",
                    outcome="PRIORITY_DECREASED",
                ),
            ],
        },
    ]


class _Assistant:
    def ask(self, message, user_id=None):
        return {"error": False, "message": message}


class _History:
    def __init__(self, histories):
        self.histories = histories
        self.calls = []

    def history(self, sku, limit=None):
        self.calls.append(sku)
        rows = [dict(item) for item in self.histories.get(sku, [])]
        return rows[:limit] if limit is not None else rows

    def learning_summary(self):
        return {
            "error": False,
            "products_count": len(self.histories),
            "decision_snapshots_count": sum(
                len(items)
                for items in self.histories.values()
            ),
            "feedback_count": 0,
            "feedback_counts": {
                "USEFUL": 0,
                "NOT_RELEVANT": 0,
            },
            "outcome_count": 0,
            "outcome_counts": {
                "PRIORITY_DECREASED": 0,
                "PRIORITY_INCREASED": 0,
                "DECISION_CHANGED": 0,
            },
        }


class _Products:
    def __init__(self, skus):
        self.skus = list(skus)

    def load_products(self):
        return [
            {
                "product_id": str(index),
                "offer_id": sku,
                "sku": str(1000 + index),
            }
            for index, sku in enumerate(self.skus, start=1)
        ]


class _Query:
    def __init__(self, histories, skus):
        self.decision_history_service = _History(histories)
        self.product_service = _Products(skus)
        self.action_proposal_confirmation_service = None
        self.action_task_draft_service = None
        self.task_draft_readiness_service = None
        self.query_calls = 0

    def query(self, sku):
        self.query_calls += 1
        raise AssertionError("coverage surface must not query decisions")

    def query_all(self):
        return {
            "error": False,
            "total": len(self.product_service.skus),
            "counts": {},
            "actionable_proposals_count": 0,
            "decisions": [
                {
                    "error": False,
                    "sku": sku,
                    "decision_type": "HOLD_STOCK",
                    "priority": "LOW",
                }
                for sku in self.product_service.skus
            ],
        }


def _handler(
    histories,
    skus,
    builder=build_product_decision_learning_coverage_queue,
):
    query = _Query(histories, skus)
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        keyboard_service=AssistantKeyboardService(),
        product_business_decision_query=query,
        product_decision_learning_coverage_builder=builder,
    )
    return handler, query


def test_v493_queue_prioritizes_feedback_then_no_history_then_waiting():
    result = build_product_decision_learning_coverage_queue(
        _rows()
    )

    assert result["status"] == (
        "PRODUCT_DECISION_LEARNING_COVERAGE_QUEUE_READY"
    )
    assert [
        item["coverage_state"]
        for item in result["items"]
    ] == [
        "NEEDS_USER_FEEDBACK",
        "NO_DECISION_HISTORY",
        "WAITING_FOR_LATER_OBSERVATION",
    ]
    assert result["counts"] == {
        "NEEDS_USER_FEEDBACK": 1,
        "NO_DECISION_HISTORY": 1,
        "WAITING_FOR_LATER_OBSERVATION": 1,
    }


def test_v494_queue_sort_is_deterministic_inside_learning_attention_rank():
    rows = [
        {
            "sku": "z-sku",
            "history": [_record("z-sku")],
        },
        {
            "sku": "a-sku",
            "history": [_record("a-sku")],
        },
    ]

    result = build_product_decision_learning_coverage_queue(
        rows
    )

    assert [item["sku"] for item in result["items"]] == [
        "a-sku",
        "z-sku",
    ]
    assert all(
        item["learning_attention_rank"] == 1
        for item in result["items"]
    )


def test_v495_latest_feedback_waits_for_future_observation_even_with_old_outcome():
    result = build_product_decision_learning_coverage_queue([
        {
            "sku": "sku-1",
            "history": [
                _record("sku-1", feedback="USEFUL"),
                _record(
                    "sku-1",
                    feedback="NOT_RELEVANT",
                    outcome="PRIORITY_DECREASED",
                ),
            ],
        }
    ])

    item = result["items"][0]

    assert item["coverage_state"] == (
        "WAITING_FOR_LATER_OBSERVATION"
    )
    assert item["historical_outcome_count"] == 1
    assert item["reason_codes"] == [
        "LATEST_DECISION_FEEDBACK_RECORDED",
        "FUTURE_DECISION_OBSERVATION_NOT_YET_AVAILABLE",
    ]


def test_v496_current_missing_feedback_wins_over_historical_outcome():
    result = build_product_decision_learning_coverage_queue([
        {
            "sku": "sku-1",
            "history": [
                _record("sku-1", feedback=None),
                _record(
                    "sku-1",
                    feedback="USEFUL",
                    outcome="DECISION_CHANGED",
                ),
            ],
        }
    ])

    item = result["items"][0]

    assert item["coverage_state"] == "NEEDS_USER_FEEDBACK"
    assert item["historical_outcome_count"] == 1


def test_v497_malformed_duplicate_or_cross_sku_history_fails_closed():
    duplicate = build_product_decision_learning_coverage_queue([
        {"sku": "same", "history": []},
        {"sku": "same", "history": []},
    ])
    assert duplicate["error"] is True
    assert duplicate["code"] == "LEARNING_COVERAGE_CONTEXT_INVALID"

    mismatch = build_product_decision_learning_coverage_queue([
        {
            "sku": "sku-a",
            "history": [_record("sku-b")],
        }
    ])
    assert mismatch["error"] is True
    assert mismatch["code"] == (
        "LEARNING_COVERAGE_HISTORY_SKU_MISMATCH"
    )


def test_v498_queue_is_learning_attention_not_business_priority():
    result = build_product_decision_learning_coverage_queue(
        _rows()
    )

    assert result["business_priority_claimed"] is False
    assert result["causal_claim_allowed"] is False
    assert result["success_rate_claim_allowed"] is False
    assert result["profitability_claim_allowed"] is False
    assert result["decision_rule_update_allowed"] is False
    assert result["automatic_execution_allowed"] is False
    assert result["executed"] is False
    assert all(
        item["business_priority_claimed"] is False
        and item["executed"] is False
        for item in result["items"]
    )


def test_v499_handler_reads_persisted_history_without_querying_decision_engine():
    histories = {
        "sku-a": [_record("sku-a")],
        "sku-b": [_record("sku-b", feedback="USEFUL")],
    }
    handler, query = _handler(
        histories,
        ["sku-a", "sku-b"],
    )

    response = handler.handle(
        "product_decision_learning_coverage"
    )

    assert response["error"] is False
    assert query.query_calls == 0
    assert query.decision_history_service.calls == [
        "sku-a",
        "sku-b",
    ]
    assert response["executed"] is False


def test_v500_menu_button_is_conditional_on_explicit_builder_di():
    histories = {
        "sku-a": [_record("sku-a")],
    }

    handler, _ = _handler(
        histories,
        ["sku-a"],
    )
    menu = handler.handle("product_decisions")
    callbacks = [
        item["callback"]
        for item in menu["keyboard"]["buttons"]
    ]
    assert "product_decision_learning_coverage" in callbacks

    no_builder, _ = _handler(
        histories,
        ["sku-a"],
        builder=None,
    )
    old_menu = no_builder.handle("product_decisions")
    old_callbacks = [
        item["callback"]
        for item in old_menu["keyboard"]["buttons"]
    ]
    assert "product_decision_learning_coverage" not in old_callbacks


def test_v501_seller_message_explains_learning_queue_not_business_priority():
    histories = {
        "sku-feedback": [_record("sku-feedback")],
        "sku-empty": [],
        "sku-wait": [
            _record("sku-wait", feedback="USEFUL"),
        ],
    }
    handler, _ = _handler(
        histories,
        ["sku-feedback", "sku-empty", "sku-wait"],
    )

    response = handler.handle(
        "product_decision_learning_coverage"
    )
    message = response["message"]

    assert "🧭 Очередь сбора обратной связи" in message
    assert "Нужна оценка: 1" in message
    assert "Нет истории решения: 1" in message
    assert "Ждём следующего наблюдения: 1" in message
    assert "sku-feedback — Нужна оценка текущего решения" in message
    assert "не бизнес-приоритет товаров" in message
    assert "не оценивает прибыльность" in message
    assert "не запускает никаких действий" in message


def test_v501_handler_rejects_forged_builder_business_priority_claim():
    def forged_builder(rows):
        result = build_product_decision_learning_coverage_queue(
            rows
        )
        result["business_priority_claimed"] = True
        return result

    handler, _ = _handler(
        {"sku-a": [_record("sku-a")]},
        ["sku-a"],
        builder=forged_builder,
    )

    response = handler.handle(
        "product_decision_learning_coverage"
    )

    assert response["error"] is True
    assert response["message"] == (
        "Очередь сбора обратной связи недоступна"
    )


def test_v501_handler_rejects_forged_counts_or_learning_rank():
    def forged_counts(rows):
        result = build_product_decision_learning_coverage_queue(
            rows
        )
        result["counts"] = dict(result["counts"])
        result["counts"]["NEEDS_USER_FEEDBACK"] += 1
        return result

    counts_handler, _ = _handler(
        {"sku-a": [_record("sku-a")]},
        ["sku-a"],
        builder=forged_counts,
    )
    assert counts_handler.handle(
        "product_decision_learning_coverage"
    )["error"] is True

    def forged_rank(rows):
        result = build_product_decision_learning_coverage_queue(
            rows
        )
        result["items"] = [
            dict(item)
            for item in result["items"]
        ]
        result["items"][0]["learning_attention_rank"] = 99
        return result

    rank_handler, _ = _handler(
        {"sku-a": [_record("sku-a")]},
        ["sku-a"],
        builder=forged_rank,
    )
    assert rank_handler.handle(
        "product_decision_learning_coverage"
    )["error"] is True


def test_v502_telegram_factory_wires_canonical_coverage_builder():
    text = (
        ROOT
        / "app"
        / "telegram_assistant_factory.py"
    ).read_text(encoding="utf-8")

    assert "build_product_decision_learning_coverage_queue" in text
    assert "product_decision_learning_coverage_builder=(" in text


def test_v503_coverage_keyboard_maps_states_to_existing_decision_route():
    keyboard = AssistantKeyboardService()

    result = keyboard.build_product_decision_learning_coverage_keyboard([
        {
            "sku": "sku-feedback",
            "coverage_state": "NEEDS_USER_FEEDBACK",
        },
        {
            "sku": "sku-empty",
            "coverage_state": "NO_DECISION_HISTORY",
        },
        {
            "sku": "sku-wait",
            "coverage_state": "WAITING_FOR_LATER_OBSERVATION",
        },
    ])

    assert result["error"] is False
    assert [item["text"] for item in result["buttons"]] == [
        "Оценить решение — sku-feedback",
        "Открыть решение — sku-empty",
        "Проверить решение — sku-wait",
        "🎯 Все решения",
    ]
    assert [item["callback"] for item in result["buttons"]] == [
        "product_decision:sku-feedback",
        "product_decision:sku-empty",
        "product_decision:sku-wait",
        "product_decisions",
    ]
    assert all(
        not item["callback"].startswith("product_decision_feedback:")
        for item in result["buttons"]
    )


def test_v504_coverage_handler_adds_navigation_without_querying_decisions():
    histories = {
        "sku-feedback": [_record("sku-feedback")],
        "sku-empty": [],
        "sku-wait": [_record("sku-wait", feedback="USEFUL")],
    }
    handler, query = _handler(
        histories,
        ["sku-feedback", "sku-empty", "sku-wait"],
    )

    response = handler.handle("product_decision_learning_coverage")

    assert response["error"] is False
    assert query.query_calls == 0
    assert [item["callback"] for item in response["keyboard"]["buttons"]] == [
        "product_decision:sku-feedback",
        "product_decision:sku-empty",
        "product_decision:sku-wait",
        "product_decisions",
    ]
    assert response["executed"] is False


def test_v505_coverage_handler_rejects_forged_navigation_callback():
    class ForgedKeyboard(AssistantKeyboardService):
        def build_product_decision_learning_coverage_keyboard(
            self,
            items,
            limit=10,
        ):
            return {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [{
                    "text": "Опасная кнопка",
                    "callback": "product_decision_feedback:useful:sku-a",
                }],
            }

    query = _Query(
        {"sku-a": [_record("sku-a")]},
        ["sku-a"],
    )
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        keyboard_service=ForgedKeyboard(),
        product_business_decision_query=query,
        product_decision_learning_coverage_builder=(
            build_product_decision_learning_coverage_queue
        ),
    )

    response = handler.handle("product_decision_learning_coverage")

    assert response["error"] is True
    assert response["message"] == (
        "Очередь сбора обратной связи недоступна"
    )
    assert response["executed"] is False
    assert query.query_calls == 0


def test_v506_coverage_keyboard_fails_closed_on_invalid_navigation_item():
    keyboard = AssistantKeyboardService()

    invalid_state = keyboard.build_product_decision_learning_coverage_keyboard([
        {
            "sku": "sku-a",
            "coverage_state": "BUSINESS_PRIORITY",
        }
    ])
    empty_sku = keyboard.build_product_decision_learning_coverage_keyboard([
        {
            "sku": "",
            "coverage_state": "NEEDS_USER_FEEDBACK",
        }
    ])
    invalid_items = keyboard.build_product_decision_learning_coverage_keyboard(
        {"sku": "sku-a"}
    )

    assert invalid_state["error"] is True
    assert invalid_state["buttons"] == []
    assert empty_sku["error"] is True
    assert empty_sku["buttons"] == []
    assert invalid_items["error"] is True
    assert invalid_items["buttons"] == []


def test_v507_coverage_navigation_is_bounded_to_visible_top_ten():
    rows = [
        {
            "sku": f"sku-{index:02d}",
            "history": [_record(f"sku-{index:02d}")],
        }
        for index in range(12)
    ]
    result = build_product_decision_learning_coverage_queue(rows)
    keyboard = AssistantKeyboardService()

    navigation = keyboard.build_product_decision_learning_coverage_keyboard(
        result["items"]
    )

    callbacks = [item["callback"] for item in navigation["buttons"]]
    assert callbacks[:-1] == [
        f"product_decision:sku-{index:02d}"
        for index in range(10)
    ]
    assert callbacks[-1] == "product_decisions"
    assert len(callbacks) == 11


def test_v508_coverage_navigation_preserves_read_only_queue_boundary():
    histories = {
        "sku-a": [_record("sku-a")],
    }
    handler, query = _handler(histories, ["sku-a"])

    response = handler.handle("product_decision_learning_coverage")

    assert query.query_calls == 0
    assert response["learning_coverage"]["automatic_execution_allowed"] is False
    assert response["learning_coverage"]["executed"] is False
    assert all(
        button["callback"] in {
            "product_decision:sku-a",
            "product_decisions",
        }
        for button in response["keyboard"]["buttons"]
    )


def test_v505_non_dict_coverage_builder_payload_fails_closed():
    handler, query = _handler(
        {"sku-a": [_record("sku-a")]},
        ["sku-a"],
        builder=lambda rows: [],
    )

    response = handler.handle("product_decision_learning_coverage")

    assert response["error"] is True
    assert response["message"] == (
        "Очередь сбора обратной связи недоступна"
    )
    assert query.query_calls == 0
