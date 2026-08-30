import json

from services.assistant_user_storage_service import (
    AssistantUserStorageService,
)


def test_v620_malformed_json_load_fails_closed_without_overwrite(
    tmp_path,
):

    path = tmp_path / "users.json"
    original = b"{broken-json"
    path.write_bytes(
        original
    )

    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    assert (
        service.load_state
        ==
        "ERROR"
    )

    result = service.get_user(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_LOAD_FAILED",
    }

    assert path.read_bytes() == original


def test_v621_non_dict_root_fails_closed_without_overwrite(
    tmp_path,
):

    path = tmp_path / "users.json"
    original = b"[]"
    path.write_bytes(
        original
    )

    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    assert service.save_memory(
        1001,
        "name",
        "Alex",
    ) == {
        "error": True,
        "message":
            "USER_STORAGE_ROOT_INVALID",
    }

    assert path.read_bytes() == original


def test_v622_absent_store_can_create_user_normally(
    tmp_path,
):

    path = tmp_path / "users.json"

    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    assert (
        service.load_state
        ==
        "ABSENT"
    )

    result = service.get_user(
        1001
    )

    assert result["error"] is False
    assert (
        result["user"][
            "user_id"
        ]
        ==
        "1001"
    )
    assert path.exists()
    assert (
        service.load_state
        ==
        "LOADED"
    )


def test_v623_malformed_existing_user_record_is_not_replaced(
    tmp_path,
):

    path = tmp_path / "users.json"
    payload = {
        "1001": "bad-record",
    }
    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )

    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    result = service.get_user(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_USER_INVALID",
    }

    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == payload


def test_v624_malformed_memory_and_history_are_not_mutated(
    tmp_path,
):

    path = tmp_path / "users.json"
    payload = {
        "1001": {
            "user_id": "1001",
            "memory": "bad",
            "history": [],
        },
        "1002": {
            "user_id": "1002",
            "memory": {},
            "history": "bad",
        },
    }
    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )

    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    assert service.save_memory(
        1001,
        "name",
        "Alex",
    ) == {
        "error": True,
        "message":
            "USER_STORAGE_USER_INVALID",
    }

    assert service.add_history(
        1002,
        {
            "event": "x",
        },
    ) == {
        "error": True,
        "message":
            "USER_STORAGE_USER_INVALID",
    }

    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == payload


def test_v625_new_user_is_removed_from_memory_when_save_fails(
    tmp_path,
    monkeypatch,
):

    path = tmp_path / "users.json"
    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    monkeypatch.setattr(
        service,
        "save",
        lambda: {
            "error": True,
            "message":
                "USER_STORAGE_SAVE_FAILED",
        },
    )

    result = service.create_user(
        1001
    )

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_SAVE_FAILED",
    }
    assert (
        "1001"
        not in service.users
    )


def test_v626_memory_change_rolls_back_when_save_fails(
    tmp_path,
    monkeypatch,
):

    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(
            {
                "1001": {
                    "user_id":
                        "1001",
                    "memory": {
                        "name":
                            "Old",
                    },
                    "history": [],
                }
            }
        ),
        encoding="utf-8",
    )

    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    monkeypatch.setattr(
        service,
        "save",
        lambda: {
            "error": True,
            "message":
                "USER_STORAGE_SAVE_FAILED",
        },
    )

    result = service.save_memory(
        1001,
        "name",
        "New",
    )

    assert result["error"] is True
    assert (
        service.users[
            "1001"
        ]["memory"]["name"]
        ==
        "Old"
    )


def test_v627_history_append_rolls_back_when_save_fails(
    tmp_path,
    monkeypatch,
):

    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(
            {
                "1001": {
                    "user_id":
                        "1001",
                    "memory": {},
                    "history": [
                        {
                            "event":
                                "old",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    monkeypatch.setattr(
        service,
        "save",
        lambda: {
            "error": True,
            "message":
                "USER_STORAGE_SAVE_FAILED",
        },
    )

    result = service.add_history(
        1001,
        {
            "event": "new",
        },
    )

    assert result["error"] is True
    assert (
        service.users[
            "1001"
        ]["history"]
        ==
        [
            {
                "event": "old",
            }
        ]
    )


def test_v628_valid_memory_and_history_persistence_remains_compatible(
    tmp_path,
):

    path = tmp_path / "users.json"
    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    assert service.save_memory(
        1001,
        "name",
        "Alex",
    ) == {
        "error": False,
        "saved": True,
    }

    assert service.add_history(
        1001,
        {
            "event": "created",
        },
    ) == {
        "error": False,
        "saved": True,
    }

    reloaded = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    assert reloaded.get_memory(
        1001
    ) == {
        "error": False,
        "memory": {
            "name": "Alex",
        },
    }

    assert reloaded.get_history(
        1001
    ) == {
        "error": False,
        "history": [
            {
                "event": "created",
            }
        ],
    }
