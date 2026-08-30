from services.assistant_business_planner_service import (
    AssistantBusinessPlannerService,
)


_DEFAULT = object()


class _RecommendationService:

    def __init__(self, result):
        self.result = result
        self.calls = []

    def analyze(self, report):
        self.calls.append(report)
        return self.result


class _PlanningService:

    def __init__(self, result=_DEFAULT):
        if result is _DEFAULT:
            result = {
                "error": False,
                "plan": [
                    {
                        "step": 1,
                        "type": "sales",
                        "action": "Проверить продажи",
                    }
                ],
                "count": 1,
            }

        self.result = result
        self.calls = []

    def build_plan(self, recommendations):
        self.calls.append(recommendations)
        return self.result


class _ExecutorService:

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

    def execute_plan(self, plan):
        self.calls.append(plan)
        return self.result


class _TaskService:

    def __init__(self, result=_DEFAULT):
        if result is _DEFAULT:
            result = {
                "error": False,
                "saved": True,
            }

        self.result = result
        self.calls = []

    def create_task(
        self,
        user_id,
        title,
        actions,
    ):
        self.calls.append(
            {
                "user_id": user_id,
                "title": title,
                "actions": actions,
            }
        )

        return self.result


def _recommendations():
    return {
        "error": False,
        "recommendations": [
            {
                "type": "sales",
                "message": "Проверить продажи",
                "context": {
                    "period": "week",
                },
            }
        ],
    }


def _service(
    recommendations=_DEFAULT,
    planning=_DEFAULT,
    execution=_DEFAULT,
    task=_DEFAULT,
):
    if recommendations is _DEFAULT:
        recommendations = _recommendations()

    recommendation_service = (
        _RecommendationService(
            recommendations
        )
    )

    planning_service = (
        _PlanningService(
            planning
        )
    )

    executor_service = (
        _ExecutorService(
            execution
        )
    )

    task_service = (
        _TaskService(
            task
        )
    )

    service = (
        AssistantBusinessPlannerService(
            recommendation_service=(
                recommendation_service
            ),
            planning_service=(
                planning_service
            ),
            executor_service=(
                executor_service
            ),
            task_service=(
                task_service
            ),
        )
    )

    return (
        service,
        recommendation_service,
        planning_service,
        executor_service,
        task_service,
    )


