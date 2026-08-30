import json
import os

from services.assistant_user_storage_service import (
    AssistantUserStorageService,
)


def _existing_service(
    tmp_path,
):

    path = tmp_path / "users.json"
    payload = {
        "1001": {
            "user_id": "1001",
            "memory": {
                "name": "Old",
            },
            "history": [
                {
                    "event": "old",
                }
            ],
        }
    }
    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )

    return (
        path,
        payload,
        AssistantUserStorageService(
            file_path=str(
                path
            )
        ),
    )


def _temps(
    tmp_path,
):

    return list(
        tmp_path.glob(
            ".users-write-*.tmp"
        )
    )


def test_v629_serialization_failure_does_not_touch_target(
    tmp_path,
):

    path, payload, service = (
        _existing_service(
            tmp_path
        )
    )

    service.users[
        "1001"
    ]["memory"]["bad"] = object()

    result = service.save()

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_SERIALIZATION_FAILED",
    }

    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == payload
    assert _temps(
        tmp_path
    ) == []


def test_v630_replace_failure_preserves_original_and_cleans_temp(
    tmp_path,
    monkeypatch,
):

    path, payload, service = (
        _existing_service(
            tmp_path
        )
    )

    service.users[
        "1001"
    ]["memory"]["name"] = "New"

    def fail_replace(
        source,
        target,
    ):
        raise OSError(
            "replace failed"
        )

    monkeypatch.setattr(
        os,
        "replace",
        fail_replace,
    )

    result = service.save()

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_SAVE_FAILED",
    }
    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == payload
    assert _temps(
        tmp_path
    ) == []


def test_v631_file_fsync_failure_preserves_original_and_cleans_temp(
    tmp_path,
    monkeypatch,
):

    path, payload, service = (
        _existing_service(
            tmp_path
        )
    )

    service.users[
        "1001"
    ]["memory"]["name"] = "New"

    def fail_fsync(
        fd,
    ):
        raise OSError(
            "fsync failed"
        )

    monkeypatch.setattr(
        os,
        "fsync",
        fail_fsync,
    )

    result = service.save()

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_SAVE_FAILED",
    }
    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == payload
    assert _temps(
        tmp_path
    ) == []


def test_v632_successful_save_uses_atomic_replace_and_leaves_no_temp(
    tmp_path,
):

    path, _, service = (
        _existing_service(
            tmp_path
        )
    )

    service.users[
        "1001"
    ]["memory"]["name"] = "New"

    result = service.save()

    assert result["error"] is False
    assert result["saved"] is True
    assert (
        result["atomic_replace"]
        is True
    )
    assert (
        "durability_warning"
        not in result
    )
    assert (
        json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )["1001"]["memory"]["name"]
        ==
        "New"
    )
    assert _temps(
        tmp_path
    ) == []


def test_v633_directory_fsync_failure_is_post_commit_warning_not_rollback(
    tmp_path,
    monkeypatch,
):

    path, _, service = (
        _existing_service(
            tmp_path
        )
    )

    service.users[
        "1001"
    ]["memory"]["name"] = "Committed"

    real_fsync = os.fsync
    calls = {
        "count": 0,
    }

    def second_fsync_fails(
        fd,
    ):
        calls["count"] += 1

        if calls["count"] == 1:
            return real_fsync(
                fd
            )

        raise OSError(
            "directory fsync failed"
        )

    monkeypatch.setattr(
        os,
        "fsync",
        second_fsync_fails,
    )

    result = service.save()

    assert result == {
        "error": False,
        "saved": True,
        "atomic_replace": True,
        "durability_warning":
            "USER_STORAGE_DIRECTORY_FSYNC_FAILED",
    }
    assert (
        json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )["1001"]["memory"]["name"]
        ==
        "Committed"
    )
    assert _temps(
        tmp_path
    ) == []


def test_v634_save_memory_rolls_back_on_serialization_failure(
    tmp_path,
):

    _, _, service = (
        _existing_service(
            tmp_path
        )
    )

    result = service.save_memory(
        1001,
        "bad",
        object(),
    )

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_SERIALIZATION_FAILED",
    }
    assert (
        "bad"
        not in service.users[
            "1001"
        ]["memory"]
    )


def test_v635_add_history_rolls_back_on_serialization_failure(
    tmp_path,
):

    _, _, service = (
        _existing_service(
            tmp_path
        )
    )

    result = service.add_history(
        1001,
        object(),
    )

    assert result == {
        "error": True,
        "message":
            "USER_STORAGE_SERIALIZATION_FAILED",
    }
    assert service.users[
        "1001"
    ]["history"] == [
        {
            "event": "old",
        }
    ]


def test_v636_absent_store_is_created_through_atomic_write(
    tmp_path,
):

    path = tmp_path / "users.json"
    service = AssistantUserStorageService(
        file_path=str(
            path
        )
    )

    result = service.get_user(
        1001
    )

    assert result["error"] is False
    assert path.exists()
    assert (
        service.load_state
        ==
        "LOADED"
    )
    assert _temps(
        tmp_path
    ) == []


def test_v637_atomic_output_reloads_with_full_memory_and_history(
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
    )["error"] is False

    assert service.add_history(
        1001,
        {
            "event": "created",
        },
    )["error"] is False

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
