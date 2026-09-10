import hashlib
import os

from services.tenant_context import get_current_tenant_user_id


def tenant_storage_path(filename):
    user_id = str(get_current_tenant_user_id() or "").strip()
    if not user_id:
        return filename

    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    directory = os.path.join("data", "tenants", digest)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, os.path.basename(filename))
