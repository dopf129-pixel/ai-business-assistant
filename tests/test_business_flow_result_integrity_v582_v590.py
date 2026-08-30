from services.assistant_business_flow_service import (
    AssistantBusinessFlowService,
)


_DEFAULT = object()


class _IntentService:

    def __init__(self, result):
        self.result = result
        self.calls = []

    def detect(self, text, context=None):
        self.calls.append(
            {
                "text": text,
                "context": context,
            }
        )
        return self.result


class _PlannerService:

    def __init__(self, result=_DEFAULT):
        if result is _DEFAULT:
            result = {
                "error": False,
                "actions": [
                    {
                        "action": {
                            "type": "sales",
                        },
                        "result": {
                            "error": False,
                        },
                    }
                ],
                "count": 1,
            }

        self.result = result
        self.calls = []

    def build_plan(self, report, user_id=None):
        self.calls.append(
            {
                "report": report,
                "user_id": user_id,
            }
        )
        return self.result


class _ExecutionService:

    def __init__(self, result=_DEFAULT):
        if result is _DEFAULT:
            result = {
                "error": False,
                "message": "Действие выполнено",
                "action": {
                    "title": "Проверить продажи",
                },
                "next_action": None,
                "completed": False,
                "progress": {
                    "done": 1,
                    "total": 2,
                },
            }

        self.result = result
        self.calls = []

    def execute_current_action(self, user_id):
        self.calls.append(user_id)
        return self.result


class _TaskService:

    def __init__(
        self,
        *,
        cancel=_DEFAULT,
        pause=_DEFAULT,
        resume=_DEFAULT,
        next_results=_DEFAULT,
        skip=_DEFAULT,
        status=_DEFAULT,
        history=_DEFAULT,
        pending=_DEFAULT,
    ):
        self.cancel_result = (
            {
                "error": False,
                "task": "Проверка магазина",
            }
            if cancel is _DEFAULT
            else cancel
        )
        self.pause_result = (
            {
                "error": False,
                "status": "PAUSED",
            }
            if pause is _DEFAULT
            else pause
        )
        self.resume_result = (
            {
                "error": False,
                "status": "ACTIVE",
            }
            if resume is _DEFAULT
            else resume
        )
        if next_results is _DEFAULT:
            next_results = [
                {
                    "error": False,
                    "action": None,
                }
            ]
        self.next_results = list(
            next_results
        )
        self.skip_result = (
            {
                "error": False,
                "action": {
                    "title": "Шаг 1",
                    "status": "SKIPPED",
                },
            }
            if skip is _DEFAULT
            else skip
        )
        self.status_result = (
            {
                "error": False,
                "status": "ACTIVE",
            }
            if status is _DEFAULT
            else status
        )
        self.history_result = (
            {
                "error": False,
                "history": [],
            }
            if history is _DEFAULT
            else history
        )
        self.pending_result = (
            {
                "error": False,
            }
            if pending is _DEFAULT
            else pending
        )
        self.calls = []

    def cancel_task(self, user_id):
        self.calls.append(
            ("cancel", user_id)
        )
        return self.cancel_result

    def pause_task(self, user_id):
        self.calls.append(
            ("pause", user_id)
        )
        return self.pause_result

    def resume_task(self, user_id):
        self.calls.append(
            ("resume", user_id)
        )
        return self.resume_result

    def get_next_action(self, user_id):
        self.calls.append(
            ("next", user_id)
        )

        if not self.next_results:
            raise AssertionError(
                "unexpected extra next-action read"
            )

        return self.next_results.pop(0)

    def skip_action(self, user_id, title):
        self.calls.append(
            ("skip", user_id, title)
        )
        return self.skip_result

    def get_task_status(self, user_id):
        self.calls.append(
            ("status", user_id)
        )
        return self.status_result

    def get_task_history(self, user_id):
        self.calls.append(
            ("history", user_id)
        )
        return self.history_result

    def set_pending_action(
        self,
        user_id,
        action,
    ):
        self.calls.append(
            ("pending", user_id, action)
        )
        return self.pending_result


def _intent(command, **extra):
    result = {
        "error": False,
        "intent": command,
        "command": command,
    }
    result.update(extra)
    return result


def _flow(
    *,
    intent,
    planner=_DEFAULT,
    task_service=None,
    execution=_DEFAULT,
):
    return AssistantBusinessFlowService(
        intent_service=(
            _IntentService(
                intent
            )
        ),
        planner_service=(
            _PlannerService(
                planner
            )
        ),
        task_service=task_service,
        execution_service=(
            _ExecutionService(
                execution
            )
            if execution is not None
            else None
        ),
    )