def test_v575_valid_result_shape_and_task_creation_are_preserved():

    (
        service,
        _,
        planning,
        executor,
        task,
    ) = _service()

    result = service.build_plan(
        {"sales_down": True},
        user_id=42,
    )

    assert result == {
        "error": False,
        "recommendations": (
            _recommendations()[
                "recommendations"
            ]
        ),
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

    assert len(
        planning.calls
    ) == 1

    assert len(
        executor.calls
    ) == 1

    assert task.calls == [
        {
            "user_id": 42,
            "title": (
                "Создание плана действий"
            ),
            "actions": result[
                "actions"
            ],
        }
    ]


def test_v575_general_only_recommendations_remain_non_actionable():

    recommendations = {
        "error": False,
        "recommendations": [
            {
                "type": "general",
                "message": (
                    "Недостаточно данных"
                ),
            }
        ],
    }

    (
        service,
        _,
        planning,
        executor,
        task,
    ) = _service(
        recommendations=(
            recommendations
        )
    )

    result = service.build_plan(
        {}
    )

    assert result == {
        "error": False,
        "recommendations": (
            recommendations[
                "recommendations"
            ]
        ),
        "actions": [],
        "count": 0,
    }

    assert planning.calls == []
    assert executor.calls == []
    assert task.calls == []


def test_v576_recommendation_explicit_error_is_preserved():

    downstream = {
        "error": True,
        "message": (
            "recommendation unavailable"
        ),
    }

    (
        service,
        _,
        planning,
        executor,
        task,
    ) = _service(
        recommendations=downstream
    )

    result = service.build_plan(
        {}
    )

    assert result is downstream
    assert planning.calls == []
    assert executor.calls == []
    assert task.calls == []


def test_v576_malformed_recommendation_results_fail_closed():

    cases = [
        None,
        [],
        {},
        {
            "error": None,
            "recommendations": [],
        },
        {
            "error": "false",
            "recommendations": [],
        },
        {
            "error": False,
        },
        {
            "error": False,
            "recommendations": (
                {"type": "general"},
            ),
        },
    ]

    for downstream in cases:

        (
            service,
            _,
            planning,
            executor,
            task,
        ) = _service(
            recommendations=downstream
        )

        result = service.build_plan(
            {}
        )

        assert result == {
            "error": True,
            "message": (
                "INVALID_RECOMMENDATION_RESULT"
            ),
            "actions": [],
            "count": 0,
        }

        assert planning.calls == []
        assert executor.calls == []
        assert task.calls == []


def test_v577_planning_explicit_error_is_preserved():

    downstream = {
        "error": True,
        "message": (
            "planning unavailable"
        ),
    }

    (
        service,
        _,
        _,
        executor,
        task,
    ) = _service(
        planning=downstream
    )

    result = service.build_plan(
        {}
    )

    assert result is downstream
    assert executor.calls == []
    assert task.calls == []


def test_v577_malformed_planning_results_fail_closed():

    cases = [
        None,
        [],
        {},
        {
            "error": None,
            "plan": [],
        },
        {
            "error": False,
        },
        {
            "error": False,
            "plan": "bad",
        },
    ]

    for downstream in cases:

        (
            service,
            _,
            _,
            executor,
            task,
        ) = _service(
            planning=downstream
        )

        result = service.build_plan(
            {}
        )

        assert result == {
            "error": True,
            "message": (
                "INVALID_PLANNING_RESULT"
            ),
            "actions": [],
            "count": 0,
        }

        assert executor.calls == []
        assert task.calls == []


def test_v578_plan_execution_explicit_error_is_preserved():

    downstream = {
        "error": True,
        "message": (
            "PLAN_EXECUTION_FAILED"
        ),
        "actions": [],
        "count": 0,
    }

    (
        service,
        _,
        _,
        executor,
        task,
    ) = _service(
        execution=downstream
    )

    result = service.build_plan(
        {},
        user_id=42,
    )

    assert result is downstream
    assert len(
        executor.calls
    ) == 1
    assert task.calls == []


def test_v578_malformed_plan_execution_results_fail_closed():

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

        (
            service,
            _,
            _,
            _,
            task,
        ) = _service(
            execution=downstream
        )

        result = service.build_plan(
            {},
            user_id=42,
        )

        assert result == {
            "error": True,
            "message": (
                "INVALID_PLAN_EXECUTION_RESULT"
            ),
            "actions": [],
            "count": 0,
        }

        assert task.calls == []


def test_v579_zero_action_success_remains_valid_and_creates_no_task():

    downstream = {
        "error": False,
        "actions": [],
        "count": 0,
    }

    (
        service,
        _,
        _,
        _,
        task,
    ) = _service(
        execution=downstream
    )

    result = service.build_plan(
        {},
        user_id=42,
    )

    assert result["error"] is False
    assert result["actions"] == []
    assert result["count"] == 0
    assert task.calls == []


def test_v580_task_creation_explicit_error_is_preserved():

    downstream = {
        "error": True,
        "message": (
            "task persistence failed"
        ),
    }

    (
        service,
        _,
        _,
        _,
        task,
    ) = _service(
        task=downstream
    )

    result = service.build_plan(
        {},
        user_id=42,
    )

    assert result is downstream
    assert len(
        task.calls
    ) == 1


def test_v580_malformed_task_creation_result_fails_closed():

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

        (
            service,
            _,
            _,
            _,
            task,
        ) = _service(
            task=downstream
        )

        result = service.build_plan(
            {},
            user_id=42,
        )

        assert result == {
            "error": True,
            "message": (
                "INVALID_TASK_CREATION_RESULT"
            ),
            "actions": [],
            "count": 0,
        }

        assert len(
            task.calls
        ) == 1


def test_v581_no_task_service_keeps_readable_plan_result():

    service = (
        AssistantBusinessPlannerService(
            recommendation_service=(
                _RecommendationService(
                    _recommendations()
                )
            ),
            planning_service=(
                _PlanningService()
            ),
            executor_service=(
                _ExecutorService()
            ),
            task_service=None,
        )
    )

    result = service.build_plan(
        {},
        user_id=42,
    )

    assert result["error"] is False
    assert result["count"] == 1
    assert len(
        result["actions"]
    ) == 1
