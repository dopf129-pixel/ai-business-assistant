from app.telegram_core_factory import create_telegram_core


ACTION = "Получить данные"
OTHER_ACTION = "Сформировать отчёт"


def test_factory_shares_memory_with_feedback_planning_and_action_generation():
    core = create_telegram_core()

    memory = core["memory_service"]

    assert core["feedback_service"].memory_service is memory
    assert core["planning_service"].memory_service is memory
    assert core["action_generator_service"].memory_service is memory


def test_feedback_experience_is_available_to_next_plan():
    core = create_telegram_core()

    core["feedback_service"].record(
        {
            "action": ACTION,
            "status": "FAILED",
        }
    )

    result = core["planning_service"].build_plan(
        [
            {
                "message": ACTION,
                "type": "task",
            }
        ]
    )

    assert result["error"] is False
    assert len(result["memory"]) == 1
    assert result["memory"][0]["action"] == ACTION
    assert result["memory"][0]["status"] == "FAILED"


def test_feedback_experience_is_available_to_next_generated_action():
    core = create_telegram_core()

    core["feedback_service"].record(
        {
            "action": ACTION,
            "status": "DONE",
        }
    )

    result = core["action_generator_service"].generate(ACTION)

    assert result["error"] is False
    assert len(result["memory"]) == 1
    assert result["memory"][0]["action"] == ACTION
    assert result["actions"][0]["memory_context"] == result["memory"]


def test_learning_context_does_not_leak_to_unrelated_action():
    core = create_telegram_core()

    core["feedback_service"].record(
        {
            "action": ACTION,
            "status": "FAILED",
        }
    )

    plan = core["planning_service"].build_plan(
        [
            {
                "message": OTHER_ACTION,
                "type": "task",
            }
        ]
    )
    generated = core["action_generator_service"].generate(OTHER_ACTION)

    assert plan["memory"] == []
    assert generated["memory"] == []
    assert generated["actions"][0]["memory_context"] == []
