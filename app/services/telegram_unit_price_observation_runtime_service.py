"""Tenant-scoped Telegram lifecycle for saved seller-price observations."""
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from secrets import token_hex
from threading import RLock
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.ozon_account_repository import split_store_tenant_scope
from services.planning_cross_docking_adapter import PlanningCrossDockingAdapter
from services.tenant_context import get_current_tenant_user_id
from services.unit_price_observation_normalizer import UnitPriceObservationNormalizer
from services.unit_price_observation_quality_service import UnitPriceObservationQualityService


class TelegramUnitPriceObservationRuntimeService:
    """Expose the Q16-Q19 evidence pipeline without changing Ozon settings."""
    DEFAULT_TIMEZONE = "Europe/Moscow"
    PLAN_TOKEN_TTL_SECONDS = 900
    PENDING_TTL_SECONDS = 600
    PAGE_SIZE = 10
    MAX_PRICE_CENTS = 999_999_999_999_999
    _ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

    def __init__(self, *, repository, planning_service, collection_service,
                 result_service, keyboard_service, normalizer=None, clock=None,
                 monotonic_clock=None, default_timezone=DEFAULT_TIMEZONE,
                 quality_service=None):
        self.repository = repository
        self.planning_service = planning_service
        self.collection_service = collection_service
        self.result_service = result_service
        self.keyboard_service = keyboard_service
        self.normalizer = normalizer or UnitPriceObservationNormalizer
        self.quality_service = quality_service or UnitPriceObservationQualityService()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic_clock = monotonic_clock or monotonic
        self.default_timezone = default_timezone
        self._lock = RLock()
        self._plan_tokens = OrderedDict()
        self._pending = OrderedDict()
        self._collecting = set()

    def plan_start_callback(self, scope, document, *, item_index=0):
        """Return a short, tenant-bound callback for one saved FBO plan row."""
        if not isinstance(scope, dict) or not isinstance(document, dict):
            return None
        payload = document.get("payload")
        items = payload.get("items") if isinstance(payload, dict) else None
        if (document.get("status") == "ARCHIVED" or not isinstance(items, list)
                or type(item_index) is not int or not 0 <= item_index < len(items)):
            return None
        if not self._plan_item(items[item_index], scope.get("store_id")):
            return None
        record = {
            "owner_id": str(scope.get("owner_id") or ""),
            "store_id": str(scope.get("store_id") or ""),
            "tenant_scope": str(scope.get("tenant_scope") or ""),
            "document_id": str(document.get("document_id") or ""),
            "revision": document.get("revision"),
            "item_index": item_index,
            "created_at": self.monotonic_clock(),
        }
        if (not record["owner_id"] or not record["document_id"]
                or type(record["revision"]) is not int or record["revision"] < 1):
            return None
        token = token_hex(8)
        with self._lock:
            self._prune_locked()
            self._plan_tokens[token] = record
            self._plan_tokens.move_to_end(token)
            while len(self._plan_tokens) > 256:
                self._plan_tokens.popitem(last=False)
        return f"upo:p:{token}"

    def handle_callback(self, callback, *, user_id=None):
        scope = self._scope(user_id)
        if scope is None:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        value = str(callback or "").strip()
        parts = value.split(":")
        if value == "upo:m":
            self._clear_pending(scope)
            return self._list(scope)
        if len(parts) == 3 and parts[:2] == ["upo", "p"]:
            return self._begin_from_saved_plan(parts[2], scope)
        if len(parts) == 3 and parts[:2] == ["upo", "confirm"]:
            return self._confirm_start(parts[2], scope)
        if len(parts) == 3 and parts[:2] == ["upo", "o"]:
            self._clear_pending(scope)
            return self._card(parts[2], scope)
        if len(parts) == 5 and parts[:2] == ["upo", "collect"]:
            return self._prompt_window(parts[2], parts[3], parts[4], scope)
        if len(parts) == 3 and parts[:2] == ["upo", "history"]:
            self._clear_pending(scope)
            return self._history(parts[2], scope)
        if len(parts) == 4 and parts[:2] == ["upo", "h"]:
            try:
                offset = int(parts[3])
            except ValueError:
                return self._stale()
            self._clear_pending(scope)
            return self._history(parts[2], scope, offset=offset)
        if len(parts) == 4 and parts[:2] == ["upo", "result"]:
            try:
                revision = int(parts[3])
            except ValueError:
                return self._stale()
            self._clear_pending(scope)
            return self._result_detail(parts[2], revision, scope)
        if len(parts) == 4 and parts[:2] == ["upo", "note"]:
            return self._prompt_note(parts[2], parts[3], scope)
        if len(parts) == 4 and parts[:2] == ["upo", "finish"]:
            return self._finish(parts[2], parts[3], scope)
        if len(parts) == 3 and parts[:2] == ["upo", "l"]:
            try:
                offset = int(parts[2])
            except ValueError:
                return self._stale()
            self._clear_pending(scope)
            return self._list(scope, offset=offset)
        return self._stale()

    def handle_text(self, text, *, user_id=None):
        scope = self._scope(user_id)
        if scope is None:
            return None
        pending = self._get_pending(scope)
        if pending is None:
            return None
        value = str(text or "").strip()
        if pending.get("stage") == "price":
            cents = self._parse_price(value)
            if cents is None:
                return self._prompt_result(
                    "PRICE_INPUT_REQUIRED",
                    "Введите установленную в кабинете цену продавца, например 100 или 99,90 ₽. Бот цену в Ozon не меняет.",
                    self._simple_keyboard("Отмена", "upo:m"),
                )
            pending["seller_price_cents"] = cents
            pending["stage"] = "effective_from"
            self._set_pending(scope, pending)
            return self._prompt_result(
                "EFFECTIVE_TIME_INPUT_REQUIRED",
                f"Цена {self._format_money(cents)} ₽ записана как ваше подтверждение, не как факт из API. Введите дату и время установки с часовым поясом, например 2026-10-27T12:00:00+03:00.",
                self._simple_keyboard("Отмена", "upo:m"),
            )
        if pending.get("stage") == "effective_from":
            moment = self._parse_effective_time(value)
            if moment is None:
                return self._prompt_result(
                    "EFFECTIVE_TIME_INPUT_REQUIRED",
                    "Нужен ISO-формат с часовым поясом, например 2026-10-27T12:00:00+03:00. Цена сохранена во временном черновике.",
                    self._simple_keyboard("Отмена", "upo:m"),
                )
            now = self.clock()
            if now.tzinfo is None or now.utcoffset() is None:
                return self._error("PLANNING_CLOCK_UNAVAILABLE")
            if moment.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                return self._prompt_result(
                    "EFFECTIVE_TIME_INPUT_REQUIRED",
                    "Дата установки цены не может быть в будущем. Введите фактические дату и время.",
                    self._simple_keyboard("Отмена", "upo:m"),
                )
            pending["effective_from"] = moment.isoformat()
            pending["stage"] = "confirm_start"
            self._set_pending(scope, pending)
            identity = pending["identity"]
            message = (
                "Проверьте наблюдение цены\n"
                f"SKU {identity['sku']} · FBO\n"
                f"Цена по вашему подтверждению: {self._format_money(pending['seller_price_cents'])} ₽\n"
                f"Установлена: {pending['effective_from']}\n"
                f"Часовой пояс окон: {self.default_timezone}\n\n"
                "Цена введена вами вручную. Ozon не изменится. Подтвердить запись?"
            )
            return self._prompt_result(
                "OBSERVATION_START_PREVIEW", message,
                self._simple_keyboard("Подтвердить наблюдение", f"upo:confirm:{pending['token']}", cancel=True),
            )
        if pending.get("stage") == "window":
            return self._collect_window(value, pending, scope)
        if pending.get("stage") == "note":
            return self._save_note(value, pending, scope)
        self._clear_pending(scope)
        return None

    def clear_pending(self, user_id):
        scope = self._scope(user_id)
        if scope is not None:
            self._clear_pending(scope)

    def clear_user_state(self, user_id):
        self.clear_pending(user_id)

    def _begin_from_saved_plan(self, token, scope):
        with self._lock:
            self._prune_locked()
            record = deepcopy(self._plan_tokens.get(token))
        if not self._record_matches_scope(record, scope):
            return self._stale()
        loaded = self.planning_service.get_document(record["document_id"], revision=record["revision"])
        if not isinstance(loaded, dict) or loaded.get("error") is True:
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_NOT_FOUND")
        document = loaded.get("document") or {}
        payload = document.get("payload") or {}
        items = payload.get("items")
        item_index = record.get("item_index")
        if (document.get("document_id") != record["document_id"]
                or document.get("revision") != record["revision"]
                or document.get("status") == "ARCHIVED"
                or not isinstance(items, list) or type(item_index) is not int
                or not 0 <= item_index < len(items)
                or not self._plan_item(items[item_index], scope["store_id"])):
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH")
        identity = items[item_index]["identity"]
        self._set_pending(scope, {
            "stage": "price", "token": token,
            "document_id": record["document_id"], "revision": record["revision"],
            "item_index": record["item_index"],
            "identity": self._observation_identity(identity, scope["store_id"]),
            "source_plan": deepcopy(document), "created_at": self.monotonic_clock(),
        })
        return self._prompt_result(
            "SELLER_PRICE_INPUT_REQUIRED",
            f"Введите цену продавца, которую вы уже установили в Ozon, для SKU {identity.get('sku')}, например 100 или 99,90. Это ваше подтверждение; бот цену не меняет.",
            self._simple_keyboard("Отмена", "upo:m"),
        )

    def _confirm_start(self, token, scope):
        pending = self._get_pending(scope)
        if pending is not None and pending.get("stage") == "created" and pending.get("token") == token:
            return self._card(pending["observation_id"], scope, message="Наблюдение уже зарегистрировано.")
        if (pending is None or pending.get("stage") != "confirm_start"
                or pending.get("token") != token):
            return self._stale()
        document = pending.get("source_plan") or {}
        payload = document.get("payload") or {}
        items = payload.get("items")
        item_index = pending.get("item_index")
        if (not isinstance(items, list) or type(item_index) is not int
                or not 0 <= item_index < len(items)
                or not self._plan_item(items[item_index], scope["store_id"])
                or document.get("document_id") != pending.get("document_id")
                or document.get("revision") != pending.get("revision")):
            self._clear_pending(scope)
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH")
        current_plan = self.planning_service.get_document(
            pending["document_id"], revision=pending["revision"],
        )
        if not isinstance(current_plan, dict) or current_plan.get("error") is True:
            self._clear_pending(scope)
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_NOT_FOUND")
        current_document = current_plan.get("document") or {}
        if (current_document.get("status") != "ACTIVE"
                or current_document.get("document_id") != pending["document_id"]
                or current_document.get("revision") != pending["revision"]):
            self._clear_pending(scope)
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH")
        identity = pending["identity"]
        result = self.repository.start_unit_price_observation(
            identity={key: identity[key] for key in ("product_id", "offer_id", "sku", "sale_schema")},
            seller_price_cents=pending["seller_price_cents"],
            source_document_id=pending["document_id"],
            source_document_revision=pending["revision"],
            effective_from=pending["effective_from"],
            window_timezone=self.default_timezone, owner_confirmed=True,
            idempotency_key="upo-start-" + token,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(result, dict) or result.get("error") is True:
            self._clear_pending(scope)
            return self._error(result.get("code") if isinstance(result, dict) else None)
        observation_id = result.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id:
            self._clear_pending(scope)
            return self._list(scope, message="Наблюдение уже зарегистрировано.")
        pending["stage"] = "created"
        pending["observation_id"] = observation_id
        self._set_pending(scope, pending)
        return self._card(observation_id, scope, message="Наблюдение создано.")

    def _prompt_window(self, observation_id, state_revision, result_revision, scope):
        loaded = self._load_observation(observation_id, scope)
        if loaded is None:
            return self._stale()
        observation = loaded["observation"]
        if (observation.get("status") != "ACTIVE"
                or str(observation.get("state_revision")) != str(state_revision)
                or str(observation.get("result_revision")) != str(result_revision)):
            return self._stale()
        self._set_pending(scope, {
            "stage": "window", "observation_id": observation_id,
            "state_revision": observation["state_revision"],
            "result_revision": observation["result_revision"],
            "created_at": self.monotonic_clock(),
        })
        return self._prompt_result(
            "OBSERVATION_WINDOW_INPUT_REQUIRED",
            f"Введите готовое окно дат для SKU {observation['identity']['sku']}: YYYY-MM-DD - YYYY-MM-DD. Нужно от 3 до 56 завершённых дней, начиная не раньше установки цены ({observation['effective_from']}); часовой пояс {observation['window_timezone']}. Пример: 2026-10-01 - 2026-10-07.",
            self._simple_keyboard("Отмена", f"upo:o:{observation_id}"),
        )

    def _collect_window(self, value, pending, scope):
        dates = self._ISO_DATE.findall(value)
        if len(dates) != 2:
            return self._prompt_result(
                "OBSERVATION_WINDOW_INPUT_REQUIRED",
                "Укажите ровно две даты в формате YYYY-MM-DD - YYYY-MM-DD. Запись пока не изменена.",
                self._simple_keyboard("Отмена", f"upo:o:{pending['observation_id']}"),
            )
        try:
            start, end = (date.fromisoformat(item) for item in dates)
        except ValueError:
            start = end = None
        if start is None or end is None or start > end or not 3 <= (end - start).days + 1 <= 56:
            return self._prompt_result(
                "OBSERVATION_WINDOW_INPUT_REQUIRED",
                "Окно должно содержать от 3 до 56 календарных дней. Пример: 2026-10-01 - 2026-10-07.",
                self._simple_keyboard("Отмена", f"upo:o:{pending['observation_id']}"),
            )
        loaded = self._load_observation(pending["observation_id"], scope)
        if loaded is None:
            return self._stale()
        observation = loaded["observation"]
        try:
            zone = ZoneInfo(observation["window_timezone"])
            now = self.clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("clock must be timezone-aware")
            local_today = now.astimezone(zone).date()
            effective = self._parse_effective_time(observation["effective_from"])
            if effective is None:
                raise ValueError("effective time is invalid")
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
            return self._error("PLANNING_CLOCK_UNAVAILABLE")
        earliest = effective.astimezone(zone).date()
        if end >= local_today or start < earliest:
            return self._prompt_result(
                "OBSERVATION_WINDOW_INPUT_REQUIRED",
                f"Окно должно быть завершённым и начинаться не раньше {earliest.isoformat()} — даты установки цены по вашему подтверждению. Исправьте даты; источник пока не запрашивался.",
                self._simple_keyboard("Отмена", f"upo:o:{pending['observation_id']}"),
            )
        key = (scope["tenant_scope"], pending["observation_id"])
        with self._lock:
            if key in self._collecting:
                return self._prompt_result(
                    "OBSERVATION_COLLECTION_IN_PROGRESS",
                    "Сбор для этого наблюдения уже выполняется. Дождитесь ответа первого запроса.",
                    self._simple_keyboard("Открыть карточку", f"upo:o:{pending['observation_id']}"),
                )
            self._collecting.add(key)
        try:
            return self._collect_and_persist(pending, start.isoformat(), end.isoformat(), scope)
        finally:
            with self._lock:
                self._collecting.discard(key)
                self._pending.pop(scope["key"], None)

    def _collect_and_persist(self, pending, date_from, date_to, scope):
        observation_id = pending["observation_id"]
        loaded = self._load_observation(observation_id, scope)
        if loaded is None:
            return self._stale()
        observation = loaded["observation"]
        if (observation.get("status") != "ACTIVE"
                or observation.get("state_revision") != pending["state_revision"]
                or observation.get("result_revision") != pending["result_revision"]):
            return self._stale()
        try:
            collected = self.collection_service.collect_window(
                observation_id, date_from=date_from, date_to=date_to,
            )
        except Exception:
            collected = None
        if self._scope_from_context() != scope["tenant_scope"]:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        if not isinstance(collected, dict) or collected.get("error") is True:
            code = collected.get("code") if isinstance(collected, dict) else None
            return self._error(code or "UNIT_PRICE_OBSERVATION_COLLECTION_UNAVAILABLE")
        normalized = self.normalizer.normalize_collected(collected)
        if not isinstance(normalized, dict) or normalized.get("error") is True:
            return self._error(normalized.get("code") if isinstance(normalized, dict) else None)
        source_plan = observation.get("source_plan") or {}
        plan_result = self.planning_service.get_document(
            source_plan.get("document_id"), revision=source_plan.get("revision"),
        )
        if not isinstance(plan_result, dict) or plan_result.get("error") is True:
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_NOT_FOUND")
        plan = plan_result.get("document") or {}
        if plan.get("document_id") != source_plan.get("document_id") or plan.get("revision") != source_plan.get("revision"):
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH")
        plan_payload = plan.get("payload") or {}
        items = plan_payload.get("items")
        if not isinstance(items, list):
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH")
        matching_items = [
            item for item in items
            if isinstance(item, dict) and self._same_plan_identity(
                item.get("identity"), observation, scope["store_id"],
            )
        ]
        if len(matching_items) != 1:
            return self._error("PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH")
        item = matching_items[0]
        item_identity = item.get("identity")
        scenario_inputs, _ = PlanningCrossDockingAdapter.restore_item(plan_payload, item)
        if not isinstance(scenario_inputs, dict):
            return self._error("PLANNING_OBSERVATION_SCENARIO_INPUTS_UNAVAILABLE")
        scenario_inputs = deepcopy(scenario_inputs)
        scenario_inputs["price"] = self._format_money(observation["seller_price_cents"])
        scenario_identity = deepcopy(item_identity or {})
        scenario_identity["store_id"] = scope["store_id"]
        provenance = deepcopy(item.get("provenance") or {})
        provenance["price"] = "OWNER_DECLARED_OBSERVATION_PRICE"
        evaluated = self.result_service.evaluate(
            normalized, scenario_inputs=scenario_inputs,
            identity=scenario_identity, provenance=provenance,
            planning_sources=item.get("sources") if isinstance(item.get("sources"), dict) else {},
        )
        if not isinstance(evaluated, dict) or evaluated.get("error") is True:
            return self._error("UNIT_PRICE_OBSERVATION_EVALUATION_UNAVAILABLE")
        result_payload = self._persistable_result(evaluated)
        if result_payload is None:
            return self._error("PLANNING_OBSERVATION_RESULT_INVALID")
        saved = self.repository.append_unit_price_observation_result(
            observation_id, result_payload,
            expected_state_revision=pending["state_revision"],
            expected_result_revision=pending["result_revision"],
            idempotency_key=f"upo-result-{observation_id[:18]}-{pending['result_revision'] + 1}-{date_from}-{date_to}",
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(saved, dict) or saved.get("error") is True:
            return self._error(saved.get("code") if isinstance(saved, dict) else None)
        return self._card(observation_id, scope, message="Сбор завершён. Результат сохранён отдельной ревизией.")

    def _prompt_note(self, observation_id, state_revision, scope):
        loaded = self._load_observation(observation_id, scope)
        if loaded is None:
            return self._stale()
        observation = loaded["observation"]
        if observation.get("status") != "ACTIVE" or str(observation.get("state_revision")) != str(state_revision):
            return self._stale()
        self._set_pending(scope, {
            "stage": "note", "observation_id": observation_id,
            "state_revision": observation["state_revision"],
            "created_at": self.monotonic_clock(),
        })
        return self._prompt_result(
            "OBSERVATION_NOTE_INPUT_REQUIRED",
            "Введите заметку до 500 символов. Чтобы очистить её, отправьте тире —.",
            self._simple_keyboard("Отмена", f"upo:o:{observation_id}"),
        )

    def _save_note(self, value, pending, scope):
        note = "" if value in {"—", "-"} else value
        result = self.repository.set_unit_price_observation_note(
            pending["observation_id"], note,
            expected_state_revision=pending["state_revision"],
            idempotency_key="upo-note-" + uuid4().hex,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        self._clear_pending(scope)
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error(result.get("code") if isinstance(result, dict) else None)
        return self._card(pending["observation_id"], scope, message="Заметка сохранена.")

    def _finish(self, observation_id, state_revision, scope):
        loaded = self._load_observation(observation_id, scope)
        if loaded is None:
            return self._stale()
        try:
            expected_revision = int(state_revision)
        except (TypeError, ValueError):
            return self._stale()
        if loaded["observation"].get("state_revision") != expected_revision:
            return self._stale()
        result = self.repository.finish_unit_price_observation(
            observation_id, expected_state_revision=expected_revision,
            idempotency_key="upo-finish-" + uuid4().hex,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error(result.get("code") if isinstance(result, dict) else None)
        return self._card(observation_id, scope, message="Наблюдение завершено. Результаты сохранены в истории.")

    def _list(self, scope, message=None, offset=0):
        if type(offset) is not int or offset < 0:
            return self._stale()
        result = self.repository.list_unit_price_observations(
            limit=self.PAGE_SIZE, offset=offset,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error(result.get("code") if isinstance(result, dict) else None)
        items = result.get("items") or []
        lines = [message or "Наблюдения цены продавца · текущий магазин"]
        buttons = []
        for item in items:
            identity = item.get("identity") or {}
            price = self._format_money(item.get("seller_price_cents"))
            label = self._status_label(item.get("status"))
            lines.append(f"SKU {identity.get('sku', '—')} · {price} ₽ · {label}")
            buttons.append({
                "text": f"SKU {identity.get('sku', '—')} · {price} ₽ · {label}",
                "callback": f"upo:o:{item['observation_id']}",
            })
        if not items:
            lines.append("Пока нет наблюдений. Откройте сохранённый однотоварный FBO-план, чтобы начать.")
        if result.get("has_more") is True and result.get("next_offset") is not None:
            buttons.append({"text": "Следующая страница", "callback": f"upo:l:{result['next_offset']}"})
        buttons.extend([
            {"text": "📚 Мои планы", "callback": "upp:m"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return self._prompt_result("OBSERVATION_LIST_READY", "\n".join(lines), self._keyboard(buttons))

    def _card(self, observation_id, scope, message=None):
        loaded = self._load_observation(observation_id, scope)
        if loaded is None:
            return self._stale()
        observation = loaded["observation"]
        latest = loaded.get("result")
        identity = observation.get("identity") or {}
        lines = [
            message or "Наблюдение цены продавца",
            f"SKU {identity.get('sku')} · FBO · {self._status_label(observation.get('status'))}",
            f"Цена по подтверждению владельца: {self._format_money(observation.get('seller_price_cents'))} ₽",
            f"Установлена: {observation.get('effective_from')} · окна: {observation.get('window_timezone')}",
            f"Источник цены: {observation.get('price_evidence_source')} (не API-история)",
            f"Сохранено результатов: {observation.get('result_revision', 0)}",
        ]
        if observation.get("note"):
            lines.append("Заметка: " + self._safe_display(observation["note"], 500))
        if isinstance(latest, dict):
            result = latest.get("payload") or {}
            window = result.get("window") or {}
            lines.append(
                f"Последний результат #{latest.get('revision')}: {self._status_label(result.get('status'))} · "
                f"{window.get('from')} — {window.get('to')}"
            )
            profit = (result.get("metrics") or {}).get("profit_per_unit")
            if result.get("evidence_basis") == "MODELLED_FROM_OBSERVED_INPUTS" and profit is not None:
                lines.append(f"Модельная прибыль по допущениям: {profit} ₽/шт.; не фактическая прибыль.")
            else:
                lines.append("Фактическая прибыль не подтверждена; причины неполноты доступны в истории.")
        lines.append("Наблюдение не меняет цену Ozon. Финансовые суммы не вычитаются повторно из прибыли.")
        buttons = []
        if observation.get("status") == "ACTIVE":
            buttons.extend([
                {"text": "Собрать данные за период", "callback": f"upo:collect:{observation_id}:{observation['state_revision']}:{observation['result_revision']}"},
                {"text": "Изменить заметку", "callback": f"upo:note:{observation_id}:{observation['state_revision']}"},
                {"text": "Завершить наблюдение", "callback": f"upo:finish:{observation_id}:{observation['state_revision']}"},
            ])
        buttons.extend([
            {"text": "История результатов", "callback": f"upo:history:{observation_id}"},
            {"text": "Мои наблюдения", "callback": "upo:m"},
            {"text": "Мои планы", "callback": "upp:m"},
        ])
        return self._prompt_result("OBSERVATION_CARD_READY", "\n".join(lines), self._keyboard(buttons))

    def _history(self, observation_id, scope, offset=0):
        if self._load_observation(observation_id, scope) is None:
            return self._stale()
        if type(offset) is not int or offset < 0 or offset > 1_000_000:
            return self._stale()
        listed = self.repository.list_unit_price_observation_results(
            observation_id, limit=self.PAGE_SIZE, offset=offset,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return self._error(listed.get("code") if isinstance(listed, dict) else None)
        lines = ["История результатов · сохранённый журнал"]
        buttons = []
        for item in listed.get("items") or []:
            result = item.get("payload") or {}
            window = result.get("window") or {}
            lines.append(
                f"#{item.get('revision')} · {self._status_label(result.get('status'))} · "
                f"{window.get('from')} — {window.get('to')} · {item.get('created_at')}"
            )
            buttons.append({
                "text": f"Открыть результат #{item.get('revision')}",
                "callback": f"upo:result:{observation_id}:{item.get('revision')}",
            })
        if not listed.get("items"):
            lines.append("Результатов пока нет. Запустите сбор из карточки наблюдения.")
        if listed.get("has_more") is True:
            next_offset = listed.get("next_offset")
            if type(next_offset) is int and next_offset <= 1_000_000:
                buttons.append({
                    "text": "Следующая страница",
                    "callback": f"upo:h:{observation_id}:{next_offset}",
                })
        buttons.extend([
            {"text": "Карточка наблюдения", "callback": f"upo:o:{observation_id}"},
            {"text": "Мои наблюдения", "callback": "upo:m"},
        ])
        return self._prompt_result("OBSERVATION_HISTORY_READY", "\n".join(lines), self._keyboard(buttons))

    def _result_detail(self, observation_id, revision, scope):
        loaded = self._load_observation(observation_id, scope, result_revision=revision)
        if loaded is None:
            return self._stale()
        result = (loaded.get("result") or {}).get("payload") or {}
        metrics = result.get("metrics") or {}
        window = result.get("window") or {}
        lines = [
            f"Результат #{revision} · {self._status_label(result.get('status'))}",
            f"Окно {window.get('from')} — {window.get('to')} · {window.get('timezone')}",
            f"Основание: {result.get('evidence_basis')}",
        ]
        if result.get("evidence_basis") == "MODELLED_FROM_OBSERVED_INPUTS":
            lines.append(f"Модельная прибыль: {metrics.get('profit_per_unit')} ₽/шт.; это не факт магазина.")
        else:
            lines.append("Прибыль с единицы не рассчитана: нет совместимого подтверждённого набора данных.")
        if result.get("reasons"):
            lines.append("Причины: " + ", ".join(str(item)[:120] for item in result["reasons"][:12]))
        if result.get("warnings"):
            lines.append("Ограничения: " + ", ".join(str(item)[:120] for item in result["warnings"][:8]))
        quality = self.quality_service.assess(
            [{
                "result": result, "result_revision": revision,
                "owner_id": scope["owner_id"], "store_id": scope["store_id"],
            }], now=self.clock(),
        )
        if not isinstance(quality, dict) or quality.get("error") is True:
            quality = None
            lines.append("Сопоставимость: пока не удалось проверить качество данных.")
        else:
            quality_label = {
                "COMPARABLE": "сопоставимо по указанному основанию",
                "INCOMPARABLE": "вариант нельзя сопоставить",
                "NOT_READY": "недостаточно вариантов для сравнения",
            }.get(quality.get("status"), "проверка не завершена")
            lines.append(f"Проверка сопоставимости: {quality_label}.")
            candidate_quality = (quality.get("candidates") or [{}])[0]
            days = candidate_quality.get("window_days")
            units = candidate_quality.get("successful_units")
            lines.append(
                f"Выборка: {days if days is not None else 'нет данных'} дней; "
                f"{units if units is not None else 'нет подтверждённых'} успешных единиц."
            )
            lines.append("Ориентир: 7 дней; менее 30 единиц — предупреждение, не статистическая уверенность.")
            reasons = list(quality.get("reasons") or [])
            reasons.extend(candidate_quality.get("reasons") or [])
            warnings = list(quality.get("warnings") or [])
            warnings.extend(candidate_quality.get("warnings") or [])
            reasons = list(dict.fromkeys(reasons))
            warnings = list(dict.fromkeys(warnings))
            if reasons:
                lines.append("Причины несопоставимости: " + "; ".join(self._quality_reason_label(item) for item in reasons))
            if warnings:
                lines.append("Предупреждения: " + "; ".join(self._quality_reason_label(item) for item in warnings))
        lines.append("Исходные ответы API и идентификаторы операций не сохраняются.")
        response = self._prompt_result(
            "OBSERVATION_RESULT_READY", "\n".join(lines),
            self._simple_keyboard("История", f"upo:history:{observation_id}"),
        )
        if quality is not None:
            response["quality_assessment"] = quality
        return response

    @staticmethod
    def _quality_reason_label(value):
        labels = {
            "AT_LEAST_TWO_PRICE_VARIANTS_REQUIRED": "для сравнения нужны как минимум две цены",
            "PRICE_VARIANTS_NOT_DISTINCT": "цены вариантов должны отличаться",
            "PRODUCT_STORE_OR_SCHEME_MISMATCH": "различаются магазин, товар или схема продаж",
            "OBSERVATION_WINDOWS_OVERLAP": "периоды пересекаются и могут учитывать продажи дважды",
            "WINDOW_DURATION_MISMATCH": "длительность периодов различается",
            "WEEKDAY_COMPOSITION_MISMATCH": "в периодах разный состав дней недели",
            "WINDOW_TIMEZONE_MISMATCH": "различаются часовые пояса периодов",
            "WINDOW_DATE_BASIS_MISMATCH": "различается основание дат периода",
            "SUCCESSFUL_UNIT_DENOMINATOR_UNCONFIRMED": "нет подтверждённого количества успешных единиц",
            "OBSERVATION_EVIDENCE_STALE": "источники данных устарели",
            "SOURCE_FRESHNESS_TIMESTAMP_UNAVAILABLE": "не подтверждено время получения данных",
            "MODEL_ASSUMPTIONS_MISMATCH": "модельные допущения различаются",
            "EVIDENCE_BASIS_MISMATCH": "расчёты имеют разные основания",
            "REVENUE_OR_ADVERTISING_BASIS_MISMATCH": "различаются основания выручки или рекламы",
            "CPC_ONLY_MODEL_OMITS_OTHER_ADVERTISING_TYPES.": "учтён только CPC; другие типы рекламы неизвестны",
            "OWNER_DECLARED_PRICE_DOES_NOT_VERIFY_PER_SALE_PRICE_HISTORY.": "ручное подтверждение не доказывает цену каждой продажи",
            "SAMPLE_THRESHOLDS_ARE_OPERATIONAL_WARNINGS_NOT_STATISTICAL_CONFIDENCE.": "ориентиры выборки не являются статистической уверенностью",
            "COMPARISON_DOES_NOT_ESTABLISH_PRICE_CHANGE_CAUSALITY.": "сравнение не доказывает, что изменения вызваны ценой",
        }
        return labels.get(value, str(value).replace("_", " ").rstrip("."))

    def _load_observation(self, observation_id, scope, result_revision=None):
        result = self.repository.get_unit_price_observation(
            observation_id, result_revision=result_revision,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return None
        observation = result.get("observation")
        if not isinstance(observation, dict) or observation.get("store_id") != scope["store_id"]:
            return None
        return result

    @staticmethod
    def _persistable_result(evaluated):
        allowed = {
            "schema_version", "identity", "seller_price_cents", "status",
            "evidence_basis", "window", "sources", "metrics",
            "completeness", "reasons", "warnings",
        }
        return deepcopy(evaluated) if isinstance(evaluated, dict) and set(evaluated) == allowed else None

    @staticmethod
    def _scope_from_context():
        return str(get_current_tenant_user_id() or "").strip()

    def _scope(self, user_id):
        owner = str(user_id or "").strip()
        tenant_scope = self._scope_from_context()
        scoped_owner, store_id = split_store_tenant_scope(tenant_scope)
        if not owner or not tenant_scope or owner != str(scoped_owner or ""):
            return None
        return {
            "owner_id": owner, "store_id": str(store_id or ""),
            "tenant_scope": tenant_scope, "key": (owner, tenant_scope),
        }

    @staticmethod
    def _record_matches_scope(record, scope):
        return bool(
            isinstance(record, dict)
            and record.get("owner_id") == scope["owner_id"]
            and record.get("store_id") == scope["store_id"]
            and record.get("tenant_scope") == scope["tenant_scope"]
        )

    @staticmethod
    def _plan_item(item, store_id):
        if not isinstance(item, dict):
            return False
        identity, inputs = item.get("identity"), item.get("inputs")
        if (not isinstance(identity, dict) or not isinstance(inputs, dict)
                or str(identity.get("store_id") or "") != str(store_id or "")
                or str(identity.get("scheme") or "").upper() != "FBO"):
            return False
        return all(
            isinstance(identity.get(key), (str, int)) and str(identity[key]).strip()
            for key in ("product_id", "offer_id", "sku")
        )

    @staticmethod
    def _observation_identity(identity, store_id):
        return {
            "store_id": str(store_id or ""),
            "product_id": str(identity.get("product_id") or "").strip(),
            "offer_id": str(identity.get("offer_id") or "").strip(),
            "sku": str(identity.get("sku") or "").strip(),
            "sale_schema": str(identity.get("scheme") or "").upper(),
        }

    @staticmethod
    def _same_plan_identity(identity, observation, store_id):
        if not isinstance(identity, dict):
            return False
        expected = observation.get("identity") or {}
        return (
            str(identity.get("store_id") or "") == str(store_id or "")
            and str(identity.get("product_id") or "") == expected.get("product_id")
            and str(identity.get("offer_id") or "") == expected.get("offer_id")
            and str(identity.get("sku") or "") == expected.get("sku")
            and str(identity.get("scheme") or "").upper() == expected.get("sale_schema")
        )

    def _set_pending(self, scope, pending):
        pending = dict(pending)
        pending["owner_id"] = scope["owner_id"]
        pending["tenant_scope"] = scope["tenant_scope"]
        with self._lock:
            self._prune_locked()
            self._pending[scope["key"]] = pending
            self._pending.move_to_end(scope["key"])
            while len(self._pending) > 128:
                self._pending.popitem(last=False)

    def _get_pending(self, scope):
        with self._lock:
            self._prune_locked()
            pending = deepcopy(self._pending.get(scope["key"]))
        if (not isinstance(pending, dict)
                or pending.get("owner_id") != scope["owner_id"]
                or pending.get("tenant_scope") != scope["tenant_scope"]):
            return None
        return pending

    def _clear_pending(self, scope):
        with self._lock:
            self._pending.pop(scope["key"], None)

    def _prune_locked(self):
        now = self.monotonic_clock()
        for key, value in list(self._pending.items()):
            if now - value.get("created_at", 0) > self.PENDING_TTL_SECONDS:
                self._pending.pop(key, None)
        for token, value in list(self._plan_tokens.items()):
            if now - value.get("created_at", 0) > self.PLAN_TOKEN_TTL_SECONDS:
                self._plan_tokens.pop(token, None)

    @classmethod
    def _parse_price(cls, value):
        if not isinstance(value, str):
            return None
        normalized = value.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        if len(normalized) > 20 or re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", normalized) is None:
            return None
        try:
            price = Decimal(normalized)
            if not price.is_finite() or price <= 0 or price > Decimal(cls.MAX_PRICE_CENTS) / 100:
                return None
            cents = int((price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError, OverflowError):
            return None
        return cents if 1 <= cents <= cls.MAX_PRICE_CENTS else None

    @staticmethod
    def _parse_effective_time(value):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            return None
        return moment if moment.tzinfo is not None and moment.utcoffset() is not None else None

    @staticmethod
    def _format_money(cents):
        if type(cents) is not int:
            return "—"
        return f"{Decimal(cents) / Decimal(100):.2f}"

    @staticmethod
    def _status_label(value):
        return {
            "ACTIVE": "активно", "FINISHED": "завершено", "ARCHIVED": "архив",
            "AVAILABLE": "модель доступна", "INSUFFICIENT_DATA": "недостаточно данных",
            "SOURCE_UNAVAILABLE": "источник недоступен", "INCOMPARABLE": "несопоставимо",
            "CONFLICT": "конфликт данных", "STALE": "устарело",
            "UNSUPPORTED_SCHEME": "схема не поддерживается",
        }.get(str(value or ""), str(value or "статус неизвестен"))

    @staticmethod
    def _safe_display(value, limit):
        return " ".join(str(value or "").replace("\x00", "").split())[:limit]

    def _keyboard(self, buttons):
        safe = [
            item for item in buttons if isinstance(item, dict)
            and isinstance(item.get("callback"), str)
            and len(item["callback"].encode("utf-8")) <= 64
        ]
        builder = getattr(self.keyboard_service, "build_unit_price_batch_keyboard", None)
        return builder(safe) if callable(builder) else {
            "error": False, "type": "inline_keyboard", "buttons": safe,
        }

    def _simple_keyboard(self, label, callback, cancel=False):
        buttons = [{"text": label, "callback": callback}]
        if cancel:
            buttons.append({"text": "Отмена", "callback": "upo:m"})
        return self._keyboard(buttons)

    @staticmethod
    def _prompt_result(status, message, keyboard):
        return {
            "error": False, "status": status, "message": message,
            "text": message, "keyboard": keyboard,
            "read_only": True, "executed": False,
        }

    def _error(self, code):
        code = str(code or "UNIT_PRICE_OBSERVATION_UNAVAILABLE")
        messages = {
            "PLANNING_TENANT_SCOPE_MISMATCH": "Активный магазин изменился. Откройте наблюдения заново в текущем магазине.",
            "PLANNING_OBSERVATION_SOURCE_PLAN_NOT_FOUND": "Исходный сохранённый план недоступен. Откройте план и начните наблюдение заново.",
            "PLANNING_OBSERVATION_SOURCE_PLAN_SCOPE_MISMATCH": "План или SKU не совпадает с наблюдением. Старая запись не изменена.",
            "PLANNING_OBSERVATION_ALREADY_ACTIVE": "Для этой цены уже есть активное наблюдение. Откройте список наблюдений.",
            "PLANNING_OBSERVATION_EFFECTIVE_TIME_FUTURE": "Дата установки цены не может быть в будущем.",
            "PLANNING_OBSERVATION_RESULT_CONFLICT": "Состояние изменилось во время сбора. Откройте карточку; старые результаты сохранены.",
            "PLANNING_OBSERVATION_NOT_ACTIVE": "Наблюдение уже завершено. Откройте его историю.",
            "PLANNING_OBSERVATION_NOT_FOUND": "Наблюдение не найдено в текущем магазине.",
            "UNIT_PRICE_OBSERVATION_COLLECTION_UNAVAILABLE": "Источник временно недоступен. Наблюдение сохранено; попробуйте другой завершённый период позже.",
            "UNIT_PRICE_OBSERVATION_WINDOW_NOT_COMPLETED": "Период должен быть завершённым и начинаться не раньше установки цены. Исправьте даты и повторите.",
        }
        return {
            "error": True, "code": code,
            "message": messages.get(code, "Не удалось выполнить действие. Запись наблюдения сохранена без изменений."),
            "read_only": True, "executed": False,
        }

    def _stale(self):
        return self._prompt_result(
            "OBSERVATION_ACTION_STALE",
            "Кнопка устарела или относится к другому магазину. Откройте список наблюдений заново.",
            self._keyboard([{"text": "Мои наблюдения", "callback": "upo:m"}]),
        )
