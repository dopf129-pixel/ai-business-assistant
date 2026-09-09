from contextvars import ContextVar


_CURRENT_TENANT_USER_ID = ContextVar(
    "current_tenant_user_id",
    default=None,
)


def set_current_tenant_user_id(user_id):
    value = str(user_id or "").strip()
    return _CURRENT_TENANT_USER_ID.set(value or None)


def reset_current_tenant_user_id(token):
    _CURRENT_TENANT_USER_ID.reset(token)


def get_current_tenant_user_id():
    return _CURRENT_TENANT_USER_ID.get()
