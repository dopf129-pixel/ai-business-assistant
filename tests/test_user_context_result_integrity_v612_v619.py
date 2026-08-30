from services.assistant_core_service import (
    AssistantCoreService,
)
from services.assistant_user_context_service import (
    AssistantUserContextService,
)


class _Profile:

    def __init__(
        self,
        get_result,
        save_result=None,
        memory_result=None,
    ):
        self.get_result = get_result
        self.save_result = save_result
        self.memory_result = memory_result
        self.save_calls = 0

    def get_user(
        self,
        user_id,
    ):
        return self.get_result

    def save(self):
        self.save_calls += 1
        return self.save_result

    def save_memory(
        self,
        user_id,
        key,
        value,
    ):
        return self.memory_result


class _Context:

    def __init__(
        self,
        initial,
        update,
        refresh=None,
    ):
        self.initial = initial
        self.update_result = update
        self.refresh = (
            initial
            if refresh is None
            else refresh
        )
        self.get_calls = 0

    def get_context(
        self,
        user_id,
    ):
        self.get_calls += 1
        if self.get_calls == 1:
            return self.initial
        return self.refresh

    def update(
        self,
        user_id,
        key,
        value,
    ):
        return self.update_result


class _Orchestrator:

    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = 0

    def process(
        self,
        text,
        context=None,
        user_id=None,
    ):
        self.calls += 1
        return dict(
            self.result
        )


def _valid_context():
    return {
        "error": False,
        "user_id": 1,
        "context": {},
        "memory": {},
    }


def test_v612_user_context_rejects_malformed_profile_result():

    for downstream in (
        None,
        [],
        {},
        {
            "error": False,
        },
        {
            "error": False,
            "user": [],
        },
        {
            "error": True,
            "user": {},
        },
    ):
        service = AssistantUserContextService(
            _Profile(
                downstream
            )
        )

        assert service.get_context(
            1
        ) == {
            "error": True,
            "message":
                "INVALID_USER_PROFILE_RESULT",
        }


def test_v613_invalid_context_or_memory_data_fails_closed():

    bad_context = AssistantUserContextService(
        _Profile(
            {
                "error": False,
                "user": {
                    "context": "bad",
                    "memory": {},
                },
            }
        )
    )

    assert bad_context.get_context(
        1
    ) == {
        "error": True,
        "message":
            "INVALID_USER_CONTEXT_DATA",
    }

    bad_memory = AssistantUserContextService(
        _Profile(
            {
                "error": False,
                "user": {
                    "context": {},
                    "memory": "bad",
                },
            }
        )
    )

    assert bad_memory.get_context(
        1
    ) == {
        "error": True,
        "message":
            "INVALID_USER_MEMORY_DATA",
    }


def test_v614_new_context_save_failure_is_not_reported_as_success():

    profile = _Profile(
        {
            "error": False,
            "user": {
                "memory": {},
            },
        },
        save_result={
            "error": True,
        },
    )

    service = AssistantUserContextService(
        profile
    )

    assert service.get_context(
        1
    ) == {
        "error": True,
        "message":
            "INVALID_USER_CONTEXT_SAVE_RESULT",
    }
    assert profile.save_calls == 1


def test_v615_update_validates_profile_and_context_before_mutation():

    user = {
        "context": "bad",
        "memory": {},
    }
    service = AssistantUserContextService(
        _Profile(
            {
                "error": False,
                "user": user,
            }
        )
    )

    result = service.update(
        1,
        "last_message",
        "hello",
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_USER_CONTEXT_DATA",
    }
    assert (
        user["context"]
        ==
        "bad"
    )


def test_v616_remember_rejects_malformed_storage_result():

    service = AssistantUserContextService(
        _Profile(
            {
                "error": False,
                "user": {},
            },
            memory_result={
                "saved": True,
            },
        )
    )

    assert service.remember(
        1,
        "name",
        "Alex",
    ) == {
        "error": True,
        "message":
            "INVALID_USER_MEMORY_SAVE_RESULT",
    }


def test_v617_core_stops_before_orchestrator_on_invalid_initial_context():

    context_service = _Context(
        {
            "error": True,
            "message":
                "INVALID_USER_PROFILE_RESULT",
        },
        {
            "error": False,
            "updated": True,
        },
    )
    orchestrator = _Orchestrator(
        {
            "error": False,
            "message": "ok",
        }
    )

    core = AssistantCoreService(
        orchestrator_service=orchestrator,
        user_context_service=context_service,
    )

    assert core.ask(
        "hello",
        user_id=1,
    ) == {
        "error": True,
        "message":
            "INVALID_USER_CONTEXT_RESULT",
    }
    assert orchestrator.calls == 0


def test_v618_post_execution_context_update_failure_preserves_business_result():

    context_service = _Context(
        _valid_context(),
        {
            "error": True,
            "message": "write failed",
        },
    )
    orchestrator = _Orchestrator(
        {
            "error": False,
            "message": "business result",
            "executed": True,
        }
    )

    core = AssistantCoreService(
        orchestrator_service=orchestrator,
        user_context_service=context_service,
    )

    result = core.ask(
        "execute",
        user_id=1,
    )

    assert result["error"] is False
    assert result["executed"] is True
    assert result[
        "context_persistence_error"
    ] == (
        "INVALID_USER_CONTEXT_UPDATE_RESULT"
    )


def test_v619_post_execution_context_refresh_failure_preserves_business_result():

    context_service = _Context(
        _valid_context(),
        {
            "error": False,
            "updated": True,
        },
        refresh={
            "error": True,
            "message": "bad refresh",
        },
    )
    orchestrator = _Orchestrator(
        {
            "error": False,
            "message": "business result",
            "executed": True,
        }
    )

    core = AssistantCoreService(
        orchestrator_service=orchestrator,
        user_context_service=context_service,
    )

    result = core.ask(
        "execute",
        user_id=1,
    )

    assert result["error"] is False
    assert result["executed"] is True
    assert result[
        "context_persistence_error"
    ] == (
        "INVALID_USER_CONTEXT_REFRESH_RESULT"
    )
