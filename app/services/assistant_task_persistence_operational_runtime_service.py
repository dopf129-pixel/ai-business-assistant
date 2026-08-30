class AssistantTaskPersistenceOperationalRuntimeService:
    """Read-only explicit runtime route for task persistence operator status."""

    TOKENS = (
        "статус хранилища задач",
        "диагностика хранилища задач",
        "статус persistence задач",
        "task persistence status",
        "task persistence diagnostics",
        "task storage status",
    )

    def __init__(self, operational_service):
        self.operational_service = operational_service

    def handle_text(self, text):
        value = " ".join(str(text or "").strip().lower().split())
        if not any(token in value for token in self.TOKENS):
            return None

        try:
            report = self.operational_service.build_report()
        except Exception:
            return self._unavailable()

        if not isinstance(report, dict):
            return self._unavailable()

        return report

    @staticmethod
    def _unavailable():
        return {
            "error": True,
            "code": "TASK_PERSISTENCE_OPERATIONAL_STATUS_UNAVAILABLE",
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "operational_state": "BLOCKED",
            "operator_attention_required": True,
            "next_action": "INSPECT_TASK_PERSISTENCE_MANUALLY",
            "business_execution_ready": False,
            "mutation_ready": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "read_only": True,
            "executed": False,
        }
