from services.assistant_main_flow_service import (
    AssistantMainFlowService,
)
from services.assistant_orchestrator_business_service import (
    AssistantOrchestratorBusinessService,
)
from services.assistant_response_builder_service import (
    AssistantResponseBuilderService,
)


class _BusinessFlow:

    def __init__(self, result):
        self.result = result

    def process(
        self,
        text,
        report,
        context=None,
        user_id=None,
    ):
        return self.result


class _BusinessService:

    def __init__(self, result):
        self.result = result

    def handle(
        self,
        text,
        report,
        context=None,
        user_id=None,
    ):
        return self.result


class _ResponseService:

    def __init__(self, result):
        self.result = result

    def build(self, result):
        return self.result


def _intent(command):
    return {
        "error": False,
        "intent": command,
        "command": command,
    }


def _orchestrator(result):
    return AssistantOrchestratorBusinessService(
        business_flow_service=(
            _BusinessFlow(result)
        )
    )


def test_v591_orchestrator_rejects_malformed_top_level_results():

    cases = [
        None,
        [],
        {},
        {
            "error": None,
        },
        {
            "error": "false",
        },
    ]

    for downstream in cases:
        result = _orchestrator(
            downstream
        ).handle(
            "текст",
            {},
        )

        assert result == {
            "error": True,
            "message":
                "INVALID_BUSINESS_FLOW_RESULT",
        }


def test_v591_orchestrator_preserves_explicit_downstream_error():

    downstream = {
        "error": True,
        "message":
            "INVALID_TASK_RESULT",
    }

    result = _orchestrator(
        downstream
    ).handle(
        "текст",
        {},
    )

    assert result is downstream


def test_v592_contradictory_execute_failure_never_claims_success():

    result = _orchestrator(
        {
            "error": False,
            "intent": _intent(
                "execute"
            ),
            "execution": {
                "error": True,
                "message":
                    "execution failed",
            },
        }
    ).handle(
        "выполни",
        {},
    )

    assert result["error"] is True
    assert (
        result["message"]
        ==
        "execution failed"
    )
    assert (
        result["message"]
        !=
        "Действие выполнено"
    )


def test_v592_malformed_execute_result_fails_closed():

    result = _orchestrator(
        {
            "error": False,
            "intent": _intent(
                "execute"
            ),
            "execution": {
                "error": False,
                "message": "",
            },
        }
    ).handle(
        "выполни",
        {},
    )

    assert result["error"] is True
    assert (
        result["message"]
        ==
        "INVALID_EXECUTION_RESULT"
    )


def test_v593_task_read_nested_error_cannot_become_success():

    result = _orchestrator(
        {
            "error": False,
            "intent": _intent(
                "task_status"
            ),
            "task_status": {
                "error": True,
                "message":
                    "status failed",
            },
        }
    ).handle(
        "статус",
        {},
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_TASK_RESULT",
    }


def test_v594_plan_count_mismatch_fails_closed():

    result = _orchestrator(
        {
            "error": False,
            "intent": _intent(
                "actions"
            ),
            "plan": [
                {
                    "action": {
                        "type": "sales",
                    }
                }
            ],
            "count": 0,
        }
    ).handle(
        "план",
        {},
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_BUSINESS_PLAN_RESULT",
    }


def test_v594_valid_plan_shape_stays_compatible():

    result = _orchestrator(
        {
            "error": False,
            "intent": _intent(
                "actions"
            ),
            "plan": [
                {
                    "action": {
                        "type": "sales",
                    }
                }
            ],
            "count": 1,
        }
    ).handle(
        "план",
        {},
    )

    assert result == {
        "error": False,
        "message":
            "Бизнес-план создан",
        "actions": [
            {
                "action": {
                    "type": "sales",
                }
            }
        ],
        "count": 1,
    }


def test_v595_main_flow_rejects_malformed_business_service_result():

    service = AssistantMainFlowService(
        business_service=(
            _BusinessService({})
        )
    )

    result = service.process(
        "текст",
        {},
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_BUSINESS_SERVICE_RESULT",
    }


def test_v595_main_flow_rejects_malformed_response_service_result():

    service = AssistantMainFlowService(
        business_service=(
            _BusinessService(
                {
                    "error": False,
                    "message": "ok",
                }
            )
        ),
        response_service=(
            _ResponseService({})
        ),
    )

    result = service.process(
        "текст",
        {},
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_RESPONSE_RESULT",
    }


def test_v596_response_builder_preserves_explicit_upstream_error():

    service = (
        AssistantResponseBuilderService()
    )

    result = service.build(
        {
            "error": True,
            "message":
                "downstream failed",
        }
    )

    assert result == {
        "error": True,
        "message":
            "downstream failed",
    }


def test_v596_response_builder_rejects_non_boolean_error_marker():

    service = (
        AssistantResponseBuilderService()
    )

    result = service.build(
        {
            "error": "false",
            "count": 0,
        }
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_RESPONSE_INPUT",
    }