def test_v582_explicit_intent_error_is_preserved():

    downstream = {
        "error": True,
        "message": (
            "Не удалось определить намерение"
        ),
    }

    flow = _flow(
        intent=downstream
    )

    result = flow.process(
        "непонятно",
        {},
    )

    assert result is downstream


def test_v582_malformed_intent_results_fail_closed():

    cases = [
        None,
        [],
        {},
        {
            "error": None,
            "command": "actions",
        },
        {
            "error": "false",
            "command": "actions",
        },
        {
            "error": False,
        },
        {
            "error": False,
            "command": "",
        },
        {
            "error": False,
            "command": 42,
        },
    ]

    for downstream in cases:
        flow = _flow(
            intent=downstream
        )

        result = flow.process(
            "текст",
            {},
        )

        assert result["error"] is True
        assert (
            result["message"]
            ==
            "INVALID_INTENT_RESULT"
        )


def test_v583_valid_planner_success_shape_is_preserved():

    flow = _flow(
        intent=_intent(
            "actions"
        )
    )

    result = flow.process(
        "покажи план",
        {
            "sales_down": True,
        },
        user_id=42,
    )

    assert result == {
        "error": False,
        "intent": _intent(
            "actions"
        ),
        "plan": [
            {
                "action": {
                    "type": "sales",
                },
                "result": {
                    "error": False,
                },
            }
        ],
        "count": 1,
    }


def test_v583_planner_error_is_not_rewritten_as_success():

    downstream = {
        "error": True,
        "message": (
            "INVALID_PLAN_EXECUTION_RESULT"
        ),
        "actions": [],
        "count": 0,
    }

    flow = _flow(
        intent=_intent(
            "actions"
        ),
        planner=downstream,
    )

    result = flow.process(
        "покажи план",
        {},
    )

    assert result == {
        "error": True,
        "message": (
            "INVALID_PLAN_EXECUTION_RESULT"
        ),
        "intent": _intent(
            "actions"
        ),
        "plan": [],
        "count": 0,
    }


def test_v583_malformed_planner_results_fail_closed():

    cases = [
        None,
        [],
        {},
        {
            "error": None,
        },
        {
            "error": False,
        },
        {
            "error": False,
            "actions": [],
        },
        {
            "error": False,
            "actions": [],
            "count": True,
        },
        {
            "error": False,
            "actions": [],
            "count": -1,
        },
        {
            "error": False,
            "actions": [],
            "count": 1,
        },
        {
            "error": False,
            "actions": "bad",
            "count": 0,
        },
        {
            "error": False,
            "actions": ["bad"],
            "count": 1,
        },
    ]

    for downstream in cases:
        flow = _flow(
            intent=_intent(
                "actions"
            ),
            planner=downstream,
        )

        result = flow.process(
            "план",
            {},
        )

        assert result == {
            "error": True,
            "message": (
                "INVALID_PLANNER_RESULT"
            ),
            "intent": _intent(
                "actions"
            ),
            "plan": [],
            "count": 0,
        }


def test_v584_valid_execute_result_shape_is_preserved():

    flow = _flow(
        intent=_intent(
            "execute"
        )
    )

    result = flow.process(
        "выполни",
        {},
        user_id=42,
    )

    assert result == {
        "error": False,
        "intent": _intent(
            "execute"
        ),
        "execution": {
            "error": False,
            "message": (
                "Действие выполнено"
            ),
            "action": {
                "title": (
                    "Проверить продажи"
                ),
            },
            "next_action": None,
            "completed": False,
            "progress": {
                "done": 1,
                "total": 2,
            },
        },
    }


def test_v584_execute_error_preserves_failure_message():

    flow = _flow(
        intent=_intent(
            "execute"
        ),
        execution={
            "error": True,
            "message": (
                "Задача находится на паузе"
            ),
        },
    )

    result = flow.process(
        "выполни",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["execution"][
            "message"
        ]
        ==
        "Задача находится на паузе"
    )
    assert (
        result["execution"][
            "message"
        ]
        !=
        "Действие выполнено"
    )


def test_v584_execute_error_without_message_uses_stable_failure_code():

    flow = _flow(
        intent=_intent(
            "execute"
        ),
        execution={
            "error": True,
        },
    )

    result = flow.process(
        "выполни",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["execution"][
            "message"
        ]
        ==
        "EXECUTION_RETURNED_ERROR"
    )


