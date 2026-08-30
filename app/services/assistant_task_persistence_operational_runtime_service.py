class AssistantTaskPersistenceOperationalRuntimeService:
    """Read-only explicit runtime route for task persistence operator status."""

    TOKENS = (
        "статус хранилища задач",
        "диагностика хранилища задач",
        "статус persistence задач",
        "task persistence status",
        "task persistence diagnostics",
        "task storage status",
        "/task-persistence",
    )

    def __init__(
        self,
        operational_service,
        access_policy,
        presentation_service,
    ):
        self.operational_service = operational_service
        self.access_policy = access_policy
        self.presentation_service = presentation_service

    def handle_text(self, text, user_id=None):
        value = " ".join(str(text or "").strip().lower().split())
        if not any(token in value for token in self.TOKENS):
            return None

        if not self.access_policy.is_allowed(user_id):
            return self._access_denied()

        try:
            report = self.operational_service.build_report()
        except Exception:
            return self._unavailable()

        if not isinstance(report, dict):
            return self._unavailable()

        try:
            presented = self.presentation_service.present(report)
        except Exception:
            return self._unavailable()

        if not isinstance(presented, dict):
            return self._unavailable()

        presented["operator_authorized"] = True
        return presented

    @staticmethod
    def _access_denied():
        return {
            "error": True,
            "code": "TASK_PERSISTENCE_OPERATOR_ACCESS_DENIED",
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "operational_state": "BLOCKED",
            "operator_authorized": False,
            "operator_attention_required": False,
            "message": "Недостаточно прав для просмотра статуса хранилища задач.",
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "path_exposed": False,
            "user_id_exposed": False,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _unavailable():
        return {
            "error": True,
            "code": "TASK_PERSISTENCE_OPERATIONAL_STATUS_UNAVAILABLE",
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "operational_state": "BLOCKED",
            "operator_attention_required": True,
            "operator_authorized": True,
            "next_action": "INSPECT_TASK_PERSISTENCE_MANUALLY",
            "business_execution_ready": False,
            "mutation_ready": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "path_exposed": False,
            "user_id_exposed": False,
            "read_only": True,
            "executed": False,
        }
