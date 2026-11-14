"""Telegram prompts for automatic FIFO batch rules and dated owner controls.

This adapter owns only transient interaction state. Automatic rules and owner
controls are persisted by their existing domain services and never alter FIFO
layers, allocations, or profit by themselves.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
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

    def __init__(self, rule_service, repository):
        self.rule_service = rule_service
        self.repository = repository

    def show_mode_choice(self, runtime, owner):
        session = runtime._sessions.get(owner)
        if not isinstance(session, dict):
            return runtime._stale()
        if session["case"].get("supply_total_mode") == "AUTO_FROM_SUPPLIES":
            return runtime._show_supply_stage(owner)
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
