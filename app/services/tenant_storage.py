import hashlib
import os

from services.tenant_context import get_current_tenant_user_id


def tenant_storage_path(filename):
    """Resolve a tenant-local path without mutating the filesystem."""
    user_id = str(get_current_tenant_user_id() or "").strip()
    if not user_id:
        return filename

    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    directory = os.path.join("data", "tenants", digest)
    return os.path.join(directory, os.path.basename(filename))


def ensure_storage_parent(path):
    """Create the parent required by an actual storage write/open."""
    parent = os.path.dirname(os.fspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path
