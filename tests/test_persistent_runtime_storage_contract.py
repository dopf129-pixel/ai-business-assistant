import hashlib
from pathlib import Path

from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.tenant_storage import ensure_storage_parent, tenant_storage_path


def _tenant_path(user_id, filename):
    token = set_current_tenant_user_id(user_id)
    try:
        return Path(tenant_storage_path(filename))
    finally:
        reset_current_tenant_user_id(token)


def test_storage_root_is_opt_in_and_preserves_legacy_paths(monkeypatch):
    monkeypatch.delenv("AI_ASSISTANT_STORAGE_ROOT", raising=False)

    assert Path(tenant_storage_path("actions.json")) == Path("actions.json")
    assert Path(tenant_storage_path("data/tax_configuration.json")) == Path(
        "data/tax_configuration.json"
    )


def test_storage_root_relocates_default_legacy_state(monkeypatch, tmp_path):
    root = tmp_path / "persistent"
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(root))

    assert Path(tenant_storage_path("actions.json")) == root / "actions.json"
    assert Path(tenant_storage_path("data/tax_configuration.json")) == (
        root / "data" / "tax_configuration.json"
    )


def test_storage_root_keeps_tenant_partitioning(monkeypatch, tmp_path):
    root = tmp_path / "persistent"
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(root))
    digest_a = hashlib.sha256(b"seller-a").hexdigest()[:24]
    digest_b = hashlib.sha256(b"seller-b").hexdigest()[:24]

    path_a = _tenant_path("seller-a", "ozon_assistant.db")
    path_b = _tenant_path("seller-b", "ozon_assistant.db")

    assert path_a == root / "data" / "tenants" / digest_a / "ozon_assistant.db"
    assert path_b == root / "data" / "tenants" / digest_b / "ozon_assistant.db"
    assert path_a != path_b


def test_storage_resolution_does_not_create_volume_directories(monkeypatch, tmp_path):
    root = tmp_path / "persistent"
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(root))

    path = _tenant_path("seller-a", "assistant_memory.json")

    assert not root.exists()
    ensure_storage_parent(path)
    assert path.parent.is_dir()


def test_absolute_paths_are_not_rebased_by_storage_root(monkeypatch, tmp_path):
    root = tmp_path / "persistent"
    explicit = tmp_path / "custom" / "state.json"
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(root))

    assert Path(tenant_storage_path(explicit)) == explicit
