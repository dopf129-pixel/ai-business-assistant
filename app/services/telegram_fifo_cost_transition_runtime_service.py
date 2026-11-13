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
    SUPPLY_REFRESH_PAGE_SIZE = 8
    _EDITABLE_STATES = frozenset({"DRAFT", "AWAITING_EVIDENCE"})
    _READY_READ_ACTIONS = frozenset({
        "finish", "check_readiness", "view_recalculation",
        "apply_transition", "confirm_apply",
    })

    def __init__(
        self, transition_service, history_service, report_import_service=None,
        *, review_service=None, supply_refresh_service=None,
        apply_service=None, cache_invalidator=None,
        monotonic_clock=monotonic, now_provider=None,
    ):
        self.transition_service = transition_service
        self.history_service = history_service
        self.report_import_service = report_import_service
        self.review_service = review_service
        self.supply_refresh_service = supply_refresh_service
        self.apply_service = apply_service
        self.cache_invalidator = cache_invalidator
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
            or case.get("state") not in self._EDITABLE_STATES | {"READY_TO_CONFIRM"}
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
        if case.get("state") == "READY_TO_CONFIRM":
            # A sealed READY preview is immutable. After restart, reopen its
            # summary so the owner can inspect/reconfirm it; never resume the
            # editable field wizard for a non-editable case.
            return self._show_summary(owner)
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
        if session.get("step") == "refresh_reference":
            return self._handle_refresh_reference(owner, session, text)
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
            or (
                case.get("state") not in self._EDITABLE_STATES
                and not (
                    case.get("state") == "READY_TO_CONFIRM"
                    and action in self._READY_READ_ACTIONS
                )
            )
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
        if action == "refresh_supply_select":
            if self.supply_refresh_service is None:
                return self._failure("Обновление поставок временно недоступно; сохранённые сведения не изменены.")
            declaration_id = ticket.get("declaration_id")
            if not isinstance(declaration_id, str) or not 8 <= len(declaration_id) <= 96:
                return self._stale()
            session["refresh_declaration_id"] = declaration_id
            session.pop("refresh_reference_id", None)
            session.pop("refresh_continuation_token", None)
            session["step"] = "refresh_reference"
            return self._result("Введите ID выбранной конкретной поставки для точечного обновления. ID не будет показан в ответе или сохранён повторно.")
        if action == "continue_supply_refresh":
            if self.supply_refresh_service is None or not session.get("refresh_reference_id"):
                return self._failure("Продолжение истекло. Выберите поставку и введите её ID ещё раз.")
            return self._run_supply_refresh(owner, session)
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
        if action == "check_readiness":
            return self._show_readiness(owner)
        if action == "view_recalculation":
            return self._show_recalculation(owner)
        if action == "apply_transition":
            return self._confirm_apply_prompt(user_id, owner, session)
        if action == "confirm_apply":
            return self._apply_transition(user_id, owner, session, ticket)
        if action == "refresh_supplies":
            return self._refresh_supplies_prompt(owner, page=0)
        if action == "refresh_supplies_page":
            page = ticket.get("page")
            if type(page) is not int or page < 0:
                return self._stale()
            return self._refresh_supplies_prompt(owner, page=page)
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

    def _handle_refresh_reference(self, owner, session, text):
        reference = self._reference(text)
        if reference is None:
            return self._result("Введите только цифры ID конкретной поставки.")
        scoped_owner, _store = split_store_tenant_scope(session["tenant"])
        matched = self.transition_service.supply_declaration_matches_reference(
            case_id=session["case_id"], declaration_id=session.get("refresh_declaration_id"),
            owner_id=scoped_owner, store_id=session["identity"]["store_id"],
            product_id=session["identity"].get("product_id"),
            offer_id=session["identity"].get("offer_id"),
            sku=session["identity"]["sku"], reference_id=reference,
        )
        if not matched:
            return self._result(
                "ID не совпадает с выбранной поставкой либо ключ проверки недоступен. "
                "Ozon не запрашивался; попробуйте ещё раз или вернитесь к делу."
            )
        session["refresh_reference_id"] = reference
        session.pop("step", None)
        return self._run_supply_refresh(owner, session)

    def _run_supply_refresh(self, owner, session):
        try:
            result = self.supply_refresh_service.refresh(
                case_id=session["case_id"],
                declaration_id=session["refresh_declaration_id"],
                reference_id=session["refresh_reference_id"],
                **session["identity"],
                expected_case_revision=session["case_revision"],
                continuation_token=session.get("refresh_continuation_token"),
            )
        except Exception:
            return self._failure("Не удалось обновить поставку. Черновик сохранён; повторите попытку позже.")
        if not hasattr(result, "status"):
            return self._failure("Источник не вернул проверяемый результат. Сохранённые сведения не изменены.")
        session["refresh_continuation_token"] = result.continuation_token
        message = (
            f"Обновление поставки: {result.status} · источник {result.source_status} · "
            f"попыток API {result.actual_http_attempts}/{result.http_attempt_cap}."
        )
        if result.issue_codes:
            message += "\nПричины: " + ", ".join(result.issue_codes[:5])
        if result.continuation_token:
            callback = self._issue_ticket(owner, session, "continue_supply_refresh")
            return self._result(
                message + "\nИсточник прочитан не полностью; продолжите bounded-запрос.",
                keyboard=self._keyboard([{"text": "⏭ Продолжить обновление", "callback": callback}]),
            )
        current = self._read_case(session["case_id"], session["identity"])
        if isinstance(current, dict) and current.get("error") is False:
            self._refresh_session(session, current)
        session.pop("refresh_reference_id", None)
        session.pop("refresh_declaration_id", None)
        session.pop("refresh_continuation_token", None)
        return self._result(
            message + "\nТекущая стоимость и прибыль не менялись.",
            keyboard=self._keyboard([{"text": "↩️ К делу", "callback": self._issue_ticket(owner, session, "finish")}]),
        )

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
            kind="REPORT_EVIDENCE", limit=101,
        )
        report_count = (
            len(evidence.get("items", ()))
            if isinstance(evidence, dict) and evidence.get("error") is False
            and len(evidence.get("items", ())) <= 100 else None
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
        buttons = []
        if case.get("state") in self._EDITABLE_STATES:
            buttons.extend([
                {"text": "📦 Поставки", "callback": self._issue_ticket(owner, session, "supply")},
                {"text": "🔄 Обновить данные поставок", "callback": self._issue_ticket(owner, session, "refresh_supplies")},
                {"text": "📄 Добавить отчёт", "callback": self._issue_ticket(owner, session, "reports")},
            ])
        buttons.extend([
            {"text": "🔍 Проверить готовность", "callback": self._issue_ticket(owner, session, "check_readiness")},
            {"text": "📊 Посмотреть пересчёт", "callback": self._issue_ticket(owner, session, "view_recalculation")},
        ])
        if case.get("state") == "READY_TO_CONFIRM" and self.apply_service is not None:
            buttons.append({
                "text": "✅ Применить подтверждённую историю",
                "callback": self._issue_ticket(owner, session, "apply_transition"),
            })
        if case.get("state") in self._EDITABLE_STATES:
            buttons.append({
                "text": "✖️ Отменить изменение",
                "callback": self._issue_ticket(owner, session, "cancel_case"),
            })
        return self._result(text, keyboard=self._keyboard(buttons))

    def _show_readiness(self, owner):
        session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return self._stale()
        review = self._assess_case(session)
        if not isinstance(review, dict) or review.get("error") is not False:
            return self._failure("Не удалось проверить готовность. Черновик не изменён; попробуйте открыть его заново.")
        readiness = review.get("readiness")
        if readiness is None:
            return self._failure("Проверка не вернула требований; данные не изменены.")
        lines = [
            f"🔍 Готовность FIFO · {session['display_name']} · редакция {review['case_revision']}",
            f"Состояние: {readiness.status}",
            f"Можно применить: {'да' if readiness.ready_to_apply else 'нет'}",
            f"Подтверждённые данные источников до: {readiness.source_data_through or 'нет данных'}",
            f"Кандидатные данные до: {readiness.candidate_data_through or 'нет данных'}",
            f"Покрытие до: {readiness.complete_through or 'не подтверждено'}",
        ]
        self._append_readiness_requirements(lines, readiness, limit=8)
        lines.append("Проверка только читает сохранённые доказательства; FIFO и прибыль не меняются.")
        return self._result(
            "\n".join(lines),
            keyboard=self._keyboard([
                {"text": "📊 Посмотреть пересчёт", "callback": self._issue_ticket(owner, session, "view_recalculation")},
                {"text": "↩️ К делу", "callback": self._issue_ticket(owner, session, "finish")},
            ]),
        )

    def _show_recalculation(self, owner):
        session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return self._stale()
        case = self._read_case(session["case_id"], session["identity"])
        if not isinstance(case, dict) or case.get("error") is not False:
            return self._failure("Не удалось открыть дело для пересчёта; данные не изменены.")
        self._refresh_session(session, case)
        review = self._assess_case(session)
        if not isinstance(review, dict) or review.get("error") is not False:
            return self._failure("Не удалось собрать пересчёт по сохранённым источникам. Дело не изменено.")
        proposal = review["proposal"]
        status = review["readiness"].status
        cost_components = case["case"].get("cost_components")
        lines = [
            f"📊 Предпросмотр перехода FIFO · редакция {review['case_revision']}",
            f"Дата первой отправки · ввод владельца: {case['case'].get('dispatch_date') or 'не указана'}",
            f"Старая стоимость (ввод владельца): {case['case'].get('old_unit_cost_rub') or 'не указана'} ₽/шт.",
            f"Новая стоимость · ввод владельца: {self._format_cost(case['case'])} ₽/шт. · режим {case['case'].get('cost_input_mode')}",
        ]
        if isinstance(cost_components, dict):
            lines.append(
                "Компоненты новой стоимости: закупка "
                f"{cost_components.get('purchase_cost_rub')} + доставка "
                f"{cost_components.get('delivery_cost_rub')} + упаковка "
                f"{cost_components.get('packaging_cost_rub')} ₽/шт."
            )
        elif case["case"].get("cost_input_mode") == "TOTAL_LANDED":
            lines.append("Новая стоимость введена итогом; разбивка компонентов отсутствует.")
        if review.get("fifo_queue_initialized") is True:
            layers = review.get("fifo_layers", ())
            lines.append(f"Подтверждённые старые FIFO-слои: {len(layers)}")
            for layer in layers[:5]:
                lines.append(
                    f"• {layer['remaining_units']} шт. × {layer['unit_cost_rub']} ₽/шт.; "
                    f"дата {layer.get('effective_date') or 'не указана'}, "
                    f"место {layer.get('location') or 'не подтверждено'}"
                )
            if len(layers) > 5:
                lines.append(f"• Ещё подтверждённых слоёв: {len(layers) - 5}")
        else:
            lines.append("Старая очередь FIFO не инициализирована; старые слои не подтверждены.")
        lines.extend([
            f"Старый товар дома/в пути по данным владельца: {proposal.old_home_units} / {proposal.old_transit_units} шт.",
            f"Количество новой партии дома: {proposal.new_home_units if proposal.new_home_units is not None else 'неизвестно'}",
            f"Отправлено владельцем: {proposal.owner_declared_shipped_total if proposal.owner_declared_shipped_total is not None else 'нет данных'} шт.",
            f"Подтверждённый FIFO cutoff: {proposal.confirmed_cutoff_date or 'отсутствует'}; состояние готовности: {status}",
            f"Покрытие финансовых данных до: {review['readiness'].source_data_through or 'нет подтверждённых данных'}",
            f"Кандидатное покрытие до: {review['readiness'].candidate_data_through or 'нет'}; полное покрытие до: {review['readiness'].complete_through or 'не подтверждено'}",
        ])
        for label, evidence_items in (
            ("Срезы остатков", proposal.stock_snapshots),
            ("Оборотные ведомости", proposal.turnover_controls),
        ):
            lines.append(f"{label}: {len(evidence_items)}")
            for evidence in evidence_items[:3]:
                period = (
                    f"{evidence.period_from or '?'}—{evidence.period_to or '?'}"
                )
                lines.append(
                    f"• период {period}; статус {evidence.completeness.value}; "
                    f"период {evidence.period_provenance.value}; снимок {evidence.captured_at}"
                )
            if len(evidence_items) > 3:
                lines.append(f"• Ещё записей: {len(evidence_items) - 3}")
        if proposal.turnover_coverage_gap:
            lines.append(
                f"Пробел в ведомостях: {proposal.turnover_coverage_gap[0]}—{proposal.turnover_coverage_gap[1]}"
            )
        if proposal.requirements:
            lines.append("Недостающие условия: " + ", ".join(proposal.requirements[:8]))
        self._append_readiness_requirements(lines, review["readiness"], limit=5)
        missing_fields = [
            label for field, label in (
                ("old_unit_cost_rub", "старая стоимость"),
                ("new_unit_cost_rub", "новая стоимость"),
                ("dispatch_date", "дата первой отправки"),
                ("owner_old_home_units", "старый остаток дома"),
                ("owner_old_transit_units", "старый товар в пути"),
                ("declared_shipped_units", "общее количество новой партии"),
            ) if case["case"].get(field) is None
        ]
        if missing_fields:
            lines.append("Не введено владельцем: " + ", ".join(missing_fields))
        old_cost = case["case"].get("old_unit_cost_rub")
        new_cost = case["case"].get("new_unit_cost_rub")
        if old_cost is not None and new_cost is not None:
            difference = Decimal(str(new_cost)) - Decimal(str(old_cost))
            lines.append(
                f"Изменение себестоимости новой партии к старой: {difference:+.2f} ₽/шт. "
                "Это разница затрат, не расчёт прибыли."
            )
        lines.extend([
            "Влияние на фактическую прибыль пока не рассчитано: необходимы подтверждённый cutoff и полный bridge продаж.",
            "Это предпросмотр сохранённых источников и ввода владельца. Текущая стоимость, история FIFO, кэш и планы не изменены.",
        ])
        return self._result(
            "\n".join(lines),
            keyboard=self._keyboard([
                {"text": "🔍 Проверить готовность", "callback": self._issue_ticket(owner, session, "check_readiness")},
                {"text": "↩️ К делу", "callback": self._issue_ticket(owner, session, "finish")},
            ]),
        )

    @staticmethod
    def _append_readiness_requirements(lines, readiness, *, limit):
        requirements = readiness.requirements
        if requirements:
            lines.append("Проверка недостающих данных:")
        status_labels = {
            "MISSING": "нужно добавить",
            "NEEDS_CONFIRMATION": "нужно подтвердить",
            "CONFLICT": "конфликт данных",
        }
        for item in requirements[:limit]:
            period = (
                f" · период {item.required_period[0]}—{item.required_period[1]}"
                if item.required_period else ""
            )
            fields = (
                f" · поля: {', '.join(item.required_fields[:5])}"
                if item.required_fields else ""
            )
            lines.append(
                f"• {status_labels.get(item.status, 'проверить')}: "
                f"{item.required_document_or_action}{period}{fields}"
            )
        if len(requirements) > limit:
            lines.append(f"• Ещё требований: {len(requirements) - limit}")

    def _assess_case(self, session):
        if self.review_service is None:
            return {"error": True, "code": "FIFO_TRANSITION_REVIEW_UNAVAILABLE"}
        return self.review_service.assess(
            case_id=session["case_id"], identity=session["identity"],
        )

    def _confirm_apply_prompt(self, user_id, owner, session):
        current = self._read_case(session["case_id"], session["identity"])
        if (
            not isinstance(current, dict) or current.get("error") is not False
            or current.get("state") != "READY_TO_CONFIRM"
            or current.get("case_revision") != session.get("case_revision")
            or self.apply_service is None
        ):
            return self._failure("Применение недоступно: нет актуального READY предпросмотра. FIFO не изменена.")
        callback = self._issue_ticket(owner, session, "confirm_apply")
        return self._result(
            "Проверьте подтверждённый предпросмотр. Применение ещё раз проверит редакции дела, источников, cutoff, налогов и FIFO.",
            keyboard=self._keyboard([
                {"text": "✅ Применить подтверждённую историю", "callback": callback},
                {"text": "↩️ Назад", "callback": self._issue_ticket(owner, session, "finish")},
            ]),
        )

    def _apply_transition(self, user_id, owner, session, ticket):
        current = self._read_case(session["case_id"], session["identity"])
        if (
            not isinstance(current, dict) or current.get("error") is not False
            or current.get("state") != "READY_TO_CONFIRM"
            or current.get("case_revision") != ticket.get("case_revision")
            or self.apply_service is None
        ):
            return self._failure("Предпросмотр устарел или больше не готов. Применение отклонено, FIFO не изменена.")
        apply_method = getattr(self.apply_service, "apply", None)
        if not callable(apply_method):
            return self._failure("Сервис применения недоступен. FIFO не изменена.")
        result = apply_method(
            case_id=session["case_id"], identity=dict(session["identity"]),
            expected_case_revision=current["case_revision"],
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._failure("Серверная проверка применения не пройдена. Данные FIFO не изменены.")
        if callable(self.cache_invalidator):
            try:
                self.cache_invalidator(dict(session["identity"]))
            except Exception:
                # The atomic commit is already authoritative. Detail callbacks
                # still validate the exact local cost/allocation revision.
                pass
        self._refresh_session(session, self._read_case(session["case_id"], session["identity"]))
        return self._show_summary(owner)

    def _refresh_supplies_prompt(self, owner, *, page):
        session = self._sessions.get(owner)
        if not isinstance(session, dict):
            return self._stale()
        manifest = self.transition_service.get_supply_manifest(
            case_id=session["case_id"], **session["identity"],
        )
        if not isinstance(manifest, dict) or manifest.get("error") is not False:
            return self._failure("Не удалось прочитать список поставок. Данные дела не изменены.")
        supported = [item for item in manifest.get("declarations", ()) if item.get("reference_kind") == "SUPPLY"]
        if not supported:
            return self._result(
                "Для обновления статуса нужен ID конкретной поставки. Добавьте поставку типа SUPPLY; номер заявки ORDER сам по себе не используется для подмены статуса.",
                keyboard=self._keyboard([{"text": "📦 Добавить поставку", "callback": self._issue_ticket(owner, session, "supply")}]),
            )
        page_count = (len(supported) + self.SUPPLY_REFRESH_PAGE_SIZE - 1) // self.SUPPLY_REFRESH_PAGE_SIZE
        if page >= page_count:
            return self._stale()
        start = page * self.SUPPLY_REFRESH_PAGE_SIZE
        page_items = supported[start:start + self.SUPPLY_REFRESH_PAGE_SIZE]
        lines = [
            f"Выберите поставку по порядковому номеру и заявленному количеству "
            f"(страница {page + 1} из {page_count}). ID скрыты:"
        ]
        buttons = []
        for index, item in enumerate(page_items, start=start + 1):
            units = item.get("declared_shipped_units")
            label = f"Поставка {index} · {units if units is not None else 'неизвестно'} шт."
            buttons.append({"text": f"🔄 {label}", "callback": self._issue_ticket(owner, session, "refresh_supply_select", declaration_id=item.get("declaration_id"))})
        if page > 0:
            buttons.append({
                "text": "⬅️ Назад",
                "callback": self._issue_ticket(owner, session, "refresh_supplies_page", page=page - 1),
            })
        if page + 1 < page_count:
            buttons.append({
                "text": "➡️ Далее",
                "callback": self._issue_ticket(owner, session, "refresh_supplies_page", page=page + 1),
            })
        lines.append("Для сверки будет запрошен только ID выбранной поставки; номер не появится в сообщениях или callback.")
        return self._result("\n".join(lines), keyboard=self._keyboard(buttons))

    def _issue_ticket(self, owner, session, action, **extra):
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
                **extra,
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
            {"text": "💾 Сохранить сведения о партии", "callback": f"{self.CALLBACK_PREFIX}:{confirm_action}:{token}"},
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
