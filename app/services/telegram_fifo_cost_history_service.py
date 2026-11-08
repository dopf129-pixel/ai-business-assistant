"""Telegram-facing FIFO cost history with opaque, revision-bound callbacks."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.fifo_cost_history_service import FifoCostHistoryService
from services.tenant_context import get_current_tenant_user_id


class TelegramFifoCostHistoryService:
    CALLBACK_PREFIX = "fifo_history"
    TTL_SECONDS = 15 * 60
    MAX_TICKETS = 1024

    def __init__(
        self, history_service=None, rate_cancellation_service=None,
        transition_service=None,
    ):
        self.history_service = history_service or FifoCostHistoryService()
        self.rate_cancellation_service = rate_cancellation_service
        self.transition_service = transition_service
        self._tickets = {}
        self._case_tickets = {}
        self._lock = RLock()

    def create_sku_callback(
        self, *, user_id, store_id, product_id, offer_id, sku, display_name,
    ):
        owner = self._user_key(user_id)
        tenant_scope = self._tenant_scope()
        if owner is None or not tenant_scope:
            return {"error": True, "code": "FIFO_HISTORY_OWNER_REQUIRED"}
        snapshot = self.history_service.get_sku_history(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
        )
        if not isinstance(snapshot, dict) or snapshot.get("error") is not False:
            return snapshot if isinstance(snapshot, dict) else {
                "error": True, "code": "FIFO_HISTORY_UNAVAILABLE",
            }
        token = uuid4().hex[:12]
        now = monotonic()
        with self._lock:
            self._purge_expired(now)
            self._tickets[(owner, token)] = {
                "owner_key": owner,
                "tenant_scope": tenant_scope,
                "store_id": str(store_id),
                "product_id": str(product_id) if product_id is not None else None,
                "offer_id": str(offer_id) if offer_id is not None else None,
                "sku": str(sku),
                "display_name": str(display_name or "Товар"),
                "revision": snapshot["revision"],
                "expires_at": now + self.TTL_SECONDS,
            }
            while len(self._tickets) > self.MAX_TICKETS:
                oldest = min(self._tickets, key=lambda key: self._tickets[key]["expires_at"])
                self._tickets.pop(oldest, None)
        return {
            "error": False,
            "callback": f"{self.CALLBACK_PREFIX}:open:{token}",
        }

    def handle_callback(self, user_id, callback):
        owner = self._user_key(user_id)
        parts = str(callback or "").split(":")
        if len(parts) != 3 or parts[0] != self.CALLBACK_PREFIX:
            return {"error": False, "handled": False, "read_only_ozon": True}
        _prefix, action, token = parts
        if action not in {
            "open", "history", "new", "late", "correct", "sku",
            "anchor", "zero_rate", "cancel_rate", "confirm_rate_cancel", "export",
            "drafts", "late_total", "late_components", "resume",
        }:
            return {"error": False, "handled": False, "read_only_ozon": True}
        if action == "resume":
            return self._resume_transition_case(owner, token)
        ticket = self._validated_ticket(owner, token)
        if isinstance(ticket, dict) and ticket.get("error") is True:
            return ticket
        if action == "new":
            if ticket["queue_initialized"] is not True:
                return self._message_result(
                    "Сначала нужно зафиксировать начальный остаток и старые партии FIFO для этого SKU. "
                    "Пока очередь не настроена, новая ставка не будет записана в FIFO.",
                    ticket["token"],
                )
            return {
                "error": False,
                "handled": True,
                "action": "start_new_rate",
                "identity": ticket["identity"],
                "display_name": ticket["display_name"],
                "expected_revision": ticket["revision"],
                "read_only_ozon": True,
            }
        if action == "anchor":
            if ticket["queue_initialized"] is True:
                return self._render_sku_card(ticket)
            return {
                "error": False,
                "handled": True,
                "action": "start_initial_anchor",
                "identity": ticket["identity"],
                "display_name": ticket["display_name"],
                "expected_revision": ticket["revision"],
                "read_only_ozon": True,
            }
        if action == "zero_rate":
            if ticket["queue_initialized"] is True:
                return self._render_sku_card(ticket)
            if self.transition_service is not None:
                active = self._active_transition_cases(ticket)
                if active is None:
                    return self._message_result(
                        "Не удалось проверить незавершённые изменения. Нулевой старт не начат; FIFO не изменена.",
                        ticket["token"],
                    )
                if active:
                    return self._message_result(
                        "Нулевой старт запрещён: для SKU есть незавершённые сведения о новой партии. "
                        "Сначала продолжите или отмените это изменение, чтобы товар в пути не потерялся.",
                        ticket["token"],
                    )
            return {
                "error": False,
                "handled": True,
                "action": "start_initial_zero_rate",
                "identity": ticket["identity"],
                "display_name": ticket["display_name"],
                "expected_revision": ticket["revision"],
                "read_only_ozon": True,
            }
        if action == "late":
            if ticket["queue_initialized"] is not True:
                return self._transition_mode_prompt(ticket)
            return {
                "error": False,
                "handled": True,
                "action": "start_late_entry",
                "identity": ticket["identity"],
                "display_name": ticket["display_name"],
                "expected_revision": ticket["revision"],
                "read_only_ozon": True,
            }
        if action in {"late_total", "late_components"}:
            if ticket["queue_initialized"] is True:
                return self._render_sku_card(ticket)
            active = self._active_transition_cases(ticket)
            if active is None:
                return self._message_result(
                    "Не удалось проверить незавершённые изменения. Новый черновик не создан.",
                    ticket["token"],
                )
            if active:
                return self._render_transition_drafts(ticket)
            return {
                "error": False,
                "handled": True,
                "action": "start_transition_wizard",
                "cost_input_mode": (
                    "TOTAL_LANDED" if action == "late_total" else "COMPONENTS"
                ),
                "identity": ticket["identity"],
                "display_name": ticket["display_name"],
                "expected_revision": ticket["revision"],
                "message": "Открываю сохранение сведений о уже отправленной партии.",
                "read_only_ozon": True,
            }
        if action == "drafts":
            return self._render_transition_drafts(ticket)
        if action == "correct":
            return self._message_result(
                "Исправление сохранённой записи пока недоступно. Старую запись нельзя заменить "
                "поверх: сначала нужен просмотр влияния и отдельное подтверждение. Данные не изменены.",
                ticket["token"],
            )
        if action == "cancel_rate":
            return self._preview_rate_cancellation(owner, ticket)
        if action == "confirm_rate_cancel":
            return self._confirm_rate_cancellation(owner, ticket)
        if action == "history":
            return self._render_history(ticket)
        if action == "export":
            return self._export_history(ticket)
        if action == "sku":
            return self._render_sku_card(ticket)
        return self._render_sku_card(ticket)

    def _validated_ticket(self, owner, token):
        if owner is None or not token:
            return self._stale_ticket()
        now = monotonic()
        with self._lock:
            self._purge_expired(now)
            ticket = self._tickets.get((owner, token))
        if not isinstance(ticket, dict) or ticket.get("tenant_scope") != self._tenant_scope():
            return self._stale_ticket()
        identity = ticket["identity"] if "identity" in ticket else {
            key: ticket[key] for key in (
                "store_id", "product_id", "offer_id", "sku",
            )
        }
        current = self.history_service.get_sku_history(
            **identity,
        )
        if (
            not isinstance(current, dict)
            or current.get("error") is not False
            or current.get("revision") != ticket["revision"]
        ):
            return self._stale_ticket()
        return {
            **ticket,
            "token": token,
            "identity": identity,
            "snapshot": current,
            "queue_initialized": current["queue_initialized"],
        }

    def _render_sku_card(self, ticket):
        snapshot = ticket["snapshot"]
        message = (
            f"💰 Себестоимость FIFO · {ticket['display_name']}\n"
            f"SKU: {ticket['sku']}\n\n"
            + self._summary_lines(snapshot)
        )
        return {
            "error": False,
            "handled": True,
            "message": message,
            "keyboard": self._sku_keyboard(
                ticket["token"],
                queue_initialized=snapshot["queue_initialized"],
            ),
            "read_only_ozon": True,
        }

    def _active_transition_cases(self, ticket):
        if self.transition_service is None:
            return None
        result = self.transition_service.list_cases(
            store_id=ticket["identity"]["store_id"],
            sku=ticket["identity"]["sku"],
            states=("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM"),
            limit=20,
        )
        if (
            not isinstance(result, dict) or result.get("error") is not False
            or not isinstance(result.get("cases"), list)
        ):
            return None
        expected = ticket["identity"]
        cases = []
        for item in result.get("cases", ()):
            payload = item.get("case") if isinstance(item, dict) else None
            metadata = payload.get("metadata") if isinstance(payload, dict) else None
            scope = metadata.get("scope") if isinstance(metadata, dict) else None
            if not isinstance(item, dict) or not isinstance(scope, dict):
                return None
            # Repository listing is already owner/tenant scoped; the payload
            # intentionally does not persist the owner identity a second time.
            if all(scope.get(key) == expected.get(key) for key in (
                "store_id", "product_id", "offer_id", "sku",
            )):
                cases.append(item)
        return cases

    def _transition_mode_prompt(self, ticket):
        if self.transition_service is None:
            return self._message_result(
                "Сохранение сведений о новой партии пока недоступно. Текущая FIFO не изменена.",
                ticket["token"],
            )
        return {
            "error": False,
            "handled": True,
            "message": (
                "Партия уже отправлена до настройки FIFO. Выберите, как зафиксировать "
                "её итоговую себестоимость. Черновик не изменит текущие расчёты."
            ),
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [
                    {"text": "Указать итоговую себестоимость", "callback": f"{self.CALLBACK_PREFIX}:late_total:{ticket['token']}"},
                    {"text": "Разбить на закупку, доставку и упаковку", "callback": f"{self.CALLBACK_PREFIX}:late_components:{ticket['token']}"},
                    {"text": "🗂 Незавершённые изменения", "callback": f"{self.CALLBACK_PREFIX}:drafts:{ticket['token']}"},
                    {"text": "↩️ К SKU", "callback": f"{self.CALLBACK_PREFIX}:sku:{ticket['token']}"},
                ],
            },
            "read_only_ozon": True,
        }

    def _render_transition_drafts(self, ticket):
        cases = self._active_transition_cases(ticket)
        if cases is None:
            return self._message_result(
                "Не удалось безопасно прочитать незавершённые изменения. Данные не изменены.",
                ticket["token"],
            )
        if not cases:
            message = "Для этого SKU нет незавершённых изменений."
            buttons = []
        else:
            message = (
                f"🗂 Незавершённые изменения · {ticket['display_name']} · SKU {ticket['sku']}\n"
                "Они сохранены отдельно и пока не меняют FIFO или расчёт прибыли."
            )
            buttons = []
            now = monotonic()
            for index, item in enumerate(cases[:20], start=1):
                if (
                    not isinstance(item.get("case_id"), str)
                    or type(item.get("case_revision")) is not int
                    or not isinstance(item.get("state"), str)
                ):
                    return self._message_result(
                        "В незавершённом изменении обнаружены неполные данные. Ничего не изменено.",
                        ticket["token"],
                    )
                case_id = item["case_id"]
                token = uuid4().hex[:12]
                owner = ticket.get("owner_key")
                if not owner:
                    return self._message_result(
                        "Не удалось создать безопасную кнопку продолжения. Данные не изменены.",
                        ticket["token"],
                    )
                with self._lock:
                    self._purge_expired(now)
                    self._case_tickets[(owner, token)] = {
                        "tenant_scope": ticket["tenant_scope"],
                        "identity": dict(ticket["identity"]),
                        "case_id": case_id,
                        "case_revision": item["case_revision"],
                        "expires_at": now + self.TTL_SECONDS,
                    }
                    while len(self._case_tickets) > self.MAX_TICKETS:
                        oldest = min(
                            self._case_tickets,
                            key=lambda key: self._case_tickets[key]["expires_at"],
                        )
                        self._case_tickets.pop(oldest, None)
                buttons.append({
                    "text": f"Продолжить изменение {index} · {item['state']}",
                    "callback": f"{self.CALLBACK_PREFIX}:resume:{token}",
                })
            buttons.append({"text": "➕ Новая партия отправлена", "callback": f"{self.CALLBACK_PREFIX}:late:{ticket['token']}"})
        buttons.append({"text": "↩️ К SKU", "callback": f"{self.CALLBACK_PREFIX}:sku:{ticket['token']}"})
        return {
            "error": False,
            "handled": True,
            "message": message,
            "keyboard": {"error": False, "type": "inline_keyboard", "buttons": buttons},
            "read_only_ozon": True,
        }

    def _resume_transition_case(self, owner, token):
        if owner is None or not token or self.transition_service is None:
            return self._stale_ticket()
        now = monotonic()
        with self._lock:
            self._purge_expired(now)
            ticket = self._case_tickets.get((owner, token))
        if not isinstance(ticket, dict) or ticket.get("tenant_scope") != self._tenant_scope():
            return self._stale_ticket()
        result = self.transition_service.get_case(
            case_id=ticket["case_id"], **ticket["identity"],
        )
        if (
            not isinstance(result, dict) or result.get("error") is not False
            or result.get("case_revision") != ticket["case_revision"]
            or result.get("state") not in {"DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM"}
        ):
            return self._stale_ticket()
        return {
            "error": False,
            "handled": True,
            "action": "resume_transition_wizard",
            "identity": dict(ticket["identity"]),
            "case_id": ticket["case_id"],
            "case_revision": result["case_revision"],
            "case": result["case"],
            "message": "Продолжаю сохранённые сведения о партии.",
            "read_only_ozon": True,
        }

    def _render_history(self, ticket):
        snapshot = ticket["snapshot"]
        lines = [
            f"📚 История себестоимости · {ticket['display_name']}",
            f"SKU: {ticket['sku']}",
            "",
            self._summary_lines(snapshot),
            "",
            "Слои FIFO:",
        ]
        if not snapshot["layers"]:
            lines.append("• Конечные партии пока не записаны.")
        else:
            for index, layer in enumerate(snapshot["layers"][:30], start=1):
                if layer["remaining_units"] is None:
                    quantity = (
                        f"остаток не пересчитан (в записи {layer['recorded_quantity']} шт.)"
                    )
                else:
                    quantity = (
                        f"{layer['remaining_units']} шт. на подтверждённом срезе"
                    )
                effective = layer.get("effective_date") or "дата не указана"
                lines.append(
                    f"{index}. {layer['unit_cost_rub']} ₽/шт. · {quantity} · "
                    f"{layer['recorded_location_label']} · с {effective} · "
                    f"{layer['provenance_label']}"
                )
            if len(snapshot["layers"]) > 30:
                lines.append(f"Показаны первые 30 из {len(snapshot['layers'])} записей слоёв.")

        lines.extend(["", "Ставки следующих партий:"])
        if not snapshot["rates"]:
            lines.append("• Новые ставки ещё не записывались.")
        else:
            for rate in snapshot["rates"][-30:]:
                status = {
                    "EFFECTIVE": "действует для новых поступлений",
                    "PLANNED": "запланирована",
                    "CANCELLED": "отменена, запись сохранена",
                }.get(rate["status"], "статус не подтверждён")
                captured = str(rate.get("captured_at") or "")[:10]
                if rate.get("cost_input_mode", "COMPONENTS") == "TOTAL_LANDED":
                    components = "полная себестоимость; разбивка компонентов не указана"
                else:
                    components = (
                        f"закупка {rate['purchase_cost_rub']} + доставка {rate['delivery_cost_rub']} "
                        f"+ упаковка {rate['packaging_cost_rub']} ₽/шт."
                    )
                lines.append(
                    f"• {rate['unit_cost_rub']} ₽/шт. с {rate['effective_date']} — {status}; "
                    f"{rate['provenance_label']}; {components}"
                )
                if rate.get("owner_old_home_units") is not None:
                    lines.append(
                        f"  На момент записи владелец указал дома {rate['owner_old_home_units']} шт. "
                        "старой партии; это подтверждение, не дополнительный складской остаток."
                    )
                if rate.get("reconciled_quantity") is not None:
                    lines.append(
                        f"  До следующей ставки подтверждено {rate['reconciled_quantity']} шт. "
                        f"по этой цене из общего остатка {rate['reconciled_total_units']} шт."
                    )
                if captured:
                    lines.append(f"  Записано: {captured}.")
            if len(snapshot["rates"]) > 30:
                lines.append(f"Показаны последние 30 из {len(snapshot['rates'])} ставок.")

        return {
            "error": False,
            "handled": True,
            "message": "\n".join(lines),
            "keyboard": self._history_keyboard(
                ticket["token"],
                allow_cancel=(
                    self.rate_cancellation_service is not None
                    and any(rate["status"] == "PLANNED" for rate in snapshot["rates"])
                ),
            ),
            "read_only_ozon": True,
        }

    def _export_history(self, ticket):
        snapshot = ticket.get("snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("error") is not False:
            return self._message_result(
                "История устарела. Откройте SKU заново перед выгрузкой.",
                ticket["token"],
            )
        layers = snapshot.get("layers")
        rates = snapshot.get("rates")
        if (
            not isinstance(layers, list) or not isinstance(rates, list)
            or len(layers) + len(rates) > 10_000
        ):
            return {"error": True, "handled": True, "code": "FIFO_HISTORY_EXPORT_LIMIT", "message": "История слишком большая или неполная; файл не сформирован.", "read_only_ozon": True}
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow((
            "Режим", "SKU", "Тип записи", "Порядок", "Действует с",
            "Количество", "Место", "Себестоимость за шт., ₽",
            "Режим разбивки", "Закупка, ₽", "Доставка, ₽", "Упаковка, ₽", "Статус",
            "Подтверждение", "Состояние источника", "Полнота источника",
            "Ревизия FIFO", "Ревизия распределения", "Дата cutoff",
            "Ссылка строки",
        ))
        allocation = snapshot.get("latest_allocation")
        allocation_revision = (
            allocation.get("revision") if isinstance(allocation, dict) else None
        )
        common = {
            "mode": "FIFO",
            "sku": ticket.get("sku"),
            "stream_revision": snapshot.get("revision"),
            "allocation_revision": allocation_revision,
            "cutoff_date": snapshot.get("cutoff_date") or "",
        }
        rows = []
        for layer in layers:
            if not isinstance(layer, dict):
                return {"error": True, "handled": True, "code": "FIFO_HISTORY_EXPORT_INVALID", "message": "Невозможно безопасно выгрузить повреждённую историю.", "read_only_ozon": True}
            rows.append({
                **common,
                "kind": "FINITE_LAYER",
                "sequence": layer.get("sequence"),
                "effective_date": layer.get("effective_date") or "",
                "quantity": layer.get("recorded_quantity"),
                "location": layer.get("location") or "UNKNOWN",
                "unit_cost": layer.get("unit_cost_rub"),
                "cost_input_mode": "NOT_APPLICABLE",
                "purchase": "", "delivery": "", "packaging": "",
                "status": layer.get("remaining_status") or "UNKNOWN",
                "provenance": layer.get("provenance") or "UNKNOWN",
                "source_status": layer.get("source_status") or "UNKNOWN",
                "coverage": layer.get("coverage_status") or "UNKNOWN",
            })
        for rate in rates:
            if not isinstance(rate, dict):
                return {"error": True, "handled": True, "code": "FIFO_HISTORY_EXPORT_INVALID", "message": "Невозможно безопасно выгрузить повреждённую историю.", "read_only_ozon": True}
            rows.append({
                **common,
                "kind": "OPEN_RATE",
                "sequence": rate.get("sequence"),
                "effective_date": rate.get("effective_date") or "",
                "quantity": rate.get("reconciled_quantity"),
                "location": "UNKNOWN",
                "unit_cost": rate.get("unit_cost_rub"),
                "cost_input_mode": rate.get("cost_input_mode", "COMPONENTS"),
                "purchase": rate.get("purchase_cost_rub"),
                "delivery": rate.get("delivery_cost_rub"),
                "packaging": rate.get("packaging_cost_rub"),
                "status": rate.get("status") or "UNKNOWN",
                "provenance": rate.get("provenance") or "UNKNOWN",
                "source_status": rate.get("source_status") or "UNKNOWN",
                "coverage": rate.get("coverage_status") or "UNKNOWN",
            })
        for row in rows:
            reference_payload = {
                key: row.get(key) for key in (
                    "mode", "sku", "kind", "sequence", "effective_date",
                    "quantity", "unit_cost", "stream_revision",
                    "allocation_revision", "cutoff_date", "provenance",
                    "cost_input_mode",
                )
            }
            reference = "fifo-export-" + hashlib.sha256(
                json.dumps(reference_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:20]
            writer.writerow((
                row["mode"], self._spreadsheet_safe(row["sku"]), row["kind"],
                row["sequence"], row["effective_date"],
                "" if row["quantity"] is None else row["quantity"],
                self._spreadsheet_safe(row["location"]),
                row["unit_cost"], row["cost_input_mode"], row["purchase"],
                row["delivery"], row["packaging"],
                self._spreadsheet_safe(row["status"]),
                self._spreadsheet_safe(row["provenance"]),
                self._spreadsheet_safe(row["source_status"]),
                self._spreadsheet_safe(row["coverage"]), row["stream_revision"],
                "" if row["allocation_revision"] is None else row["allocation_revision"],
                row["cutoff_date"], reference,
            ))
        if not rows:
            writer.writerow((
                "FIFO", self._spreadsheet_safe(ticket.get("sku")), "EMPTY", "", "",
                "", "", "", "", "", "", "", snapshot.get("stream_state") or "UNKNOWN",
                "UNKNOWN", "UNKNOWN", "UNKNOWN", snapshot.get("revision"), "",
                snapshot.get("cutoff_date") or "", "",
            ))
        content = "\ufeff" + stream.getvalue()
        if len(content.encode("utf-8")) > 1_000_000:
            return {"error": True, "handled": True, "code": "FIFO_HISTORY_EXPORT_TOO_LARGE", "message": "Выгрузка превышает 1 МБ. История и расчёты не изменены.", "read_only_ozon": True}
        return {
            "error": False,
            "handled": True,
            "message": "Выгружена только для просмотра история FIFO. Количество открытой ставки может быть неизвестно; пустое поле не означает ноль. Файл нельзя импортировать как legacy-себестоимость.",
            "filename": "fifo-cost-history.csv",
            "mime_type": "text/csv",
            "document_kind": "analytics_export",
            "file_content": content,
            "rows": len(rows),
            "revision": snapshot.get("revision"),
            "read_only_ozon": True,
        }

    @classmethod
    def _spreadsheet_safe(cls, value):
        text = str(value or "")
        probe = text.lstrip(" \t\r\n")
        return "'" + text if probe and probe[0] in "=+-@" else text

    def _preview_rate_cancellation(self, owner, ticket):
        planned_rate = next(
            (
                rate for rate in reversed(ticket["snapshot"].get("rates", ()))
                if rate["status"] == "PLANNED"
            ),
            None,
        )
        if self.rate_cancellation_service is None or planned_rate is None:
            return self._message_result(
                "Нет будущей ставки, которую можно отменить. История не изменена.",
                ticket["token"],
            )
        preview = self.rate_cancellation_service.preview(
            **ticket["identity"],
            rate_sequence=planned_rate["sequence"],
            expected_revision=ticket["revision"],
        )
        if not isinstance(preview, dict) or preview.get("error") is not False:
            return self._message_result(
                "Не удалось подготовить отмену: после запланированной даты уже есть "
                "события или сверка либо данные устарели. Ничего не изменено; "
                "обновите историю товара.",
                ticket["token"],
            )
        cancellation = {
            "preview_id": preview["preview_id"],
            "idempotency_key": "hist-cancel-" + uuid4().hex,
            "rate_sequence": planned_rate["sequence"],
            "effective_date": planned_rate["effective_date"],
            "unit_cost_rub": planned_rate["unit_cost_rub"],
        }
        with self._lock:
            stored = self._tickets.get((owner, ticket["token"]))
            if stored is None or stored.get("revision") != ticket["revision"]:
                return self._stale_ticket()
            stored["rate_cancel_preview"] = cancellation
        return {
            "error": False,
            "handled": True,
            "message": (
                f"Отменить запланированную ставку {planned_rate['unit_cost_rub']} ₽/шт. "
                f"с {planned_rate['effective_date']}?\n\n"
                "Запись останется в истории со статусом «отменена». FIFO-остатки и "
                "фактический расчёт прибыли не меняются. Подтвердите только если "
                "переход ещё не состоялся."
            ),
            "keyboard": self._rate_cancellation_confirmation_keyboard(ticket["token"]),
            "read_only_ozon": True,
        }

    def _confirm_rate_cancellation(self, owner, ticket):
        cancellation = ticket.get("rate_cancel_preview")
        if self.rate_cancellation_service is None or not isinstance(cancellation, dict):
            return self._stale_ticket()
        result = self.rate_cancellation_service.confirm(
            preview_id=cancellation["preview_id"],
            active_preview_id=cancellation["preview_id"],
            idempotency_key=cancellation["idempotency_key"],
            **ticket["identity"],
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._message_result(
                "Ставка не отменена: данные изменились или переход уже использован. "
                "Откройте SKU и проверьте актуальную историю.",
                ticket["token"],
            )
        refreshed = self.history_service.get_sku_history(**ticket["identity"])
        if not isinstance(refreshed, dict) or refreshed.get("error") is not False:
            return self._message_result(
                "Ставка отменена и запись сохранена. Не удалось обновить экран истории; "
                "откройте SKU заново.",
                ticket["token"],
            )
        with self._lock:
            stored = self._tickets.get((owner, ticket["token"]))
            if stored is None:
                return self._stale_ticket()
            stored["revision"] = refreshed["revision"]
            stored.pop("rate_cancel_preview", None)
        updated_ticket = {
            **ticket,
            "revision": refreshed["revision"],
            "snapshot": refreshed,
        }
        history = self._render_history(updated_ticket)
        history["message"] = (
            f"✅ Ставка {result['rate_sequence']} с {result['effective_date']} отменена. "
            "Исходная запись сохранена в аудите; FIFO-остатки и фактическая прибыль "
            "не изменялись.\n\n" + history["message"]
        )
        history["fifo_rate_cancelled"] = True
        return history

    def _summary_lines(self, snapshot):
        if not snapshot["queue_initialized"]:
            return (
                "FIFO-очередь для SKU ещё не настроена. Существующая себестоимость "
                "отчётов не менялась."
            )
        lines = []
        if snapshot.get("cutoff_date"):
            lines.append(f"Последний начальный срез: {snapshot['cutoff_date']}.")
        if snapshot["next_unit_cost_rub"] is not None:
            if snapshot["next_unit_cost_basis"] == "FINITE_FIFO_LAYER":
                lines.append(
                    f"Следующая единица на подтверждённом срезе: "
                    f"{snapshot['next_unit_cost_rub']} ₽/шт. по старому слою."
                )
            else:
                lines.append(
                    f"Ставка следующей партии: {snapshot['next_unit_cost_rub']} ₽/шт.; "
                    "количество новой партии неизвестно."
                )
        elif snapshot["next_planned_rate"] is not None:
            rate = snapshot["next_planned_rate"]
            lines.append(
                f"Следующая ставка запланирована: {rate['unit_cost_rub']} ₽/шт. "
                f"с {rate['effective_date']}; она ещё не действует."
            )
        else:
            lines.append("Стоимость следующей единицы пока не подтверждена.")

        if snapshot["movement_count"]:
            lines.append(
                "После последнего среза есть движения товара. Остаток старых слоёв "
                "не пересчитан, поэтому текущий порог смены цены не показываю."
            )
        else:
            total = sum(layer["recorded_quantity"] for layer in snapshot["layers"])
            lines.append(
                f"Подтверждено конечных единиц на срезе: {total} шт. "
                "Это количество на дату среза, не текущий остаток на сегодня."
            )
        if snapshot["active_rate"] is not None:
            rate = snapshot["active_rate"]
            lines.append(
                f"Действующая ставка новых партий: {rate['unit_cost_rub']} ₽/шт. "
                f"с {rate['effective_date']} ({rate['provenance_label']})."
            )
        lines.append(
            "Пока не подтверждён общий cutoff остатков и продаж, эта FIFO-история "
            "не подменяет фактическую себестоимость в отчётах прибыли."
        )
        return "\n".join(lines)

    @classmethod
    def _sku_keyboard(cls, token, *, queue_initialized=True):
        if not queue_initialized:
            buttons = [
                {"text": "📦 Зафиксировать начальный остаток", "callback": f"{cls.CALLBACK_PREFIX}:anchor:{token}"},
                {"text": "🆕 Начать с нулевого остатка", "callback": f"{cls.CALLBACK_PREFIX}:zero_rate:{token}"},
                {"text": "📦 Новая партия уже отправлена", "callback": f"{cls.CALLBACK_PREFIX}:late:{token}"},
                {"text": "🗂 Незавершённые изменения", "callback": f"{cls.CALLBACK_PREFIX}:drafts:{token}"},
                {"text": "↩️ К SKU", "callback": f"{cls.CALLBACK_PREFIX}:sku:{token}"},
            ]
            return {"error": False, "type": "inline_keyboard", "buttons": buttons}
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "➕ Новая себестоимость", "callback": f"{cls.CALLBACK_PREFIX}:new:{token}"},
                {"text": "📦 Уже отправил новую партию", "callback": f"{cls.CALLBACK_PREFIX}:late:{token}"},
                {"text": "📚 История", "callback": f"{cls.CALLBACK_PREFIX}:history:{token}"},
                {"text": "✏️ Исправить запись", "callback": f"{cls.CALLBACK_PREFIX}:correct:{token}"},
                {"text": "↩️ К SKU", "callback": f"{cls.CALLBACK_PREFIX}:sku:{token}"},
            ],
        }

    @classmethod
    def _history_keyboard(cls, token, *, allow_cancel=False):
        buttons = [
            {"text": "➕ Новая себестоимость", "callback": f"{cls.CALLBACK_PREFIX}:new:{token}"},
            {"text": "📤 Скачать историю CSV", "callback": f"{cls.CALLBACK_PREFIX}:export:{token}"},
        ]
        if allow_cancel:
            buttons.append({
                "text": "✖️ Отменить будущую ставку",
                "callback": f"{cls.CALLBACK_PREFIX}:cancel_rate:{token}",
            })
        buttons.append({"text": "↩️ К SKU", "callback": f"{cls.CALLBACK_PREFIX}:sku:{token}"})
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
        }

    @classmethod
    def _rate_cancellation_confirmation_keyboard(cls, token):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": "✅ Подтвердить отмену",
                    "callback": f"{cls.CALLBACK_PREFIX}:confirm_rate_cancel:{token}",
                },
                {"text": "↩️ К SKU", "callback": f"{cls.CALLBACK_PREFIX}:sku:{token}"},
            ],
        }

    @classmethod
    def _message_result(cls, message, token):
        return {
            "error": False,
            "handled": True,
            "message": message,
            "keyboard": cls._sku_keyboard(token),
            "read_only_ozon": True,
        }

    @staticmethod
    def _stale_ticket():
        return {
            "error": True,
            "handled": True,
            "code": "FIFO_HISTORY_CALLBACK_STALE",
            "message": "Эта кнопка устарела или относится к другому магазину. Откройте SKU заново.",
            "read_only_ozon": True,
        }

    def _purge_expired(self, now):
        for mapping in (self._tickets, self._case_tickets):
            for key, ticket in list(mapping.items()):
                if ticket["expires_at"] <= now:
                    mapping.pop(key, None)

    @staticmethod
    def _user_key(value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        return text if text and len(text) <= 128 and not any(ord(ch) < 32 for ch in text) else None

    @staticmethod
    def _tenant_scope():
        try:
            return str(get_current_tenant_user_id() or "").strip()
        except Exception:
            return ""
