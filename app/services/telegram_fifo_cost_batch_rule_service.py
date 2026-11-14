"""Telegram prompts for automatic FIFO batch rules and dated owner controls.

This adapter owns only transient interaction state. Automatic rules and owner
controls are persisted by their existing domain services and never alter FIFO
layers, allocations, or profit by themselves.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import RLock
from uuid import uuid4

from services.fifo_cost_batch_rule_contracts import (
    BatchRuleInput,
    BatchStartDayPolicy,
    BatchTotalControl,
    BatchTotalControlKind,
    BatchTotalControlStatus,
)
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_transition_contracts import ScopeIdentity
from services.ozon_account_repository import split_store_tenant_scope


class TelegramFifoCostBatchRuleService:
    """Render and confirm the narrowly scoped FIFO batch rule workflow."""

    _CONTROL_KINDS = {
        "declared_found": (
            BatchTotalControlKind.DECLARED_IN_FOUND_SUPPLIES,
            "Заявлено в найденных поставках",
        ),
        "declared_shipped": (
            BatchTotalControlKind.DECLARED_IN_SHIPPED_SUPPLIES,
            "Заявлено в отправленных поставках",
        ),
        "accepted": (BatchTotalControlKind.ACCEPTED_UNITS, "Принято на складе"),
        "planned": (BatchTotalControlKind.PLANNED_UNITS, "Запланировано"),
    }

    def __init__(
        self, rule_service, repository, *, supply_source_service=None,
        scan_checkpoint_service=None, supply_store=None,
        supply_deduplicator=None, manifest_builder=None,
    ):
        self.rule_service = rule_service
        self.repository = repository
        self.supply_source_service = supply_source_service
        self.scan_checkpoint_service = scan_checkpoint_service
        self.supply_store = supply_store
        self.supply_deduplicator = supply_deduplicator
        self.manifest_builder = manifest_builder
        self._refresh_lock = RLock()

    def show_mode_choice(self, runtime, owner):
        session = runtime._sessions.get(owner)
        if not isinstance(session, dict):
            return runtime._stale()
        if session["case"].get("supply_total_mode") == "AUTO_FROM_SUPPLIES":
            return runtime._show_summary(owner)
        self._bump_flow(session)
        session["step"] = "batch_mode_choice"
        return runtime._result(
            "Как учитывать последующие поставки этой партии? Общий итог можно не вводить.",
            keyboard=runtime._keyboard([
                {"text": "Считать по поставкам Ozon", "callback": runtime._issue_ticket(owner, session, "batch_auto")},
                {"text": "Добавить контрольное количество", "callback": runtime._issue_ticket(owner, session, "batch_control")},
                {"text": "Вернуться", "callback": runtime._issue_ticket(owner, session, "batch_back")},
            ]),
        )

    def handle_mode_text(self, runtime, owner, text):
        normalized = " ".join(str(text or "").casefold().split())
        if normalized in {"не знаю", "авто", "автоматически", "считать по поставкам ozon"}:
            return self._start_auto_choice(runtime, owner)
        return runtime._result(
            "Выберите один из вариантов кнопками. «Не знаю» откроет автоматический сценарий, но не подтвердит правило."
        )

    def handle_callback(self, runtime, owner, session, ticket, action):
        if action == "batch_card":
            return runtime._show_summary(owner)
        if action == "batch_refresh":
            return self._refresh_supplies(runtime, owner, session, ticket)
        if action == "batch_check_found":
            return self._show_found_check(runtime, owner, session)
        if action == "batch_edit_rule":
            return self._show_rule_edit_guidance(runtime, owner, session)
        if action == "batch_back":
            self._bump_flow(session)
            self._clear_transient(session)
            return runtime._show_summary(owner)
        if action == "batch_auto":
            return self._start_auto_choice(runtime, owner)
        if action == "batch_day_all":
            self._bump_flow(session)
            case = session.get("case", {})
            dispatch_date = case.get("dispatch_date")
            if not isinstance(dispatch_date, str):
                return runtime._failure("Дата первой отправки неизвестна. Правило не сохранено.")
            result = self.rule_service.preview_rule(
                self._scope(runtime, owner, session), session["case_id"],
                session["case_revision"], BatchRuleInput(
                    dispatch_date, BatchStartDayPolicy.ALL_OWNER_CONFIRMED,
                ),
            )
            if result.get("error"):
                return runtime._failure(self._safe_rule_error(result.get("code")))
            preview = result["preview"]
            session["batch_rule_preview"] = {
                "preview_id": preview.preview_id,
                "preview_fingerprint": preview.preview_fingerprint,
                "start_date": preview.start_local_date,
                "policy": preview.start_day_policy.value,
                "case_revision": preview.expected_case_revision,
            }
            session["step"] = "batch_rule_preview"
            callback = runtime._issue_ticket(
                owner, session, "batch_confirm_rule",
                preview_id=preview.preview_id,
                preview_fingerprint=preview.preview_fingerprint,
            )
            previous_total = session["case"].get("declared_shipped_units")
            previous_total_note = (
                f"Ранее введённый общий итог {previous_total} шт. останется только legacy-контролем без даты и не ограничивает автоматический состав."
                if previous_total is not None
                else "Контрольный общий итог: не указан."
            )
            text = (
                f"Проверьте границу партии для {session['display_name']} · SKU {session['identity']['sku']}\n"
                f"Новая себестоимость: {runtime._format_cost(session['case'])} ₽/упаковку\n"
                f"Начало: {preview.start_local_date} · часовой пояс магазина: {preview.store_timezone}\n"
                "Отправки за этот день: вы подтвердили, что все относятся к новой партии.\n"
                f"Старый товар дома/в пути: {session['case'].get('owner_old_home_units')} / "
                f"{session['case'].get('owner_old_transit_units')} шт.\n"
                f"Новый товар дома: неизвестно. {previous_total_note}\n"
                "Подтверждение сохранит только правило границы. FIFO и расчёт прибыли не изменятся."
            )
            return runtime._result(text, keyboard=runtime._keyboard([
                {"text": "Подтвердить правило", "callback": callback},
                {"text": "Вернуться", "callback": runtime._issue_ticket(owner, session, "batch_back")},
            ]))
        if action == "batch_day_select":
            self._bump_flow(session)
            session["step"] = "batch_mode_choice"
            return runtime._result(
                "Нельзя безопасно подтвердить только часть отправок, пока список поставок не прочитан. Правило не сохранено. "
                "После подключения чтения списка можно будет выбрать поставки первого дня. Пока можно вернуться; автоматическое правило не сохранено.",
                keyboard=runtime._keyboard([
                    {"text": "Вернуться", "callback": runtime._issue_ticket(owner, session, "batch_back")},
                ]),
            )
        if action == "batch_confirm_rule":
            return self._confirm_rule(runtime, owner, session, ticket)
        if action == "batch_control":
            self._bump_flow(session)
            self._clear_transient(session)
            session["step"] = "batch_control_kind"
            buttons = [
                {"text": label, "callback": runtime._issue_ticket(owner, session, "batch_control_kind_" + key)}
                for key, (_kind, label) in self._CONTROL_KINDS.items()
            ]
            buttons.append({"text": "↩️ Назад", "callback": runtime._issue_ticket(owner, session, "batch_back")})
            return runtime._result(
                "Выберите, какое количество вы хотите зафиксировать. Это будет отдельный контроль на указанный период, не общий итог партии.",
                keyboard=runtime._keyboard(buttons),
            )
        if action.startswith("batch_control_kind_"):
            key = action.removeprefix("batch_control_kind_")
            if key not in self._CONTROL_KINDS:
                return runtime._stale()
            self._bump_flow(session)
            kind, label = self._CONTROL_KINDS[key]
            session["batch_control_draft"] = {"kind": kind.value, "label": label}
            session["step"] = "batch_control_units"
            return runtime._result(f"Введите контрольное количество «{label}» целым числом:")
        if action == "batch_confirm_control":
            return self._confirm_control(runtime, owner, session, ticket)
        if action == "batch_cancel_control":
            self._bump_flow(session)
            self._clear_transient(session)
            return self.show_mode_choice(runtime, owner)
        return runtime._stale()

    def handle_text(self, runtime, owner, session, text):
        step = session.get("step")
        draft = session.get("batch_control_draft")
        if not isinstance(draft, dict):
            return runtime._stale()
        if step == "batch_control_units":
            try:
                draft["total_units"] = runtime._quantity(text, allow_zero=True)
            except (TypeError, ValueError):
                return runtime._result("Введите целое количество от 0 до 1 000 000. Неизвестное значение не вводите как ноль.")
            session["step"] = "batch_control_from"
            return runtime._result("Введите начало периода контроля (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД):")
        if step == "batch_control_from":
            try:
                draft["window_from"] = runtime._parse_date(text)
            except (TypeError, ValueError):
                return runtime._result("Дата не распознана. Контроль не сохранён.")
            session["step"] = "batch_control_through"
            return runtime._result("Введите конец периода контроля (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД):")
        if step == "batch_control_through":
            try:
                value = runtime._parse_date(text)
            except (TypeError, ValueError):
                return runtime._result("Дата не распознана. Контроль не сохранён.")
            if value < draft["window_from"]:
                return runtime._result("Конец периода раньше начала. Контроль не сохранён; введите дату ещё раз.")
            draft["window_through"] = value
            fingerprint = self._digest(draft)
            session["batch_control_fingerprint"] = fingerprint
            session["step"] = "batch_control_preview"
            kind, label = self._CONTROL_KINDS[next(
                key for key, (candidate, _label) in self._CONTROL_KINDS.items()
                if candidate.value == draft["kind"]
            )]
            callback = runtime._issue_ticket(
                owner, session, "batch_confirm_control",
                control_fingerprint=fingerprint,
            )
            return runtime._result(
                f"Проверьте контроль владельца: {label} — {draft['total_units']} шт.; "
                f"период {draft['window_from']} — {draft['window_through']}. Это не подтверждённое Ozon количество; "
                "запись не меняет общий итог, FIFO или прибыль.",
                keyboard=runtime._keyboard([
                    {"text": "Сохранить контроль", "callback": callback},
                    {"text": "Отменить", "callback": runtime._issue_ticket(owner, session, "batch_cancel_control")},
                ]),
            )
        return runtime._result("Продолжите кнопками в сообщении с выбором количества.")

    def _start_auto_choice(self, runtime, owner):
        session = runtime._sessions.get(owner)
        if not isinstance(session, dict):
            return runtime._stale()
        self._bump_flow(session)
        case = session.get("case", {})
        if case.get("owner_old_home_units") != 0 or case.get("owner_old_transit_units") != 0:
            return runtime._result(
                "Автоматическое правило требует подтверждённых нулевых остатков старой партии дома и в пути. "
                "Черновик стоимости сохранён; можно добавить датированный контроль или вернуться позже.",
                keyboard=runtime._keyboard([
                    {"text": "Добавить контрольное количество", "callback": runtime._issue_ticket(owner, session, "batch_control")},
                    {"text": "Вернуться", "callback": runtime._issue_ticket(owner, session, "batch_back")},
                ]),
            )
        session["step"] = "batch_day_policy"
        day = case.get("dispatch_date")
        return runtime._result(
            f"Все отправки этого SKU за {day} были из новой партии? Подтверждение относится только к этому дню; более поздние доказанные отправки можно будет классифицировать отдельно.",
            keyboard=runtime._keyboard([
                {"text": "Да, все отправки дня", "callback": runtime._issue_ticket(owner, session, "batch_day_all")},
                {"text": "Нет / не уверен — выбрать поставки", "callback": runtime._issue_ticket(owner, session, "batch_day_select")},
                {"text": "Вернуться", "callback": runtime._issue_ticket(owner, session, "batch_back")},
            ]),
        )

    def _confirm_rule(self, runtime, owner, session, ticket):
        saved = session.get("batch_rule_preview")
        if (
            not isinstance(saved, dict)
            or saved.get("case_revision") != session.get("case_revision")
            or saved.get("preview_id") != ticket.get("preview_id")
            or saved.get("preview_fingerprint") != ticket.get("preview_fingerprint")
        ):
            return runtime._stale()
        result = self.rule_service.confirm_rule(
            self._scope(runtime, owner, session), session["case_id"],
            session["case_revision"], saved["preview_id"],
            saved["preview_fingerprint"], "tg-batch-rule-" + uuid4().hex,
        )
        if result.get("error"):
            return runtime._failure(self._safe_rule_error(result.get("code")))
        case = runtime._read_case(session["case_id"], session["identity"])
        if case.get("error"):
            return runtime._failure("Правило сохранено, но карточку не удалось обновить. Откройте черновик заново.")
        runtime._refresh_session(session, case)
        self._clear_transient(session)
        self._bump_flow(session)
        response = runtime._result(
            "Правило партии сохранено. Дата отправки не считается датой приёмки или продажи. "
            "FIFO и расчёт прибыли не изменились; новые поставки и полноту источника нужно проверить отдельно.",
            keyboard=runtime._keyboard([
                {"text": "К делу", "callback": runtime._issue_ticket(owner, session, "finish")},
            ]),
        )
        ticket["confirmed_result"] = dict(response)
        return response

    def summary_lines(self, runtime, owner, session):
        """Return a no-network summary for the current automatic rule and scan."""
        try:
            rule = self.rule_service.read_active_rule(
                self._scope(runtime, owner, session),
                session["case_id"], session["case_revision"],
            )
        except (KeyError, TypeError, ValueError):
            rule = {"error": True}
        if rule.get("error"):
            lines = ["Правило автоматической партии: не удалось подтвердить сохранённую редакцию."]
        else:
            policy = {
                BatchStartDayPolicy.ALL_OWNER_CONFIRMED.value:
                    "владелец подтвердил все отправки этого дня как новую партию",
                BatchStartDayPolicy.EXPLICIT_SUPPLY_SET.value:
                    "отправки первого дня требуют выбора владельца",
            }.get(rule.get("start_day_policy"), "требует проверки")
            lines = [f"Правило автоматической партии: с {rule['start_local_date']} · {policy}."]
        scan = session.get("batch_last_scan")
        if not isinstance(scan, dict):
            if session.get("batch_refresh_error"):
                lines.append("Последняя попытка обновления не удалась; подтверждённого чтения поставок ещё нет.")
            lines.append(
                "Поставки ещё не проверялись. Открытие карточки не обращается к Ozon. "
                "Историческое покрытие не подтверждено."
            )
            return lines
        if session.get("batch_refresh_error"):
            lines.append("Последняя попытка обновления не удалась; ниже показан предыдущий результат чтения.")
        lines.extend([
            f"Последнее чтение: {scan.get('read_at', 'в этой сессии')}; заявок в ответах "
            f"{scan.get('orders', 0)}, вложенных поставок {scan.get('supplies', 0)}; "
            f"HTTP-попыток {scan.get('http_attempts', 0)}/10.",
            "Это количество строк ответа API, а не подтверждённый остаток или количество SKU. "
            "Полнота истории, статусов и дат отправки не доказана; FIFO и прибыль не менялись.",
        ])
        if scan.get("continuation_available"):
            lines.append("Ограниченный поиск можно продолжить кнопкой «Обновить поставки».")
        lines.extend(self._issue_messages(scan.get("issue_codes", ()))[:2])
        return lines

    def summary_buttons(self, runtime, owner, session):
        return [
            {"text": "Обновить поставки", "callback": runtime._issue_ticket(owner, session, "batch_refresh")},
            {"text": "Проверить найденные", "callback": runtime._issue_ticket(owner, session, "batch_check_found")},
            {"text": "Изменить правило", "callback": runtime._issue_ticket(owner, session, "batch_edit_rule")},
            {"text": "Контрольное количество", "callback": runtime._issue_ticket(owner, session, "batch_control")},
        ]

    def _refresh_supplies(self, runtime, owner, session, ticket):
        # Hold the lock only for ticket/session validation. Network I/O must not
        # serialize refreshes for unrelated stores.
        with self._refresh_lock:
            cached = ticket.get("confirmed_result")
            if isinstance(cached, dict):
                return dict(cached)
            if ticket.get("flow_revision", 0) != session.get("flow_revision", 0):
                return runtime._stale()
            self._bump_flow(session)
        return self._collect_supplies(runtime, owner, session, ticket)

    def _collect_supplies(self, runtime, owner, session, ticket):
        if self.supply_source_service is None:
            session["batch_refresh_error"] = True
            response = self._card_return(runtime, owner,
                "Автопоиск поставок временно недоступен. Сохранённое правило и данные FIFO не изменены.")
            ticket["confirmed_result"] = dict(response)
            return response
        try:
            scope = self._scope(runtime, owner, session)
            rule = self.rule_service.read_active_rule(
                scope, session["case_id"], session["case_revision"],
            )
            if rule.get("error"):
                session["batch_refresh_error"] = True
                response = self._card_return(runtime, owner,
                    "Не удалось подтвердить актуальное правило партии. Ozon не запрашивался; данные не изменены.")
                ticket["confirmed_result"] = dict(response)
                return response
            result = self.supply_source_service.collect_supplies(
                scope, session["case_id"], session["case_revision"],
                rule["rule_revision"],
                continuation_token=session.get("batch_continuation_token"),
            )
            if not getattr(result, "read_only", False):
                raise ValueError("FIFO_BATCH_SOURCE_RESULT_INVALID")
        except Exception:
            # Keep source exceptions and raw payloads out of Telegram.
            session.pop("batch_continuation_token", None)
            session["batch_refresh_error"] = True
            response = self._card_return(runtime, owner,
                "Не удалось безопасно прочитать поставки. Предыдущий результат, если он был, сохранён; FIFO и прибыль не изменились.")
            ticket["confirmed_result"] = dict(response)
            return response

        now = runtime._now_provider()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        session["batch_last_scan"] = {
            "read_at": now.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
            "status": str(getattr(result, "status", "UNKNOWN")),
            "orders": self._bounded_count(getattr(result, "orders_observed", 0)),
            "supplies": self._bounded_count(getattr(result, "supplies_observed", 0)),
            "http_attempts": min(10, self._bounded_count(getattr(result, "actual_http_attempts", 0))),
            "pagination_complete": getattr(result, "pagination_complete", False) is True,
            "details_complete": getattr(result, "details_complete", False) is True,
            "issue_codes": tuple(
                value for value in getattr(result, "issue_codes", ())
                if isinstance(value, str) and value.startswith("FIFO_BATCH_")
            )[:12],
            "continuation_available": bool(getattr(result, "continuation_token", None)),
        }
        continuation = getattr(result, "continuation_token", None)
        if isinstance(continuation, str) and len(continuation) <= 96:
            session["batch_continuation_token"] = continuation
        else:
            session.pop("batch_continuation_token", None)
        session.pop("batch_refresh_error", None)
        response = self._collection_result(runtime, owner, session)
        ticket["confirmed_result"] = dict(response)
        return response

    def _collection_result(self, runtime, owner, session):
        scan = session.get("batch_last_scan", {})
        status_labels = {
            "COMPLETE": "страницы списка прочитаны до конца в рамках этого запроса",
            "PARTIAL": "получена только часть данных",
            "BLOCKED": "чтение остановлено проверкой исходных данных",
            "CONFLICT": "ответы изменились или противоречат друг другу",
            "UNAVAILABLE": "источник временно недоступен",
            "INVALID": "ответ не прошёл проверку структуры",
        }
        lines = [
            f"Проверка поставок за {scan.get('read_at', 'текущее чтение')}: {status_labels.get(scan.get('status'), 'результат требует проверки')}.",
            f"Заявок в ответах: {scan.get('orders', 0)}; вложенных поставок: {scan.get('supplies', 0)}; "
            f"HTTP-попыток: {scan.get('http_attempts', 0)}/10.",
        ]
        if scan.get("pagination_complete") and scan.get("details_complete"):
            lines.append("Локальная пагинация и карточки прочитаны до конца; полнота исторического охвата Ozon всё равно не подтверждена.")
        else:
            lines.append("Пагинация или карточки поставок прочитаны не полностью.")
        lines.extend([
            "Показано число строк ответа. Состав конкретного SKU и принадлежность к партии не подтверждены.",
            "Результат не записан в FIFO и не изменил прибыль.",
        ])
        lines.extend(self._issue_messages(scan.get("issue_codes", ()))[:4])
        buttons = []
        if scan.get("continuation_available"):
            buttons.append({"text": "Продолжить поиск", "callback": runtime._issue_ticket(owner, session, "batch_refresh")})
        buttons.append({"text": "К карточке партии", "callback": runtime._issue_ticket(owner, session, "batch_card")})
        return runtime._result("\n".join(lines), keyboard=runtime._keyboard(buttons))

    def _show_found_check(self, runtime, owner, session):
        scan = session.get("batch_last_scan")
        if not isinstance(scan, dict):
            message = "Сначала нажмите «Обновить поставки». Список не проверялся; Ozon сейчас не запрашивается."
        else:
            message = (
                f"В сохранённой проверке: заявок в ответах {scan.get('orders', 0)}, "
                f"вложенных поставок {scan.get('supplies', 0)}.\n"
                "Это только количество строк API. Точный состав SKU и принадлежность к партии "
                "пока нельзя подтвердить по текущей схеме источника. ID и названия скрыты; "
                "подтверждение или изменение FIFO не выполнялось."
            )
            issues = self._issue_messages(scan.get("issue_codes", ()))[:3]
            if issues:
                message += "\n" + "\n".join(issues)
        return self._card_return(runtime, owner, message)

    def _show_rule_edit_guidance(self, runtime, owner, session):
        return self._card_return(runtime, owner,
            "Сохранённое правило нельзя переписывать задним числом. Новая себестоимость должна оформляться отдельной FIFO-границей; текущее правило, FIFO и прибыль не изменены. Чтобы исправить принадлежность отправок первой даты, сначала нужно сверить конкретные поставки; никаких изменений пока не сохранено.")

    @staticmethod
    def _card_return(runtime, owner, message):
        session = runtime._sessions.get(owner)
        if not isinstance(session, dict):
            return runtime._stale()
        return runtime._result(message, keyboard=runtime._keyboard([{
            "text": "К карточке партии",
            "callback": runtime._issue_ticket(owner, session, "batch_card"),
        }]))

    @staticmethod
    def _issue_messages(issue_codes):
        messages = {
            "FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED": "Ozon не подтвердил полный перечень статусов; найденные строки пока нельзя считать полным набором.",
            "FIFO_BATCH_SUPPLY_LIST_UNAVAILABLE": "Список заявок не удалось прочитать полностью. Повторите обновление.",
            "FIFO_BATCH_SUPPLY_DETAILS_UNAVAILABLE": "Не удалось прочитать часть карточек заявок. Ограниченный поиск можно продолжить.",
            "FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED": "Достигнут лимит времени или запросов на один запуск. Продолжите поиск отдельным нажатием.",
            "FIFO_BATCH_SUPPLY_PAGE_LIMIT_REACHED": "Достигнут предел страниц на один запуск. Продолжите поиск отдельным нажатием.",
            "FIFO_BATCH_SUPPLY_CURSOR_PROOF_MISSING": "Источник не подтвердил, что после этой страницы данных больше нет.",
            "FIFO_BATCH_SUPPLY_LIST_MUTATED_DURING_SCAN": "Во время проверки список изменился или повторил записи. Запустите поиск заново.",
            "FIFO_BATCH_SUPPLY_CURSOR_NOT_ADVANCING": "Источник повторил курсор страницы. Запустите поиск заново.",
            "FIFO_BATCH_SUPPLY_CURSOR_INVALID": "Источник вернул неверный номер следующей страницы. Запустите поиск заново.",
            "FIFO_BATCH_SUPPLY_CURSOR_WITH_EMPTY_PAGE": "Источник вернул ссылку на продолжение без строк данных. Запустите поиск заново.",
            "FIFO_BATCH_SUPPLY_CHECKPOINT_UNAVAILABLE": "Продолжение не удалось сохранить в памяти. Запустите поиск заново.",
            "FIFO_BATCH_SUPPLY_CONTINUATION_STALE": "Продолжение истекло или бот был перезапущен. Запустите полный поиск заново.",
            "FIFO_BATCH_SUPPLY_CONTINUATION_INVALID": "Ссылка на продолжение недействительна. Запустите полный поиск заново.",
            "FIFO_BATCH_SUPPLY_CONTINUATION_SCOPE_MISMATCH": "Продолжение относится к другому SKU или магазину; оно сброшено.",
            "FIFO_BATCH_SUPPLY_ORDER_STATE_UNSUPPORTED": "Ответ содержит неизвестный статус заявки. Строки требуют проверки и не считаются полным набором.",
            "FIFO_BATCH_SUPPLY_STATE_UNSUPPORTED": "Ответ содержит неизвестный статус поставки. Строки требуют проверки и не считаются полным набором.",
            "FIFO_BATCH_SUPPLY_NESTED_LIST_UNAVAILABLE": "В ответе не удалось проверить список вложенных поставок.",
            "FIFO_BATCH_SUPPLY_ORDER_LIMIT_REACHED": "Достигнут предел заявок на один запуск. Продолжите поиск отдельным нажатием.",
            "FIFO_BATCH_SUPPLY_ROW_LIMIT_REACHED": "Достигнут предел вложенных поставок на один запуск. Продолжите поиск отдельным нажатием.",
            "FIFO_BATCH_BUNDLE_SCHEMA_UNVERIFIED": "Состав товара внутри поставки пока не подтверждён схемой ответа Ozon.",
            "FIFO_BATCH_BUNDLE_COLLECTION_BASIS_UNAVAILABLE": "Не удалось проверить правило партии перед чтением состава товара.",
            "FIFO_BATCH_COLLECTION_BASIS_UNAVAILABLE": "Не удалось проверить текущее правило партии перед запросом.",
            "FIFO_BATCH_RULE_REVISION_CONFLICT": "Правило партии изменилось. Откройте карточку заново и повторите обновление.",
            "FIFO_BATCH_CASE_REVISION_CONFLICT": "Дело изменилось. Откройте карточку заново и повторите обновление.",
        }
        result = []
        for code in issue_codes if isinstance(issue_codes, (tuple, list)) else ():
            message = messages.get(code)
            if message and message not in result:
                result.append(message)
        return result

    @staticmethod
    def _bounded_count(value):
        return value if type(value) is int and 0 <= value <= 100_000 else 0

    def _confirm_control(self, runtime, owner, session, ticket):
        draft = session.get("batch_control_draft")
        fingerprint = self._digest(draft) if isinstance(draft, dict) else None
        if (
            not isinstance(draft, dict)
            or fingerprint != ticket.get("control_fingerprint")
            or fingerprint != session.get("batch_control_fingerprint")
            or not all(key in draft for key in ("kind", "total_units", "window_from", "window_through"))
        ):
            return runtime._stale()
        scope = self._scope(runtime, owner, session)
        now = runtime._now_provider()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        confirmed_at = now.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        control_id = "bc_" + uuid4().hex
        material = {
            "kind": "OWNER_ENTERED_CONTROL_NO_EXTERNAL_SOURCE",
            "scope": {"store": scope.store_id, "sku": scope.sku, "product": scope.product_id, "offer": scope.offer_id},
            "case_id": session["case_id"], "total_units": draft["total_units"],
            "window_from": draft["window_from"], "window_through": draft["window_through"],
            "control_kind": draft["kind"],
        }
        digest = self._digest(material)
        control = BatchTotalControl(
            control_id=control_id, control_revision=1, scope=scope,
            case_id=session["case_id"], total_units=draft["total_units"],
            window_from=draft["window_from"], window_through=draft["window_through"],
            control_kind=BatchTotalControlKind(draft["kind"]),
            control_status=BatchTotalControlStatus.OWNER_CONFIRMED,
            source_proof_fingerprint=digest,
            owner_confirmation_fingerprint=self._digest({"owner_confirmed": material}),
            idempotency_key="tg-batch-control-" + uuid4().hex,
            confirmed_at=confirmed_at,
        )
        tenant = self.repository._tenant_scope(scope.store_id)
        if tenant.get("error"):
            return runtime._failure("Не удалось проверить магазин. Контроль не сохранён.")
        result = self.repository._run_transition_write(lambda connection: FifoCostBatchSupplyStore.append_total_control(
            connection, control, tenant_fingerprint=tenant["tenant_fingerprint"],
            recorded_at=confirmed_at,
        ))
        if result.get("error"):
            return runtime._failure("Контроль не сохранён. Данные партии и FIFO не изменены.")
        label = draft["label"]
        total = draft["total_units"]
        start, end = draft["window_from"], draft["window_through"]
        self._clear_transient(session)
        self._bump_flow(session)
        response = runtime._result(
            f"Контроль владельца сохранён: {label} — {total} шт. за {start} — {end}. "
            "Это отдельное значение без подтверждения Ozon; оно не заменяет общий итог партии и не меняет FIFO или прибыль.",
            keyboard=runtime._keyboard([
                {"text": "К выбору", "callback": runtime._issue_ticket(owner, session, "batch_control")},
                {"text": "К делу", "callback": runtime._issue_ticket(owner, session, "finish")},
            ]),
        )
        ticket["confirmed_result"] = dict(response)
        return response

    @staticmethod
    def _scope(runtime, owner, session):
        scoped_owner, scoped_store = split_store_tenant_scope(session["tenant"])
        identity = session["identity"]
        if scoped_store != identity.get("store_id"):
            raise ValueError("FIFO_BATCH_TENANT_SCOPE_MISMATCH")
        return ScopeIdentity(
            owner_id=scoped_owner,
            store_id=identity["store_id"],
            product_id=identity.get("product_id"),
            offer_id=identity.get("offer_id"),
            sku=identity["sku"],
        )

    @staticmethod
    def _clear_transient(session):
        for key in (
            "batch_rule_preview", "batch_control_draft", "batch_control_fingerprint",
            "step",
        ):
            session.pop(key, None)

    @staticmethod
    def _bump_flow(session):
        session["flow_revision"] = session.get("flow_revision", 0) + 1

    @staticmethod
    def _digest(value):
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_rule_error(code):
        messages = {
            "FIFO_BATCH_OLD_HOME_NOT_CONFIRMED_ZERO": "Автоматическое правило недоступно: остаток старой партии дома не подтверждён как ноль.",
            "FIFO_BATCH_OLD_TRANSIT_NOT_CONFIRMED_ZERO": "Автоматическое правило недоступно: старый товар в пути не подтверждён как ноль.",
            "FIFO_BATCH_STORE_TIMEZONE_UNKNOWN": "Не удалось подтвердить часовой пояс магазина. Правило не сохранено.",
            "FIFO_BATCH_SAME_DAY_BOUNDARY_NEEDS_REVIEW": "Две границы стоимости приходятся на один день; требуется отдельная сверка.",
            "FIFO_BATCH_CASE_REVISION_CONFLICT": "Черновик изменился. Обновите карточку и повторите выбор.",
        }
        return messages.get(code, "Не удалось подготовить правило. Сохранённый черновик не изменён.")
