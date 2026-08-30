from services.assistant_user_context_service import (
    AssistantUserContextService,
)


class _Profile:

    def __init__(
        self,
        user,
        save_result,
    ):
        self.user = user
        self.save_result = save_result
        self.save_calls = 0

    def get_user(
        self,
        user_id,
    ):
        return {
            "error": False,
            "user": self.user,
        }

    def save(self):
        self.save_calls += 1
        return self.save_result

    def save_memory(
        self,
        user_id,
        key,
        value,
    ):
        return {
            "error": False,
            "saved": True,
        }


def test_v638_default_context_rolls_back_on_explicit_save_failure():

    user = {
        "memory": {},
    }
    service = AssistantUserContextService(
        _Profile(
            user,
            {
                "error": True,
                "message": "save failed",
            },
        )
    )

    result = service.get_context(
        1
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_USER_CONTEXT_SAVE_RESULT",
    }
    assert "context" not in user


def test_v639_existing_context_value_restored_on_explicit_save_failure():

    user = {
        "context": {
            "last_message": "old",
        },
        "memory": {},
    }
    service = AssistantUserContextService(
        _Profile(
            user,
            {
                "error": True,
            },
        )
    )

    result = service.update(
        1,
        "last_message",
        "new",
    )

    assert result["error"] is True
    assert user["context"] == {
        "last_message": "old",
    }


def test_v640_new_context_key_removed_on_explicit_save_failure():

    user = {
        "context": {
            "last_message": "old",
        },
        "memory": {},
    }
    service = AssistantUserContextService(
        _Profile(
            user,
            {
                "error": True,
            },
        )
    )

    result = service.update(
        1,
        "current_task",
        "task-1",
    )

    assert result["error"] is True
    assert user["context"] == {
        "last_message": "old",
    }


def test_v641_created_context_removed_on_explicit_save_failure():

    user = {
        "memory": {},
    }
    service = AssistantUserContextService(
        _Profile(
            user,
            {
                "error": True,
            },
        )
    )

    result = service.update(
        1,
        "last_message",
        "hello",
    )

    assert result["error"] is True
    assert "context" not in user


def test_v642_ambiguous_save_result_does_not_fabricate_rollback():

    user = {
        "context": {
            "last_message": "old",
        },
        "memory": {},
    }
    service = AssistantUserContextService(
        _Profile(
            user,
            {
                "saved": True,
            },
        )
    )

    result = service.update(
        1,
        "last_message",
        "new",
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_USER_CONTEXT_SAVE_RESULT",
    }
    assert user["context"] == {
        "last_message": "new",
    }


def test_v643_successful_save_keeps_context_update():

    user = {
        "context": {
            "last_message": "old",
        },
        "memory": {},
    }
    profile = _Profile(
        user,
        {
            "error": False,
            "saved": True,
        },
    )
    service = AssistantUserContextService(
        profile
    )

    result = service.update(
        1,
        "last_message",
        "new",
    )

    assert result == {
        "error": False,
        "updated": True,
    }
    assert user["context"] == {
        "last_message": "new",
    }
    assert profile.save_calls == 1


def test_v644_post_commit_durability_warning_is_not_rolled_back():

    user = {
        "context": {
            "last_message": "old",
        },
        "memory": {},
    }
    service = AssistantUserContextService(
        _Profile(
            user,
            {
                "error": False,
                "saved": True,
                "durability_warning":
                    "USER_STORAGE_DIRECTORY_FSYNC_FAILED",
            },
        )
    )

    result = service.update(
        1,
        "last_message",
        "committed",
    )

    assert result == {
        "error": False,
        "updated": True,
    }
    assert user["context"] == {
        "last_message": "committed",
    }
