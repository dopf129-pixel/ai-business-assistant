class TaskPersistenceOperatorPresentationService:
    """Render non-sensitive Russian operator guidance from canonical reports."""

    def present(self, report):
        if not self._valid_operational_report(report):
            return self._unavailable()

        result = dict(report)
        state = result["operational_state"]
        blockers = list(result["blockers"])
        warnings = list(result["warnings"])

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

        return self._decorate(result, message)

    def present_provenance(self, report):
        if not self._valid_provenance_report(report):
            return self._provenance_unavailable()

        result = dict(report)
        ci_state = result["ci_evidence_state"]
        revision = result["revision_id"]

        if ci_state == "BOUND":
            message = (
                "Provenance persistence: implementation/runtime evidence "
                "связано с caller-supplied exact-SHA CI metadata. "
                "Это не external verification."
            )
        elif revision is not None:
            message = (
                "Provenance persistence: revision объявлен, но exact-SHA CI "
                "evidence не привязан. External verification отсутствует."
            )
        else:
            message = (
                "Provenance persistence: implementation/runtime evidence доступно, "
                "но revision и CI evidence не привязаны. "
                "Active probing production store не выполнялся."
            )

        return self._decorate(result, message)

    def present_release(self, report):
        if not self._valid_release_report(report):
            return self._release_unavailable()

        result = dict(report)
        release_ready = result["release_ready"]
        categories = list(result["incident_categories"])
        blockers = list(result["blockers"])
        warnings = list(result["warnings"])

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

        return self._decorate(result, message)

    @classmethod
    def _valid_operational_report(cls, report):
        if not (
            isinstance(report, dict)
            and report.get("error") is False
            and report.get("status") == "TASK_PERSISTENCE_OPERATIONAL_READINESS"
            and report.get("operational_state") in {"READY", "WARNING", "BLOCKED"}
            and cls._valid_string_list(report.get("blockers"))
            and cls._valid_string_list(report.get("warnings"))
            and type(report.get("blocker_count")) is int
            and type(report.get("warning_count")) is int
            and report.get("blocker_count") == len(report.get("blockers"))
            and report.get("warning_count") == len(report.get("warnings"))
            and type(report.get("operator_attention_required")) is bool
            and report.get("write_lock_stale_proven") is False
            and report.get("automatic_lock_recovery_allowed") is False
            and report.get("manual_lock_removal_allowed") is False
            and report.get("business_execution_ready") is False
            and report.get("mutation_ready") is False
            and report.get("read_only") is True
            and report.get("executed") is False
        ):
            return False

        blockers = report["blockers"]
        warnings = report["warnings"]
        expected_state = (
            "BLOCKED"
            if blockers
            else "WARNING"
            if warnings
            else "READY"
        )
        return (
            report["operational_state"] == expected_state
            and report["operator_attention_required"]
            is (expected_state != "READY")
        )

    @classmethod
    def _valid_release_report(cls, report):
        if not (
            isinstance(report, dict)
            and report.get("error") is False
            and report.get("status") == "TASK_PERSISTENCE_RELEASE_READINESS"
            and type(report.get("release_ready")) is bool
            and report.get("operational_state") in {"READY", "WARNING", "BLOCKED"}
            and cls._valid_string_list(report.get("blockers"))
            and cls._valid_string_list(report.get("warnings"))
            and cls._valid_string_list(report.get("incident_categories"))
            and type(report.get("incident_detected")) is bool
            and type(report.get("human_review_required")) is bool
            and isinstance(report.get("capabilities"), dict)
            and bool(report.get("capabilities"))
            and all(
                isinstance(name, str)
                and bool(name)
                and type(value) is bool
                for name, value in report.get("capabilities").items()
            )
            and cls._required_string(report.get("audit_receipt_id")) is not None
            and report.get("automatic_retry_allowed") is False
            and report.get("automatic_lock_recovery_allowed") is False
            and report.get("manual_lock_removal_allowed") is False
            and report.get("business_execution_ready") is False
            and report.get("mutation_ready") is False
            and report.get("read_only") is True
            and report.get("executed") is False
        ):
            return False

        blockers = report["blockers"]
        warnings = report["warnings"]
        categories = report["incident_categories"]
        return (
            report["release_ready"] is (not blockers)
            and report["incident_detected"]
            is bool(categories or blockers or warnings)
            and report["human_review_required"]
            is bool(blockers or warnings)
        )

    @classmethod
    def _valid_provenance_report(cls, report):
        if not (
            isinstance(report, dict)
            and report.get("error") is False
            and report.get("status")
            == "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_REPORT"
            and cls._required_string(report.get("manifest_id")) is not None
            and cls._required_string(report.get("audit_receipt_id")) is not None
            and type(report.get("revision_declared")) is bool
            and type(report.get("release_ready")) is bool
            and type(report.get("capability_count")) is int
            and report.get("capability_count") >= 0
            and isinstance(report.get("capabilities"), list)
            and report.get("capability_count") == len(report.get("capabilities"))
            and type(report.get("implementation_contract_count")) is int
            and type(report.get("runtime_observation_count")) is int
            and report.get("implementation_contract_count") >= 0
            and report.get("runtime_observation_count") >= 0
            and (
                report.get("implementation_contract_count")
                + report.get("runtime_observation_count")
                == report.get("capability_count")
            )
            and report.get("ci_evidence_state") in {"BOUND", "UNBOUND"}
            and type(report.get("ci_evidence_bound")) is bool
            and report.get("active_probe_performed") is False
            and report.get("externally_verified") is False
            and report.get("automatic_retry_allowed") is False
            and report.get("automatic_lock_recovery_allowed") is False
            and report.get("manual_lock_removal_allowed") is False
            and report.get("business_execution_ready") is False
            and report.get("mutation_ready") is False
            and report.get("read_only") is True
            and report.get("executed") is False
        ):
            return False

        revision = report.get("revision_id")
        if report["revision_declared"] is (revision is None):
            return False
        if revision is not None and not cls._valid_sha(revision):
            return False

        if report["ci_evidence_state"] == "BOUND":
            return (
                report["ci_evidence_bound"] is True
                and report["revision_declared"] is True
                and type(report.get("ci_run_number")) is int
                and report.get("ci_run_number") > 0
                and type(report.get("ci_passed")) is int
                and report.get("ci_passed") >= 0
            )

        return (
            report["ci_evidence_bound"] is False
            and report.get("ci_run_number") is None
            and report.get("ci_passed") is None
        )

    @staticmethod
    def _valid_string_list(value):
        return (
            isinstance(value, list)
            and all(isinstance(item, str) and bool(item) for item in value)
            and len(value) == len(set(value))
        )

    @staticmethod
    def _required_string(value):
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _valid_sha(value):
        if not isinstance(value, str) or len(value) != 40:
            return False
        try:
            int(value, 16)
        except ValueError:
            return False
        return True

    @staticmethod
    def _decorate(result, message):
        result["message"] = message
        result["operator_message_generated"] = True
        result["path_exposed"] = False
        result["user_id_exposed"] = False
        result["lock_owner_inferred"] = False
        result["lock_age_inferred"] = False
        return result

    @staticmethod
    def _provenance_unavailable():
        return {
            "error": True,
            "code": "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_PRESENTATION_UNAVAILABLE",
            "status": "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_REPORT",
            "message": (
                "Provenance persistence недоступен. "
                "Нужна ручная проверка evidence."
            ),
            "active_probe_performed": False,
            "externally_verified": False,
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
