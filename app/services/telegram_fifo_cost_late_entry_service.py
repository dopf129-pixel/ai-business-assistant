"""Owner-confirmed late FIFO batch entry with read-only Ozon evidence checks."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramFifoCostLateEntryService:
    """Collect a late batch proposal without changing FIFO or profit results."""

    CALLBACK_PREFIX = "fifo_late"
    TTL_SECONDS = 15 * 60
    MAX_PENDING = 128
    MAX_UNITS = 1_000_000

    def __init__(
        self, *, history_service, source_collection_service,
        supply_evidence_service, date_provider=None, monotonic_clock=monotonic,
    ):
        self.history_service = history_service
        self.source_collection_service = source_collection_service
        self.supply_evidence_service = supply_evidence_service
        self.date_provider = date_provider or date.today
        self.monotonic_clock = monotonic_clock
        self._pending = {}
        self._lock = RLock()

    def start(self, user_id, identity, display_name, expected_revision):
        owner, tenant, normalized = self._validate_scope(
            user_id, identity, expected_revision,
        )
        if owner is None:
            return self._failure("Не удалось открыть этот товар. Откройте его заново в нужном магазине.")
        current = self.history_service.get_sku_history(**normalized)
        if (
            not isinstance(current, dict)
            or current.get("error") is not False
            or current.get("queue_initialized") is not True
            or current.get("revision") != expected_revision
        ):
            return self._failure(
                "FIFO-очередь изменилась или ещё не настроена. Обновите карточку SKU."
            )
        draft_id = uuid4().hex[:16]
        now = self.monotonic_clock()
        pending = {
            "tenant_scope": tenant,
            "identity": normalized,
            "display_name": self._safe_display_name(display_name),
            "expected_revision": expected_revision,
            "draft_id": draft_id,
            "step": "purchase_cost",
            "expires_at": now + self.TTL_SECONDS,
        }
        with self._lock:
            self._purge_expired(now)
            self._pending[owner] = pending
            while len(self._pending) > self.MAX_PENDING:
                oldest = min(self._pending, key=lambda key: self._pending[key]["expires_at"])
                self._pending.pop(oldest, None)
        return {
            "error": False,
            "handled": True,
            "message": (
                f"Поздний ввод партии · {pending['display_name']} · SKU {normalized['sku']}\n\n"
                "Укажите закупочную стоимость одной единицы в ₽. Затем — доставку до вас, "
                "упаковку, остаток старой партии дома и номер уже отправленной поставки.\n\n"
                "Это создаст только проверяемый черновик. История FIFO и прибыль не изменятся, "
                "пока бот не выполнит отдельный пересчёт и подтверждение."
            ),
            "read_only_ozon": True,
        }

    def handle_text(self, user_id, text):
        owner = self._user_key(user_id)
        if owner is None:
            return {"error": False, "handled": False, "read_only_ozon": True}
        with self._lock:
            self._purge_expired(self.monotonic_clock())
            pending = self._pending.get(owner)
            if pending is None:
                return {"error": False, "handled": False, "read_only_ozon": True}
            if pending.get("tenant_scope") != self._tenant_scope():
                self._pending.pop(owner, None)
                return self._stale()
            if pending.get("step") == "confirm":
                return self._confirm_prompt(pending)
            step = pending.get("step")

        if step in {"purchase_cost", "delivery_cost", "packaging_cost"}:
            amount = self._parse_money(text)
            if amount is None:
                return self._input_error(
                    "Введите сумму в рублях, например 125 или 125,50."
                )
            next_step, field, prompt = {
                "purchase_cost": (
                    "delivery_cost", "purchase_cost_rub",
                    "Введите доставку одной единицы до вас в ₽. Если она нулевая, отправьте 0.",
                ),
                "delivery_cost": (
                    "packaging_cost", "delivery_cost_rub",
                    "Введите стоимость упаковки одной единицы в ₽. Если она нулевая, отправьте 0.",
                ),
                "packaging_cost": (
                    "old_home_units", "packaging_cost_rub",
                    "Сколько единиц старой партии оставалось дома на дату отправки новой? Если ни одной — отправьте 0.",
                ),
            }[step]
            with self._lock:
                pending = self._pending.get(owner)
                if pending is None or pending.get("step") != step:
                    return self._stale()
                pending[field] = amount
                pending["step"] = next_step
            return self._text_result(prompt)

        if step == "old_home_units":
            units = self._parse_units(text)
            if units is None:
                return self._input_error(
                    "Введите целое число старых единиц дома на дату отправки. Если их не было, отправьте 0."
                )
            with self._lock:
                pending = self._pending.get(owner)
                if pending is None or pending.get("step") != step:
                    return self._stale()
                pending["owner_old_home_units"] = units
                pending["step"] = "supply_id"
            return self._text_result(
                "Введите ID завершённой поставки Ozon, где находится новая партия. "
                "Бот проверит принятый акт и точное совпадение SKU."
            )

        if step == "supply_id":
            return self._lookup_supply(owner, text)

        if step == "effective_date":
            effective_date = self._parse_effective_date(text, self.date_provider)
            if effective_date is None:
                return self._input_error(
                    "Введите дату фактического перехода новой партии в формате ГГГГ-ММ-ДД. "
                    "Дата создания акта не считается датой приёмки."
                )
            with self._lock:
                pending = self._pending.get(owner)
                if pending is None or pending.get("step") != step:
                    return self._stale()
                pending["owner_effective_date"] = effective_date
                pending["step"] = "confirm"
            return self._confirm_prompt(pending)

        return self._stale()

    def _lookup_supply(self, owner, text):
        supply_id = self._parse_supply_id(text)
        with self._lock:
            pending = self._pending.get(owner)
            if not isinstance(pending, dict) or pending.get("step") != "supply_id":
                return self._stale()
            if supply_id is None:
                return self._input_error("Введите числовой ID поставки из Ozon Seller.")
            if pending.get("supply_id") and pending["supply_id"] != supply_id:
                return self._input_error(
                    "Продолжите поиск с тем же ID поставки или отмените черновик."
                )
            pending["supply_id"] = supply_id
            identity = dict(pending["identity"])
            tenant = pending["tenant_scope"]
            checkpoint = pending.get("supply_checkpoint")
        result = self.source_collection_service.find_supply_by_id(
            supply_id,
            identity={key: identity.get(key) for key in ("product_id", "offer_id", "sku")},
            store_id=identity["store_id"],
            tenant_scope=tenant,
            checkpoint_token=checkpoint,
            max_pages_per_call=2,
            http_attempt_budget=10,
            time_budget_seconds=20.0,
        )
        if (
            not getattr(result, "read_only", False)
            or getattr(result, "status", None) not in {"COMPLETE", "CONFIRMED_ZERO"}
        ):
            status = getattr(result, "status", "UNAVAILABLE")
            issues = tuple(getattr(result, "issue_codes", ()) or ())
            checkpoint = getattr(result, "continuation_token", None)
            with self._lock:
                pending = self._pending.get(owner)
                if not isinstance(pending, dict):
                    return self._stale()
                if status == "PARTIAL" and checkpoint:
                    pending["supply_checkpoint"] = checkpoint
                    return self._text_result(
                        "Проверка поставки пока неполная из-за ограниченного поиска. "
                        "Отправьте тот же ID ещё раз, чтобы продолжить с сохранённой страницы."
                    )
                self._pending.pop(owner, None)
            if status == "NOT_FOUND":
                return self._failure(
                    "Завершённая поставка с принятым актом не найдена. Запланированную, "
                    "отменённую или принадлежащую другому магазину поставку связать нельзя. "
                    "Данные FIFO не изменены."
                )
            if "FIFO_SUPPLY_SKU_IDENTITY_MISMATCH" in issues:
                return self._failure(
                    "В акте другая номенклатура. К FIFO-очереди этого SKU поставка не привязана."
                )
            if "SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS" in issues or "FIFO_SUPPLY_SKU_IDENTITY_MISMATCH" in issues:
                return self._failure(
                    "Поставка содержит несколько SKU или неоднозначный состав. Такие поставки "
                    "нельзя автоматически связать с одним FIFO-потоком."
                )
            return self._failure(
                "Не удалось полностью проверить поставку. Черновик закрыт без изменений; "
                "проверьте ID и попробуйте позже."
            )

        snapshot = getattr(result, "supply_snapshot", None)
        quantities = getattr(snapshot, "units_by_sku", None)
        if (
            getattr(snapshot, "store_id", None) != identity["store_id"]
            or not isinstance(quantities, tuple)
            or len(quantities) != 1
            or quantities[0][0] != identity["sku"]
            or type(quantities[0][1]) is not int
            or quantities[0][1] <= 0
            or getattr(snapshot, "effective_at", None) is not None
        ):
            with self._lock:
                self._pending.pop(owner, None)
            return self._failure(
                "Состав или магазин поставки не совпал с текущим SKU. Данные не изменены."
            )
        with self._lock:
            pending = self._pending.get(owner)
            if not isinstance(pending, dict) or pending.get("tenant_scope") != self._tenant_scope():
                self._pending.pop(owner, None)
                return self._stale()
            pending["source_result"] = result
            pending["supply_checkpoint"] = None
            pending["accepted_units"] = quantities[0][1]
            pending["act_dates"] = tuple(
                item.created_date for item in getattr(snapshot, "act_evidence", ())
                if item.created_date
            )
            pending["supply_captured_at"] = snapshot.captured_at
            pending["step"] = "effective_date"
        documentary = ", ".join(pending["act_dates"]) or "не указана"
        return self._text_result(
            f"Поставка проверена: в завершённом акте принято {pending['accepted_units']} шт. "
            f"этого SKU. Дата создания акта: {documentary}; она не подтверждает физическую "
            "дату приёмки.\n\n"
            "Теперь укажите дату, когда новая партия фактически начала поступать в запас "
            "для этого SKU (ГГГГ-ММ-ДД). Это будет отдельно помечено как подтверждение владельца."
        )

    def handle_callback(self, user_id, callback):
        parts = str(callback or "").split(":")
        if len(parts) != 3 or parts[0] != self.CALLBACK_PREFIX:
            return {"error": False, "handled": False, "read_only_ozon": True}
        _prefix, action, draft_id = parts
        if action not in {"confirm", "cancel"}:
            return {"error": False, "handled": False, "read_only_ozon": True}
        owner = self._user_key(user_id)
        if owner is None:
            return self._stale()
        with self._lock:
            self._purge_expired(self.monotonic_clock())
            pending = self._pending.get(owner)
            if (
                not isinstance(pending, dict)
                or pending.get("draft_id") != draft_id
                or pending.get("tenant_scope") != self._tenant_scope()
            ):
                return self._stale()
            if action == "cancel":
                self._pending.pop(owner, None)
                return {
                    "error": False, "handled": True,
                    "message": "Поздний ввод отменён. Данные FIFO не изменены.",
                    "read_only_ozon": True,
                }
            if pending.get("step") == "committed":
                return dict(pending["committed_result"])
            if pending.get("step") != "confirm":
                return self._stale()
            frozen = dict(pending)

        current = self.history_service.get_sku_history(**frozen["identity"])
        if (
            not isinstance(current, dict)
            or current.get("error") is not False
            or current.get("revision") != frozen["expected_revision"]
        ):
            self.clear_pending(user_id)
            return self._failure(
                "FIFO-история изменилась. Черновик не сохранён; откройте SKU заново."
            )
        saved = self.supply_evidence_service.record_late_entry_draft(
            store_id=frozen["identity"]["store_id"],
            product_id=frozen["identity"]["product_id"],
            offer_id=frozen["identity"]["offer_id"],
            sku=frozen["identity"]["sku"],
            expected_revision=frozen["expected_revision"],
            snapshot=frozen["source_result"].supply_snapshot,
            owner_effective_date=frozen["owner_effective_date"],
            owner_old_home_units=frozen["owner_old_home_units"],
            purchase_cost_rub=frozen["purchase_cost_rub"],
            delivery_cost_rub=frozen["delivery_cost_rub"],
            packaging_cost_rub=frozen["packaging_cost_rub"],
        )
        if not isinstance(saved, dict) or saved.get("error") is not False:
            self.clear_pending(user_id)
            return self._failure(
                "Не удалось сохранить поздний черновик: FIFO-история могла измениться. "
                "Прибыль и остатки не изменены; откройте SKU и повторите сверку."
            )
        message = (
            f"✅ Черновик поздней партии сохранён для {frozen['display_name']} · "
            f"SKU {frozen['identity']['sku']}\n"
            f"Дата фактической границы (подтверждена вами): {frozen['owner_effective_date']}\n"
            f"Поставка Ozon №{frozen['supply_id']}\n"
            f"Принято по акту: {saved['accepted_units']} шт.; "
            f"себестоимость: {saved['unit_cost_rub']} ₽/шт.; "
            f"старая партия дома: {frozen['owner_old_home_units']} шт.\n\n"
            "В записи сохранены только хешированные ссылки на поставку и акт, подтверждённые "
            "количества и ваши допущения. FIFO-слои, себестоимость продаж и прибыль пока "
            "не пересчитаны. Для этого потребуется отдельный preview восстановления истории."
        )
        committed = {
            "error": False, "handled": True, "message": message,
            "fifo_late_entry_draft_saved": True, "read_only_ozon": True,
        }
        with self._lock:
            latest = self._pending.get(owner)
            if isinstance(latest, dict) and latest.get("draft_id") == draft_id:
                latest["step"] = "committed"
                latest["committed_result"] = committed
        return dict(committed)

    def clear_pending(self, user_id):
        owner = self._user_key(user_id)
        if owner is not None:
            with self._lock:
                self._pending.pop(owner, None)

    def _confirm_prompt(self, pending):
        unit_cost = sum((Decimal(pending[key]) for key in (
            "purchase_cost_rub", "delivery_cost_rub", "packaging_cost_rub",
        )), Decimal("0.00"))
        effective = pending["owner_effective_date"]
        captured = str(pending.get("supply_captured_at") or "неизвестно")
        documentary = ", ".join(pending.get("act_dates") or ()) or "не указана"
        message = (
            f"Проверьте позднюю партию · {pending['display_name']} · SKU {pending['identity']['sku']}\n\n"
            f"Новая себестоимость: {unit_cost:.2f} ₽/шт.\n"
            f"Дата фактической границы, подтверждённая вами: {effective}\n"
            f"Поставка Ozon №{pending['supply_id']}\n"
            f"Принято в акте Ozon: {pending['accepted_units']} шт.\n"
            f"Дата создания акта (не дата физической приёмки): {documentary}\n"
            f"Старая партия дома на эту дату: {pending['owner_old_home_units']} шт.\n"
            f"Данные Ozon получены ботом: {captured}\n\n"
            "Дата в акте — только дата создания документа. Подтверждение сохраняет отдельный "
            "черновик и источник; оно не меняет остатки FIFO и прибыль."
        )
        return {
            "error": False, "handled": True, "message": message,
            "keyboard": self._confirmation_keyboard(pending["draft_id"]),
            "fifo_late_entry_confirmation_pending": True,
            "read_only_ozon": True,
        }

    @classmethod
    def _confirmation_keyboard(cls, draft_id):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "✅ Сохранить черновик", "callback": f"{cls.CALLBACK_PREFIX}:confirm:{draft_id}"},
                {"text": "Отмена", "callback": f"{cls.CALLBACK_PREFIX}:cancel:{draft_id}"},
            ],
        }

    @classmethod
    def _validate_scope(cls, user_id, identity, expected_revision):
        owner = cls._user_key(user_id)
        tenant = cls._tenant_scope()
        normalized = cls._normalize_identity(identity)
        if (
            owner is None or not tenant or normalized is None
            or type(expected_revision) is not int or expected_revision < 0
        ):
            return None, tenant, None
        _user, tenant_store = split_store_tenant_scope(tenant)
        if tenant_store and normalized["store_id"] != tenant_store:
            return None, tenant, None
        return owner, tenant, normalized

    @staticmethod
    def _normalize_identity(value):
        if not isinstance(value, dict):
            return None
        store_id = str(value.get("store_id") or "").strip()
        sku = str(value.get("sku") or "").strip()
        product_id = str(value.get("product_id") or "").strip() or None
        offer_id = str(value.get("offer_id") or "").strip() or None
        if not store_id or not sku or (product_id is None and offer_id is None):
            return None
        return {"store_id": store_id, "product_id": product_id, "offer_id": offer_id, "sku": sku}

    @classmethod
    def _parse_money(cls, value):
        text = str(value or "").strip().replace(" ", "").replace("\u00a0", "")
        if not re.fullmatch(r"\d+(?:[,.]\d{1,2})?", text):
            return None
        try:
            amount = Decimal(text.replace(",", "."))
        except (InvalidOperation, ValueError):
            return None
        if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
            return None
        return format(amount.quantize(Decimal("0.01")), ".2f")

    @classmethod
    def _parse_units(cls, value):
        text = str(value or "").strip()
        if not re.fullmatch(r"\d{1,7}", text):
            return None
        units = int(text)
        return units if units <= cls.MAX_UNITS else None

    @staticmethod
    def _parse_supply_id(value):
        text = str(value or "").strip()
        return text if re.fullmatch(r"\d{1,19}", text) and int(text) > 0 else None

    @staticmethod
    def _parse_effective_date(value, date_provider):
        try:
            result = date.fromisoformat(str(value or "").strip())
            today = date_provider()
            if isinstance(today, datetime):
                today = today.date()
            if not isinstance(today, date) or result.isoformat() != str(value).strip() or result > today:
                return None
            return result.isoformat()
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _safe_display_name(value):
        return " ".join(str(value or "Товар").split())[:100] or "Товар"

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

    @classmethod
    def _text_result(cls, message):
        return {"error": False, "handled": True, "message": message, "read_only_ozon": True}

    @classmethod
    def _input_error(cls, message):
        return cls._text_result(message)

    @classmethod
    def _failure(cls, message):
        return {"error": True, "handled": True, "message": message, "read_only_ozon": True}

    @classmethod
    def _stale(cls):
        return cls._failure("Черновик устарел или относится к другому магазину. Откройте SKU заново.")

    def _purge_expired(self, now):
        for owner, item in list(self._pending.items()):
            if item.get("expires_at", 0) <= now:
                self._pending.pop(owner, None)

