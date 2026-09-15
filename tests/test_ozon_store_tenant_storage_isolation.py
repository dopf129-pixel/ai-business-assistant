from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.tenant_storage import tenant_storage_path


def _path_for(scope):
    token = set_current_tenant_user_id(scope)
    try:
        return tenant_storage_path("ozon_assistant.db")
    finally:
        reset_current_tenant_user_id(token)


def test_each_ozon_store_has_a_distinct_local_storage_path(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path))

    first = _path_for(make_store_tenant_scope("telegram-42", "store-a"))
    second = _path_for(make_store_tenant_scope("telegram-42", "store-b"))
    first_again = _path_for(make_store_tenant_scope("telegram-42", "store-a"))

    assert first != second
    assert first == first_again
    assert first.startswith(str(tmp_path))
    assert second.startswith(str(tmp_path))


def test_store_scope_is_separate_from_legacy_user_scope(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path))

    legacy = _path_for("telegram-42")
    store = _path_for(make_store_tenant_scope("telegram-42", "store-a"))

    # Existing mixed per-user data is intentionally not reused by a store.
    # It cannot be safely attributed retrospectively to one of several stores.
    assert legacy != store
