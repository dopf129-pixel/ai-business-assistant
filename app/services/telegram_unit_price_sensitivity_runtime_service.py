"""Bounded, tenant-scoped Telegram UI for local price sensitivity sweeps."""

from copy import deepcopy
from secrets import token_hex
from threading import RLock
from time import monotonic

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramUnitPriceSensitivityRuntimeService:
    PENDING_TTL_SECONDS = 600
    SESSION_TTL_SECONDS = 3600
    MAX_SESSIONS = 64
    MAX_ACTIONS = 512
    PAGE_SIZE = 7
    TEXT_LIMIT_UTF16 = 3500

    AXIS_LABELS = {
        "price": "Цена продавца",
        "cost": "Себестоимость",
        "advertising_rate": "Реклама",
    }
    AXIS_INPUT_LABELS = {
        "price": "цену в ₽/шт.",
        "cost": "себестоимость в ₽/шт.",
        "advertising_rate": "рекламную долю в %",
    }
    PAIRS = {
        "price_cost": ("price", "cost"),
        "price_advertising": ("price", "advertising_rate"),
        "cost_advertising": ("cost", "advertising_rate"),
    }

    def __init__(
        self,
        sensitivity_service,
        single_price_runtime_service,
        batch_plan_runtime_service,
        keyboard_service,
        clock=None,
        tenant_scope_provider=None,
    ):
        self.sensitivity_service = sensitivity_service
        self.single_price_runtime_service = single_price_runtime_service
        self.batch_plan_runtime_service = batch_plan_runtime_service
        self.keyboard_service = keyboard_service
        self.clock = clock or monotonic
        self.tenant_scope_provider = tenant_scope_provider or get_current_tenant_user_id
        self._pending = {}
        self._sessions = {}
        self._actions = {}
        self._lock = RLock()

    def begin_from_single(self, scenario_id, version, user_id=None):
        reader = getattr(self.single_price_runtime_service, "get_sensitivity_context", None)
        if not callable(reader):
            return self._error("UNIT_PRICE_SENSITIVITY_SOURCE_UNAVAILABLE")
        context = reader(scenario_id, version, user_id=user_id)
        return self.begin_from_context(context, user_id=user_id)

    def begin_from_context(self, context, user_id=None):
        scope = self._scope(user_id)
        if scope.get("error"):
            return self._context_error()
        if not self._valid_context(context, scope):
            return self._stale()
        context = deepcopy(context)
        signature = self.sensitivity_service.context_signature(context)
        if isinstance(signature, dict):
            return self._stale()
        context["base_input_signature"] = signature
        token = token_hex(8)
        with self._lock:
            self._pending[scope["key"]] = {
                "token": token,
                "context": context,
                "target_margin_percent": deepcopy(context.get("target_margin_percent")),
                "created_at": self.clock(),
            }
            self._sessions.pop(scope["key"], None)
            self._evict_locked(self._pending, self.MAX_SESSIONS)
        return self._axis_prompt(scope, token)

    def has_pending(self, user_id):
        scope = self._scope(user_id)
        if scope.get("error"):
            return False
        with self._lock:
            state = self._pending.get(scope["key"])
            return isinstance(state, dict) and self.clock() - state.get("created_at", 0) <= self.PENDING_TTL_SECONDS

    def handle_text(self, text, user_id=None):
        scope = self._scope(user_id)
        if scope.get("error"):
            return None
        pending, pending_error = self._claim_pending(scope["key"])
        with self._lock:
            session = deepcopy(self._sessions.get(scope["key"]))
        if pending_error == "BUSY":
            return self._result("UNIT_PRICE_SENSITIVITY_WORK_IN_PROGRESS", "Чувствительность уже рассчитывается. Дождитесь результата.", self._main_keyboard())
        if isinstance(pending, dict):
            if self.clock() - pending.get("created_at", 0) > self.PENDING_TTL_SECONDS:
                self.clear_pending(user_id)
                return self._result(
                    "UNIT_PRICE_SENSITIVITY_INPUT_EXPIRED",
                    "Ввод истёк. Откройте чувствительность из актуального плана ещё раз.",
                    self._main_keyboard(),
                )
            stage = pending.get("stage")
            if stage not in {"axis_1", "axis_2"}:
                self._store_pending(scope, pending)
                return self._axis_prompt(scope, pending["token"], notice="Сначала выберите ось на кнопке ниже.")
            axis_index = 0 if stage == "axis_1" else 1
            axis = pending["selected_axes"][axis_index]
            parsed = self.sensitivity_service.parse_axis_values(text, axis)
            if parsed.get("error") is True:
                self._store_pending(scope, pending)
                return self._values_prompt(
                    scope,
                    pending,
                    axis,
                    notice="Не удалось принять список. Укажите от 3 до 7 разных абсолютных чисел через «;» или с новой строки.",
                )
            selected = deepcopy(pending)
            selected.setdefault("axes", {})[axis] = parsed["values"]
            if stage == "axis_1" and len(selected.get("selected_axes", [])) == 2:
                selected["stage"] = "axis_2"
                self._store_pending(scope, selected)
                return self._values_prompt(scope, selected, selected["selected_axes"][1])
            result = self.sensitivity_service.build_sweep(
                selected["context"], selected["axes"],
                target_margin_percent=selected.get("target_margin_percent"),
            )
            if result.get("error") is True:
                self._store_pending(scope, selected)
                return self._values_prompt(scope, selected, axis, notice="Расчёт не принят: " + str(result.get("code")))
            if result.get("base_input_signature") != selected["context"].get("base_input_signature"):
                self.clear_pending(user_id)
                return self._stale()
            if not self._pending_is_current(scope["key"], selected.get("token"), scope):
                return self._stale()
            self._store_session(scope, {
                "result_id": token_hex(8),
                "context": selected["context"],
                "result": result,
                "created_at": self.clock(),
                "page": 1,
            })
            with self._lock:
                current = self._pending.get(scope["key"])
                if isinstance(current, dict) and current.get("token") == pending.get("token"):
                    self._pending.pop(scope["key"], None)
            return self._render(scope)
        if isinstance(session, dict):
            return self._render(scope, notice="Этот текст не изменил расчёт. Используйте кнопки отчёта.")
        return None

    def handle_callback(self, callback, user_id=None):
        scope = self._scope(user_id)
        if scope.get("error"):
            return self._context_error()
        value = str(callback or "")
        if value == "ups:c":
            self.clear_pending(user_id)
            return self._result("UNIT_PRICE_SENSITIVITY_CANCELLED", "Чувствительность закрыта. План цены не изменён.", self._main_keyboard())
        parts = value.split(":")
        if len(parts) != 3 or parts[:2] != ["ups", "a"]:
            return self._stale()
        action = self._consume_action(parts[2], scope)
        if not isinstance(action, dict):
            return self._stale()
        key = scope["key"]
        if action.get("kind") == "choose_axes":
            with self._lock:
                pending = deepcopy(self._pending.get(key))
            if not isinstance(pending, dict) or pending.get("token") != action.get("pending_token"):
                return self._stale()
            axes = action.get("axes")
            if not isinstance(axes, list) or len(axes) not in (1, 2) or len(set(axes)) != len(axes):
                return self._stale()
            pending.update(selected_axes=axes, axes={}, stage="axis_1")
            self._store_pending(scope, pending)
            return self._values_prompt(scope, pending, axes[0])

        if action.get("kind") == "return":
            with self._lock:
                pending = deepcopy(self._pending.get(key))
            if isinstance(pending, dict) and pending.get("token") == action.get("pending_token"):
                self.clear_pending(user_id)
                return self._return_to_origin(scope, {"context": pending.get("context")})

        with self._lock:
            session = deepcopy(self._sessions.get(key))
        if not isinstance(session, dict) or session.get("result_id") != action.get("result_id"):
            return self._stale()
        if action.get("kind") == "page":
            session["page"] = action.get("page", 1)
            self._store_session(scope, session)
            return self._render(scope)
        if action.get("kind") == "return":
            self.clear_pending(user_id)
            return self._return_to_origin(scope, session)
        if action.get("kind") == "apply":
            return self._apply(scope, session, action.get("cell_id"), user_id)
        return self._stale()

    def clear_pending(self, user_id):
        owner = str(user_id or "").strip()
        if not owner:
            return
        with self._lock:
            for key in [key for key in self._pending if key[0] == owner]:
                self._pending.pop(key, None)
            for key in [key for key in self._sessions if key[0] == owner]:
                self._sessions.pop(key, None)
            for token, action in list(self._actions.items()):
                if action.get("owner_id") == owner:
                    self._actions.pop(token, None)

    def _axis_prompt(self, scope, pending_token, notice=None):
        buttons = []
        for axis in self.AXIS_LABELS:
            buttons.append({
                "text": "Ось · " + self.AXIS_LABELS[axis],
                "callback": self._register_action(scope, "choose_axes", pending_token=pending_token, axes=[axis]),
            })
        for pair, axes in self.PAIRS.items():
            buttons.append({
                "text": "Матрица · " + self.AXIS_LABELS[axes[0]] + " × " + self.AXIS_LABELS[axes[1]],
                "callback": self._register_action(scope, "choose_axes", pending_token=pending_token, axes=list(axes)),
            })
        buttons.extend([
            {"text": "Назад к плану", "callback": self._register_action(scope, "return", result_id=None, pending_token=pending_token)},
            {"text": "Отмена", "callback": "ups:c"},
        ])
        text = "Выберите одну ось для 3–7 проверенных сценариев или пару осей для матрицы до 7×7. Будут рассчитаны абсолютные значения; исходные допущения не меняются."
        if notice:
            text = notice + "\n" + text
        return self._result("UNIT_PRICE_SENSITIVITY_AXIS_REQUIRED", text, self._keyboard(buttons))

    def _values_prompt(self, scope, pending, axis, notice=None):
        unit = "%" if axis == "advertising_rate" else "₽/шт."
        text = f"Введите 3–7 разных значений для оси «{self.AXIS_LABELS[axis]}» ({unit}) через «;» или с новой строки. Это абсолютные значения."
        if notice:
            text = notice + "\n" + text
        return self._result(
            "UNIT_PRICE_SENSITIVITY_VALUES_REQUIRED",
            text,
            self._keyboard([
                {"text": "Отмена", "callback": "ups:c"},
                {"text": "Назад к плану", "callback": self._register_action(scope, "return", pending_token=pending.get("token"))},
            ]),
        )

    def _render(self, scope, notice=None):
        with self._lock:
            session = deepcopy(self._sessions.get(scope["key"]))
        if not isinstance(session, dict) or self.clock() - session.get("created_at", 0) > self.SESSION_TTL_SECONDS:
            return self._stale()
        context = session["context"]
        current = self._read_current_context(context, scope["owner_id"])
        current_signature = self.sensitivity_service.context_signature(current) if isinstance(current, dict) and current.get("error") is not True else None
        freshness = (
            isinstance(current, dict)
            and current.get("error") is not True
            and current_signature == session["result"].get("base_input_signature")
            and current.get("source_age_seconds", float("inf")) < current.get("source_ttl_seconds", 0)
            and current.get("source_ttl_seconds", 0) <= 600
        )
        result = session["result"]
        cells = result.get("cells") or []
        page_count = max(1, (len(cells) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(1, min(int(session.get("page", 1)), page_count))
        shown = cells[(page - 1) * self.PAGE_SIZE:page * self.PAGE_SIZE]
        origin_label = "одиночного плана" if context.get("origin", {}).get("kind") == "single" else "строки пакетного плана"
        lines = ["🧭 Чувствительность плановой экономики", f"Источник: {origin_label}; дата снимка: {self._as_of_label(result.get('source_as_of'))}."]
        axes = result.get("axes") or {}
        lines.append("Оси: " + " × ".join(item.get("label", key) for key, item in axes.items()) + ".")
        lines.append(f"Сценариев: {result.get('available_cell_count', 0)} из {result.get('cell_count', len(cells))} рассчитано.")
        if result.get("target_margin_percent") is not None:
            lines.append(f"Точная цель маржи после налога: {result['target_margin_percent']}%.")
        if notice:
            lines.append(notice)
        if not freshness:
            lines.append("⚠️ Исходный план или источник устарел. Просмотр доступен, перенос ячеек отключён.")
        for index, cell in enumerate(shown, start=(page - 1) * self.PAGE_SIZE + 1):
            coordinates = cell.get("coordinates") or {}
            coordinate_text = ", ".join(
                self.AXIS_LABELS.get(axis, axis) + " " + self._number(value) + ("%" if axis == "advertising_rate" else " ₽")
                for axis, value in coordinates.items()
            )
            scenario = cell.get("scenario") or {}
            calculated = scenario.get("calculated") or {}
            if cell.get("status") == "AVAILABLE":
                line = f"{index}. {coordinate_text}: прибыль {self._number(calculated.get('profit'))} ₽/шт.; маржа {self._number(calculated.get('margin_percent'))}%; налог {self._number(calculated.get('tax'))} ₽"
                if cell.get("target_reached") is not None:
                    line += "; цель " + ("достигнута" if cell["target_reached"] else "не достигнута")
            else:
                line = f"{index}. {coordinate_text}: {self._status_label(cell.get('status'))}"
            lines.append(line + ".")
        best = self._find_cell(cells, result.get("best_checked_cell_id"))
        worst = self._find_cell(cells, result.get("worst_checked_cell_id"))
        if best and worst:
            lines.append(f"Лучший/худший среди проверенных: {self._number((best.get('scenario') or {}).get('calculated', {}).get('profit'))} / {self._number((worst.get('scenario') or {}).get('calculated', {}).get('profit'))} ₽/шт.; это не прогноз оптимума Ozon.")
        lines.append(f"Страница {page} из {page_count}. Оценка одной успешной продажи FBO; спрос и общие расходы магазина не прогнозируются.")
        buttons = []
        for index, cell in enumerate(shown, start=(page - 1) * self.PAGE_SIZE + 1):
            if freshness and cell.get("status") == "AVAILABLE":
                buttons.append({
                    "text": f"Перенести сценарий {index}",
                    "callback": self._register_action(scope, "apply", result_id=session["result_id"], cell_id=cell.get("cell_id")),
                })
        if page > 1:
            buttons.append({"text": "Предыдущая", "callback": self._register_action(scope, "page", result_id=session["result_id"], page=page - 1)})
        if page < page_count:
            buttons.append({"text": "Следующая", "callback": self._register_action(scope, "page", result_id=session["result_id"], page=page + 1)})
        buttons.extend([
            {"text": "Назад к плану", "callback": self._register_action(scope, "return", result_id=session["result_id"])},
            {"text": "Закрыть", "callback": "ups:c"},
        ])
        return self._result("UNIT_PRICE_SENSITIVITY_READY", self._truncate("\n".join(lines)), self._keyboard(buttons), sensitivity_result=result)

    def _apply(self, scope, session, cell_id, user_id):
        context = session.get("context") or {}
        current = self._read_current_context(context, user_id)
        result = session.get("result") or {}
        cell = next((item for item in result.get("cells", []) if item.get("cell_id") == cell_id), None)
        signature = self.sensitivity_service.context_signature(current) if isinstance(current, dict) and current.get("error") is not True else None
        if (
            cell is None
            or signature != result.get("base_input_signature")
            or current.get("source_age_seconds", float("inf")) >= current.get("source_ttl_seconds", 0)
            or current.get("source_ttl_seconds", 0) > 600
            or cell.get("status") != "AVAILABLE"
        ):
            return self._result("UNIT_PRICE_SENSITIVITY_SOURCE_STALE", "Исходный план изменился или устарел. Ячейка не перенесена; откройте чувствительность заново.", self._main_keyboard())
        current["base_input_signature"] = result.get("base_input_signature")
        origin_kind = context.get("origin", {}).get("kind")
        if origin_kind == "single":
            applier = getattr(self.single_price_runtime_service, "apply_sensitivity_candidate", None)
        else:
            applier = getattr(self.batch_plan_runtime_service, "apply_sensitivity_candidate", None)
        if not callable(applier):
            return self._error("UNIT_PRICE_SENSITIVITY_HANDOFF_UNAVAILABLE")
        response = applier(current, cell, user_id=user_id)
        if isinstance(response, dict) and response.get("error") is not True:
            self.clear_pending(user_id)
        return response

    def _return_to_origin(self, scope, session):
        context = session.get("context") or {}
        origin = context.get("origin") or {}
        if origin.get("kind") == "single":
            callback = f"upc:v:{origin.get('scenario_id')}:{origin.get('scenario_version')}"
            return self.single_price_runtime_service.handle_callback(callback, user_id=scope["owner_id"])
        show = getattr(self.batch_plan_runtime_service, "show_sensitivity_origin", None)
        if callable(show):
            return show(origin, user_id=scope["owner_id"])
        return self._stale()

    def _read_current_context(self, original_context, user_id):
        origin = original_context.get("origin") or {}
        if origin.get("kind") == "single":
            reader = getattr(self.single_price_runtime_service, "get_sensitivity_context", None)
            if callable(reader):
                return reader(origin.get("scenario_id"), origin.get("scenario_version"), user_id=user_id)
        if origin.get("kind") == "batch":
            reader = getattr(self.batch_plan_runtime_service, "get_sensitivity_context", None)
            if callable(reader):
                return reader(origin.get("batch_id"), origin.get("batch_version"), origin.get("row_id"), user_id=user_id)
        return {"error": True, "code": "SENSITIVITY_ORIGIN_UNKNOWN"}

    def _valid_context(self, context, scope):
        if not isinstance(context, dict) or context.get("error") is True:
            return False
        origin = context.get("origin")
        identity = context.get("identity")
        if not isinstance(origin, dict) or not isinstance(identity, dict):
            return False
        return (
            origin.get("owner_id") == scope["owner_id"]
            and origin.get("tenant_scope") == scope["tenant_scope"]
            and identity.get("tenant_scope") == scope["tenant_scope"]
            and origin.get("kind") in {"single", "batch"}
            and isinstance(context.get("inputs"), dict)
        )

    def _register_action(self, scope, kind, **values):
        with self._lock:
            token = token_hex(4)
            while token in self._actions:
                token = token_hex(4)
            self._actions[token] = {
                "owner_id": scope["owner_id"],
                "tenant_scope": scope["tenant_scope"],
                "kind": kind,
                "created_at": self.clock(),
                **deepcopy(values),
            }
            self._evict_locked(self._actions, self.MAX_ACTIONS)
        callback = "ups:a:" + token
        return callback if len(callback.encode("utf-8")) <= 64 else "ups:c"

    def _consume_action(self, token, scope):
        with self._lock:
            action = self._actions.pop(str(token or ""), None)
        if (
            not isinstance(action, dict)
            or action.get("owner_id") != scope["owner_id"]
            or action.get("tenant_scope") != scope["tenant_scope"]
            or self.clock() - action.get("created_at", 0) > self.SESSION_TTL_SECONDS
        ):
            return None
        return action

    def _store_pending(self, scope, state):
        saved = deepcopy(state)
        saved["processing"] = False
        with self._lock:
            self._pending[scope["key"]] = saved

    def _claim_pending(self, key):
        with self._lock:
            pending = self._pending.get(key)
            if not isinstance(pending, dict):
                return None, None
            if pending.get("processing"):
                return None, "BUSY"
            pending["processing"] = True
            return deepcopy(pending), None

    def _pending_is_current(self, key, token, scope):
        current_scope = self._scope(scope["owner_id"])
        if current_scope.get("tenant_scope") != scope["tenant_scope"]:
            return False
        with self._lock:
            current = self._pending.get(key)
            return isinstance(current, dict) and current.get("token") == token

    def _store_session(self, scope, state):
        with self._lock:
            self._sessions[scope["key"]] = deepcopy(state)

    def _scope(self, user_id):
        owner = str(user_id or "").strip()
        tenant_scope = str(self.tenant_scope_provider() or "").strip()
        scoped_owner, store_id = split_store_tenant_scope(tenant_scope)
        if not owner or not tenant_scope or scoped_owner != owner:
            return {"error": True, "owner_id": owner, "tenant_scope": tenant_scope}
        return {
            "error": False,
            "owner_id": owner,
            "tenant_scope": tenant_scope,
            "store_id": store_id,
            "key": (owner, tenant_scope),
        }

    def _keyboard(self, buttons):
        builder = getattr(self.keyboard_service, "build_unit_price_batch_keyboard", None)
        if callable(builder):
            return builder(buttons)
        return {"error": False, "type": "inline_keyboard", "buttons": [
            item for item in buttons
            if isinstance(item, dict) and isinstance(item.get("callback"), str)
            and len(item["callback"].encode("utf-8")) <= 64
        ]}

    def _main_keyboard(self):
        return self.keyboard_service.build_main_keyboard()

    def _result(self, status, message, keyboard, sensitivity_result=None):
        result = {
            "error": False,
            "status": status,
            "message": message,
            "keyboard": keyboard,
            "read_only": True,
            "executed": False,
        }
        if sensitivity_result is not None:
            result["sensitivity_result"] = deepcopy(sensitivity_result)
        return result

    def _context_error(self):
        return self._result("UNIT_PRICE_SENSITIVITY_CONTEXT_UNAVAILABLE", "Не удалось подтвердить активный магазин. Откройте план цены заново.", self._main_keyboard())

    def _stale(self):
        return self._result("UNIT_PRICE_SENSITIVITY_ACTION_STALE", "Кнопка устарела или относится к другому магазину. Откройте чувствительность из актуального плана.", self._main_keyboard())

    def _error(self, code):
        return self._result(str(code), "Чувствительность плановой экономики сейчас недоступна.", self._main_keyboard())

    def _evict_locked(self, mapping, limit):
        while len(mapping) > limit:
            if hasattr(mapping, "popitem"):
                mapping.popitem(last=False) if hasattr(mapping, "move_to_end") else mapping.pop(next(iter(mapping)))

    @staticmethod
    def _number(value):
        if value is None:
            return "н/д"
        return str(value).replace(".", ",")

    @staticmethod
    def _status_label(status):
        return {
            "SOURCE_STALE": "источник устарел",
            "INCOMPLETE_INPUTS": "не хватает допущений",
            "INVALID_INPUTS": "некорректные допущения",
        }.get(status, "расчёт недоступен")

    @staticmethod
    def _as_of_label(value):
        if isinstance(value, dict):
            preferred = value.get("seller_price_as_of") or value.get("as_of")
            if isinstance(preferred, str):
                return preferred[:40]
            return "снимок сохранён; точная дата не указана"
        return str(value or "дата не указана")[:40]

    @staticmethod
    def _find_cell(cells, cell_id):
        return next((cell for cell in cells if cell.get("cell_id") == cell_id), None)

    def _truncate(self, text):
        if len(text.encode("utf-16-le")) // 2 <= self.TEXT_LIMIT_UTF16:
            return text
        suffix = "\nОтчёт сокращён; полные строки доступны постранично."
        limit = self.TEXT_LIMIT_UTF16 - len(suffix.encode("utf-16-le")) // 2
        result = []
        units = 0
        for char in text:
            char_units = len(char.encode("utf-16-le")) // 2
            if units + char_units > limit:
                break
            result.append(char)
            units += char_units
        return "".join(result) + suffix
