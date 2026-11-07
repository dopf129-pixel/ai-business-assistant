"""Owner-confirmed Telegram entry for the first finite FIFO inventory snapshot."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramFifoCostAnchorEntryService:
    CALLBACK_PREFIX = "fifo_anchor"
    TTL_SECONDS = 15 * 60
    MAX_PENDING = 128
    MAX_EVENT_UNITS = FifoCostAnchorService.MAX_EVENT_UNITS
    MAX_STREAM_UNITS = FifoCostAnchorService.MAX_STREAM_UNITS
    MAX_COMMAND_EVENTS = FifoCostAnchorService.MAX_COMMAND_EVENTS
    MAX_REFERENCES_PER_SOURCE = FifoCostAnchorService.MAX_REFERENCES_PER_SOURCE
    # Every layer contributes three zone entries, each either a positive
    # command event or an explicit zero-stock reference.
    MAX_LAYERS = min(
        FifoCostAnchorService.MAX_LAYERS,
        (MAX_COMMAND_EVENTS + MAX_REFERENCES_PER_SOURCE) // 3,
    )
    _CAPACITY_ERRORS = frozenset({
        "FIFO_COMMAND_EVENT_LIMIT",
        "FIFO_SOURCE_REFERENCE_LIMIT",
        "FIFO_STREAM_QUANTITY_LIMIT",
    })

    def __init__(self, history_service, anchor_service, *, date_provider=None):
        self.history_service = history_service
        self.anchor_service = anchor_service
        self.date_provider = date_provider or date.today
        self._pending = {}
        self._lock = RLock()

    def start(self, user_id, identity, display_name, expected_revision):
        owner = self._user_key(user_id)
        tenant = self._tenant_scope()
        normalized = self._identity(identity)
        if owner is None or not tenant or normalized is None:
            return self._failure("Не удалось открыть SKU. Откройте товар заново в нужном магазине.")
        _owner, store = split_store_tenant_scope(tenant)
        if not store or store != normalized["store_id"]:
            return self._failure("Товар относится к другому магазину. Начальный остаток не записан.")
        current = self.history_service.get_sku_history(**normalized)
        if (
            not isinstance(current, dict) or current.get("error") is not False
            or current.get("queue_initialized") is not False
            or current.get("revision") != expected_revision
        ):
            return self._failure("FIFO уже настроен или история изменилась. Обновите карточку товара.")
        draft = {
            "tenant_scope": tenant,
            "identity": normalized,
            "display_name": self._safe_name(display_name),
            "revision": expected_revision,
            "draft_id": uuid4().hex[:16],
            "step": "cutoff",
            "layers": [],
            "expires_at": monotonic() + self.TTL_SECONDS,
        }
        with self._lock:
            self._purge_expired()
            self._pending[owner] = draft
            while len(self._pending) > self.MAX_PENDING:
                oldest = min(self._pending, key=lambda key: self._pending[key]["expires_at"])
                self._pending.pop(oldest, None)
        return self._prompt(
            f"Начальный FIFO-остаток · {draft['display_name']}\nSKU: {normalized['sku']}\n\n"
            "Укажите дату, на которую известны остатки, в формате ГГГГ-ММ-ДД. "
            "Дата не должна быть в будущем. Это будет граница начала FIFO-истории."
        )

    def handle_text(self, user_id, text):
        owner = self._user_key(user_id)
        if owner is None:
            return {"error": False, "handled": False, "read_only_ozon": True}
        with self._lock:
            self._purge_expired()
            draft = self._pending.get(owner)
            if draft is None:
                return {"error": False, "handled": False, "read_only_ozon": True}
            if draft["tenant_scope"] != self._tenant_scope():
                self._pending.pop(owner, None)
                return self._failure("Магазин изменился. Черновик сброшен, данные не записаны.")
            if draft.get("committed_result") is not None:
                return {"error": False, "handled": False, "read_only_ozon": True}
            if draft["step"] == "confirm":
                return self._confirmation(draft)
            step = draft["step"]

        if step == "cutoff":
            value = self._parse_date(text)
            today = self._today()
            if value is None or today is None or date.fromisoformat(value) > today:
                return self._input_error("Введите действительную дату не позже сегодняшней: ГГГГ-ММ-ДД.")
            self._set(owner, step, cutoff_date=value, step_next="layer_count")
            return self._prompt(
                "Сколько старых партий с разной себестоимостью было в остатке на эту дату? "
                f"Введите целое число от 1 до {self.MAX_LAYERS}."
            )

        if step == "layer_count":
            count = self._parse_int(text, minimum=1, maximum=self.MAX_LAYERS)
            if count is None:
                return self._input_error(f"Введите количество партий от 1 до {self.MAX_LAYERS}.")
            self._set(owner, step, layer_count=count, step_next="layer")
            return self._layer_prompt(1, count)

        if step == "layer":
            row = self._parse_layer(text)
            if row is None:
                return self._input_error(
                    "Для партии введите четыре значения через точку с запятой: "
                    f"себестоимость ₽; на Ozon; в пути; дома. Количество в каждой зоне — "
                    f"от 0 до {self.MAX_EVENT_UNITS:,}. Например: 120,50; 40; 0; 3"
                )
            with self._lock:
                draft = self._pending.get(owner)
                if not isinstance(draft, dict) or draft.get("step") != "layer":
                    return self._stale()
                sequence = len(draft["layers"]) + 1
                candidate_layers = [
                    *draft["layers"], {"sequence": sequence, **row},
                ]
                count = draft["layer_count"]
                capacity_error = self._layer_capacity_error(
                    candidate_layers, total_layer_count=count,
                )
                if capacity_error:
                    return self._input_error(
                        self._capacity_error_message(capacity_error)
                    )
                draft["layers"] = candidate_layers
                if sequence < count:
                    return self._layer_prompt(sequence + 1, count)
                draft["step"] = "layer_order_confirmation"
            return self._prompt(
                "Партии введены от самой старой к самой новой? FIFO будет списывать их именно в этом порядке. "
                "Ответьте ДА, чтобы подтвердить порядок; если не уверены, отправьте НЕТ — запись остановится."
            )

        if step in {"layer_order_confirmation", "ozon_confirmation", "transit_confirmation"}:
            answer = self._yes_no(text)
            if answer is None:
                return self._input_error("Ответьте ДА или НЕТ.")
            if not answer:
                self.clear_pending(user_id)
                if step == "layer_order_confirmation":
                    return self._failure(
                        "Порядок партий не подтверждён. Черновик удалён; FIFO-история не изменена."
                    )
                return self._failure(
                    "Начальную FIFO-очередь нельзя подтвердить без этих данных. "
                    "Черновик удалён; история и расчёты не изменились."
                )
            if step == "layer_order_confirmation":
                self._set(owner, step, step_next="ozon_confirmation")
                return self._prompt(
                    "Подтверждаете, что количество «на Ozon» включает зарезервированные единицы? "
                    "Ответьте ДА. Если не можете подтвердить, отправьте НЕТ — настройка остановится."
                )
            if step == "ozon_confirmation":
                self._set(owner, step, step_next="transit_confirmation")
                return self._prompt(
                    "Подтверждаете, что остаток «в пути» не входит в количество Ozon и не дублирует "
                    "остаток дома? Ответьте ДА. Если нет — отправьте НЕТ."
                )
            return self._build_preview(owner)

        return self._stale()

    def handle_callback(self, user_id, callback):
        parts = str(callback or "").split(":")
        if len(parts) != 3 or parts[0] != self.CALLBACK_PREFIX:
            return {"error": False, "handled": False, "read_only_ozon": True}
        _prefix, action, draft_id = parts
        if action not in {"confirm", "cancel"}:
            return {"error": False, "handled": False, "read_only_ozon": True}
        owner = self._user_key(user_id)
        with self._lock:
            self._purge_expired()
            draft = self._pending.get(owner)
            if not isinstance(draft, dict) or draft.get("draft_id") != draft_id:
                return self._stale()
            if draft.get("tenant_scope") != self._tenant_scope():
                self._pending.pop(owner, None)
                return self._stale()
            if draft.get("committed_result") is not None:
                return dict(draft["committed_result"])
            if action == "cancel":
                self._pending.pop(owner, None)
                return self._prompt("Начальная FIFO-очередь не записана. Данные не изменились.")
            if draft.get("step") != "confirm" or not isinstance(draft.get("preview"), dict):
                return self._stale()

        current = self.history_service.get_sku_history(**draft["identity"])
        if (
            not isinstance(current, dict) or current.get("error") is not False
            or current.get("revision") != draft["revision"]
            or current.get("queue_initialized") is not False
        ):
            self.clear_pending(user_id)
            return self._failure("FIFO-история изменилась. Старая кнопка не записала данные; откройте SKU заново.")
        preview_id = draft["preview"]["preview_id"]
        result = self.anchor_service.commit_opening_anchor(
            preview_id=preview_id,
            active_preview_id=preview_id,
            idempotency_key="anchor-" + draft_id,
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            self.clear_pending(user_id)
            return self._failure("Не удалось сохранить стартовый остаток: FIFO изменилась. Откройте товар заново.")
        response = self._prompt(
            f"✅ Начальная FIFO-очередь записана для {draft['display_name']} · SKU {draft['identity']['sku']}.\n"
            f"Срез: {draft['cutoff_date']}; партий: {len(draft['layers'])}; "
            f"единиц: {draft['preview']['total_units']}.\n"
            "Это начальная запись владельца. Фактическая себестоимость в отчётах прибыли "
            "не включена: общий cutoff продаж и остатков ещё требует отдельной сверки."
        )
        response["fifo_anchor_saved"] = True
        with self._lock:
            current_draft = self._pending.get(owner)
            if isinstance(current_draft, dict) and current_draft.get("draft_id") == draft_id:
                current_draft["committed_result"] = dict(response)
        return response

    def clear_pending(self, user_id):
        owner = self._user_key(user_id)
        if owner is not None:
            with self._lock:
                self._pending.pop(owner, None)

    def _build_preview(self, owner):
        with self._lock:
            draft = self._pending.get(owner)
            if not isinstance(draft, dict):
                return self._stale()
            snapshot = dict(draft)
            snapshot["layers"] = [dict(row) for row in draft["layers"]]
        preview = self.anchor_service.preview_opening_anchor(
            **snapshot["identity"],
            inventory_cutoff=snapshot["cutoff_date"],
            cost_layers=snapshot["layers"],
            ozon_units_include_reserved_confirmed=True,
            transit_not_in_ozon_confirmed=True,
            expected_revision=snapshot["revision"],
        )
        if not isinstance(preview, dict) or preview.get("error") is not False:
            code = preview.get("code") if isinstance(preview, dict) else None
            if code in self._CAPACITY_ERRORS:
                with self._lock:
                    current = self._pending.get(owner)
                    if (
                        isinstance(current, dict)
                        and current.get("draft_id") == snapshot.get("draft_id")
                        and current.get("layers")
                    ):
                        current["layers"].pop()
                        current["step"] = "layer"
                return self._input_error(
                    "Проверка обнаружила превышение лимита хранения. Черновик сохранён; "
                    "повторно введите последнюю партию с допустимыми количествами."
                )
            self.clear_pending(owner)
            return self._failure("Не удалось проверить остатки и партии. Ничего не записано; начните заново.")
        with self._lock:
            draft = self._pending.get(owner)
            if not isinstance(draft, dict) or draft.get("draft_id") != snapshot["draft_id"]:
                return self._stale()
            draft["preview"] = preview
            draft["step"] = "confirm"
        return self._confirmation(draft)

    def _confirmation(self, draft):
        preview = draft.get("preview") or {}
        zones = preview.get("zone_totals") or {}
        layer_lines = []
        for index, layer in enumerate(draft.get("layers") or (), start=1):
            total_units = sum(
                layer.get(key, 0)
                for key in ("ozon_units", "transit_units", "home_units")
            )
            layer_lines.append(
                f"{index}:{total_units}@{layer.get('unit_cost_rub')}"
            )
        layer_summary = "\n".join(layer_lines)
        return {
            "error": False,
            "handled": True,
            "message": (
                f"Проверьте начальный остаток · {draft['display_name']}\n"
                f"Срез: {draft['cutoff_date']}\n"
                f"Партий: {len(draft['layers'])}; всего единиц: {preview.get('total_units')}\n"
                "Порядок FIFO: от самой старой партии к новой. Слои (№: шт.@₽/шт.):\n"
                f"{layer_summary}\n"
                f"На Ozon: {zones.get('OZON', 0)}; в пути: {zones.get('TRANSIT', 0)}; дома: {zones.get('HOME', 0)}\n"
                f"Известная стоимость остатка: {preview.get('known_cost_rub')} ₽.\n\n"
                "Подтвердить запись? Она не включает FIFO-себестоимость в финансовые отчёты."
            ),
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [
                    {"text": "✅ Подтвердить остаток", "callback": f"{self.CALLBACK_PREFIX}:confirm:{draft['draft_id']}"},
                    {"text": "Отмена", "callback": f"{self.CALLBACK_PREFIX}:cancel:{draft['draft_id']}"},
                ],
            },
            "fifo_anchor_confirmation_pending": True,
            "read_only_ozon": True,
        }

    def _set(self, owner, expected_step, **values):
        with self._lock:
            draft = self._pending.get(owner)
            if not isinstance(draft, dict) or draft.get("step") != expected_step:
                return False
            next_step = values.pop("step_next", None)
            draft.update(values)
            if next_step is not None:
                draft["step"] = next_step
            return True

    def _layer_prompt(self, index, count):
        return self._prompt(
            f"Партия {index} из {count}. Вводите от самой старой к самой новой. "
            "FIFO будет списывать партии в этом порядке. Формат: себестоимость за единицу ₽; "
            "количество на Ozon; в пути; дома. Количества — целые, неизвестное нельзя указывать как 0. "
            "Например: 120,50; 40; 0; 3"
        )

    @classmethod
    def _layer_capacity_error(cls, layers, *, total_layer_count):
        event_count = 0
        reference_count = 0
        total_units = 0
        for layer in layers:
            for field in ("ozon_units", "transit_units", "home_units"):
                quantity = layer[field]
                if quantity:
                    event_count += 1
                    total_units += quantity
                else:
                    reference_count += 1

        if event_count > cls.MAX_COMMAND_EVENTS:
            return "events"
        if reference_count > cls.MAX_REFERENCES_PER_SOURCE:
            return "references"

        remaining_layers = total_layer_count - len(layers)
        if remaining_layers < 0:
            return "layers"
        event_capacity = cls.MAX_COMMAND_EVENTS - event_count
        reference_capacity = cls.MAX_REFERENCES_PER_SOURCE - reference_count
        future_zone_count = 3 * remaining_layers
        minimum_future_events = max(
            remaining_layers,
            future_zone_count - reference_capacity,
        )
        maximum_future_events = min(future_zone_count, event_capacity)
        if minimum_future_events > maximum_future_events:
            return "future_capacity"
        if total_units + remaining_layers > cls.MAX_STREAM_UNITS:
            return "stream_quantity"
        return None

    @classmethod
    def _capacity_error_message(cls, code):
        if code == "events":
            return (
                f"Слишком много заполненных зон: хранилище принимает не более "
                f"{cls.MAX_COMMAND_EVENTS} записей за один начальный остаток. "
                "Партия не добавлена; скорректируйте её и отправьте повторно."
            )
        if code == "references":
            return (
                f"Слишком много нулевых зон: хранилище принимает не более "
                f"{cls.MAX_REFERENCES_PER_SOURCE} подтверждений. "
                "Партия не добавлена; скорректируйте её и отправьте повторно."
            )
        if code == "stream_quantity":
            return (
                f"Общее количество превышает лимит {cls.MAX_STREAM_UNITS:,} единиц. "
                "Партия не добавлена; скорректируйте её и отправьте повторно."
            )
        return (
            "Это распределение не оставляет допустимых лимитов для оставшихся партий. "
            "Партия не добавлена; измените её и отправьте повторно."
        )

    def _today(self):
        try:
            value = self.date_provider()
            return value.date() if isinstance(value, datetime) else value if isinstance(value, date) else date.fromisoformat(str(value))
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _parse_date(value):
        text = str(value or "").strip()
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == text else None

    @classmethod
    def _parse_layer(cls, value):
        parts = [part.strip() for part in str(value or "").split(";")]
        if len(parts) != 4:
            return None
        try:
            cost = Decimal(parts[0].replace(" ", "").replace(",", "."))
        except InvalidOperation:
            return None
        if not cost.is_finite() or cost < 0 or cost > Decimal("1000000000"):
            return None
        quantities = [
            cls._parse_int(item, minimum=0, maximum=cls.MAX_EVENT_UNITS)
            for item in parts[1:]
        ]
        if any(item is None for item in quantities) or sum(quantities) <= 0:
            return None
        return {
            "unit_cost_rub": format(
                cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f",
            ),
            "ozon_units": quantities[0],
            "transit_units": quantities[1],
            "home_units": quantities[2],
        }

    @staticmethod
    def _parse_int(value, *, minimum, maximum):
        text = str(value or "").strip()
        if not re.fullmatch(r"0|[1-9][0-9]*", text):
            return None
        result = int(text)
        return result if minimum <= result <= maximum else None

    @staticmethod
    def _yes_no(value):
        text = str(value or "").strip().casefold()
        if text in {"да", "д", "yes", "y"}:
            return True
        if text in {"нет", "н", "no", "n"}:
            return False
        return None

    @staticmethod
    def _identity(value):
        if not isinstance(value, dict):
            return None
        store = str(value.get("store_id") or "").strip()
        sku = str(value.get("sku") or "").strip()
        product = str(value.get("product_id") or "").strip() or None
        offer = str(value.get("offer_id") or "").strip() or None
        if not store or not sku or not (product or offer):
            return None
        return {"store_id": store, "product_id": product, "offer_id": offer, "sku": sku}

    @staticmethod
    def _tenant_scope():
        try:
            return str(get_current_tenant_user_id() or "")
        except Exception:
            return ""

    @staticmethod
    def _user_key(value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _safe_name(value):
        return " ".join(str(value or "Товар").split())[:120] or "Товар"

    def _purge_expired(self):
        now = monotonic()
        for owner in [key for key, draft in self._pending.items() if draft.get("expires_at", 0) <= now]:
            self._pending.pop(owner, None)

    @staticmethod
    def _prompt(message):
        return {"error": False, "handled": True, "message": message, "read_only_ozon": True}

    @staticmethod
    def _input_error(message):
        return {"error": False, "handled": True, "message": message, "read_only_ozon": True}

    @staticmethod
    def _failure(message):
        return {"error": True, "handled": True, "message": message, "read_only_ozon": True, "executed": False}

    @staticmethod
    def _stale():
        return TelegramFifoCostAnchorEntryService._failure(
            "Черновик начального остатка устарел. Откройте SKU заново; данные не изменены."
        )
