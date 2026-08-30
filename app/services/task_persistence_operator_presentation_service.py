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
        elif "TASK_WRITE_LOCK_PRESENT_UNOWNED" in blockers:
            message = (
                "Хранилище задач: заблокировано. "
                "Обнаружен write-lock, но его владелец и stale-статус не подтверждены. "
                "Не удаляйте lock автоматически. "
                "Сначала вручную подтвердите владельца и безопасность удаления."
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
