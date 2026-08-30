import sys

sys.path.insert(
    0,
    "app"
)

from services.action_history_service import (
    ActionHistoryService,
)
from services.assistant_action_execution_service import (
    AssistantActionExecutionService,
)
from services.assistant_action_router_service import (
    AssistantActionRouterService,
)
from services.retry_policy_service import (
    RetryPolicyService,
)
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)


USER_ID = 1541


class _Executor:

    def __init__(
        self,
        result
    ):
        self.result = result
        self.calls = []

    def execute(
        self,
        action
    ):
        self.calls.append(
            dict(action)
        )
        return self.result


class _Feedback:

    def __init__(
        self
    ):
        self.records = []

    def record(
        self,
        record
    ):
        self.records.append(
            dict(record)
        )
        return {
            "error": False
        }


def _services(
    tmp_path,
    executor_result
):
    task_service = (
        TerminalSafeAssistantTaskService(
            file_path=str(
                tmp_path / "tasks.json"
            )
        )
    )

    task_service.create_task(
        USER_ID,
        "Lifecycle test",
        [
            {
                "title": "Проверить данные",
                "type": "sales",
                "status": "NEW",
            }
        ]
    )

    executor = _Executor(
        executor_result
    )
    router = AssistantActionRouterService(
        executors={
            "sales": executor
        }
    )
    history = ActionHistoryService()
    feedback = _Feedback()
    execution = AssistantActionExecutionService(
        task_service=task_service,
        action_router=router,
        action_runner_service=router,
        retry_policy=RetryPolicyService(),
        history_service=history,
        feedback_service=feedback,
    )

    return (
        execution,
        task_service,
        router,
        executor,
        history,
        feedback,
    )


def _action(
    task_service
):
    return (
        task_service
        .get_task(
            USER_ID
        )["task"]["actions"][0]
    )


def test_v541_router_execute_preserves_direct_error_contract():
    executor = _Executor(
        {
            "error": True,
            "message": "temporary unavailable",
        }
    )
    router = AssistantActionRouterService(
        executors={
            "sales": executor
        }
    )

    result = router.execute(
        {
            "type": "sales"
        }
    )

    assert result == {
        "error": True,
        "message": "temporary unavailable",
    }


def test_v542_error_result_becomes_failed_not_done(tmp_path):
    (
        execution,
        task_service,
        _router,
        _executor,
        history,
        feedback,
    ) = _services(
        tmp_path,
        {
            "error": True,
            "message": "temporary unavailable",
        }
    )

    result = execution.execute_current_action(
        USER_ID
    )

    persisted = _action(
        task_service
    )
    task = task_service.get_task(
        USER_ID
    )["task"]

    assert result["error"] is False
    assert result["message"] == (
        "Действие завершилось ошибкой"
    )
    assert result["action"]["status"] == "FAILED"
    assert result["action"]["retry_allowed"] is True
    assert persisted["status"] == "FAILED"
    assert persisted["error"] == "temporary unavailable"
    assert "result" not in persisted
    assert task["status"] == "ACTIVE"
    assert task["pending_action"] is None
    assert task_service.get_task_progress(
        USER_ID
    ) == {
        "error": False,
        "done": 0,
        "total": 1,
    }

    events = history.list_actions()[
        "actions"
    ]
    assert [
        event["event"]
        for event in events
    ] == [
        "execution_failed"
    ]
    assert events[0]["status"] == "FAILED"
    assert events[0]["retry_allowed"] is True

    assert feedback.records == [
        {
            "action": "Проверить данные",
            "status": "FAILED",
            "error": "temporary unavailable",
        }
    ]


def test_v543_error_result_is_retryable_through_existing_lifecycle(
    tmp_path
):
    (
        execution,
        task_service,
        _router,
        _executor,
        _history,
        _feedback,
    ) = _services(
        tmp_path,
        {
            "error": True,
            "message": "network unavailable",
        }
    )

    execution.execute_current_action(
        USER_ID
    )

    retry = execution.retry_action(
        USER_ID
    )

    assert retry["error"] is False
    assert retry["action"]["status"] == "NEW"
    assert retry["action"]["attempt"] == 2
    assert "error" not in retry["action"]
    assert _action(
        task_service
    )["status"] == "NEW"


def test_v544_non_retryable_error_result_keeps_retry_false(tmp_path):
    (
        execution,
        _task_service,
        _router,
        _executor,
        history,
        _feedback,
    ) = _services(
        tmp_path,
        {
            "error": True,
            "message": "invalid request",
        }
    )

    result = execution.execute_current_action(
        USER_ID
    )

    assert result["action"]["retry_allowed"] is False
    event = history.list_actions()[
        "actions"
    ][0]
    assert event["retry_allowed"] is False


def test_v545_error_result_without_message_uses_stable_error(
    tmp_path
):
    (
        execution,
        task_service,
        _router,
        _executor,
        _history,
        _feedback,
    ) = _services(
        tmp_path,
        {
            "error": True,
            "secret": "must-not-be-stringified",
        }
    )

    result = execution.execute_current_action(
        USER_ID
    )

    assert result["action"]["error"] == (
        "EXECUTOR_RETURNED_ERROR"
    )
    assert _action(
        task_service
    )["error"] == (
        "EXECUTOR_RETURNED_ERROR"
    )
    assert "must-not-be-stringified" not in str(
        result
    )


def test_v546_malformed_executor_result_fails_closed(tmp_path):
    (
        execution,
        task_service,
        _router,
        _executor,
        _history,
        _feedback,
    ) = _services(
        tmp_path,
        [
            "not-a-result-dict"
        ]
    )

    result = execution.execute_current_action(
        USER_ID
    )

    assert result["action"]["status"] == "FAILED"
    assert result["action"]["error"] == (
        "INVALID_EXECUTOR_RESULT"
    )
    assert _action(
        task_service
    )["status"] == "FAILED"


def test_v546_malformed_error_flag_fails_closed(tmp_path):
    (
        execution,
        task_service,
        _router,
        _executor,
        _history,
        _feedback,
    ) = _services(
        tmp_path,
        {
            "error": "yes",
            "result": {
                "message": "ambiguous"
            },
        }
    )

    result = execution.execute_current_action(
        USER_ID
    )

    assert result["action"]["error"] == (
        "INVALID_EXECUTOR_RESULT"
    )
    assert _action(
        task_service
    )["status"] == "FAILED"


def test_v547_success_result_still_completes_action_and_task(
    tmp_path
):
    (
        execution,
        task_service,
        _router,
        _executor,
        history,
        feedback,
    ) = _services(
        tmp_path,
        {
            "error": False,
            "result": {
                "message": "ok"
            },
        }
    )

    result = execution.execute_current_action(
        USER_ID
    )

    task = task_service.get_task(
        USER_ID
    )["task"]
    persisted = _action(
        task_service
    )

    assert result["message"] == "Действие выполнено"
    assert result["completed"] is True
    assert persisted["status"] == "DONE"
    assert persisted["result"] == {
        "error": False,
        "result": {
            "message": "ok"
        },
    }
    assert task["status"] == "DONE"
    assert task["pending_action"] is None

    events = history.list_actions()[
        "actions"
    ]
    assert [
        event["event"]
        for event in events
    ] == [
        "execution_completed"
    ]
    assert feedback.records[0]["status"] == "DONE"
