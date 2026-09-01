from copy import deepcopy

from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)


class _Assistant:
    pass


class _Keyboard:

    def __init__(self):
        self.overview_calls = 0

    def build_product_decisions_keyboard(self, items, **kwargs):
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


class _Query:

    def __init__(self, overview):
        self.overview = deepcopy(overview)
        self.decision_history_service = None
        self.action_proposal_confirmation_service = None
        self.action_task_draft_service = None
        self.task_draft_readiness_service = None

    def query_all(self):
        return deepcopy(self.overview)


def _proposal(
    proposal_type,
    action_required,
):
    return {
        "available": True,
        "proposal_type": proposal_type,
        "action_required": action_required,
        "requires_confirmation": action_required,
        "execution_allowed": False,
        "automation_status": "PROHIBITED",
    }


def _decision(
    sku,
    decision_type,
    priority,
    proposal=None,
):
    result = {
        "error": False,
        "sku": sku,
        "decision_type": decision_type,
        "priority": priority,
    }
    if proposal is not None:
        result["action_proposal"] = deepcopy(proposal)
    return result


def _valid_overview():
    decisions = [
        _decision(
            "hook-1",
            "REPLENISH_HIGH_PRIORITY",
            "CRITICAL",
            _proposal("REVIEW_REPLENISHMENT", True),
        ),
        _decision(
            "hook-2",
            "HOLD_STOCK",
            "LOW",
            _proposal("MONITOR_ONLY", False),
        ),
        _decision(
            "hook-3",
            "INSUFFICIENT_DATA",
            "NONE",
        ),
    ]
    return {
        "error": False,
        "code": None,
        "total": 3,
        "counts": {
            "REPLENISH_HIGH_PRIORITY": 1,
            "HOLD_STOCK": 1,
            "INSUFFICIENT_DATA": 1,
        },
        "proposal_counts": {
            "REVIEW_REPLENISHMENT": 1,
            "MONITOR_ONLY": 1,
        },
        "actionable_proposals_count": 1,
        "decisions": decisions,
    }


def _handler(overview):
    keyboard = _Keyboard()
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        keyboard_service=keyboard,
        product_business_decision_query=_Query(overview),
    )
    return handler, keyboard


def _assert_invalid(overview):
    handler, keyboard = _handler(overview)

    result = handler.handle("product_decisions")

    assert result == {
        "error": True,
        "message": "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT",
    }
    assert keyboard.overview_calls == 0


def test_v991_decision_counts_must_match_rows_exactly():
    overview = _valid_overview()
    overview["counts"]["HOLD_STOCK"] = 2

    _assert_invalid(overview)


def test_v992_count_values_are_exact_positive_integers():
    for value in (True, "1", 0, -1):
        overview = _valid_overview()
        overview["counts"] = {
            "REPLENISH_HIGH_PRIORITY": value,
            "HOLD_STOCK": 1,
            "INSUFFICIENT_DATA": 1,
        }

        _assert_invalid(overview)


def test_v993_unknown_count_key_is_rejected():
    overview = _valid_overview()
    overview["counts"]["UNKNOWN_DECISION"] = 1

    _assert_invalid(overview)


def test_v994_duplicate_sku_cannot_create_duplicate_seller_buttons():
    overview = _valid_overview()
    overview["decisions"][1]["sku"] = "hook-1"

    _assert_invalid(overview)


def test_v995_decision_type_priority_pair_is_canonical():
    overview = _valid_overview()
    overview["decisions"][0]["priority"] = "LOW"

    _assert_invalid(overview)


def test_v996_proposal_counts_must_match_nested_proposals():
    overview = _valid_overview()
    overview["proposal_counts"] = {
        "REVIEW_REPLENISHMENT": 2,
        "MONITOR_ONLY": 1,
    }

    _assert_invalid(overview)


def test_v997_actionable_count_must_match_action_required_rows():
    overview = _valid_overview()
    overview["actionable_proposals_count"] = 2

    _assert_invalid(overview)


def test_v998_unsafe_or_malformed_nested_proposal_fails_closed():
    mutations = [
        ("action_required", "true"),
        ("execution_allowed", True),
        ("automation_status", "ALLOWED"),
        ("proposal_type", "UNKNOWN_PROPOSAL"),
    ]

    for field, value in mutations:
        overview = _valid_overview()
        overview["decisions"][0]["action_proposal"][field] = value

        _assert_invalid(overview)


def test_v999_valid_mixed_overview_preserves_exact_seller_statistics():
    overview = _valid_overview()
    handler, keyboard = _handler(overview)

    result = handler.handle("product_decisions")

    assert result["error"] is False
    assert result["overview"] == overview
    assert result["overview"]["total"] == 3
    assert result["overview"]["counts"] == {
        "REPLENISH_HIGH_PRIORITY": 1,
        "HOLD_STOCK": 1,
        "INSUFFICIENT_DATA": 1,
    }
    assert result["overview"]["proposal_counts"] == {
        "REVIEW_REPLENISHMENT": 1,
        "MONITOR_ONLY": 1,
    }
    assert result["overview"]["actionable_proposals_count"] == 1
    assert keyboard.overview_calls == 1
    assert len(result["keyboard"]["buttons"]) == 3


def test_v1000_validator_is_deterministic_and_does_not_mutate_overview():
    overview = _valid_overview()
    before = deepcopy(overview)
    handler, keyboard = _handler(overview)

    first = handler._validate_product_decisions_overview(overview)
    second = handler._validate_product_decisions_overview(overview)

    assert first is None
    assert second is None
    assert overview == before
    assert keyboard.overview_calls == 0
