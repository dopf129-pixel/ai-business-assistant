"""Telegram prompts for automatic FIFO batch rules and dated owner controls.

This adapter owns only transient interaction state. Automatic rules and owner
controls are persisted by their existing domain services and never alter FIFO
layers, allocations, or profit by themselves.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    BatchMembershipDecision,
    MembershipDecisionKind,
    MembershipDecisionSource,
    canonical_membership_group_binding_fingerprint,
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
        if action == "batch_review_page":
            return self._render_candidate_page(
                runtime, owner, session, ticket.get("page"),
            )
        if action == "batch_review_toggle":
            return self._toggle_candidate(
                runtime, owner, session, ticket,
            )
        if action == "batch_review_reset":
            return self._reset_candidate_selection(runtime, owner, session)
        if action in {"batch_review_prepare_include", "batch_review_prepare_exclude"}:
            decision = (
                MembershipDecisionKind.INCLUDED
                if action.endswith("include") else MembershipDecisionKind.EXCLUDED
            )
            return self._prepare_membership_decision(
                runtime, owner, session, decision,
            )
        if action == "batch_review_confirm":
            return self._confirm_membership_decision(
                runtime, owner, session, ticket,
            )
        if action == "batch_review_cancel":
            session.pop("batch_membership_preview", None)
            return self._render_candidate_page(
                runtime, owner, session,
                (session.get("batch_membership_review") or {}).get("page", 0),
            )
        if action == "batch_edit_rule":
            return self._show_rule_edit_guidance(runtime, owner, session)
        if action == "batch_back":
            self._bump_flow(session)
            self._clear_transient(session)
            return runtime._show_summary(owner)
        if action == "batch_auto":
            return self._start_auto_choice(runtime, owner)
        if action in {"batch_day_all", "batch_day_select"}:
            self._bump_flow(session)
            policy = (
                BatchStartDayPolicy.ALL_OWNER_CONFIRMED
                if action == "batch_day_all"
                else BatchStartDayPolicy.EXPLICIT_SUPPLY_SET
            )
            return self._preview_start_day_rule(runtime, owner, session, policy)
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

    def _preview_start_day_rule(self, runtime, owner, session, policy):
        case = session.get("case", {})
        dispatch_date = case.get("dispatch_date")
        if not isinstance(dispatch_date, str):
            return runtime._failure("Дата первой отправки неизвестна. Правило не сохранено.")
        result = self.rule_service.preview_rule(
            self._scope(runtime, owner, session), session["case_id"],
            session["case_revision"], BatchRuleInput(dispatch_date, policy),
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
        previous_total = case.get("declared_shipped_units")
        previous_total_note = (
            f"Ранее введённый общий итог {previous_total} шт. останется только legacy-контролем без даты и не ограничивает автоматический состав."
            if previous_total is not None
            else "Контрольный общий итог: не указан."
        )
        if policy is BatchStartDayPolicy.ALL_OWNER_CONFIRMED:
            boundary_note = "Отправки за этот день: вы подтвердили, что все относятся к новой партии."
        else:
            boundary_note = (
                "Отправки за этот день: пока ни одна не включена автоматически. "
                "После сохранения обновите список и выберите конкретные строки первого дня. "
                "Подтверждённые отправки с более поздней датой могут учитываться по правилу автоматически."
            )
        text = (
            f"Проверьте границу партии для {session['display_name']} · SKU {session['identity']['sku']}\n"
            f"Новая себестоимость: {runtime._format_cost(case)} ₽/упаковку\n"
            f"Начало: {preview.start_local_date} · часовой пояс магазина: {preview.store_timezone}\n"
            f"{boundary_note}\n"
            f"Старый товар дома/в пути: {case.get('owner_old_home_units')} / "
            f"{case.get('owner_old_transit_units')} шт.\n"
            f"Новый товар дома: неизвестно. {previous_total_note}\n"
            "Подтверждение сохранит только правило границы. FIFO и расчёт прибыли не изменятся."
        )
        return runtime._result(text, keyboard=runtime._keyboard([
            {"text": "Подтвердить правило", "callback": callback},
            {"text": "Вернуться", "callback": runtime._issue_ticket(owner, session, "batch_back")},
        ]))

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
        message = (
            "Правило партии сохранено, но ни одна отправка первого дня не включена автоматически. "
            "Откройте карточку партии, обновите список и подтвердите нужные строки отдельно. "
            "Дата отправки не считается датой приёмки или продажи. FIFO и расчёт прибыли не изменились; "
            "полноту источника нужно проверить отдельно."
            if saved.get("policy") == BatchStartDayPolicy.EXPLICIT_SUPPLY_SET.value
            else (
                "Правило партии сохранено. Дата отправки не считается датой приёмки или продажи. "
                "FIFO и расчёт прибыли не изменились; новые поставки и полноту источника нужно проверить отдельно."
            )
        )
        response = runtime._result(
            message,
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
        elif rule.get("inputs_current") is False:
            lines = [
                f"Правило партии · редакция {rule['rule_revision']} устарело после изменения "
                "себестоимости или условий дела. Сохранённые поставки этой редакции не "
                "используются до повторного подтверждения правила; откройте изменение правила."
            ]
        else:
            policy = {
                BatchStartDayPolicy.ALL_OWNER_CONFIRMED.value:
                    "владелец подтвердил все отправки этого дня как новую партию",
                BatchStartDayPolicy.EXPLICIT_SUPPLY_SET.value:
                    "отправки первого дня требуют выбора владельца",
            }.get(rule.get("start_day_policy"), "требует проверки")
            event_label = {
                "CONFIRM": "первая редакция подтверждена владельцем",
                "REPLACE": "новая редакция подтверждена владельцем; прежняя граница закрыта",
            }.get(rule.get("event_kind"), "тип изменения не подтверждён")
            lines = [
                f"Правило партии · редакция {rule['rule_revision']}: {event_label}; "
                f"с {rule['start_local_date']} · {policy}.",
                f"Ставка правила {rule['new_unit_cost_rub']} ₽/шт. — это не текущая "
                "себестоимость FIFO: правило само по себе не создаёт FIFO-слой и не меняет прибыль.",
            ]
        if not isinstance(session.get("batch_last_scan"), dict):
            self._restore_latest_scan(runtime, owner, session)
        scan = session.get("batch_last_scan")
        if not isinstance(scan, dict):
            if session.get("batch_refresh_error"):
                lines.append("Последняя попытка обновления не удалась; подтверждённого чтения поставок ещё нет.")
            if session.get("batch_scan_restore_error"):
                lines.append(
                    "Не удалось прочитать сохранённую проверку поставок. "
                    "Повторите открытие карточки позже; Ozon не запрашивался."
                )
            else:
                lines.append(
                    "Поставки ещё не проверялись. Открытие карточки не обращается к Ozon. "
                    "Историческое покрытие и время среза Ozon не подтверждены."
                )
            return lines
        if session.get("batch_refresh_error"):
            lines.append("Последняя попытка обновления не удалась; ниже показан предыдущий результат чтения.")
        page_coverage = "полная в рамках запроса" if scan.get("pagination_complete") is True else "неполная"
        detail_coverage = "полная в рамках запроса" if scan.get("details_complete") is True else "неполная"
        attempts = scan.get("http_attempts")
        attempts_text = f"{attempts}/10" if type(attempts) is int else "не сохранено"
        status_labels = {
            "COMPLETE": "завершено в рамках текущего запроса",
            "PARTIAL": "получена только часть данных",
            "CONFLICT": "ответы противоречат друг другу",
            "UNAVAILABLE": "источник недоступен",
        }
        lines.extend([
            f"Состояние последнего чтения: {status_labels.get(scan.get('status'), 'требует проверки')}.",
            f"Последнее чтение: {scan.get('read_at', 'в этой сессии')}; заявок в ответах "
            f"{scan.get('orders', 0)}, вложенных поставок {scan.get('supplies', 0)}; "
            f"HTTP-попыток {attempts_text}.",
            f"Покрытие текущего запроса: список — {page_coverage}, карточки — {detail_coverage}. "
            "Это время чтения ботом, не время среза Ozon; отдельный source-as-of и полнота истории не подтверждены.",
            "Это количество строк ответа API, а не подтверждённый остаток или количество SKU. "
            "Полнота истории, статусов и дат отправки не доказана; автоматическое правило не меняет FIFO и прибыль.",
        ])
        if scan.get("continuation_available"):
            lines.append("Ограниченный поиск можно продолжить кнопкой «Обновить поставки».")
        elif scan.get("continuation_expired"):
            lines.append("Сохранённое продолжение истекло; запустите новый поиск кнопкой «Обновить поставки».")
        lines.extend(self._issue_messages(scan.get("issue_codes", ()))[:2])
        return lines

    def _restore_latest_scan(self, runtime, owner, session):
        """Rehydrate the exact scoped scan and resumable reference after restart."""
        if self.scan_checkpoint_service is None:
            return False
        connection = None
        try:
            scope = self._scope(runtime, owner, session)
            tenant = self.repository._tenant_scope(scope.store_id)
            if tenant.get("error"):
                raise ValueError("FIFO_BATCH_SCAN_TENANT_SCOPE_UNAVAILABLE")
            connection = self.repository.get_connection()
            scan = FifoCostBatchSupplyStore.read_latest_scan_checkpoint(
                connection, scope=scope, case_id=session["case_id"],
                tenant_fingerprint=tenant["tenant_fingerprint"],
            )
            session["batch_scan_restore_error"] = False
            if scan is None:
                return True
            status = {
                "PUBLISHED": "COMPLETE",
                "STAGING": "PARTIAL",
                "PARTIAL": "PARTIAL",
                "FAILED": "UNAVAILABLE",
                "EXPIRED": "UNAVAILABLE",
            }.get(scan.get("status"), "UNAVAILABLE")
            captured_at = scan.get("captured_at") or scan.get("updated_at")
            read_at = "сохранённое чтение"
            if isinstance(captured_at, str):
                try:
                    parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                    read_at = parsed.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
                except ValueError:
                    pass
            issues = json.loads(scan.get("issue_codes_json") or "[]")
            if not isinstance(issues, list):
                issues = []
            issue_codes = tuple(
                value for value in issues
                if isinstance(value, str) and value.startswith("FIFO_BATCH_")
            )[:12]
            if scan.get("status") == "PUBLISHED" and any(
                marker in issue
                for issue in issue_codes
                for marker in (
                    "CONFLICT", "MUTATED", "NOT_ADVANCING", "INVALID",
                    "PROOF_MISSING", "CHANGED", "DUPLICATE",
                )
            ):
                status = "CONFLICT"
            continuation_available = False
            continuation_expired = False
            if (
                scan.get("status") in {"STAGING", "PARTIAL"}
                and scan.get("encrypted_resumable_token") is not None
            ):
                token = f"{scan['scan_id']}_r{scan['revision']}"
                expires_at = datetime.fromisoformat(
                    scan["expires_at"].replace("Z", "+00:00"),
                )
                now = runtime._now_provider()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise ValueError("FIFO_BATCH_SCAN_TIMESTAMP_INVALID")
                if expires_at.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
                    continuation_expired = True
                else:
                    supported_states = json.loads(
                        scan["supported_state_profile_json"],
                    )
                    resumed = self.scan_checkpoint_service.load_continuation(
                        scope=scope, case_id=session["case_id"],
                        tenant_fingerprint=tenant["tenant_fingerprint"],
                        rule_id=scan["rule_id"], rule_revision=scan["rule_revision"],
                        rule_fingerprint=scan["rule_fingerprint"],
                        expected_case_revision=session["case_revision"],
                        source_contract_version=scan["source_contract_version"],
                        supported_state_profile=tuple(supported_states),
                        requested_from=scan.get("requested_from"),
                        requested_through=scan.get("requested_through"),
                        continuation_token=token,
                    )
                    if not resumed.get("error"):
                        continuation_available = True
                        session["batch_continuation_token"] = token
                    else:
                        issue = resumed.get("code")
                        if isinstance(issue, str) and issue.startswith("FIFO_BATCH_"):
                            issue_codes = tuple(dict.fromkeys((*issue_codes, issue)))[:12]
            if not continuation_available:
                session.pop("batch_continuation_token", None)
            session["batch_last_scan"] = {
                "read_at": read_at,
                "status": status,
                "orders": self._bounded_count(scan.get("orders_seen")),
                "supplies": self._bounded_count(scan.get("supplies_seen")),
                "http_attempts": None,
                "pagination_complete": scan.get("list_pagination_complete") == 1,
                "details_complete": scan.get("details_complete") == 1,
                "scan_id": scan.get("scan_id"),
                "scan_revision": scan.get("revision"),
                "candidates": self._bounded_count(scan.get("sku_rows_seen")),
                "sku_composition_complete": scan.get("sku_composition_complete") == 1,
                "issue_codes": issue_codes,
                "continuation_available": continuation_available,
                "continuation_expired": continuation_expired,
            }
            return True
        except Exception:
            session["batch_scan_restore_error"] = True
            session.pop("batch_continuation_token", None)
            return False
        finally:
            if connection is not None:
                connection.close()

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
            "scan_id": getattr(result, "scan_id", None),
            "scan_revision": getattr(result, "scan_revision", None),
            "candidates": self._bounded_count(
                getattr(result, "candidates_observed", 0),
            ),
            "sku_composition_complete": (
                getattr(result, "sku_composition_complete", False) is True
            ),
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
        session.pop("batch_membership_review", None)
        session.pop("batch_membership_preview", None)
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
        attempts = scan.get("http_attempts")
        attempts_text = f"{attempts}/10" if type(attempts) is int else "не сохранено"
        lines = [
            f"Проверка поставок за {scan.get('read_at', 'текущее чтение')}: {status_labels.get(scan.get('status'), 'результат требует проверки')}.",
            f"Заявок в ответах: {scan.get('orders', 0)}; вложенных поставок: {scan.get('supplies', 0)}; "
            f"HTTP-попыток: {attempts_text}.",
        ]
        if scan.get("pagination_complete") and scan.get("details_complete"):
            lines.append("Локальная пагинация и карточки прочитаны до конца; полнота исторического охвата Ozon всё равно не подтверждена.")
        else:
            lines.append("Пагинация или карточки поставок прочитаны не полностью.")
        lines.append(
            f"Точных строк выбранного SKU в составе найденных поставок: {scan.get('candidates', 0)}."
        )
        lines.append(
            "Количество из состава — заявленное количество; оно не доказывает отгрузку или приёмку."
        )
        if scan.get("sku_composition_complete") is not True:
            lines.append(
                "Состав части найденных поставок не подтверждён; выбор относится только к показанным строкам."
            )
        lines.append("Результат сохранён как источник партий; FIFO и прибыль не изменены.")
        lines.extend(self._issue_messages(scan.get("issue_codes", ()))[:4])
        buttons = []
        if scan.get("continuation_available"):
            buttons.append({"text": "Продолжить поиск", "callback": runtime._issue_ticket(owner, session, "batch_refresh")})
        if scan.get("candidates", 0) > 0:
            buttons.append({"text": "Проверить состав SKU", "callback": runtime._issue_ticket(owner, session, "batch_check_found")})
        buttons.append({"text": "К карточке партии", "callback": runtime._issue_ticket(owner, session, "batch_card")})
        return runtime._result("\n".join(lines), keyboard=runtime._keyboard(buttons))

    def _show_found_check(self, runtime, owner, session):
        scan = session.get("batch_last_scan")
        if not isinstance(scan, dict):
            message = "Сначала нажмите «Обновить поставки». Список не проверялся; Ozon сейчас не запрашивается."
            return self._card_return(runtime, owner, message)
        if not isinstance(scan.get("scan_id"), str):
            message = (
                f"В сохранённой проверке: заявок {scan.get('orders', 0)}, "
                f"вложенных поставок {scan.get('supplies', 0)}. "
                "Точный состав SKU для этой старой проверки не сохранён; "
                "нужно обновить поставки. ID и названия не показываются."
            )
            return self._card_return(runtime, owner, message)
        return self._render_candidate_page(runtime, owner, session, 0)

    def _read_candidate_snapshot(self, runtime, owner, session, *, page=0, record_keys=None):
        scan = session.get("batch_last_scan")
        if (
            not isinstance(scan, dict)
            or not isinstance(scan.get("scan_id"), str)
            or type(scan.get("scan_revision")) is not int
        ):
            return {"error": True, "code": "FIFO_BATCH_SCAN_NOT_FOUND"}
        if record_keys is not None and (
            not isinstance(record_keys, tuple) or not 1 <= len(record_keys) <= 50
        ):
            return {"error": True, "code": "FIFO_BATCH_READ_KEYS_INVALID"}
        scope = self._scope(runtime, owner, session)
        tenant = self.repository._tenant_scope(scope.store_id)
        if tenant.get("error"):
            return {"error": True, "code": "FIFO_BATCH_SCAN_TENANT_SCOPE_UNAVAILABLE"}
        connection = None
        try:
            connection = self.repository.get_connection()
            result = FifoCostBatchSupplyStore.read_scan_candidate_page(
                connection, scope=scope, case_id=session["case_id"],
                tenant_fingerprint=tenant["tenant_fingerprint"],
                scan_id=scan["scan_id"], limit=8,
                offset=max(0, int(page)) * 8,
                record_keys=record_keys,
            )
            if result.get("error") or result.get("code") != "FIFO_BATCH_SCAN_CANDIDATES_READ":
                return {"error": True, "code": result.get("code", "FIFO_BATCH_SCAN_NOT_FOUND")}
            if (
                result.get("scan_revision") != scan["scan_revision"]
                or result.get("candidate_set_fingerprint")
                != result.get("stored_candidate_set_fingerprint")
            ):
                return {"error": True, "code": "FIFO_BATCH_SCAN_STALE"}
            result["tenant_fingerprint"] = tenant["tenant_fingerprint"]
            return result
        except Exception:
            return {"error": True, "code": "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE"}
        finally:
            if connection is not None:
                connection.close()

    def _render_candidate_page(self, runtime, owner, session, page):
        if type(page) is not int or not 0 <= page <= 1_250:
            return runtime._stale()
        scan = session.get("batch_last_scan")
        if not isinstance(scan, dict) or not scan.get("scan_id"):
            return self._card_return(runtime, owner,
                "В этой проверке нет сохранённого состава по SKU. Сначала обновите поставки.")
        snapshot = self._read_candidate_snapshot(runtime, owner, session, page=page)
        if snapshot.get("error"):
            return self._card_return(runtime, owner,
                "Список поставок устарел или недоступен. Обновите его заново; прежнее решение не изменено.")
        total = snapshot["total"]
        if total == 0:
            return self._card_return(runtime, owner,
                "В сохранённой проверке нет строк с точным совпадением выбранного SKU. "
                "Другие товары и идентификаторы не показываются.")
        page_count = max(1, (total + 7) // 8)
        if page >= page_count:
            return runtime._stale()
        review = session.get("batch_membership_review")
        binding = (
            scan["scan_id"], scan["scan_revision"],
            snapshot["candidate_set_fingerprint"],
        )
        if (
            not isinstance(review, dict)
            or (review.get("scan_id"), review.get("scan_revision"),
                review.get("candidate_set_fingerprint")) != binding
        ):
            review = {
                "scan_id": scan["scan_id"],
                "scan_revision": scan["scan_revision"],
                "candidate_set_fingerprint": snapshot["candidate_set_fingerprint"],
                "total": total,
                "selected_keys": [],
                "page": page,
            }
            session["batch_membership_review"] = review
        review["page"] = page
        review["page_record_keys"] = [item["record_key"] for item in snapshot["items"]]
        label_reader = getattr(self.supply_source_service, "read_owner_candidate_labels", None)
        if not callable(label_reader):
            return self._card_return(
                runtime, owner,
                "Не удалось безопасно показать отличительные номера поставок. "
                "Выбор не сохранён; обновите список позже.",
            )
        reference_labels = label_reader(
            scope=self._scope(runtime, owner, session),
            case_id=session["case_id"],
            tenant_fingerprint=snapshot["tenant_fingerprint"],
            scan_id=scan["scan_id"],
            record_keys=tuple(review["page_record_keys"]),
        )
        if reference_labels.get("error") or not isinstance(reference_labels.get("labels"), dict):
            return self._card_return(
                runtime, owner,
                "Не удалось безопасно сопоставить строки с поставками Ozon. "
                "Выбор не сохранён; обновите список позже.",
            )
        selected = set(review.get("selected_keys", ()))
        scan_published = snapshot.get("scan_status") == "PUBLISHED"
        lines = [
            f"Точный состав SKU · страница {page + 1}/{page_count} · строк {total}.",
            "Количество ниже — заявленный состав товара в поставке. Оно не подтверждает отгрузку или приёмку.",
            "Дата отправки API не подтверждает. Решение о партии будет вашим подтверждением, а не фактом Ozon.",
        ]
        if not scan_published or scan.get("status") != "COMPLETE":
            lines.append("Скан ещё не завершён. Сначала завершите поиск, затем можно будет сохранять выбор.")
        if scan.get("sku_composition_complete") is not True:
            lines.append("Для части найденных поставок точный состав неизвестен; показаны только подтверждённые строки этого SKU.")
        buttons = []
        status_labels = {
            "DECLARED": "заявлена", "AT_DROPOFF": "на точке отгрузки",
            "IN_TRANSIT": "в пути", "RECEIVING": "приёмка",
            "PARTIALLY_ACCEPTED": "принята частично", "ACCEPTED": "завершена",
            "CANCELLED": "отменена", "UNKNOWN": "неизвестен",
        }
        for local_index, item in enumerate(snapshot["items"]):
            number = page * 8 + local_index + 1
            quantity = item.get("planned_declared_quantity")
            quantity_text = f"{quantity} шт. заявлено" if type(quantity) is int else "количество неизвестно"
            transport = status_labels.get(item.get("normalized_status"), "неизвестен")
            crossdock_value = item.get("is_crossdock")
            crossdock = "кросс-докинг" if crossdock_value is True or crossdock_value == 1 else (
                "обычная поставка" if crossdock_value is False or crossdock_value == 0
                else "тип поставки неизвестен"
            )
            marker = "☑️" if item["record_key"] in selected else "⬜"
            reference = reference_labels["labels"].get(item["record_key"])
            if not isinstance(reference, str) or not reference.startswith("••••"):
                return self._card_return(
                    runtime, owner,
                    "Не удалось безопасно сопоставить строки с поставками Ozon. "
                    "Выбор не сохранён; обновите список позже.",
                )
            lines.append(
                f"{marker} {number}. ID {reference}; {quantity_text}; "
                f"статус: {transport}; {crossdock}; дата отправки неизвестна."
            )
            buttons.append({
                "text": f"{marker} Строка {number}",
                "callback": runtime._issue_ticket(
                    owner, session, "batch_review_toggle",
                    page=page, row_index=local_index,
                    scan_id=scan["scan_id"], scan_revision=scan["scan_revision"],
                    candidate_set_fingerprint=snapshot["candidate_set_fingerprint"],
                ),
            })
        if page > 0:
            buttons.append({"text": "⬅️ Назад", "callback": runtime._issue_ticket(
                owner, session, "batch_review_page", page=page - 1,
            )})
        if page + 1 < page_count:
            buttons.append({"text": "➡️ Далее", "callback": runtime._issue_ticket(
                owner, session, "batch_review_page", page=page + 1,
            )})
        if selected and scan_published and scan.get("status") == "COMPLETE":
            buttons.extend([
                {"text": f"Выбранные — новая партия ({len(selected)}/50)",
                 "callback": runtime._issue_ticket(owner, session, "batch_review_prepare_include")},
                {"text": "Выбранные — не новая партия",
                 "callback": runtime._issue_ticket(owner, session, "batch_review_prepare_exclude")},
                {"text": "Снять выбор", "callback": runtime._issue_ticket(owner, session, "batch_review_reset")},
            ])
        buttons.append({"text": "К карточке партии", "callback": runtime._issue_ticket(owner, session, "batch_card")})
        return runtime._result("\n".join(lines), keyboard=runtime._keyboard(buttons))

    def _toggle_candidate(self, runtime, owner, session, ticket):
        review = session.get("batch_membership_review")
        scan = session.get("batch_last_scan")
        index = ticket.get("row_index")
        page = ticket.get("page")
        if (
            not isinstance(review, dict) or not isinstance(scan, dict)
            or type(index) is not int or not 0 <= index < 8
            or type(page) is not int or page != review.get("page")
            or ticket.get("scan_id") != review.get("scan_id")
            or ticket.get("scan_revision") != review.get("scan_revision")
            or ticket.get("candidate_set_fingerprint")
            != review.get("candidate_set_fingerprint")
        ):
            return runtime._stale()
        page_keys = review.get("page_record_keys")
        if not isinstance(page_keys, list) or index >= len(page_keys):
            return runtime._stale()
        selected = list(review.get("selected_keys", ()))
        record_key = page_keys[index]
        if record_key in selected:
            selected.remove(record_key)
        else:
            if len(selected) >= 50:
                return runtime._result("За один раз можно подтвердить не более 50 строк. Снимите часть выбора.")
            selected.append(record_key)
        review["selected_keys"] = selected
        return self._render_candidate_page(runtime, owner, session, page)

    def _reset_candidate_selection(self, runtime, owner, session):
        review = session.get("batch_membership_review")
        if not isinstance(review, dict):
            return runtime._stale()
        review["selected_keys"] = []
        session.pop("batch_membership_preview", None)
        return self._render_candidate_page(
            runtime, owner, session, review.get("page", 0),
        )

    def _prepare_membership_decision(self, runtime, owner, session, decision):
        review = session.get("batch_membership_review")
        scan = session.get("batch_last_scan")
        if not isinstance(review, dict) or not isinstance(scan, dict):
            return runtime._stale()
        selected = tuple(sorted(set(review.get("selected_keys", ()))))
        if not selected or len(selected) > 50:
            return runtime._result("Выберите от 1 до 50 строк поставок.")
        if scan.get("status") != "COMPLETE":
            return runtime._result("Завершите полный поиск поставок перед сохранением выбора. Текущие данные не изменены.")
        snapshot = self._read_candidate_snapshot(
            runtime, owner, session, record_keys=selected,
        )
        if (
            snapshot.get("error")
            or snapshot.get("candidate_set_fingerprint")
            != review.get("candidate_set_fingerprint")
            or len(snapshot.get("items", ())) != len(selected)
        ):
            return self._card_return(runtime, owner,
                "Список изменился после просмотра. Обновите поставки; решение не сохранено.")
        rule = self.rule_service.read_active_rule(
            self._scope(runtime, owner, session),
            session["case_id"], session["case_revision"],
        )
        if rule.get("error"):
            return runtime._result("Не удалось подтвердить активное правило партии. Выбор не сохранён.")
        pairs = tuple(sorted(
            (item["record_key"], item["source_fingerprint"])
            for item in snapshot["items"]
        ))
        preview = {
            "scan_id": review["scan_id"],
            "scan_revision": review["scan_revision"],
            "candidate_set_fingerprint": review["candidate_set_fingerprint"],
            "decision": decision.value,
            "record_keys": selected,
            "source_fingerprints": pairs,
            "rule_id": rule["rule_id"],
            "rule_revision": rule["rule_revision"],
            "rule_fingerprint": rule["rule_fingerprint"],
            "case_revision": session["case_revision"],
        }
        preview_fingerprint = self._digest(preview)
        preview["preview_fingerprint"] = preview_fingerprint
        session["batch_membership_preview"] = preview
        callback = runtime._issue_ticket(
            owner, session, "batch_review_confirm",
            preview_fingerprint=preview_fingerprint,
            scan_id=preview["scan_id"], scan_revision=preview["scan_revision"],
            candidate_set_fingerprint=preview["candidate_set_fingerprint"],
        )
        label = "включить в новую партию" if decision is MembershipDecisionKind.INCLUDED else "исключить из новой партии"
        return runtime._result(
            f"Подтвердите: {len(selected)} выбранных поставок {label}. "
            "Это ваше решение о принадлежности к партии; дата и количество отгрузки не подтверждены Ozon. "
            "FIFO и прибыль не изменятся.",
            keyboard=runtime._keyboard([
                {"text": "Подтвердить выбор", "callback": callback},
                {"text": "Вернуться к списку", "callback": runtime._issue_ticket(
                    owner, session, "batch_review_cancel",
                )},
            ]),
        )

    def _confirm_membership_decision(self, runtime, owner, session, ticket):
        preview = session.get("batch_membership_preview")
        if (
            not isinstance(preview, dict)
            or preview.get("preview_fingerprint") != ticket.get("preview_fingerprint")
            or preview.get("scan_id") != ticket.get("scan_id")
            or preview.get("scan_revision") != ticket.get("scan_revision")
            or preview.get("candidate_set_fingerprint")
            != ticket.get("candidate_set_fingerprint")
            or preview.get("case_revision") != session.get("case_revision")
        ):
            return runtime._stale()
        saved_preview_fp = preview.pop("preview_fingerprint", None)
        if self._digest(preview) != saved_preview_fp:
            preview["preview_fingerprint"] = saved_preview_fp
            return runtime._stale()
        preview["preview_fingerprint"] = saved_preview_fp
        result = self._persist_membership_decision(runtime, owner, session, preview)
        if result.get("error"):
            return runtime._failure(self._safe_membership_error(result.get("code")))
        session.pop("batch_membership_preview", None)
        review = session.get("batch_membership_review")
        if isinstance(review, dict):
            review["selected_keys"] = []
        kind = "включены в новую партию" if preview["decision"] == "INCLUDED" else "исключены из новой партии"
        response = runtime._result(
            f"Решение владельца сохранено: {len(preview['record_keys'])} поставок {kind}. "
            "Это подтверждение принадлежности к партии, не доказательство отправки или приёмки Ozon. "
            "Себестоимость FIFO и прибыль не изменились.",
            keyboard=runtime._keyboard([{
                "text": "К списку поставок",
                "callback": runtime._issue_ticket(owner, session, "batch_check_found"),
            }]),
        )
        ticket["confirmed_result"] = dict(response)
        return response

    def _persist_membership_decision(self, runtime, owner, session, preview):
        scope = self._scope(runtime, owner, session)
        tenant = self.repository._tenant_scope(scope.store_id)
        if tenant.get("error"):
            return {"error": True, "code": "FIFO_BATCH_SCAN_TENANT_SCOPE_UNAVAILABLE"}
        try:
            confirmed_at = runtime._now_provider()
            if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
                return {"error": True, "code": "FIFO_BATCH_DECISION_TIME_INVALID"}
            confirmed_text = confirmed_at.astimezone(timezone.utc).isoformat(
                timespec="microseconds",
            ).replace("+00:00", "Z")
            decision_kind = MembershipDecisionKind(preview["decision"])
            record_keys = tuple(preview["record_keys"])
            source_fingerprints = tuple(
                (str(key), str(fingerprint))
                for key, fingerprint in preview["source_fingerprints"]
            )
            binding = canonical_membership_group_binding_fingerprint(
                scope=scope, rule_id=preview["rule_id"],
                rule_revision=preview["rule_revision"],
                rule_fingerprint=preview["rule_fingerprint"],
                decision=decision_kind, record_keys=record_keys,
            )

            def operation(connection):
                current_case = connection.execute(
                    """SELECT current_revision FROM fifo_cost_transition_cases
                       WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                         AND store_id=? AND sku=? AND product_id IS ? AND offer_id IS ?""",
                    (
                        session["case_id"], FifoCostBatchSupplyStore._digest(scope.owner_id),
                        tenant["tenant_fingerprint"], scope.store_id, scope.sku,
                        scope.product_id, scope.offer_id,
                    ),
                ).fetchone()
                if current_case is None or current_case["current_revision"] != preview["case_revision"]:
                    return {"error": True, "code": "FIFO_BATCH_CASE_REVISION_CONFLICT"}
                scan_row = FifoCostBatchSupplyStore.read_scan_checkpoint(
                    connection, scope=scope, case_id=session["case_id"],
                    tenant_fingerprint=tenant["tenant_fingerprint"],
                    scan_id=preview["scan_id"],
                )
                if (
                    scan_row is None or scan_row["status"] != "PUBLISHED"
                    or scan_row["revision"] != preview["scan_revision"]
                    or scan_row["rule_id"] != preview["rule_id"]
                    or scan_row["rule_revision"] != preview["rule_revision"]
                    or scan_row["rule_fingerprint"] != preview["rule_fingerprint"]
                ):
                    return {"error": True, "code": "FIFO_BATCH_SCAN_STALE"}
                latest_scan = FifoCostBatchSupplyStore.read_latest_scan_checkpoint(
                    connection, scope=scope, case_id=session["case_id"],
                    tenant_fingerprint=tenant["tenant_fingerprint"],
                )
                if (
                    latest_scan is None
                    or latest_scan["scan_id"] != preview["scan_id"]
                    or latest_scan["revision"] != preview["scan_revision"]
                    or latest_scan["status"] != "PUBLISHED"
                ):
                    return {"error": True, "code": "FIFO_BATCH_SCAN_STALE"}
                current_set = FifoCostBatchSupplyStore.read_scan_candidate_page(
                    connection, scope=scope, case_id=session["case_id"],
                    tenant_fingerprint=tenant["tenant_fingerprint"],
                    scan_id=preview["scan_id"], limit=1,
                )
                if (
                    current_set.get("error")
                    or current_set.get("candidate_set_fingerprint")
                    != preview["candidate_set_fingerprint"]
                    or current_set.get("stored_candidate_set_fingerprint")
                    != preview["candidate_set_fingerprint"]
                ):
                    return {"error": True, "code": "FIFO_BATCH_SCAN_STALE"}
                selected = FifoCostBatchSupplyStore.read_scan_candidate_page(
                    connection, scope=scope, case_id=session["case_id"],
                    tenant_fingerprint=tenant["tenant_fingerprint"],
                    scan_id=preview["scan_id"], record_keys=record_keys,
                )
                current_pairs = tuple(sorted(
                    (item["record_key"], item["source_fingerprint"])
                    for item in selected.get("items", ())
                ))
                if len(current_pairs) != len(record_keys) or current_pairs != source_fingerprints:
                    return {"error": True, "code": "FIFO_BATCH_SCAN_STALE"}
                existing_decisions = FifoCostBatchSupplyStore.read_membership_decisions(
                    connection, scope=scope, case_id=session["case_id"],
                    tenant_fingerprint=tenant["tenant_fingerprint"], limit=20_000,
                )
                selected_keys = set(record_keys)
                overlapping = []
                for row in existing_decisions:
                    if (
                        row["rule_id"] != preview["rule_id"]
                        or row["rule_revision"] != preview["rule_revision"]
                    ):
                        continue
                    prior_keys = self._json_record_keys(row["record_keys_json"])
                    if selected_keys.intersection(prior_keys):
                        overlapping.append(row)
                if overlapping:
                    latest_time = max(row["confirmed_at"] for row in overlapping)
                    latest_decisions = [
                        row for row in overlapping if row["confirmed_at"] == latest_time
                    ]
                    latest_outcomes = {row["decision"] for row in latest_decisions}
                    if len(latest_outcomes) > 1:
                        return {"error": True, "code": "FIFO_BATCH_DECISION_CONFLICT"}
                    if any(
                        row["membership_binding_fingerprint"] == binding
                        and row["decision"] == decision_kind.value
                        for row in latest_decisions
                    ):
                        return {"error": False, "code": "FIFO_BATCH_DECISION_ALREADY_CONFIRMED"}
                    predecessor = max(
                        latest_decisions,
                        key=lambda row: (row["decision_id"], row["revision"]),
                    )
                else:
                    latest_time = None
                    predecessor = None
                decision_time = confirmed_text
                if latest_time is not None:
                    if decision_time <= latest_time:
                        parsed = datetime.fromisoformat(latest_time.replace("Z", "+00:00"))
                        decision_time = (parsed + timedelta(microseconds=1)).astimezone(
                            timezone.utc,
                        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
                decision = BatchMembershipDecision(
                    decision_id="bmd_" + uuid4().hex,
                    revision=1, scope=scope, case_id=session["case_id"],
                    rule_id=preview["rule_id"],
                    rule_revision=preview["rule_revision"],
                    decision=decision_kind,
                    source=MembershipDecisionSource.OWNER_SELECTED_SET,
                    record_keys=record_keys,
                    relevant_source_fingerprints=source_fingerprints,
                    candidate_set_fingerprint=preview["candidate_set_fingerprint"],
                    membership_binding_fingerprint=binding,
                    idempotency_key="tg-bmd-" + uuid4().hex,
                    confirmed_at=decision_time,
                    previous_decision_ref=(
                        f"{predecessor['decision_id']}-r{predecessor['revision']}"
                        if predecessor is not None else None
                    ),
                )
                stored = FifoCostBatchSupplyStore.append_membership_decision(
                    connection, decision,
                    tenant_fingerprint=tenant["tenant_fingerprint"],
                    recorded_at=decision_time,
                )
                return stored

            return self.repository._run_transition_write(operation)
        except Exception:
            return {"error": True, "code": "FIFO_BATCH_DECISION_STORAGE_UNAVAILABLE"}

    @staticmethod
    def _json_record_keys(value):
        parsed = json.loads(value)
        if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
            raise ValueError("FIFO_BATCH_DECISION_RECORD_KEYS_INVALID")
        return tuple(parsed)

    @staticmethod
    def _safe_membership_error(code):
        return {
            "FIFO_BATCH_CASE_REVISION_CONFLICT": "Дело изменилось после просмотра. Откройте его заново; решение не сохранено.",
            "FIFO_BATCH_SCAN_STALE": "Состав поставок изменился после просмотра. Обновите его; решение не сохранено.",
            "FIFO_BATCH_SCAN_NOT_FOUND": "Проверка поставок больше недоступна. Обновите её.",
            "FIFO_BATCH_DECISION_CONFLICT": "Для этого набора уже сохранено противоположное решение. Нужна отдельная проверка владельца.",
            "FIFO_BATCH_DECISION_STORAGE_UNAVAILABLE": "Не удалось сохранить решение. Данные FIFO не изменены; попробуйте позже.",
            "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE": "Не удалось прочитать сохранённые данные поставок. Обновите поиск.",
            "FIFO_BATCH_SCAN_TENANT_SCOPE_UNAVAILABLE": "Не удалось подтвердить текущий магазин. Откройте карточку заново.",
            "FIFO_BATCH_READ_KEYS_INVALID": "Список выбранных строк устарел. Откройте его заново.",
            "FIFO_BATCH_DECISION_TIME_INVALID": "Не удалось подтвердить время записи. Решение не сохранено.",
        }.get(code, "Решение не сохранено: текущая проверка требует обновления или повторного просмотра.")

    @staticmethod
    def _candidate_quantity_text(value):
        return f"{value} шт." if type(value) is int else "неизвестно"

    def _show_rule_edit_guidance(self, runtime, owner, session):
        return self._card_return(runtime, owner,
            "Сохранённое правило нельзя переписывать задним числом. Для следующей цены откройте карточку этого SKU в разделе «Себестоимость FIFO» и нажмите «Новая себестоимость»: бот отдельно покажет дату границы и расчёт, а ставка сохранится только после вашего подтверждения. Если новая партия уже отправлялась до даты из предпросмотра, не подтверждайте её как текущую — для прошлой даты нужен отдельный сценарий исправления/пересчёта. Текущее правило, FIFO и прибыль не изменены. Чтобы уточнить принадлежность поставок первой даты, сначала сверьте конкретные поставки; изменений не сохранено.")

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
            "FIFO_BATCH_BUNDLE_UNAVAILABLE": "Состав одной из поставок временно недоступен. Поиск можно продолжить; эта поставка пока не считается проверенной.",
            "FIFO_BATCH_BUNDLE_REFERENCE_UNAVAILABLE": "Для части поставок Ozon не вернул ссылку на товарный состав. Такие поставки не показаны как пустые.",
            "FIFO_BATCH_BUNDLE_TOTAL_COUNT_CHANGED": "Во время чтения изменилось число строк в составе поставки. Эта поставка требует повторной проверки.",
            "FIFO_BATCH_BUNDLE_CURSOR_NOT_ADVANCING": "Ozon повторил страницу состава поставки. Эта поставка не считается полностью прочитанной.",
            "FIFO_BATCH_BUNDLE_SKU_MAPPING_CONFLICT": "Совпадение SKU с карточкой товара неоднозначно. Поставка не включена автоматически.",
            "FIFO_BATCH_BUNDLE_DUPLICATE_SKU_MAPPING": "В одной поставке найдено несколько строк выбранного SKU. Требуется ручная сверка состава.",
            "FIFO_BATCH_SUPPLY_MUTATED_DURING_SCAN": "Данные уже сохранённой поставки изменились во время чтения. Решение не сохранено.",
            "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE": "Не удалось проверить сохранённые строки поставок. Ozon не запрашивался, повторите позже.",
            "FIFO_BATCH_SCAN_REFERENCE_CONFLICT": "В сохранённых строках обнаружено противоречие. Обновите проверку перед выбором.",
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
