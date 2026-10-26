from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import threading
from uuid import uuid4

from services.period_profit_external_expense_evidence_service import (
    PeriodProfitExternalExpenseEvidenceService,
)
from services.tenant_context import get_current_tenant_user_id


class TelegramExternalExpenseRuntimeService:
    """Explicitly confirmed Telegram flow for tenant-local external expenses."""

    MAX_VISIBLE_EXPENSES = 10
    MAX_DRAFTS = 500
    MAX_CATEGORY_LENGTH = 80
    MAX_DESCRIPTION_LENGTH = 240

    def __init__(
        self,
        repository,
        keyboard_service,
        evidence_service=None,
        today_provider=None,
    ):
        self.repository = repository
        self.keyboard_service = keyboard_service
        self.evidence_service = (
            evidence_service
            or PeriodProfitExternalExpenseEvidenceService(repository)
        )
        self.today_provider = today_provider or date.today
        self._lock = threading.RLock()
        self._sessions = {}
        self._drafts = OrderedDict()

    def open_menu(self, user_id=None):
        key = self._key(user_id)
        if key is None:
            return self._unavailable()
        with self._lock:
            self._invalidate_other_scopes(key)
            self._cancel_active_draft(key)
            self._sessions[key] = {
                "stage": None,
                "period": None,
                "view_id": None,
                "draft_id": None,
            }
        return self._result(
            "За какой период показать внешние расходы?",
            keyboard=self.keyboard_service.build_external_expenses_period_keyboard(),
            status="TELEGRAM_EXTERNAL_EXPENSE_PERIOD_MENU",
        )

    def open_period(
        self, date_from, date_to, user_id=None, return_callback=None
    ):
        """Open an exact period from a scoped report and retain a safe return action."""
        key = self._key(user_id)
        start = self._parse_date(date_from)
        end = self._parse_date(date_to)
        callback = str(return_callback or "").strip()
        if (
            key is None
            or start is None
            or end is None
            or start > end
            or (
                callback
                and not re.fullmatch(
                    r"period_profit_report:[0-9a-f]{12}", callback
                )
            )
        ):
            return self._stale()
        with self._lock:
            self._invalidate_other_scopes(key)
            self._cancel_active_draft(key)
            self._sessions[key] = {
                "stage": None,
                "period": (start, end),
                "view_id": None,
                "draft_id": None,
                "return_callback": callback or None,
            }
        return self._show_period(key, (start, end))

    def handle_text(self, text, user_id=None):
        key = self._key(user_id)
        if key is None:
            return None
        with self._lock:
            self._invalidate_other_scopes(key)
            session = self._sessions.get(key)
            stage = session.get("stage") if session else None
            draft_id = session.get("draft_id") if session else None
            draft = self._drafts.get((key, draft_id)) if draft_id else None

        if stage is None:
            return None
        value = str(text or "").strip()
        if value.lower() in {"отмена", "cancel", "/cancel"}:
            return self._cancel_draft(key, draft_id)

        if stage == "period":
            period = self._parse_period(value)
            if period is None:
                return self._result(
                    "Не распознал период. Введите две даты, например 01.08.2026 — 31.08.2026.",
                    keyboard=self.keyboard_service.build_external_expenses_period_input_keyboard(),
                    status="TELEGRAM_EXTERNAL_EXPENSE_PERIOD_INVALID",
                )
            return self._show_period(key, period)

        draft_status = draft.get("status") if isinstance(draft, dict) else None
        description_input_allowed = (
            stage == "description"
            and draft_status == "AWAITING_DESCRIPTION"
        )
        if (
            not isinstance(draft, dict)
            or (draft_status != "READY" and not description_input_allowed)
        ):
            self.clear_pending(user_id)
            return self._result(
                "Черновик устарел. Откройте раздел «Внешние расходы» и начните заново.",
                status="TELEGRAM_EXTERNAL_EXPENSE_DRAFT_STALE",
            )

        if stage == "expense_date":
            expense_date = self._parse_date(value)
            if expense_date is None:
                return self._expense_prompt(
                    draft,
                    "Введите дату как ДД.ММ.ГГГГ, например 15.08.2026.",
                    "expense_date",
                )
            if not draft["date_from"] <= expense_date <= draft["date_to"]:
                return self._expense_prompt(
                    draft,
                    "Дата расхода должна входить в выбранный период "
                    + self._period_label(draft["date_from"], draft["date_to"])
                    + ". Введите дату ещё раз.",
                    "expense_date",
                )
            self._update_draft(key, draft_id, expense_date=expense_date)
            self._set_stage(key, "category", draft_id)
            return self._expense_prompt(
                draft,
                "Укажите категорию внешнего расхода. Не вносите сюда удержания, уже учтённые Ozon.",
                "category",
            )

        if stage == "category":
            if not value or len(value) > self.MAX_CATEGORY_LENGTH:
                return self._expense_prompt(
                    draft,
                    "Категория обязательна и должна быть не длиннее 80 символов. Введите её ещё раз.",
                    "category",
                )
            self._update_draft(key, draft_id, category=value)
            self._set_stage(key, "amount", draft_id)
            return self._expense_prompt(
                draft,
                "Введите сумму в рублях, например 1250,50. Отрицательные суммы не принимаются.",
                "amount",
            )

        if stage == "amount":
            amount = self._parse_amount(value)
            if amount is None:
                return self._expense_prompt(
                    draft,
                    "Не получилось прочитать сумму. Введите конечное неотрицательное число, например 1250,50.",
                    "amount",
                )
            self._update_draft(key, draft_id, amount=amount)
            with self._lock:
                current = self._drafts.get((key, draft_id))
                if current is not None:
                    current["status"] = "AWAITING_DESCRIPTION"
                    self._sessions[key]["stage"] = "description"
            return self._expense_prompt(
                self._drafts.get((key, draft_id), draft),
                "Добавьте описание или пропустите этот шаг.",
                "description",
            )

        if stage == "description":
            if len(value) > self.MAX_DESCRIPTION_LENGTH:
                return self._expense_prompt(
                    draft,
                    "Описание должно быть не длиннее 240 символов. Сократите его или пропустите.",
                    "description",
                )
            self._update_draft(key, draft_id, description=value)
            return self._expense_preview(key, draft_id)

        return None

    def handle_callback(self, callback, user_id=None):
        key = self._key(user_id)
        if key is None:
            return self._unavailable()
        value = str(callback or "").strip()
        with self._lock:
            self._invalidate_other_scopes(key)

        if value == "external_expenses":
            return self.open_menu(user_id)

        if value.startswith("external_expenses:period:"):
            period_code = value.split(":", 2)[2]
            if period_code.lower() == "custom":
                with self._lock:
                    self._cancel_active_draft(key)
                    self._sessions[key] = {
                        "stage": "period",
                        "period": None,
                        "view_id": None,
                        "draft_id": None,
                    }
                return self._result(
                    "Введите период в формате ДД.ММ.ГГГГ — ДД.ММ.ГГГГ.",
                    keyboard=self.keyboard_service.build_external_expenses_period_input_keyboard(),
                    status="TELEGRAM_EXTERNAL_EXPENSE_CUSTOM_PERIOD_INPUT",
                )
            period = self._quick_period(period_code)
            if period is None:
                return self._stale()
            return self._show_period(key, period)

        if value.startswith("external_expenses:add:"):
            view_id = value.split(":", 2)[2]
            session = self._current_view(key, view_id)
            if session is None:
                return self._stale()
            draft_id = self._new_draft(
                key,
                {
                    "kind": "EXPENSE",
                    "status": "READY",
                    "date_from": session["period"][0],
                    "date_to": session["period"][1],
                    "expense_date": None,
                    "category": None,
                    "amount": None,
                    "description": "",
                },
            )
            self._set_stage(key, "expense_date", draft_id)
            return self._expense_prompt(
                self._drafts[(key, draft_id)],
                "Введите дату расхода как ДД.ММ.ГГГГ.",
                "expense_date",
            )

        if value.startswith("external_expenses:coverage:"):
            view_id = value.split(":", 2)[2]
            session = self._current_view(key, view_id)
            if session is None:
                return self._stale()
            draft_id = self._new_draft(
                key,
                {
                    "kind": "COVERAGE",
                    "status": "READY",
                    "date_from": session["period"][0],
                    "date_to": session["period"][1],
                    "note": "Подтверждено через Telegram",
                },
            )
            self._set_stage(key, "coverage_confirm", draft_id)
            return self._coverage_preview(key, draft_id)

        if value.startswith("external_expenses:skip-description:"):
            draft_id = value.split(":", 2)[2]
            draft = self._get_ready_draft(key, draft_id, "EXPENSE")
            if draft is None or not self._session_has_draft(key, draft_id, "description"):
                return self._stale()
            self._update_draft(key, draft_id, description="")
            return self._expense_preview(key, draft_id)

        if value.startswith("external_expenses:expense-confirm:"):
            draft_id = value.split(":", 2)[2]
            return self._confirm_expense(key, draft_id)

        if value.startswith("external_expenses:coverage-confirm:"):
            draft_id = value.split(":", 2)[2]
            return self._confirm_coverage(key, draft_id)

        if value.startswith("external_expenses:cancel:"):
            draft_id = value.split(":", 2)[2]
            return self._cancel_draft(key, draft_id)

        return self._stale()

    def clear_pending(self, user_id=None):
        if user_id is None:
            return
        user = str(user_id)
        with self._lock:
            keys = [
                key for key in self._sessions
                if key[0] == user
            ]
            for key in keys:
                self._cancel_active_draft(key)
                self._sessions.pop(key, None)

    def _show_period(self, key, period):
        date_from, date_to = period
        evidence = self.evidence_service.load(date_from, date_to)
        if not isinstance(evidence, dict) or evidence.get("error") is True:
            return self._result(
                "Не удалось прочитать внешние расходы. Попробуйте открыть период ещё раз.",
                keyboard=self.keyboard_service.build_external_expenses_period_keyboard(),
                status="TELEGRAM_EXTERNAL_EXPENSE_LIST_UNAVAILABLE",
            )

        view_id = uuid4().hex[:10]
        with self._lock:
            previous_session = self._sessions.get(key) or {}
            return_callback = previous_session.get("return_callback")
            self._cancel_active_draft(key)
            self._sessions[key] = {
                "stage": None,
                "period": period,
                "view_id": view_id,
                "draft_id": None,
                "return_callback": return_callback,
            }

        lines = [
            "💸 Внешние расходы за период "
            + self._period_label(date_from, date_to),
            "Записей: " + str(evidence.get("expense_count", 0)),
        ]
        expenses = evidence.get("expenses") or []
        for expense in expenses[: self.MAX_VISIBLE_EXPENSES]:
            line = (
                "• "
                + self._display_date(expense.get("expense_date"))
                + " · "
                + str(expense.get("category") or "Расход")
                + " · "
                + self._money(expense.get("amount"))
            )
            description = str(expense.get("description") or "").strip()
            if description:
                line += " — " + description[:100]
            lines.append(line)
        hidden_count = max(0, len(expenses) - self.MAX_VISIBLE_EXPENSES)
        if hidden_count:
            lines.append("… ещё записей: " + str(hidden_count))
        lines.append(
            "Всего внесено: "
            + self._money(evidence.get("observed_expense_total"))
        )

        if evidence.get("coverage_complete") is True:
            lines.append("Полнота расходов: подтверждена за весь период.")
            if not expenses:
                lines.append("Подтверждённый ноль: расходов за период не внесено.")
        elif evidence.get("coverage_configured") is True:
            lines.append("Полнота расходов: подтверждена частично.")
        else:
            lines.append("Полнота расходов: не подтверждена; пустой список не означает ноль.")

        gaps = evidence.get("coverage_gaps") or []
        if gaps:
            lines.append("Не подтверждены даты:")
            for gap in gaps[:5]:
                lines.append(
                    "• "
                    + self._display_date(gap.get("date_from"))
                    + " — "
                    + self._display_date(gap.get("date_to"))
                )
            if len(gaps) > 5:
                lines.append("… ещё интервалов: " + str(len(gaps) - 5))

        lines.append(
            "Сюда вносятся только расходы вне начислений Ozon. "
            "Реклама, логистика, комиссия и хранение из отчётов Ozon повторно не добавляйте."
        )
        return self._result(
            "\n".join(lines),
            keyboard=self.keyboard_service.build_external_expenses_period_view_keyboard(
                view_id,
                return_callback=return_callback,
            ),
            status="TELEGRAM_EXTERNAL_EXPENSE_PERIOD_READY",
            period=[date_from, date_to],
            coverage_complete=evidence.get("coverage_complete") is True,
            observed_expense_total=evidence.get("observed_expense_total"),
            read_only=True,
            executed=False,
        )

    def _expense_prompt(self, draft, message, stage):
        draft_id = draft.get("draft_id")
        return self._result(
            message,
            keyboard=self.keyboard_service.build_external_expense_input_keyboard(
                draft_id,
                skip_description=(stage == "description"),
            ),
            status="TELEGRAM_EXTERNAL_EXPENSE_INPUT_" + stage.upper(),
        )

    def _expense_preview(self, key, draft_id):
        draft = self._get_ready_draft(key, draft_id, "EXPENSE")
        if draft is None:
            return self._stale()
        with self._lock:
            draft["status"] = "READY_TO_CONFIRM"
            session = self._sessions.get(key)
            if session:
                session["stage"] = "preview"
        description = str(draft.get("description") or "").strip()
        text = (
            "Проверьте внешний расход перед сохранением:\n"
            + "Дата: " + self._display_date(draft.get("expense_date")) + "\n"
            + "Категория: " + str(draft.get("category") or "") + "\n"
            + "Сумма: " + self._money(draft.get("amount"))
        )
        if description:
            text += "\nОписание: " + description
        text += (
            "\n\nПосле подтверждения расход попадёт в расчёт прибыли один раз. "
            "Убедитесь, что он не включён в начисления Ozon."
        )
        return self._result(
            text,
            keyboard=self.keyboard_service.build_external_expense_preview_keyboard(
                draft_id
            ),
            status="TELEGRAM_EXTERNAL_EXPENSE_PREVIEW",
        )

    def _coverage_preview(self, key, draft_id, message_prefix=""):
        draft = self._get_ready_draft(key, draft_id, "COVERAGE")
        if draft is None:
            return self._stale()
        with self._lock:
            draft["status"] = "READY"
            session = self._sessions.get(key)
            if session:
                session["stage"] = "coverage_confirm"
        message = (
            "Подтвердить, что все внешние расходы за период "
            + self._period_label(draft["date_from"], draft["date_to"])
            + " внесены? Пустой подтверждённый период будет считаться нулём."
        )
        if message_prefix:
            message = str(message_prefix) + "\n\n" + message
        return self._result(
            message,
            keyboard=self.keyboard_service.build_external_expense_preview_keyboard(
                draft_id,
                coverage=True,
            ),
            status="TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_PREVIEW",
        )

    def _confirm_expense(self, key, draft_id):
        draft_key = (key, draft_id)
        with self._lock:
            draft = self._drafts.get(draft_key)
            if not isinstance(draft, dict) or draft.get("kind") != "EXPENSE":
                return self._stale()
            if draft.get("status") == "CONFIRMED":
                return self._result(
                    "Этот расход уже сохранён. Повторное нажатие не добавило вторую запись.",
                    status="TELEGRAM_EXTERNAL_EXPENSE_ALREADY_SAVED",
                    read_only=True,
                    executed=False,
                )
            if draft.get("status") == "SAVING":
                return self._result(
                    "Сохранение уже выполняется. Дождитесь ответа.",
                    status="TELEGRAM_EXTERNAL_EXPENSE_SAVE_IN_PROGRESS",
                )
            if draft.get("status") != "READY_TO_CONFIRM" or not self._session_has_draft(
                key, draft_id, "preview"
            ):
                return self._stale()
            values = dict(draft)
            draft["status"] = "SAVING"

        try:
            result = self.repository.add_expense(
                values["expense_date"],
                values["category"],
                values["amount"],
                values.get("description", ""),
            )
        except Exception:
            with self._lock:
                self._drafts[draft_key]["status"] = "UNCERTAIN"
            return self._result(
                "Не удалось подтвердить результат записи. Обновите список расходов перед повторным вводом, чтобы избежать дубля.",
                status="TELEGRAM_EXTERNAL_EXPENSE_SAVE_UNCERTAIN",
                error=True,
                read_only=False,
                executed=False,
            )

        if not isinstance(result, dict) or result.get("error") is not False:
            with self._lock:
                self._drafts[draft_key]["status"] = "READY_TO_CONFIRM"
            return self._expense_preview(key, draft_id)

        with self._lock:
            self._drafts[draft_key]["status"] = "CONFIRMED"
            self._drafts[draft_key]["saved_expense_id"] = result.get("id")
            session = self._sessions.get(key)
            period = (values["date_from"], values["date_to"])
            if session and session.get("draft_id") == draft_id:
                session["draft_id"] = None
                session["stage"] = None
        rendered = self._show_period(key, period)
        rendered["message"] = "Расход сохранён.\n\n" + rendered.get("message", "")
        rendered["status"] = "TELEGRAM_EXTERNAL_EXPENSE_SAVED"
        rendered["read_only"] = False
        rendered["executed"] = True
        return rendered

    def _confirm_coverage(self, key, draft_id):
        draft_key = (key, draft_id)
        with self._lock:
            draft = self._drafts.get(draft_key)
            if not isinstance(draft, dict) or draft.get("kind") != "COVERAGE":
                return self._stale()
            if draft.get("status") == "CONFIRMED":
                return self._result(
                    "Полнота этого периода уже подтверждена.",
                    status="TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_ALREADY_CONFIRMED",
                    read_only=True,
                    executed=False,
                )
            if draft.get("status") == "SAVING":
                return self._result(
                    "Подтверждение уже выполняется. Дождитесь ответа.",
                    status="TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_IN_PROGRESS",
                )
            if draft.get("status") != "READY" or not self._session_has_draft(
                key, draft_id, "coverage_confirm"
            ):
                return self._stale()
            values = dict(draft)
            draft["status"] = "SAVING"

        try:
            result = self.repository.confirm_coverage(
                values["date_from"],
                values["date_to"],
                note=values.get("note", ""),
            )
        except Exception:
            with self._lock:
                self._drafts[draft_key]["status"] = "UNCERTAIN"
            return self._result(
                "Не удалось подтвердить результат записи. Обновите список периода перед повторным действием.",
                status="TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_UNCERTAIN",
                error=True,
                read_only=False,
                executed=False,
            )

        if not isinstance(result, dict) or result.get("error") is not False:
            with self._lock:
                self._drafts[draft_key]["status"] = "READY"
            return self._coverage_preview(
                key,
                draft_id,
                "Не удалось записать подтверждение полноты. Проверьте соединение и повторите действие.",
            )

        period = (values["date_from"], values["date_to"])
        with self._lock:
            self._drafts[draft_key]["status"] = "CONFIRMED"
            session = self._sessions.get(key)
            if session and session.get("draft_id") == draft_id:
                session["draft_id"] = None
                session["stage"] = None
        rendered = self._show_period(key, period)
        rendered["message"] = "Полнота расходов за период подтверждена.\n\n" + rendered.get("message", "")
        rendered["status"] = "TELEGRAM_EXTERNAL_EXPENSE_COVERAGE_CONFIRMED"
        rendered["read_only"] = False
        rendered["executed"] = True
        return rendered

    def _cancel_draft(self, key, draft_id):
        with self._lock:
            draft = self._drafts.get((key, draft_id))
            if isinstance(draft, dict) and draft.get("status") not in {
                "CONFIRMED",
                "SAVING",
                "UNCERTAIN",
            }:
                draft["status"] = "CANCELLED"
            session = self._sessions.get(key)
            period = session.get("period") if session else None
            if session and session.get("draft_id") == draft_id:
                session["draft_id"] = None
                session["stage"] = None
        if period:
            return self._show_period(key, period)
        return self.open_menu(key[0])

    def _current_view(self, key, view_id):
        with self._lock:
            session = self._sessions.get(key)
            if (
                not isinstance(session, dict)
                or session.get("view_id") != view_id
                or not session.get("period")
            ):
                return None
            return dict(session)

    def _new_draft(self, key, values):
        draft_id = uuid4().hex[:10]
        draft = dict(values)
        draft["draft_id"] = draft_id
        with self._lock:
            self._drafts[(key, draft_id)] = draft
            self._drafts.move_to_end((key, draft_id))
            while len(self._drafts) > self.MAX_DRAFTS:
                self._drafts.popitem(last=False)
        return draft_id

    def _get_ready_draft(self, key, draft_id, kind):
        with self._lock:
            draft = self._drafts.get((key, draft_id))
            if (
                isinstance(draft, dict)
                and draft.get("kind") == kind
                and draft.get("status") in {
                    "READY",
                    "AWAITING_DESCRIPTION",
                    "READY_TO_CONFIRM",
                }
            ):
                return draft
        return None

    def _update_draft(self, key, draft_id, **changes):
        with self._lock:
            draft = self._drafts.get((key, draft_id))
            if isinstance(draft, dict):
                draft.update(changes)
                if draft.get("kind") == "EXPENSE":
                    draft["status"] = "READY"

    def _set_stage(self, key, stage, draft_id):
        with self._lock:
            session = self._sessions.get(key) or {}
            session["stage"] = stage
            session["draft_id"] = draft_id
            self._sessions[key] = session

    def _session_has_draft(self, key, draft_id, stage):
        with self._lock:
            session = self._sessions.get(key)
            return bool(
                isinstance(session, dict)
                and session.get("draft_id") == draft_id
                and session.get("stage") == stage
            )

    def _cancel_active_draft(self, key):
        session = self._sessions.get(key)
        if not isinstance(session, dict):
            return
        draft_id = session.get("draft_id")
        draft = self._drafts.get((key, draft_id)) if draft_id else None
        if isinstance(draft, dict) and draft.get("status") in {
            "READY",
            "AWAITING_DESCRIPTION",
            "READY_TO_CONFIRM",
        }:
            draft["status"] = "CANCELLED"

    def _invalidate_other_scopes(self, current_key):
        for key in list(self._sessions):
            if key[0] == current_key[0] and key != current_key:
                self._cancel_active_draft(key)
                self._sessions.pop(key, None)

    def _quick_period(self, period_code):
        today = self.today_provider()
        if isinstance(today, datetime):
            today = today.date()
        if not isinstance(today, date):
            today = date.today()
        code = str(period_code or "").strip().upper()
        if code == "TODAY":
            days = 1
        elif code.endswith("D") and code[:-1].isdigit():
            days = int(code[:-1])
            if days not in {7, 28, 56, 90}:
                return None
        else:
            return None
        return ((today - timedelta(days=days - 1)).isoformat(), today.isoformat())

    @classmethod
    def _parse_period(cls, value):
        date_pattern = r"(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})"
        match = re.fullmatch(
            r"\s*(" + date_pattern + r")\s*(?:—|–|-)\s*(" + date_pattern + r")\s*",
            str(value or ""),
        )
        if not match:
            return None
        start = cls._parse_date(match.group(1))
        end = cls._parse_date(match.group(2))
        if start is None or end is None or start > end:
            return None
        return (start, end)

    @staticmethod
    def _parse_date(value):
        text = str(value or "").strip()
        for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date().isoformat()
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_amount(value):
        text = str(value or "").strip()
        text = text.replace("₽", "").replace("руб.", "").replace("руб", "")
        text = re.sub(r"[\s\u00a0\u202f]", "", text)
        if not text:
            return None
        if "," in text:
            if "." in text and text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            elif "." not in text:
                if text.count(",") != 1:
                    return None
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        elif text.count(".") > 1:
            chunks = text.split(".")
            if any(len(chunk) != 3 for chunk in chunks[1:]):
                return None
            text = "".join(chunks)
        try:
            amount = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
        if not amount.is_finite() or amount < 0:
            return None
        try:
            rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None
        return float(rounded)

    @staticmethod
    def _key(user_id):
        if user_id is None:
            return None
        scope = get_current_tenant_user_id()
        return (str(user_id), str(scope or user_id))

    @staticmethod
    def _period_label(date_from, date_to):
        return date_from + " — " + date_to

    @classmethod
    def _display_date(cls, value):
        parsed = cls._parse_date(value)
        if parsed is None:
            return str(value or "—")
        return datetime.strptime(parsed, "%Y-%m-%d").strftime("%d.%m.%Y")

    @staticmethod
    def _money(value):
        try:
            amount = Decimal(str(value))
            if not amount.is_finite():
                raise InvalidOperation
            rendered = f"{abs(amount):,.2f}".replace(",", " ")
            sign = "−" if amount < 0 else ""
            return sign + rendered + " ₽"
        except (InvalidOperation, TypeError, ValueError):
            return "—"

    @staticmethod
    def _result(message, keyboard=None, status=None, **values):
        result = {
            "error": values.pop("error", False),
            "message": str(message),
            "status": status,
            "read_only": values.pop("read_only", True),
            "executed": values.pop("executed", False),
        }
        if keyboard is not None:
            result["keyboard"] = keyboard
        result.update(values)
        return result

    @staticmethod
    def _stale():
        return {
            "error": False,
            "status": "TELEGRAM_EXTERNAL_EXPENSE_CALLBACK_STALE",
            "message": "Эта кнопка устарела. Откройте «Внешние расходы» и повторите действие.",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _unavailable():
        return {
            "error": True,
            "status": "TELEGRAM_EXTERNAL_EXPENSE_USER_UNAVAILABLE",
            "message": "Не удалось определить пользователя и активный магазин.",
            "read_only": True,
            "executed": False,
        }
