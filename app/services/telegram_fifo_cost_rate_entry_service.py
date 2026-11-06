"""Owner-facing, revision-bound entry for a new FIFO cost rate."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramFifoCostRateEntryService:
    TTL_SECONDS = 10 * 60
    MAX_PENDING = 128
    MAX_UNITS = 1_000_000
    CALLBACK_PREFIX = "fifo_rate"

    def __init__(self, history_service, rate_service, date_provider=None):
        self.history_service = history_service
        self.rate_service = rate_service
        self.date_provider = date_provider or date.today
        self._pending = {}
        self._lock = RLock()

    def start(self, user_id, identity, display_name, expected_revision):
        owner = self._user_key(user_id)
        tenant = self._tenant_scope()
        normalized = self._normalize_identity(identity)
        if owner is None or not tenant or normalized is None:
            return self._failure("Не удалось открыть этот товар. Откройте его заново в нужном магазине.")
        _user, tenant_store = split_store_tenant_scope(tenant)
        if tenant_store and normalized["store_id"] != tenant_store:
            return self._failure("Товар относится к другому магазину. Откройте его заново.")
        if type(expected_revision) is not int or expected_revision < 0:
            return self._failure("Данные FIFO изменились. Откройте товар заново.")
        snapshot = self.history_service.get_sku_history(**normalized)
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("error") is not False
            or snapshot.get("queue_initialized") is not True
            or snapshot.get("revision") != expected_revision
        ):
            return self._failure(
                "Очередь FIFO изменилась или ещё не настроена. Сначала обновите карточку товара."
            )
        draft_id = uuid4().hex[:16]
        now = monotonic()
        pending = {
            "tenant_scope": tenant,
            "identity": normalized,
            "display_name": self._safe_display_name(display_name),
            "revision": expected_revision,
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
                f"Новая себестоимость · {pending['display_name']} · SKU {normalized['sku']}\n\n"
                "Введите закупочную стоимость одной единицы в ₽. "
                "Доставку до вас и упаковку бот спросит отдельно."
            ),
            "read_only_ozon": True,
        }

    def handle_text(self, user_id, text):
        owner = self._user_key(user_id)
        if owner is None:
            return {"error": False, "handled": False, "read_only_ozon": True}
        with self._lock:
            self._purge_expired(monotonic())
            pending = self._pending.get(owner)
            if pending is None:
                return {"error": False, "handled": False, "read_only_ozon": True}
            if pending["tenant_scope"] != self._tenant_scope():
                self._pending.pop(owner, None)
                return self._stale()
            step = pending["step"]
            if step in {"confirm", "committed"}:
                return {
                    "error": False,
                    "handled": True,
                    "message": "Проверьте расчёт и подтвердите или отмените его кнопкой ниже.",
                    "keyboard": self._confirmation_keyboard(pending["draft_id"]),
                    "read_only_ozon": True,
                }
            if step == "old_home_units":
                units = self._parse_units(text)
                if units is None:
                    return self._input_error(
                        "Введите целое число старых единиц, оставшихся дома. Если их нет, отправьте 0."
                    )
                return self._build_preview(owner, pending, units)

            amount = self._parse_money(text)
            if amount is None:
                return self._input_error(
                    "Не удалось распознать сумму. Введите число в рублях, например 125 или 125,50."
                )
            field_by_step = {
                "purchase_cost": ("purchase_cost_rub", "delivery_cost", "Введите доставку одной единицы до вас в ₽. Если она нулевая, отправьте 0."),
                "delivery_cost": ("delivery_cost_rub", "packaging_cost", "Введите стоимость упаковки одной единицы в ₽. Если она нулевая, отправьте 0."),
                "packaging_cost": ("packaging_cost_rub", "old_home_units", "Сколько единиц старой партии осталось у вас дома? Не включайте товар на Ozon или уже отправленный товар. Если старой партии дома нет, отправьте 0."),
            }
            field = field_by_step.get(step)
            if field is None:
                self._pending.pop(owner, None)
                return self._stale()
            pending[field[0]] = amount
            pending["step"] = field[1]
            return {
                "error": False,
                "handled": True,
                "message": field[2],
                "read_only_ozon": True,
            }

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
            self._purge_expired(monotonic())
            pending = self._pending.get(owner)
            if (
                not isinstance(pending, dict)
                or pending.get("draft_id") != draft_id
            ):
                return self._stale()
            if pending.get("tenant_scope") != self._tenant_scope():
                self._pending.pop(owner, None)
                return self._stale()
            if action == "cancel":
                self._pending.pop(owner, None)
                return {
                    "error": False,
                    "handled": True,
                    "message": "Новая себестоимость не сохранена.",
                    "read_only_ozon": True,
                }
            if pending.get("step") == "committed":
                return dict(pending["committed_result"])
            if pending.get("step") != "confirm":
                return self._stale()
            result = self.rate_service.confirm_new_cost(
                preview_id=pending["preview_id"],
                active_preview_id=pending["preview_id"],
                idempotency_key="rate-" + draft_id,
            )
            if not isinstance(result, dict) or result.get("error") is not False:
                self._pending.pop(owner, None)
                return self._failure(
                    "Не удалось сохранить новую ставку: данные FIFO успели измениться. "
                    "Откройте товар заново и повторите ввод."
                )
            committed = {
                "error": False,
                "handled": True,
                "message": (
                    f"✅ Новая ставка сохранена для {pending['display_name']} · "
                    f"SKU {pending['identity']['sku']}: {pending['unit_cost_rub']} ₽/шт. "
                    f"с {pending['effective_date']}.\n"
                    "Старые конечные слои сохраняются и списываются первыми. "
                    "Количество новой закупки не добавлено, так как оно неизвестно. "
                    "Фактический расчёт прибыли пока не изменён."
                ),
                "fifo_rate_saved": True,
                "read_only_ozon": True,
            }
            pending["step"] = "committed"
            pending["committed_result"] = committed
            return dict(committed)

    def clear_pending(self, user_id):
        owner = self._user_key(user_id)
        if owner is not None:
            with self._lock:
                self._pending.pop(owner, None)

    def _build_preview(self, owner, pending, old_home_units):
        try:
            effective_date = self.date_provider()
            if isinstance(effective_date, datetime):
                effective_date = effective_date.date()
            if not isinstance(effective_date, date):
                effective_date = date.fromisoformat(str(effective_date))
        except (TypeError, ValueError, OverflowError):
            return self._failure("Не удалось определить дату новой ставки. Изменений не внесено.")
        preview = self.rate_service.preview_new_cost(
            **pending["identity"],
            effective_date=effective_date.isoformat(),
            purchase_cost_rub=pending["purchase_cost_rub"],
            delivery_cost_rub=pending["delivery_cost_rub"],
            packaging_cost_rub=pending["packaging_cost_rub"],
            old_home_units=old_home_units,
            expected_revision=pending["revision"],
        )
        if not isinstance(preview, dict) or preview.get("error") is not False:
            self._pending.pop(owner, None)
            return self._failure(
                "Не удалось построить подтверждённый расчёт. Очередь FIFO изменилась или требует сверки; "
                "ничего не сохранено. Откройте товар заново."
            )
        pending.update({
            "old_home_units": old_home_units,
            "preview_id": preview["preview_id"],
            "unit_cost_rub": preview["unit_cost_rub"],
            "effective_date": preview["effective_date"],
            "finite_units_at_anchor": preview["finite_units_at_anchor"],
            "prior_rate_unit_cost_rub": preview.get("prior_rate_unit_cost_rub"),
            "step": "confirm",
        })
        message = (
            f"Проверьте новую себестоимость · {pending['display_name']} · SKU {pending['identity']['sku']}\n\n"
            f"Закупка: {pending['purchase_cost_rub']} ₽/шт.\n"
            f"Доставка до вас: {pending['delivery_cost_rub']} ₽/шт.\n"
            f"Упаковка: {pending['packaging_cost_rub']} ₽/шт.\n"
            f"Новая полная ставка: {pending['unit_cost_rub']} ₽/шт. с {pending['effective_date']}\n"
            f"Остаток старой партии дома: {old_home_units} шт.\n"
            f"Конечные старые единицы на подтверждённом срезе: "
            f"{pending['finite_units_at_anchor']} шт.\n\n"
            "Старые известные слои сохраняются и списываются первыми. "
            "Количество новой партии не задано и не добавляется к остатку. "
            "Эта запись пока не меняет фактическую прибыль в отчётах."
        )
        return {
            "error": False,
            "handled": True,
            "message": message,
            "keyboard": self._confirmation_keyboard(pending["draft_id"]),
            "fifo_rate_confirmation_pending": True,
            "read_only_ozon": True,
        }

    @classmethod
    def _confirmation_keyboard(cls, draft_id):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "✅ Сохранить ставку", "callback": f"{cls.CALLBACK_PREFIX}:confirm:{draft_id}"},
                {"text": "Отмена", "callback": f"{cls.CALLBACK_PREFIX}:cancel:{draft_id}"},
            ],
        }

    @classmethod
    def _input_error(cls, message):
        return {"error": False, "handled": True, "message": message, "read_only_ozon": True}

    @classmethod
    def _failure(cls, message):
        return {"error": True, "handled": True, "message": message, "read_only_ozon": True}

    @classmethod
    def _stale(cls):
        return cls._failure("Подтверждение устарело или относится к другому магазину. Откройте SKU заново.")

    def _purge_expired(self, now):
        for owner, item in list(self._pending.items()):
            if item.get("expires_at", 0) <= now:
                self._pending.pop(owner, None)

    @staticmethod
    def _parse_money(value):
        text = str(value or "").strip().replace(" ", "").replace("\u00a0", "")
        if not text or not re.fullmatch(r"(?:\d+)(?:[,.]\d{1,2})?", text):
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
    def _normalize_identity(value):
        if not isinstance(value, dict):
            return None
        store_id = str(value.get("store_id") or "").strip()
        sku = str(value.get("sku") or "").strip()
        product_id = str(value.get("product_id") or "").strip() or None
        offer_id = str(value.get("offer_id") or "").strip() or None
        if not store_id or not sku or any(ord(ch) < 32 for ch in store_id + sku):
            return None
        return {
            "store_id": store_id,
            "product_id": product_id,
            "offer_id": offer_id,
            "sku": sku,
        }

    @staticmethod
    def _safe_display_name(value):
        text = " ".join(str(value or "Товар").split())
        return text[:100] or "Товар"

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
