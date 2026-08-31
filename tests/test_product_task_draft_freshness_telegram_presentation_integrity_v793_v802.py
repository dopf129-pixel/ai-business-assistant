from app.telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter,
)


class _ButtonHandler:
    def __init__(self, result):
        self.result = result

    def handle(self, callback, user_id=None):
        return self.result


class _Keyboard:
    def build_main_keyboard(self):
        return []


def _adapter(result):
    return AssistantTelegramAdapter(
        assistant=None,
        keyboard_service=_Keyboard(),
        button_handler=_ButtonHandler(result),
    )


def _summary(**overrides):
    summary = {
        "freshness_counts": {
            "FRESH": 1,
            "STALE": 0,
            "UNKNOWN": 2,
        },
        "freshness_coverage_counts": {
            "SOURCE_PROVEN": 1,
            "OBSERVED_ONLY": 1,
            "NO_EVIDENCE": 1,
        },
        "freshness_source_timestamp_counts": {
            "VERIFIED": 1,
            "UNVERIFIED": 0,
            "ABSENT": 2,
        },
        "freshness_refresh_counts": {
            "SOURCE_TIMESTAMP_REQUIRED": 2,
            "VERIFY_SOURCE_TIMESTAMP": 0,
            "REFRESH_SOURCE_DATA": 0,
        },
    }
    summary.update(overrides)
    return {
        "error": False,
        "message": "Черновики",
        "readiness_summary": summary,
        "executed": False,
    }


def _detail(**readiness_overrides):
    readiness = {
        "freshness": {
            "status": "UNKNOWN",
            "decision_snapshot": {
                "age_seconds": None,
            },
            "reasons": [
                "SALES_TIMESTAMP_UNKNOWN",
            ],
        },
        "freshness_coverage": {
            "components": {
                "sales": {
                    "evidence_state": "OBSERVED_ONLY",
                    "source_timestamp_state": "ABSENT",
                },
            },
        },
        "freshness_refresh_guidance": {
            "targets": [
                {
                    "component": "sales",
                    "action": "SOURCE_TIMESTAMP_REQUIRED",
                },
            ],
        },
        "execution_ready": False,
        "executed": False,
    }
    readiness.update(readiness_overrides)
    return {
        "error": False,
        "message": "Черновик",
        "readiness": readiness,
        "executed": False,
    }


FAILURE = {
    "error": True,
    "message": "INVALID_TELEGRAM_TASK_DRAFT_FRESHNESS_RESULT",
    "executed": False,
}


def test_v793_malformed_readiness_summary_fails_closed():
    for malformed in ([], "bad", 1):
        result = {
            "error": False,
            "message": "Черновики",
            "readiness_summary": malformed,
            "executed": False,
        }
        assert _adapter(result).handle_button(
            "product_action_task_drafts"
        ) == FAILURE


def test_v794_partial_or_invalid_freshness_counts_cannot_invent_zero():
    invalid_maps = (
        {
            "FRESH": 1,
            "STALE": 0,
        },
        {
            "FRESH": 1,
            "STALE": 0,
            "UNKNOWN": -1,
        },
        {
            "FRESH": True,
            "STALE": 0,
            "UNKNOWN": 0,
        },
    )

    for counts in invalid_maps:
        result = _summary(
            freshness_counts=counts
        )
        response = _adapter(result).handle_button(
            "product_action_task_drafts"
        )
        assert response == FAILURE
        assert "Неизвестно: 0" not in response["message"]


def test_v795_legitimate_zero_freshness_counts_remain_visible_success():
    result = _summary(
        freshness_counts={
            "FRESH": 0,
            "STALE": 0,
            "UNKNOWN": 0,
        }
    )

    response = _adapter(result).handle_button(
        "product_action_task_drafts"
    )

    assert response["error"] is False
    assert "Свежие: 0" in response["message"]
    assert "Устарели: 0" in response["message"]
    assert "Неизвестно: 0" in response["message"]
    assert response["executed"] is False


