import hashlib
import os

from services.tenant_context import get_current_tenant_user_id


_STORAGE_ROOT_ENV = "AI_ASSISTANT_STORAGE_ROOT"


def _configured_storage_root():
    value = str(os.getenv(_STORAGE_ROOT_ENV, "") or "").strip()
    return value or None


def tenant_storage_path(filename):
    """Resolve a tenant-local path without mutating the filesystem.

    When ``AI_ASSISTANT_STORAGE_ROOT`` is configured, default relative storage
    paths are rooted there so container-local seller state can live on one
    persistent volume. With no configured root, historical relative paths are
    preserved exactly.
    """
    user_id = str(get_current_tenant_user_id() or "").strip()
    if not user_id:
        path = os.fspath(filename)
    else:
        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
        directory = os.path.join("data", "tenants", digest)
        path = os.path.join(directory, os.path.basename(os.fspath(filename)))

    storage_root = _configured_storage_root()
    if storage_root and not os.path.isabs(path):
        return os.path.join(storage_root, path)

    return path


def ensure_storage_parent(path):
    """Create the parent required by an actual storage write/open."""
    parent = os.path.dirname(os.fspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path
