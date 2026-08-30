from services.assistant_telegram_memory_service import (
    AssistantTelegramMemoryService,
)


class _Storage:

    def __init__(
        self,
        user_result,
        save_result=None,
        get_error=None,
        save_error=None,
    ):
        self.user_result = user_result
        self.save_result = save_result
        self.get_error = get_error
        self.save_error = save_error
        self.save_calls = 0

    def get_user(
        self,
        user_id,
    ):
        if self.get_error:
            raise self.get_error

        return self.user_result

    def save(self):
        self.save_calls += 1

        if self.save_error:
            raise self.save_error

        return self.save_result


def _valid_user(
    memory=None,
):

    return {
        "error": False,
        "user": {
            "user_id": "1001",
            "memory": (
                {
                    "name": "Alex",
                }
                if memory is None
                else memory
            ),
            "history": [],
        },
    }


def test_v660_clear_mutates_actual_user_record_and_persists():

    user_result = _valid_user()
    storage = _Storage(
        user_result,
        {
            "error": False,
            "saved": True,
            "atomic_replace": True,
        },
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": False,
        "cleared": True,
    }
    assert user_result[
        "user"
    ]["memory"] == {}
    assert storage.save_calls == 1


def test_v661_explicit_user_read_failure_is_preserved_without_save():

    failure = {
        "error": True,
        "message":
            "USER_STORAGE_LOAD_FAILED",
    }
    storage = _Storage(
        failure,
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result is failure
    assert storage.save_calls == 0


def test_v662_malformed_user_result_fails_closed_without_save():

    storage = _Storage(
        {
            "user": {},
        },
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_TELEGRAM_MEMORY_USER_RESULT",
        "cleared": False,
    }
    assert storage.save_calls == 0


def test_v663_invalid_memory_data_fails_closed_without_mutation():

    user_result = _valid_user(
        memory=[
            "bad",
        ]
    )
    storage = _Storage(
        user_result,
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_TELEGRAM_MEMORY_DATA",
        "cleared": False,
    }
    assert user_result[
        "user"
    ]["memory"] == [
        "bad",
    ]
    assert storage.save_calls == 0


def test_v664_explicit_precommit_save_failure_rolls_back_memory():

    user_result = _valid_user()
    previous = user_result[
        "user"
    ]["memory"]
    storage = _Storage(
        user_result,
        {
            "error": True,
            "message":
                "USER_STORAGE_SAVE_FAILED",
        },
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_SAVE_FAILED",
        "cleared": False,
        "rolled_back": True,
    }
    assert user_result[
        "user"
    ]["memory"] is previous


def test_v665_malformed_save_result_does_not_fabricate_rollback():

    user_result = _valid_user()
    storage = _Storage(
        user_result,
        {
            "error": False,
        },
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_TELEGRAM_MEMORY_SAVE_RESULT",
        "cleared": False,
        "persistence_state_unknown":
            True,
    }
    assert user_result[
        "user"
    ]["memory"] == {}


def test_v666_save_exception_preserves_ambiguous_commit_state():

    user_result = _valid_user()
    storage = _Storage(
        user_result,
        save_error=OSError(
            "unknown commit state"
        ),
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "TELEGRAM_MEMORY_SAVE_FAILED",
        "cleared": False,
        "persistence_state_unknown":
            True,
    }
    assert user_result[
        "user"
    ]["memory"] == {}


def test_v667_postcommit_durability_warning_keeps_clear_committed():

    user_result = _valid_user()
    storage = _Storage(
        user_result,
        {
            "error": False,
            "saved": True,
            "atomic_replace": True,
            "durability_warning":
                "USER_STORAGE_DIRECTORY_FSYNC_FAILED",
        },
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": False,
        "cleared": True,
        "durability_warning":
            "USER_STORAGE_DIRECTORY_FSYNC_FAILED",
    }
    assert user_result[
        "user"
    ]["memory"] == {}


def test_v667_user_read_exception_is_safe_and_non_secret():

    storage = _Storage(
        None,
        get_error=RuntimeError(
            "secret path details"
        ),
    )
    service = AssistantTelegramMemoryService(
        storage
    )

    result = service.clear(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "TELEGRAM_MEMORY_USER_READ_FAILED",
        "cleared": False,
    }
    assert "secret" not in result[
        "message"
    ]
    assert storage.save_calls == 0
