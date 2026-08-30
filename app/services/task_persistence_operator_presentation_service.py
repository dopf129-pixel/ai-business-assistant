class TaskPersistenceOperatorPresentationService:
    """Render non-sensitive Russian operator guidance from a canonical report."""

    def present(self, report):
        if not isinstance(report, dict):
            return self._unavailable()

        result = dict(report)
        state = result.get("operational_state")
        blockers = list(result.get("blockers") or [])
        warnings = list(result.get("warnings") or [])

        if state == "READY":
            message = (
                "Хранилище задач: готово. "
                "Критических проблем persistence не обнаружено. "
                "Автоматическое восстановление lock отключено."
            )
        elif "TASK_FILE_WRITE_LOCKED" in blockers:
            message = (
                "Хранилище задач: заблокировано. "
                "При последней попытке записи kernel lock был занят другим writer. "
                "Владелец и stale-статус не выводятся. "
                "Не удаляйте coordination file: он не является признаком stale lock. "
                "Повторите запись вручную только после завершения активного writer."
            )
        elif "TASK_WRITE_LOCK_INSPECTION_FAILED" in blockers:
            message = (
                "Хранилище задач: заблокировано. "
                "Не удалось безопасно проверить write-lock. "
                "Нужна ручная проверка persistence boundary."
            )
        elif "TASK_STORE_UNREADABLE" in blockers or "TASK_STORE_INVALID_ROOT" in blockers:
            message = (
                "Хранилище задач: заблокировано. "
                "Persisted task store требует ручного восстановления или проверки формата."
            )
        elif state == "BLOCKED":
            message = (
                "Хранилище задач: заблокировано. "
                "Последняя операция persistence требует ручной проверки. "
                "Автоматический retry не выполняется."
            )
        elif "TASK_DIRECTORY_FSYNC_ERROR" in warnings:
            message = (
                "Хранилище задач: предупреждение. "
                "Запись завершилась, но crash-durability родительской директории "
                "не удалось подтвердить. Проверьте файловую систему."
            )
        elif state == "WARNING":
            message = (
                "Хранилище задач: предупреждение. "
                "Есть persistence-сигналы, требующие внимания оператора."
            )
        else:
            return self._unavailable()

        result["message"] = message
        result["operator_message_generated"] = True
        result["path_exposed"] = False
        result["user_id_exposed"] = False
        result["lock_owner_inferred"] = False
        result["lock_age_inferred"] = False
        return result

    def present_release(self, report):
        if not isinstance(report, dict):
            return self._release_unavailable()

        result = dict(report)
        if result.get("status") != "TASK_PERSISTENCE_RELEASE_READINESS":
            return self._release_unavailable()

        release_ready = result.get("release_ready")
        categories = list(result.get("incident_categories") or [])
        blockers = list(result.get("blockers") or [])
        warnings = list(result.get("warnings") or [])

        if release_ready is True:
            if warnings:
                message = (
                    "Release-готовность persistence: готово с предупреждениями. "
                    "Критические capability blockers отсутствуют, "
                    "но оператору нужно просмотреть текущие warning-сигналы."
                )
            else:
                message = (
                    "Release-готовность persistence: готово. "
                    "Kernel lock, optimistic concurrency, atomic replace "
                    "и fsync capability evidence подтверждены."
                )
        elif "LOCK_CONTENTION" in categories:
            message = (
                "Release-готовность persistence: заблокировано. "
                "Последняя запись встретила активный kernel-lock contention. "
                "Автоматический retry и удаление coordination file запрещены."
            )
        elif "DURABILITY" in categories:
            message = (
                "Release-готовность persistence: требует проверки durability. "
                "Запись могла завершиться, но directory fsync evidence "
                "содержит предупреждение."
            )
        elif blockers:
            message = (
                "Release-готовность persistence: заблокировано. "
                "Есть release blockers или отсутствующее capability evidence. "
                "Нужна ручная проверка."
            )
        else:
            message = (
                "Release-готовность persistence: не подтверждена. "
                "Нужна ручная проверка release evidence."
            )

        result["message"] = message
        result["operator_message_generated"] = True
        result["path_exposed"] = False
        result["user_id_exposed"] = False
        result["lock_owner_inferred"] = False
        result["lock_age_inferred"] = False
        return result

    @staticmethod
    def _release_unavailable():
        return {
            "error": True,
            "code": "TASK_PERSISTENCE_RELEASE_PRESENTATION_UNAVAILABLE",
            "status": "TASK_PERSISTENCE_RELEASE_READINESS",
            "release_ready": False,
            "human_review_required": True,
            "message": (
                "Release-готовность persistence недоступна. "
                "Нужна ручная проверка."
            ),
            "automatic_retry_allowed": False,
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "path_exposed": False,
            "user_id_exposed": False,
            "lock_owner_inferred": False,
            "lock_age_inferred": False,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _unavailable():
        return {
            "error": True,
            "code": "TASK_PERSISTENCE_OPERATOR_PRESENTATION_UNAVAILABLE",
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "operational_state": "BLOCKED",
            "operator_attention_required": True,
            "message": (
                "Статус хранилища задач недоступен. "
                "Нужна ручная проверка persistence boundary."
            ),
            "automatic_lock_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "business_execution_ready": False,
            "mutation_ready": False,
            "path_exposed": False,
            "user_id_exposed": False,
            "lock_owner_inferred": False,
            "lock_age_inferred": False,
            "read_only": True,
            "executed": False,
        }
