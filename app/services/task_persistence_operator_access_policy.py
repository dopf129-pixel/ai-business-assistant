class TaskPersistenceOperatorAccessPolicy:
    """Explicit default-deny operator access policy for persistence diagnostics."""

    def __init__(self, allowed_user_ids=None):
        values = allowed_user_ids or ()
        normalized = set()

        for value in values:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("INVALID_TASK_PERSISTENCE_OPERATOR_USER_ID")
            normalized.add(value)

        self._allowed_user_ids = frozenset(normalized)

    def is_allowed(self, user_id):
        return (
            isinstance(user_id, int)
            and not isinstance(user_id, bool)
            and user_id > 0
            and user_id in self._allowed_user_ids
        )

    def get_diagnostics(self):
        return {
            "error": False,
            "status": "TASK_PERSISTENCE_OPERATOR_ACCESS_POLICY",
            "configured": bool(self._allowed_user_ids),
            "allowed_count": len(self._allowed_user_ids),
            "default_deny": True,
            "user_ids_exposed": False,
            "read_only": True,
            "executed": False,
        }
