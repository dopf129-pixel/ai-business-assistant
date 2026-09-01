from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)


class _Assistant:

    def ask(
        self,
        text,
        user_id=None,
    ):
        return {
            "error": False,
            "message": "ok",
        }


class _Keyboard:

    def __init__(
        self,
    ):
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
                    "callback":
                        "product_decision:"
                        + item["sku"],
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
        return {
            "buttons": [],
        }


class _Query:

    def __init__(
        self,
        overview,
        detail,
    ):
        self.overview = overview
        self.detail = detail
        self.decision_history_service = None
        self.action_proposal_confirmation_service = None
        self.action_task_draft_service = None
        self.task_draft_readiness_service = None

    def query_all(self):
        return self.overview

    def query(
        self,
        sku,
    ):
        return self.detail


def _handler(
    overview,
    detail,
):

    keyboard = _Keyboard()
    query = _Query(
        overview,
        detail,
    )
    handler = AssistantButtonHandlerService(
        assistant=_Assistant(),
        keyboard_service=keyboard,
        product_business_decision_query=query,
    )

    return handler, keyboard


def _valid_overview(
    decisions=None,
):

    items = (
        [
            {
                "error": False,
                "sku": "hook-2",
                "decision_type":
                    "REPLENISH_NORMAL",
                "priority": "HIGH",
            },
        ]
        if decisions is None
        else decisions
    )

    return {
        "error": False,
        "code": None,
        "total": len(
            items
        ),
        "counts": (
            {
                "REPLENISH_NORMAL":
                    len(
                        items
                    ),
            }
            if items
            else {}
        ),
        "proposal_counts": {},
        "actionable_proposals_count": 0,
        "decisions": items,
    }


def _valid_detail():

    return {
        "error": False,
        "code": None,
        "product_id": "101",
        "sku": "hook-2",
        "decision_type":
            "REPLENISH_NORMAL",
        "priority": "HIGH",
        "reasons": [
            "DAYS_OF_STOCK_LOW",
        ],
        "confidence": "HIGH",
        "missing_data": [],
        "decision_history_available":
            False,
    }


def test_v714_overview_explicit_failure_is_not_rewritten_as_empty_success():

    failure = {
        "error": True,
        "code":
            "PRODUCT_DECISION_QUERY_FAILED",
    }
    handler, keyboard = _handler(
        failure,
        _valid_detail(),
    )

    result = handler.handle(
        "product_decisions"
    )

    assert result["error"] is True
    assert result[
        "code"
    ] == "PRODUCT_DECISION_QUERY_FAILED"
    assert result[
        "message"
    ] == "Не удалось получить решения по товарам"
    assert keyboard.overview_calls == 0


def test_v715_malformed_overview_result_fails_closed():

    for malformed in (
        None,
        [],
        {},
        {
            "error": False,
        },
        {
            "error": "false",
            "decisions": [],
        },
    ):

        handler, keyboard = _handler(
            malformed,
            _valid_detail(),
        )

        result = handler.handle(
            "product_decisions"
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT",
        }
        assert keyboard.overview_calls == 0


def test_v716_overview_requires_consistent_explicit_evidence_shape():

    invalid_items = [
        {
            **_valid_overview(),
            "counts": [],
        },
        {
            **_valid_overview(),
            "total": 99,
        },
        {
            **_valid_overview(),
            "actionable_proposals_count":
                None,
        },
        {
            **_valid_overview(),
            "decisions": [
                "bad",
            ],
            "total": 1,
        },
        {
            **_valid_overview(),
            "decisions": [
                {
                    "sku": "hook-2",
                    "priority": "HIGH",
                },
            ],
            "total": 1,
        },
    ]

    for overview in invalid_items:

        handler, keyboard = _handler(
            overview,
            _valid_detail(),
        )

        result = handler.handle(
            "product_decisions"
        )

        assert result["error"] is True
        assert result[
            "message"
        ] == "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
        assert keyboard.overview_calls == 0


def test_v717_valid_empty_overview_remains_empty_success():

    handler, keyboard = _handler(
        _valid_overview(
            decisions=[]
        ),
        _valid_detail(),
    )

    result = handler.handle(
        "product_decisions"
    )

    assert result == {
        "error": False,
        "message": "Товары не найдены",
    }
    assert keyboard.overview_calls == 0


def test_v718_valid_overview_still_builds_seller_navigation():

    handler, keyboard = _handler(
        _valid_overview(),
        _valid_detail(),
    )

    result = handler.handle(
        "product_decisions"
    )

    assert result["error"] is False
    assert result[
        "overview"
    ]["total"] == 1
    assert keyboard.overview_calls == 1
    assert result[
        "keyboard"
    ]["buttons"][0][
        "callback"
    ] == "product_decision:hook-2"


def test_v719_malformed_detail_result_fails_closed():

    for malformed in (
        None,
        [],
        {},
        {
            "error": False,
        },
        {
            "error": "false",
            "sku": "hook-2",
        },
    ):

        handler, keyboard = _handler(
            _valid_overview(),
            malformed,
        )

        result = handler.handle(
            "product_decision:hook-2"
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_PRODUCT_DECISION_DETAIL_RESULT",
        }
        assert keyboard.feedback_calls == 0


def test_v720_explicit_detail_failure_remains_failure_without_feedback():

    failure = {
        "error": True,
        "code": "SKU_NOT_FOUND",
        "product_id": None,
        "sku": "missing",
        "decision_type":
            "INSUFFICIENT_DATA",
        "priority": "NONE",
        "reasons": [],
        "confidence": "LOW",
        "missing_data": [
            "sku",
        ],
    }
    handler, keyboard = _handler(
        _valid_overview(),
        failure,
    )

    result = handler.handle(
        "product_decision:missing"
    )

    assert result["error"] is True
    assert result[
        "message"
    ] == "Товар не найден"
    assert result[
        "decision"
    ] is failure
    assert keyboard.feedback_calls == 0


def test_v721_valid_detail_preserves_read_only_decision_card():

    detail = _valid_detail()
    handler, keyboard = _handler(
        _valid_overview(),
        detail,
    )

    result = handler.handle(
        "product_decision:hook-2"
    )

    assert result["error"] is False
    assert result[
        "decision"
    ] == detail
    assert "Решение по товару" in result[
        "message"
    ]
    assert keyboard.feedback_calls == 0
