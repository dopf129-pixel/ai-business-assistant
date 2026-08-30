import pytest

from services.assistant_action_plan_executor_service import (
    AssistantActionPlanExecutorService,
)


_DEFAULT = object()


class _Generator:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def generate(self, plan):
        self.calls.append(plan)
        if self.error:
            raise self.error
        return self.result


class _Priority:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def resolve(self, action):
        self.calls.append(action)
        if self.error:
            raise self.error
        if callable(self.result):
            return self.result(action)
        return self.result


class _Execution:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def execute(self, actions):
        self.calls.append(actions)
        if self.error:
            raise self.error
        return self.result


def _default_priority(action):
    return {
        "error": False,
        "action": dict(action),
    }


def _default_execution():
    return {
        "error": False,
        "executed": [{
            "action": {"type": "sales"},
            "result": {"error": False},
        }],
        "count": 1,
    }


def _service(
    generated,
    priority=_DEFAULT,
    executed=_DEFAULT,
    generator_error=None,
    priority_error=None,
    execution_error=None,
):
    generator = _Generator(
        generated,
        error=generator_error,
    )
    priority_service = _Priority(
        _default_priority
        if priority is _DEFAULT
        else priority,
        error=priority_error,
    )
    execution = _Execution(
        _default_execution()
        if executed is _DEFAULT
        else executed,
        error=execution_error,
    )

    return (
        AssistantActionPlanExecutorService(
            priority_service=priority_service,
            action_generator_service=generator,
            execution_service=execution,
        ),
        generator,
        priority_service,
        execution,
    )


def _valid_generated():
    return {
        "error": False,
        "actions": [{
            "type": "sales",
            "title": "Проверить продажи",
        }],
    }


def _failure(code):
    return {
        "error": True,
        "message": code,
        "actions": [],
        "count": 0,
    }


def test_v568_success_preserves_existing_result_shape():
    service, generator, priority, execution = _service(
        _valid_generated()
    )

    result = service.execute_plan([
        {"type": "sales"}
    ])

    assert result == {
        "error": False,
        "actions": [{
            "action": {"type": "sales"},
            "result": {"error": False},
        }],
        "count": 1,
    }
    assert len(generator.calls) == 1
    assert len(priority.calls) == 1
    assert len(execution.calls) == 1


def test_v568_generator_explicit_error_is_returned_and_stops_pipeline():
    generated = {
        "error": True,
        "message": "generator failed",
    }
    service, _, priority, execution = _service(generated)

    result = service.execute_plan([])

    assert result is generated
    assert priority.calls == []
    assert execution.calls == []


@pytest.mark.parametrize(
    "generated",
    [
        None,
        [],
        {"actions": []},
        {"error": None, "actions": []},
        {"error": "false", "actions": []},
        {"error": False, "actions": "bad"},
    ],
)
def test_v569_generator_malformed_results_fail_closed(generated):
    service, _, priority, execution = _service(generated)

    assert service.execute_plan([]) == _failure(
        "INVALID_GENERATOR_RESULT"
    )
    assert priority.calls == []
    assert execution.calls == []


def test_v569_generator_exception_uses_stable_error_code():
    service, _, priority, execution = _service(
        None,
        generator_error=RuntimeError(
            "secret generator details"
        ),
    )

    result = service.execute_plan([])

    assert result == _failure("ACTION_GENERATION_FAILED")
    assert "secret" not in result["message"]
    assert priority.calls == []
    assert execution.calls == []


def test_v569_empty_generated_action_list_fails_closed():
    service, _, priority, execution = _service({
        "error": False,
        "actions": [],
    })

    assert service.execute_plan([]) == _failure(
        "EMPTY_ACTION_PLAN"
    )
    assert priority.calls == []
    assert execution.calls == []


def test_v570_non_dict_generated_action_fails_closed():
    service, _, priority, execution = _service({
        "error": False,
        "actions": ["bad-action"],
    })

    assert service.execute_plan([]) == _failure(
        "INVALID_GENERATED_ACTION"
    )
    assert priority.calls == []
    assert execution.calls == []


