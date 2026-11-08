"""Resumable owner-input flow for a FIFO late-entry transition case."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.fifo_cost_transition_contracts import (
    CostComponents,
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ReportType,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
    utc_now,
)
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramFifoCostTransitionRuntimeService:
    CALLBACK_PREFIX = "fifo_transition"
    TTL_SECONDS = 15 * 60
    MAX_SESSIONS = 256
    MAX_TICKETS = 1024
    _EDITABLE_STATES = frozenset({"DRAFT", "AWAITING_EVIDENCE"})

    def __init__(
        self, transition_service, history_service, report_import_service=None,
        *, monotonic_clock=monotonic, now_provider=None,
    ):
        self.transition_service = transition_service
        self.history_service = history_service
        self.report_import_service = report_import_service
        self._monotonic = monotonic_clock
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._sessions = {}
        self._tickets = {}
        self._lock = RLock()

    def start_new_case(
        self, user_id, identity, display_name, expected_revision, cost_input_mode,
    ):
        owner, tenant = self._identity(user_id)
        if owner is None or not tenant or not isinstance(identity, dict):
            return self._failure("Профиль магазина недоступен. Черновик не создан.")
        scoped_owner, scoped_store = split_store_tenant_scope(tenant)
        if scoped_store != identity.get("store_id"):
            return self._failure("Магазин изменился. Откройте SKU заново; черновик не создан.")
        try:
            mode = CostInputMode(
                cost_input_mode.value if isinstance(cost_input_mode, CostInputMode)
                else str(cost_input_mode)
            )
            current_history = self.history_service.get_sku_history(**identity)
        except (TypeError, ValueError):
            return self._failure("Не удалось проверить SKU. Черновик не создан.")
        if (
            not isinstance(current_history, dict)
            or current_history.get("error") is not False
            or current_history.get("revision") != expected_revision
            or current_history.get("queue_initialized") is not False
        ):
            return self._failure(
                "FIFO или карточка SKU изменилась. Откройте карточку заново; данные не изменены."
            )
        existing = self._find_active_case(identity)
        if existing is None:
            return self._failure(
                "Не удалось проверить сохранённые изменения. Новый черновик не создан."
            )
        if existing:
            case = existing[0]
            return self.resume_case(
                user_id,
                identity=identity,
                display_name=display_name,
                case_id=case["case_id"],
                expected_case_revision=case["case_revision"],
            )

        now = self._now()
        case_id = "case_" + uuid4().hex
        unknown_values = {
            field: {
                "reason_code": "SOURCE_PROOF_UNAVAILABLE",
                "source_kind": EvidenceSourceKind.OWNER_INPUT.value,
            }
            for field in (
                "dispatch_date", "old_unit_cost_rub", "new_unit_cost_rub",
                "owner_old_home_units", "owner_old_transit_units",
                "new_home_quantity", "declared_shipped_units",
            )
        }
        unknown_values = {
            field: UnknownValue(
                TransitionReasonCode(value["reason_code"]),
                EvidenceSourceKind(value["source_kind"]),
            )
            for field, value in unknown_values.items()
        }
        try:
            scope = ScopeIdentity(
                owner_id=scoped_owner,
                store_id=identity["store_id"],
                product_id=identity.get("product_id"),
                offer_id=identity.get("offer_id"),
                sku=identity["sku"],
            )
            fingerprint = self._fingerprint(
                "fifo-transition-ui-create-v1", owner, tenant,
                identity["store_id"], identity["sku"], mode.value,
            )
            metadata = TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
                completeness=EvidenceCompleteness.PARTIAL,
                source_fingerprint=fingerprint,
            )
            case = TransitionCase(
                metadata=metadata,
                case_id=case_id,
                case_revision=1,
                state=TransitionState.DRAFT,
                created_at=now,
                updated_at=now,
                dispatch_date=None,
                old_unit_cost_rub=None,
                new_unit_cost_rub=None,
                cost_input_mode=mode,
                cost_components=None,
                owner_old_home_units=None,
                owner_old_transit_units=None,
                new_home_quantity=None,
                declared_shipped_units=None,
                unknown_values=unknown_values,
            )
        except (TypeError, ValueError, KeyError):
            return self._failure("Не удалось подготовить черновик. FIFO не изменена.")
        created = self.transition_service.create_case(
            case=case,
            idempotency_key="tg-create-" + uuid4().hex,
        )
        if not isinstance(created, dict) or created.get("error") is not False:
            # A duplicate callback can arrive after the first create committed.
            existing = self._find_active_case(identity)
            if existing:
                item = existing[0]
                return self.resume_case(
                    user_id,
                    identity=identity,
                    display_name=display_name,
                    case_id=item["case_id"],
                    expected_case_revision=item["case_revision"],
                )
            return self._failure(
                "Не удалось сохранить сведения о партии. Проверьте незавершённые изменения; FIFO не изменена."
            )
        if not self._set_session(
            owner, tenant, identity, display_name, case_id, created["case_revision"],
        ):
            return self._failure("Черновик сохранён, но не удалось его перечитать. Откройте список изменений.")
        return self._prompt_next(owner)

    def resume_case(
        self, user_id, *, identity, display_name, case_id,
        expected_case_revision,
    ):
        owner, tenant = self._identity(user_id)
        if owner is None or not tenant or not isinstance(identity, dict):
            return self._failure("Профиль магазина недоступен. Черновик не открыт.")
        case = self._read_case(case_id, identity)
        if (
            not isinstance(case, dict) or case.get("error") is not False
            or case.get("case_revision") != expected_case_revision
            or case.get("state") not in self._EDITABLE_STATES
            or not self._case_matches_identity(case.get("case"), identity)
        ):
            return self._failure(
                "Черновик устарел или принадлежит другому SKU. Откройте список изменений заново."
            )
        if not self._set_session(
            owner, tenant, identity, display_name, case_id,
            case["case_revision"],
        ):
            return self._failure("Черновик не удалось загрузить в мастер. Откройте список изменений заново.")
        return self._prompt_next(owner)

    def handle_text(self, user_id, text):
        owner, tenant = self._identity(user_id)
        if owner is None:
            return {"error": False, "handled": False, "read_only_ozon": True}
        with self._lock:
            self._purge(self._now_monotonic())
            session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return {"error": False, "handled": False, "read_only_ozon": True}
        if session["tenant"] != tenant:
            self.clear_pending(user_id)
            return self._failure(
                "Активный магазин изменился. Текст не записан; откройте нужный черновик заново."
            )
        if session.get("candidate_pending"):
            return self._result(
                "Проверьте введённое значение и подтвердите его кнопкой. Другой текст не сохранён.",
                keyboard=self._field_confirmation_keyboard(session["candidate_token"]),
            )
        if session.get("step") in {"supply_reference_kind", "supply_reference", "supply_quantity"}:
            return self._handle_supply_text(owner, session, text)
        return self._handle_field_text(owner, session, text)

    def handle_callback(self, user_id, callback):
        owner, tenant = self._identity(user_id)
        parts = str(callback or "").split(":")
        if len(parts) != 3 or parts[0] != self.CALLBACK_PREFIX:
            return {"error": False, "handled": False, "read_only_ozon": True}
        action, token = parts[1:]
        if owner is None or not self._valid_token(token):
            return self._stale()
        now = self._now_monotonic()
        with self._lock:
            self._purge(now)
            ticket = self._tickets.get((owner, token))
            if isinstance(ticket, dict) and ticket.get("confirmed_result") is not None:
                return dict(ticket["confirmed_result"])
        if (
            not isinstance(ticket, dict) or ticket.get("tenant") != tenant
            or ticket.get("action") != action
        ):
            return self._stale()
        session = self._sessions.get(owner)
        if not isinstance(session, dict) or not self._ticket_matches_session(ticket, session):
            return self._stale()
        case = self._read_case(session["case_id"], session["identity"])
        if (
            not isinstance(case, dict) or case.get("error") is not False
            or case.get("state") not in self._EDITABLE_STATES
        ):
            return self._stale()
        if case.get("case_revision") != session["case_revision"]:
            if action not in {
                "finish", "supply", "skip_supplies", "report_turnover",
                "report_stock", "reports",
            }:
                return self._stale()
            self._refresh_session(session, case)
        if action == "confirm_field":
            return self._confirm_field(owner, session, ticket)
        if action == "cancel_field":
            session.pop("candidate_pending", None)
            session.pop("candidate_token", None)
            session.pop("candidate", None)
            return self._prompt_next(owner)
        if action == "supply":
            session["step"] = "supply_reference_kind"
            return self._supply_kind_prompt(owner)
        if action == "supply_order" or action == "supply_supply":
            session["reference_kind"] = "ORDER" if action == "supply_order" else "SUPPLY"
            session["step"] = "supply_reference"
            return self._result(
                "Введите номер заявки или ID поставки цифрами. Он будет использоваться только для поиска и сохранится зашифрованным, если ключ доступен."
            )
        if action == "skip_supplies":
            session.pop("step", None)
            return self._documents_prompt(owner)
        if action == "confirm_supply":
            return self._confirm_supply(owner, session, ticket)
        if action in {"report_turnover", "report_stock"}:
            return self._start_report_import(user_id, session, action)
        if action == "reports":
            return self._documents_prompt(owner)
        if action == "finish":
            return self._show_summary(owner)
        if action == "cancel_case":
            cancel_callback = self._issue_ticket(owner, session, "confirm_cancel")
            back_callback = self._issue_ticket(owner, session, "finish")
            return self._result(
                "Отменить сохранённые сведения о партии? FIFO и текущая себестоимость не изменятся.",
                keyboard=self._keyboard([
                    {"text": "✅ Подтвердить отмену", "callback": cancel_callback},
                    {"text": "↩️ Назад", "callback": back_callback},
                ]),
            )
        if action == "confirm_cancel":
            result = self.transition_service.cancel_case(
                case_id=session["case_id"], **session["identity"],
                expected_revision=session["case_revision"],
                idempotency_key="tg-cancel-" + uuid4().hex,
            )
            if not isinstance(result, dict) or result.get("error") is not False:
                return self._failure("Не удалось отменить изменение: данные могли измениться. Откройте список заново.")
            self.clear_pending(user_id)
            return self._result("Изменение отменено. Запись сохранена в истории; FIFO и прибыль не изменились.")
        return self._stale()

    def clear_pending(self, user_id):
        owner, _tenant = self._identity(user_id)
        if owner is None:
            return
        with self._lock:
            self._sessions.pop(owner, None)
            for key in [key for key in self._tickets if key[0] == owner]:
                self._tickets.pop(key, None)

    def _handle_field_text(self, owner, session, text):
        step = self._next_field(session["case"])
        if step is None:
            return self._show_supply_stage(owner)
        try:
            if step == "old_unit_cost_rub":
                updates = {step: self._money(text, allow_zero=False)}
                label = "Старая итоговая себестоимость"
                shown = f"{updates[step]:.2f} ₽/шт."
            elif step == "new_unit_cost_rub" and session["case"]["cost_input_mode"] == "TOTAL_LANDED":
                updates = {step: self._money(text, allow_zero=False)}
                label = "Новая итоговая себестоимость"
                shown = f"{updates[step]:.2f} ₽/шт."
            elif step == "new_unit_cost_rub":
                return self._handle_component_text(owner, session, text)
            elif step == "dispatch_date":
                updates = {step: self._parse_date(text)}
                label = "Дата первой отправки новой партии"
                shown = updates[step]
            elif step in {"owner_old_home_units", "owner_old_transit_units"}:
                updates = {step: self._quantity(text, allow_zero=True)}
                label = (
                    "Старый остаток дома"
                    if step == "owner_old_home_units" else "Старый товар в пути"
                )
                shown = f"{updates[step]} шт."
            elif step == "declared_shipped_units":
                updates = {step: self._quantity(text, allow_zero=False)}
                label = "Всего отправлено из новой партии"
                shown = f"{updates[step]} шт."
            else:
                return self._show_summary(owner)
        except (InvalidOperation, TypeError, ValueError):
            return self._input_error(step)
        return self._stage_field_confirmation(owner, session, updates, label, shown)

    def _handle_component_text(self, owner, session, text):
        component_fields = (
            ("purchase_cost_rub", "Закупочная стоимость"),
            ("delivery_cost_rub", "Доставка до вас"),
            ("packaging_cost_rub", "Упаковка"),
        )
        values = list(session.get("component_values", ()))
        index = len(values)
        if index >= len(component_fields):
            return self._result(
                "Проверьте три компонента кнопкой ниже. Новый текст не сохранён.",
                keyboard=self._field_confirmation_keyboard(session["candidate_token"]),
            )
        try:
            values.append(self._money(text, allow_zero=True))
        except (InvalidOperation, TypeError, ValueError):
            return self._input_error("new_unit_cost_rub")
        if len(values) < len(component_fields):
            session["component_values"] = values
            session["step"] = "components"
            return self._result(f"{component_fields[len(values)][1]} за одну единицу, в ₽:")
        components = CostComponents(
            purchase_cost_rub=values[0],
            delivery_cost_rub=values[1],
            packaging_cost_rub=values[2],
        )
        if components.total_rub <= 0:
            session["component_values"] = []
            return self._result(
                "Итоговая себестоимость должна быть больше нуля. Введите закупочную стоимость заново:"
            )
        updates = {
            "new_unit_cost_rub": components.total_rub,
            "cost_components": components,
        }
        session.pop("component_values", None)
        return self._stage_field_confirmation(
            owner, session, updates, "Новая итоговая себестоимость по компонентам",
            f"Закупка {components.purchase_cost_rub:.2f} + доставка {components.delivery_cost_rub:.2f} "
            f"+ упаковка {components.packaging_cost_rub:.2f} = {components.total_rub:.2f} ₽/шт.",
        )

    def _stage_field_confirmation(self, owner, session, updates, label, shown):
        callback = self._issue_ticket(owner, session, "confirm_field")
        token = callback.rsplit(":", 1)[-1]
        ticket = self._ticket(owner, token)
        ticket["updates"] = updates
        ticket["idempotency_key"] = "tg-input-" + uuid4().hex
        session["candidate_pending"] = True
        session["candidate_token"] = token
        session["candidate"] = {"updates": updates, "label": label, "shown": shown}
        return self._result(
            f"Проверьте ввод: {label} — {shown}\n\nПодтверждение сохранит только сведения в черновике; текущая FIFO и прибыль не изменятся.",
            keyboard=self._field_confirmation_keyboard(token),
        )

    def _confirm_field(self, owner, session, ticket):
        if not session.get("candidate_pending") or session.get("candidate_token") != ticket.get("token"):
            return self._stale()
        updates = ticket.get("updates")
        if not isinstance(updates, dict):
            return self._stale()
        next_state = (
            TransitionState.AWAITING_EVIDENCE
            if self._next_field(session["case"], overrides=updates) is None
            else TransitionState(session["case"]["state"])
        )
        saved = self.transition_service.update_owner_inputs(
            case_id=session["case_id"], **session["identity"],
            expected_revision=session["case_revision"], updates=updates,
            idempotency_key=ticket["idempotency_key"], state=next_state,
        )
        if not isinstance(saved, dict) or saved.get("error") is not False:
            return self._failure(
                "Сведения не сохранены: черновик изменился или ввод не прошёл проверку. Откройте его заново."
            )
        case = self._read_case(session["case_id"], session["identity"])
        if not isinstance(case, dict) or case.get("error") is not False:
            return self._failure("Сведения сохранены, но карточку не удалось обновить. Откройте список изменений.")
        self._refresh_session(session, case)
        session.pop("candidate_pending", None)
        session.pop("candidate_token", None)
        session.pop("candidate", None)
        session.pop("component_values", None)
        result = self._prompt_next(owner)
        ticket["confirmed_result"] = dict(result)
        return result

    def _handle_supply_text(self, owner, session, text):
        step = session["step"]
        if step == "supply_reference":
            reference = self._reference(text)
            if reference is None:
                return self._result("Введите только цифры номера заявки или ID поставки.")
            session["reference_id"] = reference
            session["step"] = "supply_quantity"
            return self._result("Введите количество единиц в этой поставке:")
        if step == "supply_quantity":
            try:
                quantity = self._quantity(text, allow_zero=False)
            except ValueError:
                return self._result("Введите положительное целое количество единиц.")
            callback = self._issue_ticket(owner, session, "confirm_supply")
            token = callback.rsplit(":", 1)[-1]
            ticket = self._ticket(owner, token)
            ticket.update({
                "reference_kind": session.get("reference_kind"),
                "reference_id": session.get("reference_id"),
                "declared_shipped_units": quantity,
                "idempotency_key": "tg-supply-" + uuid4().hex,
            })
            session["candidate_pending"] = True
            session["candidate_token"] = token
            return self._result(
                f"Добавить {quantity} шт. как отдельную поставку типа {ticket['reference_kind']}? "
                f"Номер заканчивается на …{ticket['reference_id'][-4:]}.",
                keyboard=self._field_confirmation_keyboard(token, confirm_action="confirm_supply"),
            )
        return self._supply_kind_prompt(owner)

    def _confirm_supply(self, owner, session, ticket):
        if session.get("candidate_token") != ticket.get("token") or not session.get("candidate_pending"):
            return self._stale()
        result = self.transition_service.declare_supply(
            case_id=session["case_id"], **session["identity"],
            reference_kind=ticket["reference_kind"],
            reference_id=ticket["reference_id"],
            declared_shipped_units=ticket["declared_shipped_units"],
            dispatch_date=session["case"].get("dispatch_date"),
            expected_case_revision=session["case_revision"],
            idempotency_key=ticket["idempotency_key"],
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._failure(
                "Поставка не добавлена: проверьте номер, количество и общий объявленный итог. Другие сведения сохранены."
            )
        case = self._read_case(session["case_id"], session["identity"])
        if not isinstance(case, dict) or case.get("error") is not False:
            return self._failure("Поставка сохранена, но список не обновился. Откройте черновик заново.")
        self._refresh_session(session, case)
        session.pop("candidate_pending", None)
        session.pop("candidate_token", None)
        session.pop("reference_id", None)
        session.pop("reference_kind", None)
        result = self._show_supply_stage(owner)
        ticket["confirmed_result"] = dict(result)
        return result

    def _start_report_import(self, user_id, session, action):
        if self.report_import_service is None:
            return self._failure("Импорт отчёта недоступен. Сведения о партии сохранены.")
        scope_payload = session["case"]["metadata"]["scope"]
        owner, _store = split_store_tenant_scope(session["tenant"])
        try:
            scope = ScopeIdentity(
                owner_id=owner,
                store_id=scope_payload["store_id"],
                product_id=scope_payload.get("product_id"),
                offer_id=scope_payload.get("offer_id"),
                sku=scope_payload["sku"],
            )
            report_type = (
                ReportType.TURNOVER if action == "report_turnover"
                else ReportType.STOCK_MANAGEMENT
            )
        except (TypeError, ValueError, KeyError):
            return self._failure("Не удалось связать отчёт с текущим SKU. Данные дела не изменены.")
        return self.report_import_service.create_selection_callback(
            user_id=user_id,
            case_id=session["case_id"],
            scope=scope,
            report_type=report_type,
        )

    def _prompt_next(self, owner):
        session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return self._stale()
        if session.get("candidate_pending"):
            return self._result(
                "Проверьте введённое значение и подтвердите его кнопкой.",
                keyboard=self._field_confirmation_keyboard(session["candidate_token"]),
            )
        step = self._next_field(session["case"])
        if step is None:
            return self._show_supply_stage(owner)
        session["step"] = step
        prompt = {
            "old_unit_cost_rub": (
                "Введите старую итоговую себестоимость одной упаковки в ₽. "
                "Это справочное значение владельца; существующие старые FIFO-слои оно не заменит."
            ),
            "new_unit_cost_rub": (
                "Введите новую итоговую себестоимость одной упаковки в ₽."
                if session["case"]["cost_input_mode"] == "TOTAL_LANDED"
                else "Введите закупочную стоимость одной новой упаковки в ₽:"
            ),
            "dispatch_date": "Введите дату первой отправки новой партии в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД:",
            "owner_old_home_units": "Сколько единиц старой партии оставалось дома на дату первой отправки? Если не было — введите 0:",
            "owner_old_transit_units": "Сколько единиц старой партии уже было в пути на дату первой отправки? Если не было — введите 0:",
            "declared_shipped_units": "Введите известное общее количество единиц новой партии, отправленных в Ozon:",
        }[step]
        if step == "new_unit_cost_rub" and session["case"]["cost_input_mode"] == "COMPONENTS":
            session["component_values"] = []
        return self._result(prompt)

    def _show_supply_stage(self, owner):
        session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return self._stale()
        manifest = self.transition_service.get_supply_manifest(
            case_id=session["case_id"], **session["identity"],
        )
        if not isinstance(manifest, dict) or manifest.get("error") is not False:
            return self._failure("Поставки временно не удалось прочитать. Ввод сохранён.")
        session["step"] = "supplies"
        owner_total = manifest.get("owner_declared_total")
        known = manifest.get("known_assigned_units")
        undistributed = manifest.get("undistributed_units")
        text = (
            f"Сведения о партии сохранены · {session['display_name']} · SKU {session['identity']['sku']}\n"
            f"Новая стоимость: {self._format_cost(session['case'])} ₽/шт.\n"
            f"Дата отправки: {session['case'].get('dispatch_date')}\n"
            f"Старая партия дома: {session['case'].get('owner_old_home_units')} шт.; "
            f"в пути: {session['case'].get('owner_old_transit_units')} шт.\n"
            f"Всего новой партии: {owner_total} шт.; по отдельным поставкам: {known} шт."
        )
        if undistributed is not None and undistributed > 0:
            text += f"; не распределено по поставкам: {undistributed} шт."
        text += (
            "\nКоличество новой партии, оставшейся дома, не спрашивается и остаётся неизвестным. "
            "Эти сведения не меняют FIFO или фактическую прибыль."
        )
        buttons = [
            {"text": "📦 Добавить поставку", "callback": self._issue_ticket(owner, session, "supply")},
            {"text": "Продолжить без списка поставок", "callback": self._issue_ticket(owner, session, "skip_supplies")},
        ]
        return self._result(text, keyboard=self._keyboard(buttons))

    def _supply_kind_prompt(self, owner):
        session = self._sessions[owner]
        return self._result(
            "Какой идентификатор хотите привязать? Заявка на поставку или конкретная поставка:",
            keyboard=self._keyboard([
                {"text": "Номер заявки", "callback": self._issue_ticket(owner, session, "supply_order")},
                {"text": "ID поставки", "callback": self._issue_ticket(owner, session, "supply_supply")},
            ]),
        )

    def _documents_prompt(self, owner):
        session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return self._stale()
        session["step"] = "documents"
        buttons = [
            {"text": "📄 Добавить оборотную ведомость", "callback": self._issue_ticket(owner, session, "report_turnover")},
            {"text": "📦 Добавить отчёт по остаткам", "callback": self._issue_ticket(owner, session, "report_stock")},
            {"text": "Продолжить без отчётов", "callback": self._issue_ticket(owner, session, "finish")},
        ]
        return self._result(
            "Теперь можно добавить подтверждения: оборотную ведомость и отчёт по остаткам. "
            "Периоды файлов бот попросит подтвердить отдельно; отсутствие отчёта не удаляет уже введённые сведения.",
            keyboard=self._keyboard(buttons),
        )

    def _show_summary(self, owner):
        session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return self._stale()
        case = self._read_case(session["case_id"], session["identity"])
        if not isinstance(case, dict) or case.get("error") is not False:
            return self._failure("Не удалось открыть сохранённый черновик. Данные не изменены.")
        self._refresh_session(session, case)
        manifest = self.transition_service.get_supply_manifest(
            case_id=session["case_id"], **session["identity"],
        )
        evidence = self.transition_service.repository.read_transition_evidence(
            case_id=session["case_id"], **session["identity"],
            kind="REPORT", limit=100,
        )
        report_count = (
            len(evidence.get("items", ()))
            if isinstance(evidence, dict) and evidence.get("error") is False else None
        )
        text = (
            f"🧾 Черновик поздней партии · {session['display_name']} · SKU {session['identity']['sku']}\n"
            f"Состояние: {case['state']} · редакция {case['case_revision']}\n"
            f"Старая стоимость: {case['case'].get('old_unit_cost_rub')} ₽/шт. (ввод владельца; старые FIFO-слои не заменены)\n"
            f"Новая стоимость: {self._format_cost(case['case'])} ₽/шт.\n"
            f"Дата отправки: {case['case'].get('dispatch_date')}\n"
            f"Старый остаток дома/в пути: {case['case'].get('owner_old_home_units')} / {case['case'].get('owner_old_transit_units')} шт.\n"
            f"Отправлено новой партии: {case['case'].get('declared_shipped_units')} шт.; "
            f"количество новой партии дома: неизвестно\n"
            f"Поставки: {manifest.get('known_assigned_units') if isinstance(manifest, dict) else 'нет данных'} из "
            f"{manifest.get('owner_declared_total') if isinstance(manifest, dict) else 'нет данных'} шт.; "
            f"отчётов сохранено: {report_count if report_count is not None else 'не удалось прочитать'}\n\n"
            "Это сохранённые сведения для сверки. История FIFO, текущая себестоимость и прибыль не применялись."
        )
        buttons = [
            {"text": "📦 Поставки", "callback": self._issue_ticket(owner, session, "supply")},
            {"text": "📄 Добавить отчёты", "callback": self._issue_ticket(owner, session, "reports")},
            {"text": "✖️ Отменить изменение", "callback": self._issue_ticket(owner, session, "cancel_case")},
        ]
        return self._result(text, keyboard=self._keyboard(buttons))

    def _issue_ticket(self, owner, session, action):
        token = uuid4().hex[:12]
        now = self._now_monotonic()
        with self._lock:
            self._purge(now)
            self._tickets[(owner, token)] = {
                "token": token,
                "tenant": session["tenant"],
                "case_id": session["case_id"],
                "identity": dict(session["identity"]),
                "case_revision": session["case_revision"],
                "action": action,
                "expires_at": now + self.TTL_SECONDS,
            }
            while len(self._tickets) > self.MAX_TICKETS:
                oldest = min(self._tickets, key=lambda key: self._tickets[key]["expires_at"])
                self._tickets.pop(oldest, None)
        return f"{self.CALLBACK_PREFIX}:{action}:{token}"

    def _ticket(self, owner, token):
        return self._tickets[(owner, token)]

    def _set_session(self, owner, tenant, identity, display_name, case_id, revision):
        now = self._now_monotonic()
        session = {
            "tenant": tenant,
            "identity": dict(identity),
            "display_name": str(display_name or "Товар"),
            "case_id": case_id,
            "case_revision": revision,
            "expires_at": now + self.TTL_SECONDS,
        }
        case = self._read_case(case_id, identity)
        if not isinstance(case, dict) or case.get("error") is not False:
            return False
        self._refresh_session(session, case)
        with self._lock:
            self._purge(now)
            self._sessions[owner] = session
            while len(self._sessions) > self.MAX_SESSIONS:
                oldest = min(self._sessions, key=lambda key: self._sessions[key]["expires_at"])
                self._sessions.pop(oldest, None)
        return True

    def _read_case(self, case_id, identity):
        return self.transition_service.get_case(case_id=case_id, **identity)

    @staticmethod
    def _case_matches_identity(payload, identity):
        if not isinstance(payload, dict):
            return False
        metadata = payload.get("metadata")
        scope = metadata.get("scope") if isinstance(metadata, dict) else None
        return isinstance(scope, dict) and all(
            scope.get(key) == identity.get(key)
            for key in ("store_id", "product_id", "offer_id", "sku")
        )

    def _find_active_case(self, identity):
        result = self.transition_service.list_cases(
            store_id=identity["store_id"], sku=identity["sku"],
            states=("DRAFT", "AWAITING_EVIDENCE"), limit=20,
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return None
        return [
            item for item in result.get("cases", ())
            if isinstance(item, dict) and self._case_matches_identity(item.get("case"), identity)
        ]

    def _refresh_session(self, session, case_result):
        session["case_revision"] = case_result["case_revision"]
        session["case"] = case_result["case"]
        session["state"] = case_result["state"]
        session["expires_at"] = self._now_monotonic() + self.TTL_SECONDS

    def _refresh_session_revision(self, session, revision):
        session["case_revision"] = revision

    def _next_field(self, case, overrides=None):
        if not isinstance(case, dict):
            return "old_unit_cost_rub"
        values = dict(case)
        if isinstance(overrides, dict):
            values.update(overrides)
        for field in (
            "old_unit_cost_rub", "new_unit_cost_rub", "dispatch_date",
            "owner_old_home_units", "owner_old_transit_units", "declared_shipped_units",
        ):
            if values.get(field) is None:
                return field
        return None

    @staticmethod
    def _format_cost(case):
        if not isinstance(case, dict):
            return "не указана"
        value = case.get("new_unit_cost_rub")
        return "не указана" if value is None else f"{Decimal(str(value)):.2f}"

    @staticmethod
    def _money(value, *, allow_zero):
        if not isinstance(value, str):
            raise ValueError("money invalid")
        text = value.replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
        amount = Decimal(text)
        if not amount.is_finite() or amount < (Decimal("0") if allow_zero else Decimal("0.01")):
            raise ValueError("money invalid")
        if amount > Decimal("1000000000"):
            raise ValueError("money invalid")
        return amount

    @staticmethod
    def _quantity(value, *, allow_zero):
        if not isinstance(value, str):
            raise ValueError("quantity invalid")
        text = value.strip()
        if not text.isascii() or not text.isdigit():
            raise ValueError("quantity invalid")
        quantity = int(text)
        if quantity < (0 if allow_zero else 1) or quantity > 1_000_000:
            raise ValueError("quantity invalid")
        return quantity

    @staticmethod
    def _parse_date(value):
        if not isinstance(value, str):
            raise ValueError("date invalid")
        text = value.strip()
        try:
            parsed = date.fromisoformat(text) if len(text) == 10 and text[4] == "-" else date(
                int(text[6:10]), int(text[3:5]), int(text[0:2]),
            )
        except (TypeError, ValueError):
            raise ValueError("date invalid")
        return parsed.isoformat()

    @staticmethod
    def _reference(value):
        if isinstance(value, bool):
            return None
        text = str(value or "").strip()
        if not text.isascii() or not text.isdigit() or len(text) > 40 or int(text) <= 0:
            return None
        return str(int(text))

    def _input_error(self, step):
        messages = {
            "old_unit_cost_rub": "Введите положительную сумму в ₽, например 21 или 21,00.",
            "new_unit_cost_rub": "Введите сумму в ₽; компоненты могут быть нулевыми, итоговая стоимость должна быть больше нуля.",
            "dispatch_date": "Дата не распознана. Используйте ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.",
            "owner_old_home_units": "Введите целое число от 0 до 1 000 000.",
            "owner_old_transit_units": "Введите целое число от 0 до 1 000 000.",
            "declared_shipped_units": "Введите положительное целое число до 1 000 000.",
        }
        return self._result(messages.get(step, "Проверьте формат ввода."))

    def _field_confirmation_keyboard(self, token, *, confirm_action="confirm_field"):
        return self._keyboard([
            {"text": "✅ Подтвердить и сохранить", "callback": f"{self.CALLBACK_PREFIX}:{confirm_action}:{token}"},
            {"text": "↩️ Отменить ввод", "callback": f"{self.CALLBACK_PREFIX}:cancel_field:{token}"},
        ])

    @staticmethod
    def _keyboard(buttons):
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    def _result(self, message, *, keyboard=None):
        result = {
            "error": False,
            "handled": True,
            "message": message,
            "read_only_ozon": True,
        }
        if keyboard is not None:
            result["keyboard"] = keyboard
        return result

    def _failure(self, message):
        return {
            "error": True,
            "handled": True,
            "message": message,
            "read_only_ozon": True,
        }

    def _stale(self):
        return self._failure("Кнопка устарела или не относится к этому магазину. Откройте незавершённые изменения заново.")

    def _identity(self, user_id):
        if user_id is None or isinstance(user_id, bool):
            return None, ""
        owner = str(user_id).strip()
        try:
            tenant = str(get_current_tenant_user_id() or "").strip()
        except Exception:
            tenant = ""
        return (owner if owner and len(owner) <= 128 else None), tenant

    @staticmethod
    def _valid_token(token):
        return isinstance(token, str) and len(token) == 12 and token.isascii() and token.isalnum()

    def _ticket_matches_session(self, ticket, session):
        return (
            ticket.get("case_id") == session.get("case_id")
            and ticket.get("tenant") == session.get("tenant")
            and ticket.get("case_revision") == session.get("case_revision")
            and ticket.get("identity") == session.get("identity")
        )

    def _now(self):
        return utc_now(self._now_provider)

    def _now_monotonic(self):
        return self._monotonic()

    @staticmethod
    def _fingerprint(*parts):
        import hashlib
        return hashlib.sha256("\0".join(map(str, parts)).encode("utf-8")).hexdigest()

    def _purge(self, now):
        for mapping in (self._sessions, self._tickets):
            for key, value in list(mapping.items()):
                if value.get("expires_at", 0) <= now:
                    mapping.pop(key, None)