def test_v796_malformed_optional_summary_evidence_maps_fail_closed():
    cases = (
        (
            "freshness_coverage_counts",
            {
                "SOURCE_PROVEN": 1,
                "OBSERVED_ONLY": 0,
            },
        ),
        (
            "freshness_source_timestamp_counts",
            {
                "VERIFIED": 1,
                "UNVERIFIED": 0,
                "ABSENT": False,
            },
        ),
        (
            "freshness_refresh_counts",
            {
                "SOURCE_TIMESTAMP_REQUIRED": 0,
                "VERIFY_SOURCE_TIMESTAMP": 0,
                "REFRESH_SOURCE_DATA": -1,
            },
        ),
    )

    for field, value in cases:
        result = _summary(**{field: value})
        assert _adapter(result).handle_button(
            "product_action_task_drafts"
        ) == FAILURE


def test_v797_absent_optional_summary_evidence_is_not_invented():
    result = _summary()
    del result["readiness_summary"][
        "freshness_coverage_counts"
    ]
    del result["readiness_summary"][
        "freshness_source_timestamp_counts"
    ]
    del result["readiness_summary"][
        "freshness_refresh_counts"
    ]

    response = _adapter(result).handle_button(
        "product_action_task_drafts"
    )

    assert response["error"] is False
    assert "Свежесть данных:" in response["message"]
    assert "Доказательства свежести:" not in response["message"]
    assert "Проверка timestamp источника:" not in response["message"]
    assert "Что требуется:" not in response["message"]


def test_v798_malformed_detail_readiness_or_freshness_fails_closed():
    for readiness in (
        [],
        {
            "freshness": [],
        },
        {
            "freshness": {
                "status": "MAYBE",
                "decision_snapshot": {
                    "age_seconds": None,
                },
                "reasons": [],
            },
        },
    ):
        result = {
            "error": False,
            "message": "Черновик",
            "readiness": readiness,
            "executed": False,
        }
        assert _adapter(result).handle_button(
            "product_task_draft:view:d1"
        ) == FAILURE


def test_v799_invalid_age_or_reason_fails_closed_without_formatter_exception():
    cases = (
        {
            "freshness": {
                "status": "UNKNOWN",
                "decision_snapshot": {
                    "age_seconds": "secret",
                },
                "reasons": [],
            },
        },
        {
            "freshness": {
                "status": "UNKNOWN",
                "decision_snapshot": {
                    "age_seconds": None,
                },
                "reasons": [
                    "UNKNOWN_INTERNAL_REASON",
                ],
            },
        },
    )

    for readiness in cases:
        result = {
            "error": False,
            "message": "Черновик",
            "readiness": readiness,
            "executed": False,
        }
        response = _adapter(result).handle_button(
            "product_task_draft:view:d1"
        )
        assert response == FAILURE
        assert "secret" not in str(response)


def test_v800_malformed_coverage_component_fails_closed():
    result = _detail(
        freshness_coverage={
            "components": {
                "sales": {
                    "evidence_state": "SOURCE_PROVEN",
                },
            },
        },
    )

    assert _adapter(result).handle_button(
        "product_task_draft:view:d1"
    ) == FAILURE


def test_v801_malformed_refresh_guidance_target_fails_closed():
    result = _detail(
        freshness_refresh_guidance={
            "targets": [
                {
                    "component": "sales",
                    "action": "EXECUTE_NOW",
                },
            ],
        },
    )

    response = _adapter(result).handle_button(
        "product_task_draft:view:d1"
    )

    assert response == FAILURE
    assert "EXECUTE_NOW" not in str(response)


def test_v802_valid_unknown_evidence_remains_read_only_success():
    result = _detail()

    response = _adapter(result).handle_button(
        "product_task_draft:view:d1"
    )

    assert response["error"] is False
    assert "свежесть неизвестна" in response["message"]
    assert "есть только время наблюдения" in response["message"]
    assert "нужен достоверный timestamp источника" in response["message"]
    assert "время данных продаж неизвестно" in response["message"]
    assert response["executed"] is False
