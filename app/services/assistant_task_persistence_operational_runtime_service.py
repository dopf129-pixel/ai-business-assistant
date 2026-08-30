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

    RELEASE_TOKENS = (
        "готовность persistence",
        "готовность хранилища задач",
        "task persistence release",
        "task persistence release status",
        "/task-persistence-release",
    )

    def __init__(
        self,
        operational_service,
        access_policy,
        presentation_service,
        release_observability_service=None,
    ):
        self.operational_service = operational_service
        self.access_policy = access_policy
        self.presentation_service = presentation_service
        self.release_observability_service = release_observability_service

    def handle_text(self, text, user_id=None):
        value = " ".join(str(text or "").strip().lower().split())
        release_requested = any(
            token in value for token in self.RELEASE_TOKENS
        )
        operational_requested = any(
            token in value for token in self.TOKENS
        )

        if not release_requested and not operational_requested:
            return None

        if not self.access_policy.is_allowed(user_id):
            return self._access_denied()

        if release_requested:
            if self.release_observability_service is None:
                return self._release_unavailable()
            try:
                report = (
                    self.release_observability_service
                    .build_release_report()
                )
            except Exception:
                return self._release_unavailable()

            if not isinstance(report, dict):
                return self._release_unavailable()

            try:
                presented = (
                    self.presentation_service
                    .present_release(report)
                )
            except Exception:
                return self._release_unavailable()

            if not isinstance(presented, dict):
                return self._release_unavailable()

            presented["operator_authorized"] = True
            return presented

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
    def _release_unavailable():
        return {
            "error": True,
            "code": "TASK_PERSISTENCE_RELEASE_STATUS_UNAVAILABLE",
            "status": "TASK_PERSISTENCE_RELEASE_READINESS",
            "release_ready": False,
            "operator_authorized": True,
            "human_review_required": True,
            "message": (
                "Release-готовность хранилища задач недоступна. "
                "Нужна ручная проверка persistence boundary."
            ),
            "automatic_retry_allowed": False,
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