def test_v585_malformed_execute_results_never_claim_success():

    cases = [
        None,
        [],
        {},
        {
            "error": None,
        },
        {
            "error": False,
        },
        {
            "error": False,
            "message": "",
        },
        {
            "error": False,
            "message": "ok",
            "action": "bad",
        },
        {
            "error": False,
            "message": "ok",
            "completed": 1,
        },
        {
            "error": False,
            "message": "ok",
            "progress": {
                "done": True,
                "total": 1,
            },
        },
        {
            "error": False,
            "message": "ok",
            "progress": {
                "done": 2,
                "total": 1,
            },
        },
    ]

    for downstream in cases:
        flow = _flow(
            intent=_intent(
                "execute"
            ),
            execution=downstream,
        )

        result = flow.process(
            "выполни",
            {},
            user_id=42,
        )

        assert result["error"] is True
        assert (
            result["execution"][
                "message"
            ]
            ==
            "INVALID_EXECUTION_RESULT"
        )
        assert (
            result["execution"][
                "message"
            ]
            !=
            "Действие выполнено"
        )


def test_v585_execute_success_without_optional_progress_stays_compatible():

    flow = _flow(
        intent=_intent(
            "execute"
        ),
        execution={
            "error": False,
            "message": (
                "Действие уже обработано"
            ),
            "action": {
                "title": "Шаг",
            },
        },
    )

    result = flow.process(
        "выполни",
        {},
        user_id=42,
    )

    assert result["error"] is False
    assert (
        result["execution"][
            "completed"
        ]
        is False
    )
    assert (
        result["execution"][
            "progress"
        ]
        ==
        {
            "done": 0,
            "total": 0,
        }
    )


def test_v586_cancel_error_does_not_claim_task_cancelled():

    task = _TaskService(
        cancel={
            "error": True,
            "message": (
                "Задача не найдена"
            ),
        }
    )

    flow = _flow(
        intent=_intent(
            "cancel_task"
        ),
        task_service=task,
    )

    result = flow.process(
        "отмени",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["message"]
        ==
        "Задача не найдена"
    )
    assert (
        result["message"]
        !=
        "Задача отменена"
    )


def test_v586_pause_and_resume_errors_do_not_claim_success():

    cases = [
        (
            "pause_task",
            _TaskService(
                pause={
                    "error": True,
                    "message": "pause failed",
                }
            ),
            "pause failed",
        ),
        (
            "resume_task",
            _TaskService(
                resume={
                    "error": True,
                    "message": "resume failed",
                }
            ),
            "resume failed",
        ),
    ]

    for command, task, expected in cases:
        flow = _flow(
            intent=_intent(
                command
            ),
            task_service=task,
        )

        result = flow.process(
            "command",
            {},
            user_id=42,
        )

        assert result["error"] is True
        assert result["message"] == expected


def test_v586_malformed_task_command_results_fail_closed():

    cases = [
        (
            "cancel_task",
            _TaskService(
                cancel=None
            ),
        ),
        (
            "pause_task",
            _TaskService(
                pause=[]
            ),
        ),
        (
            "resume_task",
            _TaskService(
                resume={}
            ),
        ),
    ]

    for command, task in cases:
        flow = _flow(
            intent=_intent(
                command
            ),
            task_service=task,
        )

        result = flow.process(
            "command",
            {},
            user_id=42,
        )

        assert result["error"] is True
        assert (
            result["message"]
            ==
            "INVALID_TASK_RESULT"
        )


def test_v587_task_read_commands_reject_malformed_results():

    commands = [
        (
            "task_status",
            _TaskService(
                status=None
            ),
            "INVALID_TASK_RESULT",
        ),
        (
            "task_history",
            _TaskService(
                history=[]
            ),
            "INVALID_TASK_RESULT",
        ),
        (
            "task_details",
            _TaskService(
                history={}
            ),
            "INVALID_TASK_RESULT",
        ),
        (
            "task_next",
            _TaskService(
                next_results=[None]
            ),
            "INVALID_TASK_NEXT_RESULT",
        ),
    ]

    for command, task, expected in commands:
        flow = _flow(
            intent=_intent(
                command
            ),
            task_service=task,
        )

        result = flow.process(
            "command",
            {},
            user_id=42,
        )

        assert result["error"] is True
        assert result["message"] == expected


def test_v587_task_read_explicit_error_is_preserved_in_wrapper():

    downstream = {
        "error": True,
        "message": "status failed",
    }

    task = _TaskService(
        status=downstream
    )

    flow = _flow(
        intent=_intent(
            "task_status"
        ),
        task_service=task,
    )

    result = flow.process(
        "статус",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["task_status"]
        is downstream
    )


