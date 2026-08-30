from services.assistant_feedback_service import (
    AssistantFeedbackService,
)
from services.assistant_memory_integration_service import (
    AssistantMemoryIntegrationService,
)
from services.assistant_memory_service import (
    AssistantMemoryService,
)


class _Storage:

    def __init__(
        self,
        context=None,
        save_result=True,
        save_error=None,
    ):
        self.context = (
            {}
            if context is None
            else context
        )
        self.save_result = save_result
        self.save_error = save_error
        self.saved_contexts = []

    def load(self):
        return self.context

    def save(
        self,
        context,
    ):
        self.saved_contexts.append(
            context
        )

        if self.save_error:
            raise self.save_error

        return self.save_result


class _Intent:

    def detect(
        self,
        text,
    ):
        return {
            "error": False,
            "command": "report",
        }


class _MemorySaveSequence:

    def __init__(
        self,
        results,
    ):
        self.results = list(
            results
        )
        self.calls = []

    def save(
        self,
        key,
        value,
    ):
        self.calls.append(
            (
                key,
                value,
            )
        )
        return self.results.pop(
            0
        )


class _RememberFailure:

    def remember(
        self,
        experience,
    ):
        return {
            "error": True,
            "message":
                "MEMORY_STORAGE_SAVE_FAILED",
            "persistence_state_unknown":
                True,
        }


def test_v652_remember_rolls_back_only_explicit_false_save():

    storage = _Storage(
        save_result=False,
    )
    service = AssistantMemoryService(
        storage_service=storage
    )

    result = service.remember(
        {
            "action": "report",
            "status": "DONE",
        }
    )

    assert result == {
        "error": True,
        "message":
            "MEMORY_STORAGE_SAVE_REJECTED",
        "rolled_back": True,
    }
    assert service.memory == []
    assert "memory" not in service.context


def test_v653_remember_exception_reports_unknown_state_without_fake_rollback():

    storage = _Storage(
        save_error=OSError(
            "write failed"
        ),
    )
    service = AssistantMemoryService(
        storage_service=storage
    )

    result = service.remember(
        {
            "action": "report",
            "status": "DONE",
        }
    )

    assert result == {
        "error": True,
        "message":
            "MEMORY_STORAGE_SAVE_FAILED",
        "persistence_state_unknown":
            True,
    }
    assert len(
        service.memory
    ) == 1
    assert service.context[
        "memory"
    ] is service.memory


def test_v654_save_restores_existing_value_on_explicit_false_save():

    context = {
        "period": "30D",
    }
    service = AssistantMemoryService(
        storage_service=_Storage(
            context=context,
            save_result=False,
        )
    )

    result = service.save(
        "period",
        "90D",
    )

    assert result["error"] is True
    assert result["rolled_back"] is True
    assert service.context == {
        "period": "30D",
    }


def test_v655_malformed_save_result_fails_closed_without_fake_rollback():

    context = {
        "period": "30D",
    }
    service = AssistantMemoryService(
        storage_service=_Storage(
            context=context,
            save_result={
                "saved": True,
            },
        )
    )

    result = service.save(
        "period",
        "90D",
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_MEMORY_STORAGE_SAVE_RESULT",
        "persistence_state_unknown":
            True,
    }
    assert service.context[
        "period"
    ] == "90D"


def test_v656_clear_restores_context_on_explicit_false_save():

    context = {
        "period": "30D",
        "memory": [
            {
                "action": "report",
            }
        ],
    }
    service = AssistantMemoryService(
        storage_service=_Storage(
            context=context,
            save_result=False,
        )
    )

    result = service.clear()

    assert result["error"] is True
    assert result["rolled_back"] is True
    assert service.context is context
    assert service.memory is context[
        "memory"
    ]


def test_v657_memory_integration_stops_after_first_save_failure():

    memory = _MemorySaveSequence(
        [
            {
                "error": True,
                "message":
                    "MEMORY_STORAGE_SAVE_REJECTED",
            },
            {
                "error": False,
                "saved": True,
            },
        ]
    )
    service = AssistantMemoryIntegrationService(
        memory_service=memory,
        intent_service=_Intent(),
    )

    result = service.process(
        "report"
    )

    assert result["error"] is True
    assert result[
        "memory_saved"
    ] is False
    assert memory.calls == [
        (
            "last_command",
            "report",
        )
    ]


def test_v658_memory_integration_reports_partial_state_after_second_failure():

    memory = _MemorySaveSequence(
        [
            {
                "error": False,
                "saved": True,
            },
            {
                "error": True,
                "message":
                    "MEMORY_STORAGE_SAVE_FAILED",
                "persistence_state_unknown":
                    True,
            },
        ]
    )
    service = AssistantMemoryIntegrationService(
        memory_service=memory,
        intent_service=_Intent(),
    )

    result = service.process(
        "report text"
    )

    assert result["error"] is True
    assert result[
        "memory_saved"
    ] is False
    assert result[
        "partial_memory_saved"
    ] is True
    assert len(
        memory.calls
    ) == 2


def test_v659_feedback_memory_failure_is_not_reported_as_full_success():

    service = AssistantFeedbackService(
        memory_service=(
            _RememberFailure()
        )
    )

    result = service.record(
        {
            "action": "report",
            "status": "DONE",
        }
    )

    assert result["error"] is True
    assert result[
        "feedback_recorded"
    ] is True
    assert result[
        "memory_saved"
    ] is False
    assert result[
        "persistence_state_unknown"
    ] is True
    assert len(
        service.experiences
    ) == 1
