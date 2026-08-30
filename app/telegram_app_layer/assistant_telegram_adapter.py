from telegram_app_layer.telegram_call_compat import (
    call_with_legacy_arity,
)


class AssistantTelegramAdapter:

    FRESHNESS_STATUS_LABELS = {
        "FRESH": "свежие",
        "STALE": "устарели",
        "UNKNOWN": "свежесть неизвестна",
    }

    FRESHNESS_EVIDENCE_LABELS = {
        "SOURCE_PROVEN": "поле timestamp источника присутствует",
        "OBSERVED_ONLY": "есть только время наблюдения",
        "NO_EVIDENCE": "временных доказательств нет",
    }

    FRESHNESS_SOURCE_TIMESTAMP_LABELS = {
        "VERIFIED": "timestamp источника проверен",
        "UNVERIFIED": "timestamp источника требует проверки",
        "ABSENT": "timestamp источника отсутствует",
    }

    FRESHNESS_COMPONENT_LABELS = {
        "sales": "Продажи",
        "stock": "Остатки",
        "unit_economics": "Юнит-экономика",
    }

    FRESHNESS_REFRESH_ACTION_LABELS = {
        "SOURCE_TIMESTAMP_REQUIRED": (
            "нужен достоверный timestamp источника"
        ),
        "VERIFY_SOURCE_TIMESTAMP": (
            "проверить timestamp источника"
        ),
        "REFRESH_SOURCE_DATA": (
            "обновить данные из источника"
        ),
    }

    FRESHNESS_REASON_LABELS = {
        "DECISION_SNAPSHOT_STALE": "снимок решения устарел",
        "DECISION_SNAPSHOT_TIMESTAMP_UNKNOWN": (
            "время снимка решения неизвестно"
        ),
        "DECISION_SNAPSHOT_TIMESTAMP_IN_FUTURE": (
            "время снимка решения находится в будущем"
        ),
        "SALES_DATA_STALE": "данные продаж устарели",
        "SALES_TIMESTAMP_UNKNOWN": "время данных продаж неизвестно",
        "SALES_TIMESTAMP_IN_FUTURE": (
            "время данных продаж находится в будущем"
        ),
        "STOCK_DATA_STALE": "данные остатков устарели",
        "STOCK_TIMESTAMP_UNKNOWN": "время данных остатков неизвестно",
        "STOCK_TIMESTAMP_IN_FUTURE": (
            "время данных остатков находится в будущем"
        ),
        "UNIT_ECONOMICS_DATA_STALE": "данные юнит-экономики устарели",
        "UNIT_ECONOMICS_TIMESTAMP_UNKNOWN": (
            "время данных юнит-экономики неизвестно"
        ),
        "UNIT_ECONOMICS_TIMESTAMP_IN_FUTURE": (
            "время данных юнит-экономики находится в будущем"
        ),
    }

    def __init__(
        self,
        assistant,
        keyboard_service,
        button_handler,
        user_profile_service=None,
        memory_command_service=None
    ):

        self.assistant = (
            assistant
        )

        self.keyboard_service = (
            keyboard_service
        )

        self.button_handler = (
            button_handler
        )

        self.user_profile_service = (
            user_profile_service
        )

        self.memory_command_service = (
            memory_command_service
        )

    def get_start_response(
        self,
        user_id=None
    ):

        profile_failure = (
            self._admit_user_profile(
                user_id
            )
        )

        if profile_failure:

            result = dict(
                profile_failure
            )

            result.setdefault(
                "text",
                "Профиль пользователя недоступен"
            )

            return result

        return {
            "error": False,

            "text":
                "Привет! Я AI Assistant. Выберите действие:",

            "keyboard":
                self.keyboard_service
                .build_main_keyboard()
        }

    def handle_text(
        self,
        text,
        user_id=None
    ):

        profile_failure = (
            self._admit_user_profile(
                user_id
            )
        )

        if profile_failure:

            return profile_failure

        if (
            self.memory_command_service
        ):

            try:

                memory_result = (
                    self.memory_command_service
                    .handle(
                        user_id,
                        text
                    )
                )

            except Exception:

                return {
                    "error": True,
                    "message":
                        "TELEGRAM_MEMORY_COMMAND_FAILED"
                }

            if (
                not isinstance(
                    memory_result,
                    dict
                )
                or type(
                    memory_result.get(
                        "error"
                    )
                )
                is not bool
                or type(
                    memory_result.get(
                        "handled"
                    )
                )
                is not bool
            ):

                return {
                    "error": True,
                    "message":
                        "INVALID_TELEGRAM_MEMORY_COMMAND_RESULT"
                }

            if memory_result.get(
                "handled"
            ) is True:

                if memory_result.get(
                    "error"
                ) is True:

                    return dict(
                        memory_result
                    )

                return {
                    "error": False,
                    "message":
                        "Запомнил 👍"
                }

        return (
            self.assistant
            .ask(
                text,
                user_id
            )
        )

    def handle_button(
        self,
        callback,
        user_id=None
    ):

        profile_failure = (
            self._admit_user_profile(
                user_id
            )
        )

        if profile_failure:

            return profile_failure

        result = call_with_legacy_arity(
            self.button_handler
            .handle,
            (
                callback,
                user_id,
            ),
            (
                callback,
            ),
        )

        return self._with_task_draft_freshness(
            callback,
            result,
        )

    def _admit_user_profile(
        self,
        user_id
    ):

        if (
            not self.user_profile_service
            or user_id is None
        ):

            return None

        try:

            result = (
                self.user_profile_service
                .create_user(
                    user_id
                )
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "TELEGRAM_USER_PROFILE_CREATE_FAILED"
            }

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return {
                "error": True,
                "message":
                    "INVALID_TELEGRAM_USER_PROFILE_RESULT"
            }

        if result.get(
            "error"
        ) is True:

            return dict(
                result
            )

        if not isinstance(
            result.get(
                "user"
            ),
            dict
        ):

            return {
                "error": True,
                "message":
                    "INVALID_TELEGRAM_USER_PROFILE_RESULT"
            }

        return None


    def _with_task_draft_freshness(self, callback, result):
        if not isinstance(result, dict):
            return result
        if callback == "product_action_task_drafts":
            return self._with_freshness_summary(result)
        if str(callback).startswith("product_task_draft:view:"):
            return self._with_freshness_detail(result)
        return result

    def _with_freshness_summary(self, result):
        summary = result.get("readiness_summary") or {}
        counts = summary.get("freshness_counts") or {}
        if not counts:
            return result

        lines = [
            "",
            "Свежесть данных:",
            "Свежие: " + str(counts.get("FRESH", 0)),
            "Устарели: " + str(counts.get("STALE", 0)),
            "Неизвестно: " + str(counts.get("UNKNOWN", 0)),
        ]

        coverage = summary.get("freshness_coverage_counts") or {}
        if coverage:
            lines.extend([
                "",
                "Доказательства свежести:",
                "Поле timestamp источника есть: "
                + str(coverage.get("SOURCE_PROVEN", 0)),
                "Только наблюдение: "
                + str(coverage.get("OBSERVED_ONLY", 0)),
                "Нет временных доказательств: "
                + str(coverage.get("NO_EVIDENCE", 0)),
            ])

        source_timestamp_counts = summary.get(
            "freshness_source_timestamp_counts"
        ) or {}
        if source_timestamp_counts:
            lines.extend([
                "",
                "Проверка timestamp источника:",
                "Проверен: "
                + str(source_timestamp_counts.get("VERIFIED", 0)),
                "Требует проверки: "
                + str(source_timestamp_counts.get("UNVERIFIED", 0)),
                "Отсутствует: "
                + str(source_timestamp_counts.get("ABSENT", 0)),
            ])

        refresh_counts = summary.get("freshness_refresh_counts") or {}
        if refresh_counts:
            lines.extend([
                "",
                "Что требуется:",
                "Нужен timestamp источника: "
                + str(refresh_counts.get("SOURCE_TIMESTAMP_REQUIRED", 0)),
                "Проверить timestamp: "
                + str(refresh_counts.get("VERIFY_SOURCE_TIMESTAMP", 0)),
                "Обновить источник: "
                + str(refresh_counts.get("REFRESH_SOURCE_DATA", 0)),
            ])

        return self._append_message(result, lines)

    def _with_freshness_detail(self, result):
        readiness = result.get("readiness") or {}
        freshness = readiness.get("freshness") or {}
        status = freshness.get("status")
        if not status:
            return result

        snapshot = freshness.get("decision_snapshot") or {}
        age = self._format_freshness_age(snapshot.get("age_seconds"))
        lines = [
            "",
            "Свежесть данных:",
            self.FRESHNESS_STATUS_LABELS.get(status, str(status)),
            "Возраст снимка решения: " + age,
        ]

        coverage = readiness.get("freshness_coverage") or {}
        components = coverage.get("components") or {}
        if components:
            lines.extend(["", "Доказательства по компонентам:"])
            for component_name, component in components.items():
                evidence_state = component.get("evidence_state")
                component_label = self.FRESHNESS_COMPONENT_LABELS.get(
                    component_name,
                    str(component_name),
                )
                evidence_label = self.FRESHNESS_EVIDENCE_LABELS.get(
                    evidence_state,
                    str(evidence_state),
                )
                source_timestamp_state = component.get(
                    "source_timestamp_state"
                )
                if evidence_state == "SOURCE_PROVEN":
                    evidence_label = (
                        self.FRESHNESS_SOURCE_TIMESTAMP_LABELS.get(
                            source_timestamp_state,
                            evidence_label,
                        )
                    )
                lines.append(
                    "• " + component_label + ": " + evidence_label
                )

        guidance = readiness.get("freshness_refresh_guidance") or {}
        targets = guidance.get("targets") or []
        if targets:
            lines.extend(["", "Что требуется:"])
            for target in targets:
                component_name = target.get("component")
                action = target.get("action")
                component_label = self.FRESHNESS_COMPONENT_LABELS.get(
                    component_name,
                    str(component_name),
                )
                action_label = self.FRESHNESS_REFRESH_ACTION_LABELS.get(
                    action,
                    str(action),
                )
                lines.append(
                    "• " + component_label + ": " + action_label
                )

        reasons = freshness.get("reasons") or []
        if reasons:
            lines.append("Причины:")
            lines.extend(
                "• " + self.FRESHNESS_REASON_LABELS.get(reason, str(reason))
                for reason in reasons
            )

        return self._append_message(result, lines)

    def _append_message(self, result, lines):
        enriched = dict(result)
        message = str(enriched.get("message") or "")
        addition = "\n".join(lines)
        enriched["message"] = message + addition
        return enriched

    def _format_freshness_age(self, seconds):
        if seconds is None:
            return "неизвестен"
        value = max(0, int(seconds))
        if value < 60:
            return str(value) + " сек."
        if value < 3600:
            return str(value // 60) + " мин."
        hours = value // 3600
        minutes = (value % 3600) // 60
        if minutes:
            return str(hours) + " ч. " + str(minutes) + " мин."
        return str(hours) + " ч."
