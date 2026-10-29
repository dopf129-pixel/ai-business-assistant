"""Tenant-scoped Telegram entry flow for saved price experiments."""

from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from secrets import token_hex
from threading import RLock
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.unit_economics_experiment_recommendation_service import (
    UnitEconomicsExperimentRecommendationService,
)
from services.unit_economics_experiment_snapshot_view_service import (
    UnitEconomicsExperimentSnapshotViewService,
)


class TelegramUnitEconomicsExperimentRuntimeService:
    """Guide an owner from a saved SKU plan to an explicitly confirmed baseline."""

    PENDING_TTL_SECONDS = 600
    ACTION_TTL_SECONDS = 900
    MAX_PENDING = 64
    MAX_ACTIONS = 256
    PAGE_SIZE = 10
    MAX_SNAPSHOT_PAGES = 5
    DEFAULT_DURATION_DAYS = 7
    MAX_PRICE_CENTS = 99_999_999_999_999
    _PRICE_LIST_SEPARATOR = re.compile(r"\s*;\s*")

    def __init__(self, *, repository, keyboard_service=None, observation_runtime_service=None,
                 history_export_service=None, default_timezone="Europe/Moscow",
                 clock=None, monotonic_clock=None):
        self.repository = repository
        self.keyboard_service = keyboard_service
        self.observation_runtime_service = observation_runtime_service
        self.history_export_service = history_export_service
        self.default_timezone = default_timezone
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic_clock = monotonic_clock or monotonic
        self._pending = OrderedDict()
        self._actions = OrderedDict()
        self._lock = RLock()

    def handle_callback(self, callback, *, user_id=None):
        scope = self._scope(user_id)
        if scope is None:
            self.clear_pending(user_id)
            return self._error("UNIT_ECONOMICS_EXPERIMENT_TENANT_SCOPE_MISMATCH")
        self._clear_other_scopes(scope)
        value = str(callback or "")
        if value == "uex:m":
            self.clear_pending(user_id)
            self._clear_actions(scope)
            return self._home(scope)
        if value == "uex:new":
            self.clear_pending(user_id)
            self._clear_actions(scope)
            return self._list_plans(scope, 0)
        if value.startswith("uex:plans:"):
            parts = value.split(":")
            if len(parts) != 3 or not parts[2].isdigit():
                return self._stale()
            self.clear_pending(user_id)
            self._clear_actions(scope)
            return self._list_plans(scope, int(parts[2]))
        if value.startswith("uex:experiments:"):
            parts = value.split(":")
            if len(parts) != 3 or not parts[2].isdigit():
                return self._stale()
            self.clear_pending(user_id)
            self._clear_actions(scope)
            return self._list_experiments(scope, int(parts[2]))
        if value.startswith("uex:read:"):
            parts = value.split(":")
            if len(parts) != 3:
                return self._stale()
            action = self._get_action(parts[2], scope)
            if action is None:
                return self._stale()
            return self._handle_read_action(scope, action)
        if value == "uex:c":
            cancelled = self._cancel_confirmation_drafts(scope)
            self.clear_pending(user_id)
            self._clear_actions(scope)
            return self._result(
                "UNIT_ECONOMICS_EXPERIMENT_CANCELLED",
                (
                    "Настройка отменена. Незапущенный черновик эксперимента сохранён "
                    "в истории со статусом «Отменён»."
                    if cancelled else "Настройка отменена. Сохранённые планы и данные не изменены."
                ),
                self._home_keyboard(),
            )
        if value == "uex:b":
            self.clear_pending(user_id)
            self._clear_actions(scope)
            return self._list_plans(scope, 0)
        if value.startswith("uex:a:"):
            parts = value.split(":")
            if len(parts) != 3:
                return self._stale()
            action = self._get_action(parts[2], scope)
            if action is None:
                return self._stale()
            if action.get("kind") == "plan":
                self._remove_action(parts[2])
                return self._select_plan(scope, action)
            if action.get("kind") == "snapshot":
                self._remove_action(parts[2])
                return self._select_snapshot(scope, action)
            if action.get("kind") == "confirm":
                return self._confirm_baseline(scope, action)
        return self._stale()

    def handle_text(self, text, *, user_id=None):
        scope = self._scope(user_id)
        if scope is None:
            self.clear_pending(user_id)
            return None
        self._clear_other_scopes(scope)
        with self._lock:
            pending = deepcopy(self._pending.get(scope["key"]))
        if pending is None:
            return None
        if self.monotonic_clock() - pending["created_at"] > self.PENDING_TTL_SECONDS:
            self.clear_pending(user_id)
            return self._stale()
        if pending.get("stage") == "candidate_prices":
            prices = self._parse_price_list(text)
            if prices is None:
                return self._result(
                    "UNIT_ECONOMICS_EXPERIMENT_PRICES_INVALID",
                    "Введите от 2 до 10 разных цен через точку с запятой, например: 95; 99,90; 105.",
                    self._cancel_keyboard(),
                )
            pending["candidate_prices_cents"] = prices
            pending["stage"] = "baseline_price_time"
            pending["created_at"] = self.monotonic_clock()
            self._save_pending(scope, pending)
            return self._result(
                "UNIT_ECONOMICS_EXPERIMENT_BASELINE_INPUT_REQUIRED",
                "Введите фактическую цену продавца и когда вы установили её в Ozon. "
                "Формат: цена; ГГГГ-ММ-ДД ЧЧ:ММ (время магазина, "
                f"{self.default_timezone}). Например: 100; 2026-10-29 12:30. "
                "Это будет ваше подтверждение, а не история цены из Ozon.",
                self._cancel_keyboard(),
            )
        if pending.get("stage") == "baseline_price_time":
            parsed = self._parse_baseline_input(text)
            if parsed is None:
                return self._result(
                    "UNIT_ECONOMICS_EXPERIMENT_BASELINE_INPUT_INVALID",
                    "Не удалось разобрать цену или дату. Используйте формат: "
                    "100; 2026-10-29 12:30. Дата и время должны быть прошедшими.",
                    self._cancel_keyboard(),
                )
            return self._create_and_preview_baseline(scope, pending, parsed)
        self.clear_pending(user_id)
        return self._stale()

    def open_menu(self, user_id=None):
        scope = self._scope(user_id)
        if scope is None:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_TENANT_SCOPE_MISMATCH")
        self._clear_other_scopes(scope)
        return self._home(scope)

    def clear_pending(self, user_id):
        scope = self._scope(user_id)
        if scope is not None:
            with self._lock:
                self._pending.pop(scope["key"], None)

    def clear_user_state(self, user_id):
        self.clear_pending(user_id)
        scope = self._scope(user_id)
        if scope is not None:
            self._clear_actions(scope)

    def _home(self, scope):
        result = self.repository.list_price_experiments(
            owner_id=scope["owner_id"], store_id=scope["store_id"], limit=self.PAGE_SIZE,
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_LIST_UNAVAILABLE")
        items = result.get("items")
        if not isinstance(items, list):
            return self._error("UNIT_ECONOMICS_EXPERIMENT_LIST_INVALID")
        lines = ["🧪 Ценовые эксперименты", ""]
        if items:
            lines.append("Сохранённые эксперименты:")
            buttons = []
            for item in items:
                config = item.get("config") or {}
                identity = config.get("identity") or {}
                lines.append(
                    f"• SKU {identity.get('sku', '—')} — "
                    f"{self._state_label(item.get('status'))}"
                )
                token = self._remember_action(scope, {
                    "kind": "experiment", "experiment_id": item.get("experiment_id"),
                })
                if token:
                    buttons.append({
                        "text": self._short_label(
                            f"SKU {identity.get('sku', '—')} · "
                            f"{self._state_label(item.get('status'))}", 60,
                        ),
                        "callback": f"uex:read:{token}",
                    })
        else:
            lines.append("Пока нет сохранённых экспериментов.")
            buttons = []
        lines.extend([
            "", "Перед запуском нужен точный сохранённый план SKU и полный "
            "56-дневный снимок расходов. Если такого снимка нет, эксперимент "
            "не начнётся и неизвестные расходы не будут приняты за ноль.",
        ])
        buttons.insert(0, {"text": "➕ Новый эксперимент", "callback": "uex:new"})
        if result.get("has_more"):
            buttons.append({"text": "➡️ Ещё эксперименты", "callback": "uex:experiments:10"})
        buttons.extend([
            {"text": "↩️ Юнит-экономика", "callback": "unit_economics"},
            {"text": "↩️ Главное меню", "callback": "main_menu"},
        ])
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_MENU", "\n".join(lines), self._keyboard(buttons),
        )

    def _list_experiments(self, scope, offset):
        if offset < 0 or offset % self.PAGE_SIZE or offset > 1000:
            return self._stale()
        result = self.repository.list_price_experiments(
            owner_id=scope["owner_id"], store_id=scope["store_id"],
            limit=self.PAGE_SIZE, offset=offset,
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_LIST_UNAVAILABLE")
        lines = ["🧪 История экспериментов", ""]
        buttons = []
        for item in result.get("items", []):
            config = item.get("config") or {}
            identity = config.get("identity") or {}
            label = self._short_label(
                f"SKU {identity.get('sku', '—')} · {self._state_label(item.get('status'))}",
                60,
            )
            lines.append("• " + label)
            token = self._remember_action(scope, {
                "kind": "experiment", "experiment_id": item.get("experiment_id"),
            })
            if token:
                buttons.append({"text": label, "callback": f"uex:read:{token}"})
        if not result.get("items"):
            lines.append("Сохранённых экспериментов пока нет.")
        if result.get("has_more") is True:
            buttons.append({
                "text": "➡️ Следующая страница",
                "callback": f"uex:experiments:{result.get('next_offset')}",
            })
        buttons.extend([
            {"text": "➕ Новый эксперимент", "callback": "uex:new"},
            {"text": "↩️ Эксперименты", "callback": "uex:m"},
        ])
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_HISTORY", "\n".join(lines), self._keyboard(buttons),
        )

    def _handle_read_action(self, scope, action):
        handlers = {
            "experiment": self._show_experiment,
            "experiment_revision": self._show_experiment_revision,
            "experiment_history": self._show_experiment_history,
            "phase": self._show_phase,
            "phase_revision": self._show_phase_revision,
            "phase_history": self._show_phase_history,
            "phase_results": self._show_phase_results,
            "result": self._show_result,
            "snapshot": self._show_frozen_snapshot,
            "export_menu": self._show_export_menu,
            "export": self._export_history,
        }
        handler = handlers.get(action.get("kind"))
        return handler(scope, action) if handler is not None else self._stale()

    def _show_experiment(self, scope, action):
        experiment_id = action.get("experiment_id")
        loaded = self.repository.get_price_experiment(
            experiment_id, owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        experiment = loaded.get("experiment") if isinstance(loaded, dict) else None
        if not isinstance(experiment, dict):
            return self._stale()
        identity = experiment.get("config", {}).get("identity", {})
        phases = self.repository.list_price_experiment_phases(
            experiment_id, limit=10, owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(phases, dict) or phases.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_PHASE_HISTORY_UNAVAILABLE")
        config = experiment["config"]
        lines = [
            "🧪 Карточка эксперимента",
            f"SKU {identity.get('sku', '—')} · {self._state_label(experiment.get('status'))}",
            f"Показатель: {self._metric_label(config.get('metric'))}",
            "Кандидаты: " + ", ".join(
                self._format_price(value) for value in config.get("candidate_prices_cents", [])
            ) + " ₽",
            f"Сохранённые версии: состояние {experiment.get('state_revision')}, "
            f"результаты {experiment.get('result_revision')}",
            "",
            "Фазы:",
        ]
        buttons = []
        for phase in phases.get("items", []):
            phase_config = phase.get("config") or {}
            phase_label = (
                f"{self._phase_label(phase.get('kind'))} · "
                f"{self._state_label(phase.get('status'))} · "
                f"{self._format_price(phase_config.get('planned_price_cents', 0))} ₽"
            )
            lines.append("• " + phase_label)
            phase_token = self._remember_action(scope, {
                "kind": "phase", "experiment_id": experiment_id,
                "phase_id": phase.get("phase_id"),
            })
            if phase_token:
                buttons.append({
                    "text": self._short_label(phase_label, 60),
                    "callback": f"uex:read:{phase_token}",
                })
            observation_id = phase.get("observation_id")
            if isinstance(observation_id, str) and observation_id and self.observation_runtime_service:
                buttons.append({
                    "text": f"📈 Сбор метрик: сегмент {phase_config.get('segment_number', '—')}",
                    "callback": f"upo:o:{observation_id}",
                })
            result_token = self._remember_action(scope, {
                "kind": "phase_results", "experiment_id": experiment_id,
                "phase_id": phase.get("phase_id"),
            })
            if result_token and phase.get("result_revision", 0) > 0:
                buttons.append({
                    "text": f"💡 Результаты: сегмент {phase_config.get('segment_number', '—')}",
                    "callback": f"uex:read:{result_token}",
                })
        if not phases.get("items"):
            lines.append("Пока нет сохранённых фаз.")
        history_token = self._remember_action(scope, {
            "kind": "experiment_history", "experiment_id": experiment_id,
        })
        snapshot_token = self._remember_action(scope, {
            "kind": "snapshot", "experiment_id": experiment_id,
        })
        refresh_token = self._remember_action(scope, {
            "kind": "experiment", "experiment_id": experiment_id,
        })
        if history_token:
            buttons.append({"text": "📜 История версий", "callback": f"uex:read:{history_token}"})
        if snapshot_token:
            buttons.append({"text": "🔎 Сохранённые исходные данные", "callback": f"uex:read:{snapshot_token}"})
        export_token = self._remember_action(scope, {
            "kind": "export_menu", "experiment_id": experiment_id,
        })
        if export_token:
            buttons.append({"text": "⬇️ Выгрузить историю", "callback": f"uex:read:{export_token}"})
        if refresh_token:
            buttons.append({"text": "↻ Обновить карточку", "callback": f"uex:read:{refresh_token}"})
        buttons.extend([
            {"text": "↩️ История экспериментов", "callback": "uex:experiments:0"},
            {"text": "↩️ Эксперименты", "callback": "uex:m"},
        ])
        lines.extend([
            "", "Данные перечитаны из сохранённых версий; Ozon не опрашивался. "
            "Поздний результат появится после обновления карточки.",
        ])
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_DETAIL", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_experiment_history(self, scope, action):
        experiment_id = action.get("experiment_id")
        offset = action.get("offset", 0)
        listed = self.repository.list_price_experiment_revisions(
            experiment_id, limit=10, offset=offset,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_REVISION_HISTORY_UNAVAILABLE")
        lines = ["📜 История версий эксперимента · только чтение"]
        buttons = []
        for item in listed.get("items", []):
            lines.append(
                f"#{item['revision']} · {self._state_label(item['status'])} · "
                f"{item['created_at']} · состояние {item['state_revision']}"
            )
            token = self._remember_action(scope, {
                "kind": "experiment_revision", "experiment_id": experiment_id,
                "revision": item["revision"], "offset": offset,
            })
            if token:
                buttons.append({
                    "text": f"Открыть версию #{item['revision']}",
                    "callback": f"uex:read:{token}",
                })
        if not listed.get("items"):
            lines.append("История пока пуста.")
        if listed.get("has_more") is True:
            next_token = self._remember_action(scope, {
                "kind": "experiment_history", "experiment_id": experiment_id,
                "offset": listed.get("next_offset"),
            })
            if next_token:
                buttons.append({"text": "➡️ Следующие версии", "callback": f"uex:read:{next_token}"})
        self._append_experiment_back_button(scope, experiment_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_REVISION_HISTORY", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_experiment_revision(self, scope, action):
        experiment_id, revision = action.get("experiment_id"), action.get("revision")
        listed = self.repository.list_price_experiment_revisions(
            experiment_id, limit=10, offset=action.get("offset", 0),
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_REVISION_UNAVAILABLE")
        item = next((value for value in listed.get("items", [])
                     if value.get("revision") == revision), None)
        if item is None:
            return self._stale()
        config = item["config"]
        identity = config["identity"]
        lines = [
            f"📜 Версия эксперимента #{revision} · только чтение",
            f"SKU {identity['sku']} · {self._state_label(item['status'])}",
            f"Показатель: {self._metric_label(config['metric'])}",
            "Кандидаты: " + ", ".join(
                self._format_price(value) for value in config["candidate_prices_cents"]
            ) + " ₽",
            f"План: {config['planned_duration_days']} дней; порог "
            f"{config['decision_threshold_rub']} ₽/шт.",
            "Эта ревизия не меняет текущий эксперимент.",
        ]
        buttons = []
        self._append_experiment_back_button(scope, experiment_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_REVISION_DETAIL", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_phase(self, scope, action):
        experiment_id, phase_id = action.get("experiment_id"), action.get("phase_id")
        loaded = self._load_phase(scope, experiment_id, phase_id)
        if loaded is None:
            return self._stale()
        phase = loaded
        config = phase["config"]
        collections = self.repository.list_price_experiment_phase_collections(
            experiment_id, phase_id, limit=1,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        results = self.repository.list_price_experiment_results(
            experiment_id, phase_id, limit=1,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if any(not isinstance(value, dict) or value.get("error") is True
               for value in (collections, results)):
            return self._error("UNIT_ECONOMICS_EXPERIMENT_PHASE_DETAIL_UNAVAILABLE")
        latest_collection = (collections.get("items") or [None])[0]
        latest_result = (results.get("items") or [None])[0]
        lines = [
            f"📊 {self._phase_label(phase['kind'])} · сегмент {config['segment_number']}",
            f"Статус: {self._state_label(phase['status'])}",
            f"Цена продавца: {self._format_price(config['planned_price_cents'])} ₽",
            f"Окно: {config['planned_from_date']} — {config['planned_to_date']} ({config['timezone']})",
            f"Ревизии: состояние {phase['state_revision']}, результаты {phase['result_revision']}",
        ]
        if latest_collection:
            lines.append(
                f"Последний сбор #{latest_collection['collection_revision']}: "
                f"{latest_collection['created_at']} · снимок {latest_collection['collection_id'][:12]}"
            )
        else:
            lines.append("Сбор метрик ещё не сохранён.")
        if latest_result:
            payload = latest_result["payload"]
            lines.append(
                f"Последняя оценка #{latest_result['result_revision']}: "
                f"{self._outcome_label(payload['outcome'])} · {latest_result['created_at']}"
            )
        buttons = []
        phase_history_token = self._remember_action(scope, {
            "kind": "phase_history", "experiment_id": experiment_id, "phase_id": phase_id,
        })
        result_token = self._remember_action(scope, {
            "kind": "phase_results", "experiment_id": experiment_id, "phase_id": phase_id,
        })
        if phase_history_token:
            buttons.append({"text": "📜 История фазы", "callback": f"uex:read:{phase_history_token}"})
        if result_token and results.get("items"):
            buttons.append({"text": "💡 Результаты и причины", "callback": f"uex:read:{result_token}"})
        observation_id = phase.get("observation_id")
        if isinstance(observation_id, str) and observation_id and self.observation_runtime_service:
            buttons.append({
                "text": "📈 Открыть сбор метрик",
                "callback": f"upo:o:{observation_id}",
            })
        token = self._remember_action(scope, {"kind": "experiment", "experiment_id": experiment_id})
        if token:
            buttons.append({"text": "↩️ К эксперименту", "callback": f"uex:read:{token}"})
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_PHASE_DETAIL", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_phase_history(self, scope, action):
        experiment_id, phase_id = action.get("experiment_id"), action.get("phase_id")
        offset = action.get("offset", 0)
        listed = self.repository.list_price_experiment_phase_revisions(
            experiment_id, phase_id, limit=10, offset=offset,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_PHASE_HISTORY_UNAVAILABLE")
        lines, buttons = ["📜 История ревизий фазы · только чтение"], []
        for item in listed.get("items", []):
            lines.append(
                f"#{item['revision']} · {self._state_label(item['status'])} · "
                f"{item['created_at']} · состояние {item['state_revision']} · "
                f"результат {item['result_revision']}"
            )
            token = self._remember_action(scope, {
                "kind": "phase_revision", "experiment_id": experiment_id,
                "phase_id": phase_id, "revision": item["revision"], "offset": offset,
            })
            if token:
                buttons.append({"text": f"Открыть ревизию #{item['revision']}", "callback": f"uex:read:{token}"})
        if not listed.get("items"):
            lines.append("Ревизии пока не сохранены.")
        if listed.get("has_more") is True:
            next_token = self._remember_action(scope, {
                "kind": "phase_history", "experiment_id": experiment_id,
                "phase_id": phase_id, "offset": listed.get("next_offset"),
            })
            if next_token:
                buttons.append({"text": "➡️ Следующие ревизии", "callback": f"uex:read:{next_token}"})
        self._append_phase_back_button(scope, experiment_id, phase_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_PHASE_HISTORY", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_phase_revision(self, scope, action):
        experiment_id, phase_id, revision = (
            action.get("experiment_id"), action.get("phase_id"), action.get("revision")
        )
        listed = self.repository.list_price_experiment_phase_revisions(
            experiment_id, phase_id, limit=10, offset=action.get("offset", 0),
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_PHASE_REVISION_UNAVAILABLE")
        item = next((value for value in listed.get("items", [])
                     if value.get("revision") == revision), None)
        if item is None:
            return self._stale()
        config = item["config"]
        message = (
            f"📜 Ревизия фазы #{revision} · только чтение\n"
            f"{self._phase_label(config['kind'])} · {self._state_label(item['status'])}\n"
            f"Цена {self._format_price(config['planned_price_cents'])} ₽ · "
            f"{config['planned_from_date']} — {config['planned_to_date']} "
            f"({config['timezone']})\n"
            f"Ревизии: состояние {item['state_revision']}, результаты {item['result_revision']}"
        )
        buttons = []
        self._append_phase_back_button(scope, experiment_id, phase_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_PHASE_REVISION_DETAIL", message, self._keyboard(buttons),
        )

    def _show_phase_results(self, scope, action):
        experiment_id, phase_id = action.get("experiment_id"), action.get("phase_id")
        offset = action.get("offset", 0)
        listed = self.repository.list_price_experiment_results(
            experiment_id, phase_id, limit=10, offset=offset,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_RESULT_HISTORY_UNAVAILABLE")
        lines, buttons = ["💡 История результатов · сохранённые вычисления"], []
        for item in listed.get("items", []):
            payload = item["payload"]
            lines.append(
                f"#{item['result_revision']} · {self._outcome_label(payload['outcome'])} · "
                f"{item['created_at']} · снимок {item['content_hash'][:12]}"
            )
            token = self._remember_action(scope, {
                "kind": "result", "experiment_id": experiment_id,
                "phase_id": phase_id, "result_revision": item["result_revision"],
                "offset": offset,
            })
            if token:
                buttons.append({"text": f"Открыть результат #{item['result_revision']}", "callback": f"uex:read:{token}"})
        if not listed.get("items"):
            lines.append("Сохранённых результатов пока нет. После сбора и оценки данные появятся здесь.")
        if listed.get("has_more") is True:
            next_token = self._remember_action(scope, {
                "kind": "phase_results", "experiment_id": experiment_id,
                "phase_id": phase_id, "offset": listed.get("next_offset"),
            })
            if next_token:
                buttons.append({"text": "➡️ Следующие результаты", "callback": f"uex:read:{next_token}"})
        self._append_phase_back_button(scope, experiment_id, phase_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_RESULT_HISTORY", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_result(self, scope, action):
        experiment_id, phase_id = action.get("experiment_id"), action.get("phase_id")
        revision = action.get("result_revision")
        listed = self.repository.list_price_experiment_results(
            experiment_id, phase_id, limit=10, offset=action.get("offset", 0),
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_RESULT_UNAVAILABLE")
        item = next((value for value in listed.get("items", [])
                     if value.get("result_revision") == revision), None)
        if item is None:
            return self._stale()
        candidates = self._latest_candidate_results(scope, experiment_id)
        recommendation = UnitEconomicsExperimentRecommendationService.explain_result(
            item["payload"], evaluated_candidates=candidates,
        )
        if recommendation.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_RECOMMENDATION_UNAVAILABLE")
        payload = item["payload"]
        lines = [
            f"💡 Результат #{revision} · {self._outcome_label(payload['outcome'])}",
            recommendation["explanation"],
            recommendation["next_step"],
        ]
        if payload.get("window"):
            window = payload["window"]
            lines.append(
                f"Окно данных: {window['from_date']} — {window['to_date']} ({window['timezone']})"
            )
        if payload.get("baseline_profit_per_unit_rub") is not None:
            lines.append(f"База: {payload['baseline_profit_per_unit_rub']} ₽/шт.")
        if payload.get("candidate_profit_per_unit_rub") is not None:
            lines.append(f"Кандидат: {payload['candidate_profit_per_unit_rub']} ₽/шт.")
        if payload.get("delta_profit_per_unit_rub") is not None:
            lines.append(f"Изменение модели: {payload['delta_profit_per_unit_rub']} ₽/шт.")
        reasons = recommendation.get("reason_codes", [])
        if reasons:
            lines.extend(["Причины ограничений:"])
            lines.extend("• " + self._reason_label(code) for code in reasons[:6])
            if len(reasons) > 6:
                lines.append(f"• Ещё причин: {len(reasons) - 6}")
        ranking = recommendation.get("candidate_ranking") or {}
        if ranking.get("status") == "RANKED":
            lines.append(
                f"Максимум среди {ranking['evaluated_candidate_count']} "
                f"сопоставимых оценённых цен: {ranking['maximum_profit_per_unit_rub']} ₽/шт."
            )
        lines.append(
            "Результат отражает модель по сохранённым данным, не доказывает причинность "
            "и не меняет цену в Ozon."
        )
        buttons = []
        self._append_phase_back_button(scope, experiment_id, phase_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_RESULT_DETAIL", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_frozen_snapshot(self, scope, action):
        experiment_id = action.get("experiment_id")
        frozen = self.repository.get_price_experiment_frozen_snapshot(
            experiment_id, owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(frozen, dict) or frozen.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_UNAVAILABLE")
        projection = UnitEconomicsExperimentSnapshotViewService.project(frozen)
        if projection.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT_INVALID")
        view = projection["view"]
        revisions = view["revisions"]
        economics = view["economics"]
        stored_projection = economics.get("projection") or {}
        lines = [
            "🔎 Сохранённые исходные данные · без обновления источников",
            f"Режим расчёта: {view['calculation_mode']}",
            f"План: ревизия {revisions['plan_revision']}, "
            f"расчётная версия {revisions['plan_calculation_version']}",
            f"Снимок расходов: {revisions['expense_snapshot_fingerprint'][:16]}",
            f"Покрытие расходов: {'полное' if view['expense_coverage']['coverage_complete'] else 'неполное'}",
        ]
        if stored_projection.get("available") is True:
            for key, label in (("revenue", "Выручка"), ("profit_before_tax", "Прибыль до налога"),
                               ("tax", "Налог"), ("profit", "Прибыль модели")):
                value = stored_projection.get(key)
                if value is not None:
                    lines.append(f"{label}: {value} ₽/шт.")
        tariff = view.get("tariff") or {}
        if tariff.get("revision") is not None:
            lines.append(f"Профиль комиссии: ревизия {tariff['revision']}")
        quantity = view.get("quantity_evidence") or {}
        lines.append("Количество: " + (
            f"результат ревизии {quantity.get('result_revision')}"
            if quantity.get("status") != "UNKNOWN" else "не подтверждено"
        ))
        if view.get("model_limits"):
            lines.append("Ограничения: " + ", ".join(view["model_limits"][:5]))
        lines.append("Показан зафиксированный снимок; данные Ozon не запрашивались и не пересчитаны.")
        buttons = []
        self._append_experiment_back_button(scope, experiment_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_FROZEN_SNAPSHOT", "\n".join(lines), self._keyboard(buttons),
        )

    def _show_export_menu(self, scope, action):
        if self.history_export_service is None:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_UNAVAILABLE")
        experiment_id = action.get("experiment_id")
        buttons = []
        for file_format, label in (("json", "JSON"), ("csv", "CSV")):
            token = self._remember_action(scope, {
                "kind": "export", "experiment_id": experiment_id,
                "file_format": file_format,
            })
            if token:
                buttons.append({"text": label, "callback": f"uex:read:{token}"})
        self._append_experiment_back_button(scope, experiment_id, buttons)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_EXPORT_FORMAT",
            "Выгрузить все сохранённые версии, фазы, результаты, контрольные события "
            "и решения для этого эксперимента. Источники не обновляются, экономика "
            "не пересчитывается; идентификаторы владельца, магазина, товара и фаз скрыты.",
            self._keyboard(buttons),
        )

    def _export_history(self, scope, action):
        if self.history_export_service is None:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_UNAVAILABLE")
        result = self.history_export_service.export(
            action.get("experiment_id"), action.get("file_format"),
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(result, dict):
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_FAILED")
        if result.get("error") is True:
            return self._error(result.get("code", "UNIT_ECONOMICS_EXPERIMENT_EXPORT_FAILED"))
        return result

    def _latest_candidate_results(self, scope, experiment_id):
        phases = self.repository.list_price_experiment_phases(
            experiment_id, limit=10, owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(phases, dict) or phases.get("error") is True:
            return []
        candidates = []
        for phase in phases.get("items", []):
            if phase.get("kind") != "CANDIDATE":
                continue
            listed = self.repository.list_price_experiment_results(
                experiment_id, phase["phase_id"], limit=1,
                owner_id=scope["owner_id"], store_id=scope["store_id"],
            )
            if (not isinstance(listed, dict) or listed.get("error") is True
                    or not listed.get("items")):
                continue
            latest = listed["items"][0]
            candidates.append({
                "phase_id": phase["phase_id"],
                "result_revision": latest["result_revision"],
                "latest_result_revision": phase["result_revision"],
                "payload": latest["payload"],
            })
        return candidates[:UnitEconomicsExperimentRecommendationService.MAX_CANDIDATES]

    def _load_phase(self, scope, experiment_id, phase_id):
        listed = self.repository.list_price_experiment_phases(
            experiment_id, limit=10, owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(listed, dict) or listed.get("error") is True:
            return None
        return next((item for item in listed.get("items", [])
                     if item.get("phase_id") == phase_id), None)

    def _append_experiment_back_button(self, scope, experiment_id, buttons):
        token = self._remember_action(scope, {"kind": "experiment", "experiment_id": experiment_id})
        if token:
            buttons.append({"text": "↩️ К эксперименту", "callback": f"uex:read:{token}"})

    def _append_phase_back_button(self, scope, experiment_id, phase_id, buttons):
        token = self._remember_action(scope, {
            "kind": "phase", "experiment_id": experiment_id, "phase_id": phase_id,
        })
        if token:
            buttons.append({"text": "↩️ К фазе", "callback": f"uex:read:{token}"})

    def _list_plans(self, scope, offset):
        if offset < 0 or offset % self.PAGE_SIZE or offset > 100:
            return self._stale()
        result = self.repository.list_documents(
            owner_id=scope["owner_id"], store_id=scope["store_id"],
            limit=self.PAGE_SIZE, offset=offset,
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_PLAN_LIST_UNAVAILABLE")
        rows = []
        for document in result.get("items", []):
            if not isinstance(document, dict):
                continue
            loaded = self.repository.get_document(
                document.get("document_id"), revision=document.get("revision"),
                owner_id=scope["owner_id"], store_id=scope["store_id"],
            )
            value = loaded.get("document") if isinstance(loaded, dict) else None
            payload = value.get("payload") if isinstance(value, dict) else None
            items = payload.get("items") if isinstance(payload, dict) else None
            if value is None or value.get("status") != "ACTIVE" or not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                identity = self._plan_identity(item, scope)
                if identity is None:
                    continue
                token = self._remember_action(scope, {
                    "kind": "plan", "document_id": value["document_id"],
                    "revision": value["revision"], "item_index": index,
                    "identity": identity,
                })
                if token:
                    rows.append((identity["sku"], token))
        if not rows:
            message = (
                "Не найден сохранённый план для FBO/SKU в текущем магазине. "
                "Сначала рассчитайте цену и сохраните план в разделе «Плановая экономика»; "
                "эксперимент не создаётся из черновика другого магазина."
            )
            buttons = [{"text": "💾 Открыть сохранённые планы", "callback": "upp:m"}]
        else:
            message = "Выберите сохранённый план и SKU для эксперимента:"
            buttons = [
                {"text": f"SKU {sku}", "callback": f"uex:a:{token}"}
                for sku, token in rows[:self.PAGE_SIZE]
            ]
        if result.get("has_more"):
            buttons.append({
                "text": "➡️ Ещё планы",
                "callback": f"uex:plans:{offset + self.PAGE_SIZE}",
            })
        buttons.extend([
            {"text": "↩️ Эксперименты", "callback": "uex:m"},
            {"text": "Отмена", "callback": "uex:c"},
        ])
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_PLAN_SELECTION", message, self._keyboard(buttons),
        )

    def _select_plan(self, scope, action):
        loaded = self.repository.get_document(
            action.get("document_id"), revision=action.get("revision"),
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        document = loaded.get("document") if isinstance(loaded, dict) else None
        payload = document.get("payload") if isinstance(document, dict) else None
        items = payload.get("items") if isinstance(payload, dict) else None
        index = action.get("item_index")
        if (document is None or document.get("status") != "ACTIVE"
                or not isinstance(items, list) or type(index) is not int
                or not 0 <= index < len(items)
                or self._plan_identity(items[index], scope) != action.get("identity")):
            return self._stale()
        identity = action["identity"]
        complete = []
        offset = 0
        for _ in range(self.MAX_SNAPSHOT_PAGES):
            snapshots = self.repository.list_unit_economics_expense_snapshots(
                identity=identity, owner_id=scope["owner_id"], store_id=scope["store_id"],
                limit=self.PAGE_SIZE, offset=offset,
            )
            if not isinstance(snapshots, dict) or snapshots.get("error") is True:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_SNAPSHOT_LIST_UNAVAILABLE")
            for row in snapshots.get("items", []):
                read = self.repository.get_unit_economics_expense_snapshot(
                    row.get("snapshot_id"), owner_id=scope["owner_id"], store_id=scope["store_id"],
                )
                snapshot = read.get("payload") if isinstance(read, dict) and not read.get("error") else None
                readiness = snapshot.get("readiness") if isinstance(snapshot, dict) else None
                window = readiness.get("window") if isinstance(readiness, dict) else None
                if (isinstance(readiness, dict)
                        and readiness.get("status") == "COMPLETE"
                        and readiness.get("scope_kind") == "REFERENCE_56_COMPLETED_LOCAL_DAYS"
                        and readiness.get("coverage_complete") is True
                        and isinstance(window, dict)
                        and window.get("timezone") == self.default_timezone
                        and self._date_span(window.get("from_date"), window.get("to_date")) == 56):
                    token = self._remember_action(scope, {
                        "kind": "snapshot", "document_id": action["document_id"],
                        "revision": action["revision"], "item_index": index,
                        "identity": identity, "snapshot_id": row["snapshot_id"],
                    })
                    if token:
                        complete.append((row["snapshot_id"], window, token))
            if not snapshots.get("has_more"):
                break
            offset = snapshots.get("next_offset")
            if type(offset) is not int:
                break
        else:
            return self._result(
                "UNIT_ECONOMICS_EXPERIMENT_SNAPSHOT_SCAN_LIMIT",
                "Снимков для этого SKU слишком много, и текущего лимита страниц недостаточно, "
                "чтобы проверить весь список. Эксперимент не запускается; неизвестные данные "
                "не считаются нулевыми.",
                self._keyboard([
                    {"text": "↩️ Выбрать план", "callback": "uex:b"},
                    {"text": "Отмена", "callback": "uex:c"},
                ]),
            )
        if not complete:
            return self._result(
                "UNIT_ECONOMICS_EXPERIMENT_REFERENCE_SNAPSHOT_REQUIRED",
                f"Для SKU {identity['sku']} нет полного снимка расходов за 56 завершённых дней. "
                "Я не подставляю нули и не запускаю неполный эксперимент. В текущем мастере "
                "автоматический сбор такого базового снимка пока не подключён.",
                self._keyboard([
                    {"text": "↩️ Выбрать план", "callback": "uex:b"},
                    {"text": "↩️ Сохранённые планы", "callback": "upp:m"},
                    {"text": "Отмена", "callback": "uex:c"},
                ]),
            )
        buttons = [
            {
                "text": f"56 дней · {window['from_date']} — {window['to_date']}",
                "callback": f"uex:a:{token}",
            }
            for _, window, token in complete[:self.PAGE_SIZE]
        ]
        buttons.extend([
            {"text": "↩️ Выбрать план", "callback": "uex:b"},
            {"text": "Отмена", "callback": "uex:c"},
        ])
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_SNAPSHOT_SELECTION",
            f"Выберите сохранённый полный снимок расходов для SKU {identity['sku']}:",
            self._keyboard(buttons),
        )

    def _select_snapshot(self, scope, action):
        loaded = self.repository.get_document(
            action.get("document_id"), revision=action.get("revision"),
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        document = loaded.get("document") if isinstance(loaded, dict) else None
        payload = document.get("payload") if isinstance(document, dict) else None
        items = payload.get("items") if isinstance(payload, dict) else None
        index = action.get("item_index")
        if (document is None or document.get("status") != "ACTIVE"
                or not isinstance(items, list) or type(index) is not int
                or not 0 <= index < len(items)
                or self._plan_identity(items[index], scope) != action.get("identity")):
            return self._stale()
        snapshot = self.repository.get_unit_economics_expense_snapshot(
            action.get("snapshot_id"), owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        snapshot_payload = snapshot.get("payload") if isinstance(snapshot, dict) else None
        readiness = snapshot_payload.get("readiness") if isinstance(snapshot_payload, dict) else None
        if (not isinstance(snapshot, dict) or snapshot.get("error") is True
                or not isinstance(snapshot_payload, dict)
                or snapshot_payload.get("identity") != action["identity"]
                or not isinstance(readiness, dict)
                or readiness.get("status") != "COMPLETE"
                or readiness.get("scope_kind") != "REFERENCE_56_COMPLETED_LOCAL_DAYS"
                or readiness.get("coverage_complete") is not True
                or readiness.get("window", {}).get("timezone") != self.default_timezone):
            return self._stale()
        self._set_pending(scope, {
            "stage": "candidate_prices", "document_id": action["document_id"],
            "revision": action["revision"], "item_index": index,
            "identity": action["identity"], "snapshot_id": action["snapshot_id"],
            "created_at": self.monotonic_clock(),
        })
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_PRICES_REQUIRED",
            "Введите от 2 до 10 цен продавца для проверки через точку с запятой, "
            "например: 95; 99,90; 105. Бот сравнит только цены, которые вы указали; "
            "он не прогнозирует спрос и не меняет цены в Ozon.",
            self._cancel_keyboard(),
        )

    def _create_and_preview_baseline(self, scope, pending, parsed):
        identity = pending.get("identity")
        document = self.repository.get_document(
            pending.get("document_id"), revision=pending.get("revision"),
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        doc = document.get("document") if isinstance(document, dict) else None
        payload = doc.get("payload") if isinstance(doc, dict) else None
        items = payload.get("items") if isinstance(payload, dict) else None
        index = pending.get("item_index")
        if (doc is None or doc.get("status") != "ACTIVE" or not isinstance(items, list)
                or type(index) is not int or not 0 <= index < len(items)
                or self._plan_identity(items[index], scope) != identity):
            self.clear_pending(scope["owner_id"])
            return self._stale()
        snapshot = self.repository.get_unit_economics_expense_snapshot(
            pending.get("snapshot_id"), owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        snapshot_payload = snapshot.get("payload") if isinstance(snapshot, dict) else None
        readiness = snapshot_payload.get("readiness") if isinstance(snapshot_payload, dict) else None
        if (not isinstance(snapshot_payload, dict)
                or snapshot_payload.get("identity") != identity
                or not isinstance(readiness, dict)
                or readiness.get("status") != "COMPLETE"
                or readiness.get("coverage_complete") is not True
                or readiness.get("window", {}).get("timezone") != self.default_timezone):
            self.clear_pending(scope["owner_id"])
            return self._stale()

        prices = pending.get("candidate_prices_cents")
        minimum, maximum = min(prices), max(prices)
        flags = {key: "UNKNOWN" for key in (
            "inventory", "promotion", "advertising", "card", "cost", "tariff",
        )}
        now = self._aware_now()
        if now is None:
            self.clear_pending(scope["owner_id"])
            return self._error("UNIT_ECONOMICS_EXPERIMENT_CLOCK_UNAVAILABLE")
        experiment_payload = {
            "schema_version": 1, "identity": identity,
            "title": (
                f"Цена SKU {identity['sku']} · "
                f"{now.astimezone(ZoneInfo(self.default_timezone)).date().isoformat()}"
            ),
            "metric": "MAX_RUB_PER_UNIT", "calculation_mode": "WINDOW_COST_ALLOCATION",
            "source_references": {
                "plan": {"document_id": pending["document_id"], "revision": pending["revision"]},
                "expense_snapshot_id": pending["snapshot_id"],
                "tariff": None, "observation": None,
            },
            "candidate_prices_cents": prices,
            "candidate_price_bounds_cents": {
                "min_price_cents": minimum, "max_price_cents": maximum,
            },
            "decision_threshold_rub": "0.01",
            "planned_duration_days": self.DEFAULT_DURATION_DAYS,
            "currency": "RUB", "control_flags": flags,
            "plan_schema_version": 1, "maturity_min_days": 7, "maturity_min_units": 30,
        }
        created = self.repository.create_price_experiment(
            experiment_payload, idempotency_key=pending["create_key"],
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(created, dict) or created.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_CREATE_FAILED")
        zone = ZoneInfo(self.default_timezone)
        start = now.astimezone(zone).date() + timedelta(days=1)
        end = start + timedelta(days=self.DEFAULT_DURATION_DAYS - 1)
        phase_payload = {
            "schema_version": 1, "kind": "BASELINE", "segment_number": 1,
            "planned_price_cents": parsed["price_cents"],
            "expense_snapshot_id": pending["snapshot_id"],
            "planned_from_date": start.isoformat(), "planned_to_date": end.isoformat(),
            "timezone": self.default_timezone, "control_flags": flags,
        }
        phase = self.repository.create_price_experiment_phase(
            created["experiment_id"], phase_payload,
            expected_state_revision=created["state_revision"],
            idempotency_key=pending["phase_key"],
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(phase, dict) or phase.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_BASELINE_PHASE_FAILED")
        ready = self.repository.transition_price_experiment(
            created["experiment_id"], "mark_ready",
            expected_state_revision=phase["experiment_state_revision"],
            idempotency_key=pending["ready_key"],
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(ready, dict) or ready.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_READINESS_FAILED")
        preview = self.repository.preview_price_experiment_phase_confirmation(
            created["experiment_id"], phase["phase_id"],
            seller_price_cents=parsed["price_cents"], effective_from=parsed["effective_from"],
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(preview, dict) or preview.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_BASELINE_PREVIEW_FAILED")
        token = self._remember_action(scope, {
            "kind": "confirm", "experiment_id": created["experiment_id"],
            "phase_id": phase["phase_id"], "price_cents": parsed["price_cents"],
            "effective_from": parsed["effective_from"],
            "experiment_revision": preview["experiment_state_revision"],
            "phase_revision": preview["phase_state_revision"],
            "idempotency_key": token_hex(16),
        })
        if not token:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_CONFIRMATION_UNAVAILABLE")
        self.clear_pending(scope["owner_id"])
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_CONFIRMATION_REQUIRED",
            f"Проверьте базовую фазу. Цена: {self._format_price(parsed['price_cents'])} ₽. "
            f"Период: {start.isoformat()} — {end.isoformat()} ({self.default_timezone}). "
            f"Первая полная дата после установки цены: {preview.get('first_full_local_day')}.\n\n"
            "Подтверждение означает только ваши сведения о цене и времени; история цены Ozon "
            "не проверена. После подтверждения бот сохранит эксперимент локально и не изменит Ozon.",
            self._keyboard([
                {"text": "✅ Подтверждаю и начать", "callback": f"uex:a:{token}"},
                {"text": "Отмена", "callback": "uex:c"},
            ]),
        )

    def _confirm_baseline(self, scope, action):
        result = self.repository.confirm_price_experiment_phase(
            action["experiment_id"], action["phase_id"],
            seller_price_cents=action["price_cents"],
            effective_from=action["effective_from"], owner_confirmed=True,
            expected_state_revision=action["experiment_revision"],
            expected_phase_state_revision=action["phase_revision"],
            idempotency_key=action["idempotency_key"],
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_CONFIRMATION_FAILED")
        self.clear_pending(scope["owner_id"])
        self._clear_actions(scope)
        return self._result(
            "UNIT_ECONOMICS_EXPERIMENT_BASELINE_ACTIVE",
            "Базовая фаза запущена. Цена и время отмечены как подтверждённые вами; "
            "это не доказательство истории цены Ozon. Бот не менял цену и не выполнял API-запросов.",
            self._home_keyboard(),
        )

    def _parse_baseline_input(self, value):
        if not isinstance(value, str) or len(value) > 160:
            return None
        pieces = value.split(";", 1)
        if len(pieces) != 2:
            return None
        price = self._price_cents(pieces[0])
        if price is None:
            return None
        try:
            zone = ZoneInfo(self.default_timezone)
            local = datetime.strptime(pieces[1].strip(), "%Y-%m-%d %H:%M")
            effective = local.replace(tzinfo=zone)
            if effective.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != local:
                return None
            now = self._aware_now()
        except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
            return None
        if now is None or effective.astimezone(timezone.utc) > now.astimezone(timezone.utc):
            return None
        return {"price_cents": price, "effective_from": effective.isoformat()}

    @classmethod
    def _parse_price_list(cls, value):
        if not isinstance(value, str) or len(value) > 160:
            return None
        parts = cls._PRICE_LIST_SEPARATOR.split(value.strip())
        if not 2 <= len(parts) <= 10:
            return None
        prices = [cls._price_cents(item) for item in parts]
        if any(item is None for item in prices) or len(set(prices)) != len(prices):
            return None
        return sorted(prices)

    @classmethod
    def _price_cents(cls, value):
        if not isinstance(value, str):
            return None
        normalized = value.strip().replace(" ", "").replace(",", ".")
        try:
            amount = Decimal(normalized)
            cents = amount * 100
        except (InvalidOperation, ValueError, TypeError):
            return None
        if (not amount.is_finite() or amount <= 0 or cents != cents.to_integral_value()
                or cents > cls.MAX_PRICE_CENTS):
            return None
        return int(cents)

    def _plan_identity(self, item, scope):
        if not isinstance(item, dict):
            return None
        value = item.get("identity")
        inputs = item.get("inputs")
        if not isinstance(value, dict) or not isinstance(inputs, dict):
            return None
        if str(value.get("store_id") or "") != scope["store_id"]:
            return None
        if str(value.get("scheme") or "").upper() != "FBO":
            return None
        keys = ("product_id", "offer_id", "sku")
        if any(not isinstance(value.get(key), (str, int)) or not str(value[key]).strip() for key in keys):
            return None
        return {
            "owner_id": scope["owner_id"], "store_id": scope["store_id"],
            "product_id": str(value["product_id"]).strip(),
            "offer_id": str(value["offer_id"]).strip(),
            "sku": str(value["sku"]).strip(), "sale_schema": "FBO",
        }

    @staticmethod
    def _date_span(start, end):
        try:
            return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        except (TypeError, ValueError):
            return None

    def _scope(self, user_id):
        owner = str(user_id or "").strip()
        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        scoped_owner, store_id = split_store_tenant_scope(tenant_scope)
        if not owner or not tenant_scope or owner != str(scoped_owner or "") or not store_id:
            return None
        return {
            "owner_id": owner, "store_id": str(store_id), "tenant_scope": tenant_scope,
            "key": (owner, tenant_scope),
        }

    def _clear_other_scopes(self, scope):
        with self._lock:
            for key in list(self._pending):
                if key[0] == scope["owner_id"] and key != scope["key"]:
                    self._pending.pop(key, None)
            for token, record in list(self._actions.items()):
                if (record.get("owner_id") == scope["owner_id"]
                        and record.get("tenant_scope") != scope["tenant_scope"]):
                    self._actions.pop(token, None)

    def _set_pending(self, scope, value):
        value = deepcopy(value)
        value.setdefault("create_key", token_hex(16))
        value.setdefault("phase_key", token_hex(16))
        value.setdefault("ready_key", token_hex(16))
        with self._lock:
            self._pending[scope["key"]] = value
            self._pending.move_to_end(scope["key"])
            while len(self._pending) > self.MAX_PENDING:
                self._pending.popitem(last=False)

    def _save_pending(self, scope, value):
        self._set_pending(scope, value)

    def _remember_action(self, scope, value):
        token = token_hex(8)
        record = deepcopy(value)
        record.update({
            "owner_id": scope["owner_id"], "store_id": scope["store_id"],
            "tenant_scope": scope["tenant_scope"], "created_at": self.monotonic_clock(),
        })
        with self._lock:
            self._prune_locked()
            self._actions[token] = record
            self._actions.move_to_end(token)
            while len(self._actions) > self.MAX_ACTIONS:
                self._actions.popitem(last=False)
        return token

    def _get_action(self, token, scope):
        with self._lock:
            self._prune_locked()
            record = self._actions.get(token)
            record = deepcopy(record) if record is not None else None
        if (record is None or record.get("owner_id") != scope["owner_id"]
                or record.get("store_id") != scope["store_id"]
                or record.get("tenant_scope") != scope["tenant_scope"]):
            return None
        return record

    def _remove_action(self, token):
        with self._lock:
            self._actions.pop(token, None)

    def _clear_actions(self, scope):
        with self._lock:
            for token, record in list(self._actions.items()):
                if (record.get("owner_id") == scope["owner_id"]
                        and record.get("tenant_scope") == scope["tenant_scope"]):
                    self._actions.pop(token, None)

    def _cancel_confirmation_drafts(self, scope):
        with self._lock:
            pending = [
                deepcopy(record) for record in self._actions.values()
                if (record.get("kind") == "confirm"
                    and record.get("owner_id") == scope["owner_id"]
                    and record.get("tenant_scope") == scope["tenant_scope"])
            ]
        cancelled = False
        for action in pending:
            result = self.repository.transition_price_experiment(
                action["experiment_id"], "cancel",
                expected_state_revision=action["experiment_revision"],
                idempotency_key=token_hex(16),
                owner_id=scope["owner_id"], store_id=scope["store_id"],
            )
            cancelled = cancelled or (
                isinstance(result, dict) and result.get("error") is False
                and result.get("status") == "CANCELLED"
            )
        return cancelled

    def _prune_locked(self):
        now = self.monotonic_clock()
        for token, value in list(self._actions.items()):
            if now - value.get("created_at", 0) > self.ACTION_TTL_SECONDS:
                self._actions.pop(token, None)
        for key, value in list(self._pending.items()):
            if now - value.get("created_at", 0) > self.PENDING_TTL_SECONDS:
                self._pending.pop(key, None)

    def _aware_now(self):
        try:
            value = self.clock()
        except Exception:
            return None
        return value if isinstance(value, datetime) and value.tzinfo is not None else None

    @staticmethod
    def _keyboard(buttons):
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    def _home_keyboard(self):
        return self._keyboard([
            {"text": "➕ Новый эксперимент", "callback": "uex:new"},
            {"text": "↩️ Юнит-экономика", "callback": "unit_economics"},
            {"text": "↩️ Главное меню", "callback": "main_menu"},
        ])

    def _cancel_keyboard(self):
        return self._keyboard([
            {"text": "Отмена", "callback": "uex:c"},
            {"text": "↩️ Эксперименты", "callback": "uex:m"},
        ])

    @staticmethod
    def _state_label(value):
        return {
            "DRAFT": "черновик", "READY": "готов", "BASELINE_ACTIVE": "базовая фаза",
            "BASELINE_REVIEW": "анализ базовой фазы", "CANDIDATE_READY": "кандидат готов",
            "CANDIDATE_ACTIVE": "тест цены", "CANDIDATE_REVIEW": "анализ теста",
            "PAUSED": "пауза", "CANCELLED": "отменён", "COMPLETED": "завершён",
            "ARCHIVED": "архив", "ACTIVE": "активна", "PLANNED": "запланирована",
            "FINISHED": "завершена",
        }.get(value, "статус неизвестен")

    @staticmethod
    def _phase_label(value):
        return {"BASELINE": "Базовая цена", "CANDIDATE": "Цена-кандидат"}.get(value, "Фаза")

    @staticmethod
    def _metric_label(value):
        return {"MAX_RUB_PER_UNIT": "максимальная прибыль с единицы"}.get(
            value, "неизвестная метрика",
        )

    @staticmethod
    def _outcome_label(value):
        return {
            "CONTINUE_COLLECTING": "нужно больше данных",
            "FIX_DATA_OR_CONDITIONS": "нужно исправить данные/условия",
            "INCOMPARABLE": "фазы несопоставимы",
            "NO_CLEAR_DIFFERENCE": "разница ниже порога",
            "CANDIDATE_BETTER_IN_MODEL": "кандидат лучше в модели",
            "BASELINE_BETTER_IN_MODEL": "база лучше в модели",
        }.get(value, "результат недоступен")

    @staticmethod
    def _reason_label(code):
        return {
            "PHASE_NOT_MATURE_AND_READY": "период или объём продаж ещё недостаточны",
            "PHASE_CONTROL_CONDITIONS_NOT_CONFIRMED": "условия теста не подтверждены",
            "SOLD_UNIT_DENOMINATOR_UNCONFIRMED": "число проданных единиц не подтверждено",
            "PHASE_FINANCIAL_OR_UNIT_DATA_INCOMPLETE": "финансовые данные или количество неполны",
            "RETURNED_UNIT_DISPOSITION_UNKNOWN": "неизвестен исход части возвратов",
            "COST_OR_EXPENSE_SNAPSHOT_CHANGED": "изменилась себестоимость или снимок расходов",
            "PHASE_CONTROL_FLAGS_DIFFER": "условия сравниваемых фаз отличаются",
            "PHASE_CONTROL_FLAGS_CHANGED_OR_UNKNOWN": "одно из контрольных условий неизвестно или изменилось",
            "PHASE_WINDOWS_OVERLAP_OR_REVERSED": "периоды фаз пересекаются или идут не по порядку",
            "WINDOW_DURATION_OR_WEEKDAY_COVERAGE_DIFFERS": "длительность/дни недели не совпадают",
            "TIMEZONE_OR_WINDOW_INVALID": "не удалось проверить даты или часовой пояс",
            "SOURCE_AS_OF_INVALID": "дата актуальности источника некорректна",
            "SOURCE_AS_OF_MATURITY_DIFFERS": "снимки данных имеют разную зрелость",
            "STRICT_RETAINED_COHORT_DISPOSITION_UNAVAILABLE": "нельзя подтвердить точную когорту выкупа",
            "BASELINE_AND_CANDIDATE_PRICE_ARE_EQUAL": "цены базовой и тестовой фаз совпадают",
        }.get(code, "не выполнена проверка качества данных")

    @staticmethod
    def _short_label(value, max_length):
        text = " ".join(str(value or "").split())
        return text if len(text) <= max_length else text[:max_length - 1] + "…"

    @staticmethod
    def _format_price(cents):
        return f"{cents // 100:,}".replace(",", " ") + f",{cents % 100:02d}"

    @staticmethod
    def _result(status, message, keyboard):
        return {
            "error": False, "status": status, "message": message,
            "keyboard": keyboard, "read_only": True, "executed": False,
        }

    @staticmethod
    def _error(code):
        return {
            "error": True, "code": code,
            "message": "Не удалось продолжить настройку эксперимента. Откройте меню экспериментов и попробуйте снова.",
            "read_only": True, "executed": False,
        }

    @staticmethod
    def _stale():
        return {
            "error": False, "status": "UNIT_ECONOMICS_EXPERIMENT_ACTION_STALE",
            "message": "Действие устарело или относится к другому магазину. Откройте мастер заново.",
            "read_only": True, "executed": False,
        }
