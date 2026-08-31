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

        try:

            keyboard = (
                self.keyboard_service
                .build_main_keyboard()
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "TELEGRAM_KEYBOARD_BUILD_FAILED"
            }

        return {
            "error": False,

            "text":
                "Привет! Я AI Assistant. Выберите действие:",

            "keyboard": keyboard
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

        try:

            result = (
                self.assistant
                .ask(
                    text,
                    user_id
                )
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "TELEGRAM_ASSISTANT_DISPATCH_FAILED"
            }

        return self._validated_runtime_result(
            result,
            "INVALID_TELEGRAM_ASSISTANT_RESULT",
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

        try:

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

        except Exception:

            return {
                "error": True,
                "message":
                    "TELEGRAM_BUTTON_DISPATCH_FAILED"
            }

        validated = (
            self._validated_runtime_result(
                result,
                "INVALID_TELEGRAM_BUTTON_RESULT",
            )
        )

        if validated.get(
            "error"
        ) is True:

            return validated

        return self._with_task_draft_freshness(
            callback,
            validated,
        )

    @staticmethod
    def _validated_runtime_result(
        result,
        invalid_code
    ):

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
                "message": invalid_code
            }

        return result


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
        if callback == "product_action_task_drafts":
            return self._with_freshness_summary(result)
        if str(callback).startswith("product_task_draft:view:"):
            return self._with_freshness_detail(result)
        return result

    def _with_freshness_summary(self, result):
        summary = result.get("readiness_summary")
        if summary is None:
            return result
        if not isinstance(summary, dict):
            return self._freshness_presentation_failure()

        counts = summary.get("freshness_counts")
        if counts is None:
            return result
        if not self._valid_count_map(
            counts,
            {"FRESH", "STALE", "UNKNOWN"},
        ):
            return self._freshness_presentation_failure()

        lines = [
            "",
            "Свежесть данных:",
            "Свежие: " + str(counts["FRESH"]),
            "Устарели: " + str(counts["STALE"]),
            "Неизвестно: " + str(counts["UNKNOWN"]),
        ]

        coverage = summary.get("freshness_coverage_counts")
        if coverage is not None:
            if not self._valid_count_map(
                coverage,
                {"SOURCE_PROVEN", "OBSERVED_ONLY", "NO_EVIDENCE"},
            ):
                return self._freshness_presentation_failure()
            lines.extend([
                "",
                "Доказательства свежести:",
                "Поле timestamp источника есть: "
                + str(coverage["SOURCE_PROVEN"]),
                "Только наблюдение: "
                + str(coverage["OBSERVED_ONLY"]),
                "Нет временных доказательств: "
                + str(coverage["NO_EVIDENCE"]),
            ])

        source_timestamp_counts = summary.get(
            "freshness_source_timestamp_counts"
        )
        if source_timestamp_counts is not None:
            if not self._valid_count_map(
                source_timestamp_counts,
                {"VERIFIED", "UNVERIFIED", "ABSENT"},
            ):
                return self._freshness_presentation_failure()
            lines.extend([
                "",
                "Проверка timestamp источника:",
                "Проверен: "
                + str(source_timestamp_counts["VERIFIED"]),
                "Требует проверки: "
                + str(source_timestamp_counts["UNVERIFIED"]),
                "Отсутствует: "
                + str(source_timestamp_counts["ABSENT"]),
            ])

        refresh_counts = summary.get("freshness_refresh_counts")
        if refresh_counts is not None:
            if not self._valid_count_map(
                refresh_counts,
                {
                    "SOURCE_TIMESTAMP_REQUIRED",
                    "VERIFY_SOURCE_TIMESTAMP",
                    "REFRESH_SOURCE_DATA",
                },
            ):
                return self._freshness_presentation_failure()
            lines.extend([
                "",
                "Что требуется:",
                "Нужен timestamp источника: "
                + str(refresh_counts["SOURCE_TIMESTAMP_REQUIRED"]),
                "Проверить timestamp: "
                + str(refresh_counts["VERIFY_SOURCE_TIMESTAMP"]),
                "Обновить источник: "
                + str(refresh_counts["REFRESH_SOURCE_DATA"]),
            ])

        return self._append_message(result, lines)

    def _with_freshness_detail(self, result):
        readiness = result.get("readiness")
        if readiness is None:
            return result
        if not isinstance(readiness, dict):
            return self._freshness_presentation_failure()

        freshness = readiness.get("freshness")
        if freshness is None:
            return result
        if not isinstance(freshness, dict):
            return self._freshness_presentation_failure()

        status = freshness.get("status")
        if status not in self.FRESHNESS_STATUS_LABELS:
            return self._freshness_presentation_failure()

        snapshot = freshness.get("decision_snapshot")
        if not isinstance(snapshot, dict):
            return self._freshness_presentation_failure()

        age_seconds = snapshot.get("age_seconds")
        if (
            age_seconds is not None
            and (
                isinstance(age_seconds, bool)
                or not isinstance(age_seconds, (int, float))
                or age_seconds < 0
            )
        ):
            return self._freshness_presentation_failure()

        reasons = freshness.get("reasons")
        if (
            not isinstance(reasons, list)
            or any(
                reason not in self.FRESHNESS_REASON_LABELS
                for reason in reasons
            )
        ):
            return self._freshness_presentation_failure()

        age = self._format_freshness_age(age_seconds)
        lines = [
            "",
            "Свежесть данных:",
            self.FRESHNESS_STATUS_LABELS[status],
            "Возраст снимка решения: " + age,
        ]

        coverage = readiness.get("freshness_coverage")
        if coverage is not None:
            if not isinstance(coverage, dict):
                return self._freshness_presentation_failure()
            components = coverage.get("components")
            if not isinstance(components, dict):
                return self._freshness_presentation_failure()
            if components:
                lines.extend(["", "Доказательства по компонентам:"])
                for component_name, component in components.items():
                    if (
                        component_name not in self.FRESHNESS_COMPONENT_LABELS
                        or not isinstance(component, dict)
                    ):
                        return self._freshness_presentation_failure()
                    evidence_state = component.get("evidence_state")
                    if evidence_state not in self.FRESHNESS_EVIDENCE_LABELS:
                        return self._freshness_presentation_failure()
                    source_timestamp_state = component.get(
                        "source_timestamp_state"
                    )
                    if (
                        source_timestamp_state is not None
                        and source_timestamp_state
                        not in self.FRESHNESS_SOURCE_TIMESTAMP_LABELS
                    ):
                        return self._freshness_presentation_failure()
                    component_label = self.FRESHNESS_COMPONENT_LABELS[
                        component_name
                    ]
                    evidence_label = self.FRESHNESS_EVIDENCE_LABELS[
                        evidence_state
                    ]
                    if evidence_state == "SOURCE_PROVEN":
                        if source_timestamp_state is None:
                            return self._freshness_presentation_failure()
                        evidence_label = (
                            self.FRESHNESS_SOURCE_TIMESTAMP_LABELS[
                                source_timestamp_state
                            ]
                        )
                    lines.append(
                        "• " + component_label + ": " + evidence_label
                    )

        guidance = readiness.get("freshness_refresh_guidance")
        if guidance is not None:
            if not isinstance(guidance, dict):
                return self._freshness_presentation_failure()
            targets = guidance.get("targets")
            if not isinstance(targets, list):
                return self._freshness_presentation_failure()
            if targets:
                lines.extend(["", "Что требуется:"])
                for target in targets:
                    if not isinstance(target, dict):
                        return self._freshness_presentation_failure()
                    component_name = target.get("component")
                    action = target.get("action")
                    if (
                        component_name not in self.FRESHNESS_COMPONENT_LABELS
                        or action not in self.FRESHNESS_REFRESH_ACTION_LABELS
                    ):
                        return self._freshness_presentation_failure()
                    lines.append(
                        "• "
                        + self.FRESHNESS_COMPONENT_LABELS[component_name]
                        + ": "
                        + self.FRESHNESS_REFRESH_ACTION_LABELS[action]
                    )

        if reasons:
            lines.append("Причины:")
            lines.extend(
                "• " + self.FRESHNESS_REASON_LABELS[reason]
                for reason in reasons
            )

        return self._append_message(result, lines)

    @staticmethod
    def _valid_count_map(value, states):
        return (
            isinstance(value, dict)
            and set(value) == states
            and all(
                type(value[state]) is int
                and value[state] >= 0
                for state in states
            )
        )

    @staticmethod
    def _freshness_presentation_failure():
        return {
            "error": True,
            "message":
                "INVALID_TELEGRAM_TASK_DRAFT_FRESHNESS_RESULT",
            "executed": False,
        }


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
