import json

from services.assistant_user_storage_service import (
    AssistantUserStorageService,
)


def _service_with_payload(
    tmp_path,
    payload,
):
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return (
        AssistantUserStorageService(
            file_path=str(path),
        ),
        path,
    )


def _invalid_user_result():
    return {
        "error": True,
        "message": "USER_STORAGE_USER_INVALID",
    }


def test_v645_existing_null_user_record_is_not_recreated(tmp_path):
    payload = {
        "1001": None,
    }
    service, path = _service_with_payload(
        tmp_path,
        payload,
    )

    assert service.get_user(1001) == _invalid_user_result()
    assert service.users == payload
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_v646_existing_empty_user_record_fails_closed(tmp_path):
    payload = {
        "1001": {},
    }
    service, path = _service_with_payload(
        tmp_path,
        payload,
    )

    assert service.get_user(1001) == _invalid_user_result()
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_v647_existing_user_requires_memory_field(tmp_path):
    payload = {
        "1001": {
            "user_id": "1001",
            "history": [],
        },
    }
    service, _ = _service_with_payload(
        tmp_path,
        payload,
    )

    assert service.get_user(1001) == _invalid_user_result()


def test_v648_existing_user_requires_history_field(tmp_path):
    payload = {
        "1001": {
            "user_id": "1001",
            "memory": {},
        },
    }
    service, _ = _service_with_payload(
        tmp_path,
        payload,
    )

    assert service.get_user(1001) == _invalid_user_result()


def test_v649_existing_user_id_must_match_storage_key(tmp_path):
    payload = {
        "1001": {
            "user_id": "2002",
            "memory": {},
            "history": [],
        },
    }
    service, path = _service_with_payload(
        tmp_path,
        payload,
    )

    assert service.save_memory(
        1001,
        "name",
        "Alex",
    ) == _invalid_user_result()
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_v650_valid_existing_user_with_optional_context_remains_compatible(
    tmp_path,
):
    payload = {
        "1001": {
            "user_id": "1001",
            "memory": {
                "name": "Alex",
            },
            "history": [],
            "context": {
                "last_message": "hello",
            },
        },
    }
    service, _ = _service_with_payload(
        tmp_path,
        payload,
    )

    result = service.get_user(1001)

    assert result["error"] is False
    assert result["user"] == payload["1001"]


def test_v651_absent_user_still_uses_normal_creation_path(tmp_path):
    path = tmp_path / "users.json"
    service = AssistantUserStorageService(
        file_path=str(path),
    )

    result = service.get_user(1001)

    assert result["error"] is False
    assert result["user"] == {
        "user_id": "1001",
        "memory": {},
        "history": [],
    }
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "1001": result["user"],
    }