def test_v588_skip_next_error_is_not_no_action_success():

    task = _TaskService(
        next_results=[
            {
                "error": True,
                "message": (
                    "next unavailable"
                ),
            }
        ]
    )

    flow = _flow(
        intent=_intent(
            "skip_action"
        ),
        task_service=task,
    )

    result = flow.process(
        "пропусти",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["message"]
        ==
        "next unavailable"
    )
    assert (
        "Нет доступного шага"
        not in result["message"]
    )


def test_v588_skip_malformed_action_fails_before_mutation():

    task = _TaskService(
        next_results=[
            {
                "error": False,
                "action": {
                    "status": "NEW",
                },
            }
        ]
    )

    flow = _flow(
        intent=_intent(
            "skip_action"
        ),
        task_service=task,
    )

    result = flow.process(
        "пропусти",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["message"]
        ==
        "INVALID_TASK_NEXT_RESULT"
    )
    assert not any(
        call[0] == "skip"
        for call in task.calls
    )


def test_v589_skip_committed_then_next_read_failure_reports_partial_state():

    skipped_action = {
        "title": "Шаг 1",
        "status": "SKIPPED",
    }

    task = _TaskService(
        next_results=[
            {
                "error": False,
                "action": {
                    "title": "Шаг 1",
                    "status": "NEW",
                },
            },
            {
                "error": True,
                "message": (
                    "next read failed"
                ),
            },
        ],
        skip={
            "error": False,
            "action": skipped_action,
        },
    )

    flow = _flow(
        intent=_intent(
            "skip_action"
        ),
        task_service=task,
    )

    result = flow.process(
        "пропусти",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["message"]
        ==
        "next read failed"
    )
    assert (
        result["action"]
        is skipped_action
    )
    assert result["next_action"] is None
    assert any(
        call[0] == "skip"
        for call in task.calls
    )


def test_v589_valid_skip_success_shape_is_preserved():

    first = {
        "title": "Шаг 1",
        "status": "NEW",
    }
    second = {
        "title": "Шаг 2",
        "status": "NEW",
    }
    skipped = {
        "title": "Шаг 1",
        "status": "SKIPPED",
    }

    task = _TaskService(
        next_results=[
            {
                "error": False,
                "action": first,
            },
            {
                "error": False,
                "action": second,
            },
        ],
        skip={
            "error": False,
            "action": skipped,
        },
    )

    flow = _flow(
        intent=_intent(
            "skip_action"
        ),
        task_service=task,
    )

    result = flow.process(
        "пропусти",
        {},
        user_id=42,
    )

    assert result == {
        "error": False,
        "intent": _intent(
            "skip_action"
        ),
        "message": "Шаг пропущен",
        "action": skipped,
        "next_action": second,
    }


def test_v590_continue_next_error_is_not_success():

    task = _TaskService(
        next_results=[
            {
                "error": True,
                "message": "next failed",
            }
        ]
    )

    flow = _flow(
        intent=_intent(
            "continue",
            task="Проверка магазина",
        ),
        task_service=task,
    )

    result = flow.process(
        "продолжи",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert result["message"] == "next failed"
    assert not any(
        call[0] == "pending"
        for call in task.calls
    )


def test_v590_continue_pending_failure_is_not_success():

    next_action = {
        "title": "Шаг 1",
        "status": "NEW",
    }

    task = _TaskService(
        next_results=[
            {
                "error": False,
                "action": next_action,
            }
        ],
        pending={
            "error": True,
            "message": (
                "pending save failed"
            ),
        },
    )

    flow = _flow(
        intent=_intent(
            "continue",
            task="Проверка магазина",
        ),
        task_service=task,
    )

    result = flow.process(
        "продолжи",
        {},
        user_id=42,
    )

    assert result["error"] is True
    assert (
        result["message"]
        ==
        "pending save failed"
    )


def test_v590_valid_continue_shape_is_preserved():

    next_action = {
        "title": "Шаг 1",
        "status": "NEW",
    }

    task = _TaskService(
        next_results=[
            {
                "error": False,
                "action": next_action,
            }
        ]
    )

    flow = _flow(
        intent=_intent(
            "continue",
            task="Проверка магазина",
        ),
        task_service=task,
    )

    result = flow.process(
        "продолжи",
        {},
        user_id=42,
    )

    assert result == {
        "error": False,
        "intent": _intent(
            "continue",
            task="Проверка магазина",
        ),
        "plan": [],
        "count": 0,
        "continued_task": (
            "Проверка магазина"
        ),
        "next_action": next_action,
    }

    assert any(
        call[0] == "pending"
        for call in task.calls
    )