def test_v570_priority_explicit_error_is_returned_and_stops_execution():
    priority_result = {
        "error": True,
        "message": "priority unavailable",
    }
    service, _, priority, execution = _service(
        _valid_generated(),
        priority=priority_result,
    )

    result = service.execute_plan([])

    assert result is priority_result
    assert len(priority.calls) == 1
    assert execution.calls == []


@pytest.mark.parametrize(
    "priority_result",
    [
        None,
        [],
        {},
        {"error": None},
        {"error": False},
        {"error": False, "action": "bad"},
    ],
)
def test_v570_priority_malformed_results_fail_closed(priority_result):
    service, _, _, execution = _service(
        _valid_generated(),
        priority=priority_result,
    )

    assert service.execute_plan([]) == _failure(
        "INVALID_PRIORITY_RESULT"
    )
    assert execution.calls == []


def test_v571_priority_exception_uses_stable_error_code():
    service, _, _, execution = _service(
        _valid_generated(),
        priority_error=RuntimeError(
            "secret priority details"
        ),
    )

    result = service.execute_plan([])

    assert result == _failure("PRIORITY_RESOLUTION_FAILED")
    assert "secret" not in result["message"]
    assert execution.calls == []


def test_v571_execution_explicit_error_is_returned():
    executed = {
        "error": True,
        "message": "execution unavailable",
    }
    service, _, _, execution = _service(
        _valid_generated(),
        executed=executed,
    )

    result = service.execute_plan([])

    assert result is executed
    assert len(execution.calls) == 1


def test_v571_execution_exception_uses_stable_error_code():
    service, _, _, execution = _service(
        _valid_generated(),
        execution_error=RuntimeError(
            "secret execution details"
        ),
    )

    result = service.execute_plan([])

    assert result == _failure("PLAN_EXECUTION_FAILED")
    assert "secret" not in result["message"]
    assert len(execution.calls) == 1


@pytest.mark.parametrize(
    "executed",
    [
        None,
        [],
        {},
        {"error": None},
        {"error": False},
        {"error": False, "executed": [], "count": True},
        {"error": False, "executed": [], "count": -1},
        {"error": False, "executed": [], "count": 1},
        {"error": False, "executed": "bad", "count": 0},
        {"error": False, "executed": ["bad"], "count": 1},
    ],
)
def test_v572_execution_malformed_results_fail_closed(executed):
    service, _, _, _ = _service(
        _valid_generated(),
        executed=executed,
    )

    assert service.execute_plan([]) == _failure(
        "INVALID_EXECUTION_RESULT"
    )


def test_v573_multiple_actions_preserve_priority_order_into_execution():
    generated = {
        "error": False,
        "actions": [
            {"type": "sales", "priority": "HIGH"},
            {"type": "finance", "priority": "NORMAL"},
        ],
    }
    execution_result = {
        "error": False,
        "executed": [
            {"action": {"type": "sales"}, "result": {}},
            {"action": {"type": "finance"}, "result": {}},
        ],
        "count": 2,
    }
    service, _, priority, execution = _service(
        generated,
        executed=execution_result,
    )

    result = service.execute_plan([])

    assert result["error"] is False
    assert result["count"] == 2
    assert [item["type"] for item in priority.calls] == [
        "sales",
        "finance",
    ]
    assert [
        item["type"]
        for item in execution.calls[0]
    ] == [
        "sales",
        "finance",
    ]


def test_v574_first_priority_failure_stops_later_actions():
    calls = []

    def resolve(action):
        calls.append(action["type"])
        if action["type"] == "sales":
            return {
                "error": True,
                "message": "priority failed",
            }
        raise AssertionError(
            "later action should not be resolved"
        )

    service, _, _, execution = _service(
        {
            "error": False,
            "actions": [
                {"type": "sales"},
                {"type": "finance"},
            ],
        },
        priority=resolve,
    )

    result = service.execute_plan([])

    assert result["error"] is True
    assert calls == ["sales"]
    assert execution.calls == []
