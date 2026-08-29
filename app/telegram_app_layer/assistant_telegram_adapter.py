class AssistantTelegramAdapter:

    FRESHNESS_STATUS_LABELS = {
        "FRESH": "свежие",
        "STALE": "устарели",
        "UNKNOWN": "свежесть неизвестна",
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

        if (
            self.user_profile_service
            and user_id is not None
        ):

            self.user_profile_service.create_user(
                user_id
            )

        return {
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

        if (
            self.user_profile_service
            and user_id is not None
        ):

            self.user_profile_service.create_user(
                user_id
            )

        if (
            self.memory_command_service
        ):

            memory_result = (
                self.memory_command_service
                .handle(
                    user_id,
                    text
                )
            )

            if not memory_result["error"]:

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

        if (
            self.user_profile_service
            and user_id is not None
        ):

            self.user_profile_service.create_user(
                user_id
            )

        try:
            result = (
                self.button_handler
                .handle(
                    callback,
                    user_id
                )
            )
        except TypeError:
            result = (
                self.button_handler
                .handle(
                    callback
                )
            )

        return self._with_task_draft_freshness(
            callback,
            result,
        )

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
