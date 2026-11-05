"""Short-lived, tenant-scoped Telegram flow for batch seller-price plans."""

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from secrets import token_hex
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.planning_cross_docking_adapter import PlanningCrossDockingAdapter
from services.planning_extended_scenario_adapter import PlanningExtendedScenarioAdapter
from services.period_profit_operation_diagnostics import current_period_profit_trace
from services.tenant_context import get_current_tenant_user_id
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter


class TelegramUnitPriceBatchPlanRuntimeService:
    PENDING_TTL_SECONDS = 600
    SNAPSHOT_TTL_SECONDS = 600
    MAX_PENDING = 64
    MAX_BATCHES = 64
    MAX_ACTIONS = 512
    PAGE_SIZE = 5
    TEXT_LIMIT_UTF16 = 3500

    FIELD_LABELS = {
        "price": "Цена продавца ₽/шт.",
        "cost": "Себестоимость ₽/шт.",
        "commission_rate": "Комиссия %",
        "advertising_rate": "Реклама %",
        "discount_points_rate": "Баллы за скидки %",
        "logistics_per_unit": "Логистика ₽/шт.",
        "last_mile_per_unit": "Последняя миля ₽/шт.",
        "acquiring_per_unit": "Эквайринг ₽/шт.",
    }
    STATUS_LABELS = {
        "READY": "цель подтверждена",
        "INCOMPLETE_INPUTS": "нужны допущения",
        "SOURCE_UNAVAILABLE": "источник недоступен",
        "SOURCE_STALE": "снимок устарел",
        "UNSUPPORTED_SCHEME": "схема не поддерживается",
        "TARGET_NOT_CONFIRMED": "цена для цели не подтверждена",
        "BUDGET_EXHAUSTED": "лимит запроса исчерпан",
    }

    def __init__(
        self,
        batch_plan_service,
        product_overview_service,
        keyboard_service,
        single_price_runtime_service=None,
        sensitivity_runtime_service=None,
        clock=None,
        tenant_scope_provider=None,
        analytics_export_service=None,
        advertising_cap_service=None,
    ):
        self.batch_plan_service = batch_plan_service
        self.product_overview_service = product_overview_service
        self.keyboard_service = keyboard_service
        self.single_price_runtime_service = single_price_runtime_service
        self.sensitivity_runtime_service = sensitivity_runtime_service
        self.analytics_export_service = analytics_export_service
        self.advertising_cap_service = advertising_cap_service
        self.clock = clock or monotonic
        self.tenant_scope_provider = tenant_scope_provider or get_current_tenant_user_id
        self._pending = OrderedDict()
        self._batches = OrderedDict()
        self._actions = OrderedDict()
        self._refresh_tickets = OrderedDict()
        self._lock = RLock()

    def begin_from_overview_selection(self, user_id):
        scope = self._scope(user_id)
        if scope.get("error"):
            return self._context_error()
        try:
            selection = self.product_overview_service.get_price_plan_selection()
        except Exception:
            return self._error("BATCH_PLAN_SELECTION_UNAVAILABLE")
        items = selection.get("items") if isinstance(selection, dict) else None
        if not isinstance(items, list) or not 2 <= len(items) <= 10:
            return self._result(
                "UNIT_PRICE_BATCH_SELECTION_REQUIRED",
                "Для пакетного плана выберите в обзоре от 2 до 10 разных товаров одного магазина.",
                self._prompt_keyboard(),
            )
        ticket = token_hex(8)
        key = scope["key"]
        with self._lock:
            current_entry = self._batches.get(key)
            current_batch = (
                current_entry.get("batch")
                if isinstance(current_entry, dict)
                and self.clock() - current_entry.get("stored_at", 0)
                < self.SNAPSHOT_TTL_SECONDS
                else None
            )
            self._refresh_tickets.pop(key, None)
            self._pending[key] = {
                "ticket": ticket,
                "kind": "batch_target",
                "items": deepcopy(items),
                "base_batch_id": current_batch.get("batch_id")
                if isinstance(current_batch, dict)
                else None,
                "base_batch_version": current_batch.get("version")
                if isinstance(current_batch, dict)
                else None,
                "created_at": self.clock(),
                "processing": False,
            }
            self._pending.move_to_end(key)
            self._evict_locked(self._pending, self.MAX_PENDING)
        return self._result(
            "UNIT_PRICE_BATCH_TARGET_INPUT_REQUIRED",
            f"Выбрано товаров: {len(items)}. Введите целевую маржу от 0 до 100%. Для 0% бот проверит безубыточность. Расчёт плановый, отдельно для каждой единицы товара.",
            self._prompt_keyboard(),
        )

    def has_pending(self, user_id):
        scope = self._scope(user_id)
        if scope.get("error"):
            return False
        with self._lock:
            pending = self._pending.get(scope["key"])
            return (
                isinstance(pending, dict)
                and self.clock() - pending.get("created_at", 0)
                <= self.PENDING_TTL_SECONDS
            )

    def handle_text(self, text, user_id=None):
        scope = self._scope(user_id)
        if scope.get("error"):
            owner = str(user_id or "").strip()
            with self._lock:
                has_scoped_state = any(
                    key[0] == owner
                    for mapping in (self._pending, self._batches)
                    for key in mapping
                )
            if has_scoped_state:
                self._clear_other_scopes(owner, scope.get("tenant_scope"))
                return self._result(
                    "UNIT_PRICE_BATCH_CONTEXT_CHANGED",
                    "Активный магазин изменился или недоступен. Начните пакетный план заново из обзора товаров.",
                    self._main_keyboard(),
                )
            return None
        key = scope["key"]
        pending, error = self._claim_pending(key)
        if pending is None:
            if error is None:
                with self._lock:
                    entry = self._batches.get(key)
                    current_batch = (
                        deepcopy(entry.get("batch"))
                        if isinstance(entry, dict)
                        else None
                    )
                if isinstance(current_batch, dict):
                    current_batch = self._get_batch(
                        scope,
                        current_batch.get("batch_id"),
                        current_batch.get("version"),
                    )
                    if current_batch is not None:
                        return self._render(
                            scope,
                            current_batch,
                            notice="Используйте кнопки ниже для изменения плана. Этот текст ничего не изменил.",
                        )
            if error == "OTHER_SCOPE":
                self._clear_other_scopes(scope["owner_id"], scope["tenant_scope"])
                return self._result(
                    "UNIT_PRICE_BATCH_CONTEXT_CHANGED",
                    "Активный магазин изменился. Начните пакетный план заново из обзора товаров.",
                    self._main_keyboard(),
                )
            if error == "BUSY":
                return self._result(
                    "UNIT_PRICE_BATCH_WORK_IN_PROGRESS",
                    "Пакетный расчёт уже обрабатывается. Дождитесь его результата.",
                    self._cancel_keyboard(),
                )
            if error == "EXPIRED":
                return self._result(
                    "UNIT_PRICE_BATCH_INPUT_EXPIRED",
                    "Ввод пакетного плана истёк. Начните его заново из обзора товаров.",
                    self._main_keyboard(),
                )
            return None

        stage = pending.get("kind")
        if stage == "batch_target":
            parsed = self.batch_plan_service.target_planning_service.parse_target_margin(
                str(text or "")
            )
            if parsed.get("error"):
                self._release_pending(key, pending["ticket"])
                return self._result(
                    "UNIT_PRICE_BATCH_TARGET_INPUT_REQUIRED",
                    "Не понял целевую маржу. Введите число от 0 до 100%, не более двух знаков после запятой.",
                    self._prompt_keyboard(),
                )
            result = self.batch_plan_service.build(
                pending.get("items"),
                user_id=scope["owner_id"],
                target_margin_percent=parsed["normalized"],
                parent_trace=current_period_profit_trace(),
            )
            if result.get("error") is True:
                self._release_pending(key, pending["ticket"])
                return self._error(result.get("code"), keyboard=self._prompt_keyboard())
            if not self._publish_initial_batch(scope, pending, result):
                return self._result(
                    "UNIT_PRICE_BATCH_RESULT_STALE",
                    "Запрос устарел после смены магазина или нового действия. Откройте обзор снова.",
                    self._main_keyboard(),
                )
            return self._render(scope, result)

        batch = self._batch_for_pending(scope, pending)
        if batch is None:
            self._complete_pending(key, pending["ticket"])
            return self._stale()
        if stage == "target_edit":
            result = self.batch_plan_service.set_target_margin(batch, str(text or ""))
            if result.get("error") is True:
                self._release_pending(key, pending["ticket"])
                return self._result(
                    "UNIT_PRICE_BATCH_TARGET_INPUT_REQUIRED",
                    "Цель не изменилась. Введите процент от 0 до 100, не более двух знаков после запятой.",
                    self._cancel_keyboard(),
                )
            return self._finish_mutation(scope, pending, result)
        if stage == "row_edit":
            result = self.batch_plan_service.edit_row_assumption(
                batch,
                pending.get("row_id"),
                pending.get("field"),
                str(text or "").strip(),
            )
            if result.get("error") is True:
                self._release_pending(key, pending["ticket"])
                label = self.FIELD_LABELS.get(pending.get("field"), "значение")
                return self._result(
                    "UNIT_PRICE_BATCH_ASSUMPTION_INPUT_REQUIRED",
                    f"Значение для «{label}» не принято. Введите число в допустимом диапазоне; 0 допустим, если это ваше подтверждённое допущение.",
                    self._cancel_keyboard(),
                )
            return self._finish_mutation(scope, pending, result)
        if stage == "advertising_rate":
            preview = self.batch_plan_service.preview_advertising_rate(
                batch,
                pending.get("row_ids"),
                str(text or "").strip(),
            )
            if preview.get("error") is True:
                self._release_pending(key, pending["ticket"])
                return self._result(
                    "UNIT_PRICE_BATCH_ADVERTISING_INPUT_REQUIRED",
                    "Не удалось проверить рекламную долю. Введите число от 0 до 100%; исходные сценарии не менялись.",
                    self._cancel_keyboard(),
                )
            self._complete_pending(key, pending["ticket"])
            return self._show_advertising_preview(scope, batch, preview)
        self._complete_pending(key, pending["ticket"])
        return self._stale()

    def handle_callback(self, callback, user_id=None):
        scope = self._scope(user_id)
        if scope.get("error"):
            return self._context_error()
        value = str(callback or "")
        if value == "upb:c":
            self.clear_pending(user_id)
            return self._result(
                "UNIT_PRICE_BATCH_CANCELLED",
                "Ввод пакетного плана отменён. Сохранённый снимок товаров не изменился.",
                self._main_keyboard(),
            )
        parts = value.split(":")
        if len(parts) != 3 or parts[:2] != ["upb", "a"]:
            return self._stale()
        action = self._consume_action(parts[2], scope)
        if not isinstance(action, dict):
            return self._stale()
        batch = self._get_batch(scope, action.get("batch_id"), action.get("batch_version"))
        if batch is None:
            return self._stale()
        kind = action.get("kind")
        if kind == "export":
            if self.analytics_export_service is None or action.get("file_format") not in {"csv", "json"}:
                return self._error("ANALYTICS_EXPORT_UNAVAILABLE")
            export_batch = self._project_batch_freshness(batch)
            return self.analytics_export_service.export_unit_price_batch(
                export_batch,
                action["file_format"],
                active_sort=action.get("sort_by", "selection"),
            )
        if kind == "page":
            return self._render(
                scope, batch, page=action.get("page", 1),
                sort_by=action.get("sort_by", "selection"),
            )
        if kind == "sort":
            return self._render(scope, batch, sort_by=action.get("sort_by", "selection"))
        if kind == "target_edit":
            return self._begin_batch_input(scope, batch, "target_edit")
        if kind == "row_edit_menu":
            return self._row_edit_menu(scope, batch, action.get("row_id"))
        if kind == "row_edit":
            return self._begin_batch_input(
                scope, batch, "row_edit",
                row_id=action.get("row_id"), field=action.get("field"),
            )
        if kind == "open_candidate":
            opener = getattr(
                self.single_price_runtime_service, "open_batch_candidate", None
            )
            if not callable(opener):
                return self._error("UNIT_PRICE_SCENARIO_HANDOFF_UNAVAILABLE")
            return opener(
                batch,
                action.get("row_id"),
                user_id=scope["owner_id"],
                expected_batch_version=action.get("batch_version"),
            )
        if kind == "sensitivity":
            runtime = self.sensitivity_runtime_service
            opener = getattr(runtime, "begin_from_context", None)
            context_reader = getattr(self, "get_sensitivity_context", None)
            if not callable(opener) or not callable(context_reader):
                return self._error("UNIT_PRICE_SENSITIVITY_UNAVAILABLE")
            context = context_reader(
                action.get("batch_id"),
                action.get("batch_version"),
                action.get("row_id"),
                user_id=scope["owner_id"],
            )
            return opener(context, user_id=scope["owner_id"])
        if kind == "advertising_cap":
            return self._show_advertising_cap(scope, batch, action.get("row_id"))
        if kind == "advertising_cap_apply":
            return self._apply_advertising_cap(scope, batch, action)
        if kind == "advertising_rate":
            return self._begin_batch_input(
                scope, batch, "advertising_rate",
                row_ids=action.get("row_ids"),
            )
        if kind == "advertising_confirm":
            result = self.batch_plan_service.apply_advertising_rate(
                batch,
                action.get("row_ids"),
                action.get("rate"),
                confirmed=True,
                expected_batch_id=action.get("batch_id"),
                expected_batch_version=action.get("batch_version"),
            )
            if result.get("error") is True:
                return self._stale()
            if not self._publish_batch_update(
                scope,
                result,
                expected_batch_id=action.get("batch_id"),
                expected_version=action.get("batch_version"),
            ):
                return self._stale()
            return self._render(scope, result, notice="Рекламная доля применена только к локальным допущениям.")
        if kind == "advertising_cancel":
            self._revoke_batch_actions(
                scope,
                action.get("batch_id"),
                action.get("batch_version"),
                kinds={"advertising_confirm"},
            )
            return self._result(
                "UNIT_PRICE_BATCH_ADVERTISING_CANCELLED",
                "Изменение рекламной доли отменено. План не изменён.",
                self._render(scope, batch)["keyboard"],
                batch=batch,
            )
        if kind == "refresh":
            refresh_ticket = self._begin_refresh(scope, batch)
            if refresh_ticket is None:
                return self._stale()
            result = self.batch_plan_service.refresh(
                batch, parent_trace=current_period_profit_trace()
            )
            if result.get("error") is True:
                self._finish_refresh_error(scope, refresh_ticket)
                return self._error(result.get("code"))
            if not self._publish_refresh(
                scope, batch, refresh_ticket, result
            ):
                return self._result(
                    "UNIT_PRICE_BATCH_RESULT_STALE",
                    "Обновление источников завершилось после отмены или изменения плана. Старый результат не применён.",
                    self._main_keyboard(),
                )
            return self._render(scope, result, notice="Источники обновлены; ручные допущения сохранены.")
        return self._stale()

    def get_sensitivity_context(self, batch_id, batch_version, row_id, user_id=None):
        """Read an immutable row snapshot for source-free sensitivity planning."""
        scope = self._scope(user_id)
        if scope.get("error"):
            return {"error": True, "code": "UNIT_PRICE_BATCH_CONTEXT_UNAVAILABLE"}
        batch = self._get_batch(scope, batch_id, batch_version)
        if batch is None:
            return {"error": True, "code": "UNIT_PRICE_BATCH_ACTION_STALE"}
        matches = [row for row in batch.get("rows", []) if row.get("row_id") == row_id]
        if len(matches) != 1:
            return {"error": True, "code": "UNIT_PRICE_BATCH_ACTION_STALE"}
        row = matches[0]
        snapshot = row.get("snapshot")
        if not isinstance(snapshot, dict):
            return {"error": True, "code": "UNIT_PRICE_BATCH_SNAPSHOT_UNAVAILABLE"}
        snapshot_identity = deepcopy(snapshot.get("identity") or {})
        row_identity = row.get("identity") or {}
        if (
            snapshot_identity.get("tenant_scope") != scope["tenant_scope"]
            or str(snapshot_identity.get("product_id") or "") != str(row_identity.get("product_id") or "")
            or str(snapshot_identity.get("offer_id") or "") != str(row_identity.get("offer_id") or "")
            or str(snapshot_identity.get("sku") or "") != str(row_identity.get("catalog_sku") or "")
            or str(snapshot_identity.get("store_id") or "") != str(scope["store_id"] or "")
        ):
            return {"error": True, "code": "UNIT_PRICE_BATCH_IDENTITY_MISMATCH"}
        age_at_load = self._seconds(row.get("source_age_seconds_at_load"), 0.0)
        loaded_at = self._seconds(row.get("source_loaded_at"), self.clock())
        ttl = min(self._seconds(row.get("source_ttl_seconds"), 0.0), self.SNAPSHOT_TTL_SECONDS)
        age = age_at_load + max(0.0, float(self.clock()) - loaded_at)
        periods = deepcopy(snapshot.get("source_periods") or {})
        return {
            "error": False,
            "snapshot": snapshot,
            "identity": snapshot_identity,
            "inputs": deepcopy(row.get("inputs") or {}),
            "extended_scenario": deepcopy(row.get("extended_scenario")),
            "strict_return_evidence": deepcopy(row.get("strict_return_evidence")),
            "provenance": deepcopy(row.get("provenance") or {}),
            "sources": {
                "periods": periods,
                "as_of": periods.get("seller_price_as_of"),
                "completeness": deepcopy(snapshot.get("source_completeness") or {}),
            },
            "frozen_tariff_resolution": deepcopy(row.get("frozen_tariff_resolution")),
            "legacy_tariff_price_cents": row.get("legacy_tariff_price_cents"),
            "source_age_seconds": age,
            "source_ttl_seconds": ttl,
            "source_version": f"{batch['batch_id']}:{batch['version']}:{row_id}",
            "source_as_of": periods,
            "target_margin_percent": deepcopy(batch.get("target_margin_percent")),
            "origin": {
                "kind": "batch",
                "batch_id": batch["batch_id"],
                "batch_version": batch["version"],
                "row_id": row_id,
                "owner_id": scope["owner_id"],
                "tenant_scope": scope["tenant_scope"],
            },
            "read_only": True,
            "executed": False,
        }

    def _show_advertising_cap(self, scope, batch, row_id):
        if self.advertising_cap_service is None:
            return self._error("UNIT_PRICE_ADVERTISING_CAP_UNAVAILABLE")
        context = self.get_sensitivity_context(
            batch.get("batch_id"), batch.get("version"), row_id,
            user_id=scope["owner_id"],
        )
        if context.get("error") is True:
            return self._stale()
        result = self.advertising_cap_service.solve(
            context.get("inputs"), batch.get("target_margin_percent"),
            identity=context.get("identity"), provenance=context.get("provenance"),
            sources=context.get("sources"),
            **self._extended_scenario_kwargs(context),
        )
        fresh = (
            context.get("source_ttl_seconds", 0) > 0
            and context.get("source_age_seconds", float("inf")) < context.get("source_ttl_seconds", 0)
        )
        inputs = context.get("inputs") or {}
        lines = [
            "Допустимые расходы на рекламу · сохранённая строка плана",
            f"Цена продавца: {inputs.get('price', '—')} ₽/шт.; целевая маржа: {batch.get('target_margin_percent', '—')}%.",
            "Комиссия на этой цене: "
            + (f"{inputs.get('commission_rate')}%" if inputs.get('commission_rate') is not None else "не подтверждена")
            + " · " + str((context.get("provenance") or {}).get("commission_rate") or "источник неизвестен") + ".",
            f"Исходные тарифы: {'актуальны' if fresh else 'устарели; подстановка отключена'}.",
            "Результат относится к одной успешной продаже и не прогнозирует эффективность кампании.",
        ]
        buttons = []
        for criterion, key, label in (
            ("break_even", "break_even", "Безубыточность"),
            ("target", "target", "Целевая маржа"),
        ):
            outcome = result.get(key) or {}
            if outcome.get("available") is True:
                lines.append(
                    f"{label}: {outcome.get('advertising_rate')}% = {outcome.get('advertising_per_unit')} ₽/шт.; "
                    f"прибыль {outcome.get('profit_per_unit')} ₽; запас {outcome.get('headroom_percentage_points')} п.п. / {outcome.get('headroom_per_unit')} ₽/шт."
                )
                if fresh:
                    buttons.append({
                        "text": f"Подставить · {label.lower()}",
                        "callback": self._register_action(
                            scope, batch, "advertising_cap_apply", row_id=row_id,
                            criterion=criterion, advertising_rate=outcome.get("advertising_rate"),
                            source_version=context.get("source_version"),
                        ),
                    })
            else:
                lines.append(f"{label}: предел не подтверждён ({outcome.get('status', result.get('code', 'UNAVAILABLE'))}).")
        buttons.extend([
            {"text": "Назад к плану", "callback": self._register_action(scope, batch, "page", page=1)},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return self._result(
            "UNIT_PRICE_BATCH_ADVERTISING_CAP_RESULT", "\n".join(lines)[:3000],
            self._keyboard(buttons),
        )

    def _apply_advertising_cap(self, scope, batch, action):
        if self.advertising_cap_service is None:
            return self._stale()
        row_id = action.get("row_id")
        context = self.get_sensitivity_context(
            batch.get("batch_id"), batch.get("version"), row_id,
            user_id=scope["owner_id"],
        )
        if (context.get("error") is True
                or context.get("source_version") != action.get("source_version")
                or context.get("source_ttl_seconds", 0) <= 0
                or context.get("source_age_seconds", float("inf")) >= context.get("source_ttl_seconds", 0)):
            return self._stale()
        fresh_cap = self.advertising_cap_service.solve(
            context.get("inputs"), batch.get("target_margin_percent"),
            identity=context.get("identity"), provenance=context.get("provenance"),
            sources=context.get("sources"),
            **self._extended_scenario_kwargs(context),
        )
        key = action.get("criterion")
        outcome = (fresh_cap.get(key) or {}) if isinstance(fresh_cap, dict) else {}
        if (outcome.get("available") is not True
                or outcome.get("advertising_rate") != action.get("advertising_rate")):
            return self._stale()
        updated = self.batch_plan_service.edit_row_assumption(
            batch, row_id, "advertising_rate", action.get("advertising_rate"),
        )
        if updated.get("error") is True or not self._publish_batch_update(
            scope, updated, expected_batch_id=batch.get("batch_id"),
            expected_version=batch.get("version"),
        ):
            return self._stale()
        return self._render(
            scope, updated,
            notice="Рекламный предел применён только к локальным допущениям строки. Кампании Ozon не изменялись.",
        )

    def get_saved_plan_capture(self, batch_id, batch_version, user_id=None):
        """Return a defensive, exact-version recipe for explicit local save."""
        scope = self._scope(user_id)
        if scope.get("error"):
            return self._context_error()
        if isinstance(batch_version, str) and batch_version.isdigit():
            batch_version = int(batch_version)
        if type(batch_version) is not int or batch_version < 1:
            return self._stale()
        batch = self._get_batch(scope, batch_id, batch_version)
        if batch is None or not 2 <= len(batch.get("rows") or []) <= 10:
            return self._stale()
        rows = []
        for row in batch["rows"]:
            if not isinstance(row, dict) or not isinstance(row.get("identity"), dict):
                return self._stale()
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            identity = row["identity"]
            source_identity = snapshot.get("identity") or {}
            sku = str(identity.get("catalog_sku") or "").strip()
            product_id = str(identity.get("product_id") or "").strip()
            offer_id = str(identity.get("offer_id") or "").strip()
            if not sku or not product_id or not offer_id:
                return self._stale()
            if snapshot and (
                str(source_identity.get("product_id") or "") != product_id
                or str(source_identity.get("offer_id") or "") != offer_id
                or str(source_identity.get("sku") or "") != sku
                or str(source_identity.get("tenant_scope") or "") != scope["tenant_scope"]
                or str(source_identity.get("store_id") or "") != str(scope["store_id"] or "")
            ):
                return self._stale()
            product = snapshot.get("product") or {}
            inputs = deepcopy(row.get("inputs") or {})
            inputs.setdefault("cross_docking_per_unit", None)
            provenance = deepcopy(row.get("provenance") or {})
            cross_docking = PlanningCrossDockingAdapter.project_source(
                snapshot.get("cross_docking")
            )
            provenance.setdefault("cross_docking_per_unit", "unknown")
            completeness = deepcopy(snapshot.get("source_completeness") or {})
            completeness["cross_docking"] = PlanningCrossDockingAdapter.completeness_projection(
                cross_docking
            )
            sources = {
                "periods": deepcopy(snapshot.get("source_periods") or {}),
                "as_of": (snapshot.get("source_periods") or {}).get("seller_price_as_of"),
                "loaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "completeness": completeness,
                "cross_docking": cross_docking,
                **({"tariff_resolution": deepcopy(row.get("frozen_tariff_resolution"))}
                   if isinstance(row.get("frozen_tariff_resolution"), dict) else {}),
            }
            identity_for_calc = {
                "user_id": scope["owner_id"], "store_id": scope["store_id"],
                "tenant_scope": scope["tenant_scope"], "sku": sku,
                "product_id": product_id, "offer_id": offer_id,
            }
            extended_scenario = row.get("extended_scenario")
            strict_return_evidence = row.get("strict_return_evidence")
            if extended_scenario is not None:
                extended_scenario = PlanningExtendedScenarioAdapter.project_extended(
                    extended_scenario
                )
                identity_for_calc.update({
                    "owner_id": scope["owner_id"],
                    "sale_schema": str(product.get("scheme") or row.get("scheme") or "FBO").upper(),
                })
                if extended_scenario is None:
                    return self._stale()
            elif strict_return_evidence is not None:
                return self._stale()
            projection_result = self.batch_plan_service.scenario_service.calculate(
                inputs, identity=identity_for_calc, provenance=provenance,
                sources={"periods": sources["periods"], "as_of": sources["as_of"],
                         "completeness": sources["completeness"]},
                **self._extended_scenario_kwargs({
                    "extended_scenario": extended_scenario,
                    "strict_return_evidence": strict_return_evidence,
                }),
            )
            if extended_scenario is not None and (
                projection_result.get("available") is not True
                or (projection_result.get("extended_calculation") or {}).get("status") != "APPLIED"
            ):
                return self._stale()
            if strict_return_evidence is not None:
                strict_return_evidence = PlanningExtendedScenarioAdapter.project_strict_evidence(
                    strict_return_evidence,
                    {key: identity_for_calc.get(key) for key in
                     PlanningExtendedScenarioAdapter.STRICT_IDENTITY_FIELDS},
                )
                if strict_return_evidence is None:
                    return self._stale()
            calculated = projection_result.get("calculated") or {}
            projection = {
                "status": str(row.get("status") or "INCOMPLETE_INPUTS"),
                "available": projection_result.get("available") is True,
                "missing_inputs": list(projection_result.get("missing_inputs") or row.get("missing_inputs") or [])[:20],
                "invalid_inputs": list(projection_result.get("invalid_inputs") or [])[:20],
            }
            for field in (
                "revenue", "discount_points", "taxable_revenue", "commission",
                "advertising", "fees", "profit_before_tax", "tax",
                "effective_tax_rate", "profit", "margin_percent", "cross_docking",
            ):
                projection[field] = calculated.get(field)
            if extended_scenario is not None:
                projection["additional_unit_expenses"] = calculated.get(
                    "additional_unit_expenses"
                )
            saved_row = {
                "row_id": str(row.get("row_id") or "")[:64],
                "identity": {
                    "product_id": product_id, "offer_id": offer_id, "sku": sku,
                    "product_name": str(product.get("name") or "")[:160] or None,
                    "store_id": str(scope["store_id"] or ""),
                    "scheme": str(product.get("scheme") or row.get("scheme") or "FBO")[:24],
                },
                "inputs": inputs, "provenance": provenance,
                "sources": sources, "projection": projection,
            }
            if extended_scenario is not None:
                saved_row["extended_scenario"] = extended_scenario
                if strict_return_evidence is not None:
                    saved_row["strict_return_evidence"] = strict_return_evidence
            rows.append(saved_row)
        return {
            "error": False,
            "batch_id": batch["batch_id"],
            "version": batch["version"],
            "tenant_scope": scope["tenant_scope"],
            "payload": {
                "plan_kind": "batch",
                "schema_version": (
                    4 if any(row.get("extended_scenario") is not None for row in rows)
                    else PlanningCrossDockingAdapter.CURRENT_VERSION
                ),
                "calculation_version": self.batch_plan_service.scenario_service.VERSION,
                "target_margin_percent": batch.get("target_margin_percent"),
                "items": rows,
            },
            "read_only": True, "executed": False,
        }

    def restore_saved_plan(self, payload, user_id=None):
        """Open stored rows locally; source TTL is zero until explicit refresh."""
        scope = self._scope(user_id)
        if scope.get("error"):
            return self._context_error()
        if (
            not isinstance(payload, dict)
            or payload.get("plan_kind") != "batch"
            or not isinstance(payload.get("items"), list)
            or not 2 <= len(payload["items"]) <= 10
        ):
            return self._stale()
        rows = []
        scenario_service = self.batch_plan_service.scenario_service
        for index, item in enumerate(payload["items"], start=1):
            if not isinstance(item, dict):
                return self._stale()
            identity = item.get("identity") or {}
            inputs, cross_docking = PlanningCrossDockingAdapter.restore_item(payload, item)
            if inputs is None or cross_docking is None:
                return self._stale()
            provenance = deepcopy(item.get("provenance") or {})
            sources = item.get("sources") or {}
            periods = deepcopy(sources.get("periods") or {})
            sku = str(identity.get("sku") or "").strip()
            product_id = str(identity.get("product_id") or "").strip()
            offer_id = str(identity.get("offer_id") or "").strip()
            if (
                not sku or not product_id or not offer_id
                or str(identity.get("store_id") or "") != str(scope["store_id"] or "")
            ):
                return self._stale()
            extended_scenario = None
            strict_return_evidence = None
            if payload.get("schema_version") == 4 and item.get("extended_scenario") is not None:
                extended_scenario = PlanningExtendedScenarioAdapter.project_extended(
                    item.get("extended_scenario")
                )
                if extended_scenario is None:
                    return self._stale()
                if item.get("strict_return_evidence") is not None:
                    strict_return_evidence = (
                        PlanningExtendedScenarioAdapter.project_strict_evidence(
                            item.get("strict_return_evidence"),
                            {
                                "owner_id": scope["owner_id"],
                                "store_id": str(identity.get("store_id") or ""),
                                "product_id": product_id, "offer_id": offer_id, "sku": sku,
                                "sale_schema": str(identity.get("scheme") or "FBO").upper(),
                            },
                        )
                    )
                    if strict_return_evidence is None:
                        return self._stale()
            elif item.get("strict_return_evidence") is not None:
                return self._stale()
            snapshot_identity = {
                "user_id": scope["owner_id"], "store_id": scope["store_id"],
                "tenant_scope": scope["tenant_scope"], "product_id": product_id,
                "offer_id": offer_id, "sku": sku,
            }
            snapshot = {
                "identity": snapshot_identity,
                "product": {"name": str(identity.get("product_name") or offer_id),
                            "scheme": str(identity.get("scheme") or "FBO")},
                "suggested_inputs": deepcopy(inputs),
                "input_provenance": deepcopy(provenance),
                "source_periods": periods,
                "source_completeness": deepcopy(sources.get("completeness") or {}),
                "cross_docking": PlanningCrossDockingAdapter.display_source(cross_docking),
            }
            frozen_tariff = None
            if "tariff_resolution" in sources:
                frozen_tariff = UnitPriceTariffSnapshotAdapter.validate(
                    sources.get("tariff_resolution"),
                    {
                        "owner_id": scope["owner_id"],
                        "store_id": scope["store_id"],
                        "product_id": product_id,
                        "offer_id": offer_id,
                        "sku": sku,
                    },
                    inputs,
                )
                if frozen_tariff is None:
                    return self._stale()
                snapshot["tariff_resolution"] = deepcopy(frozen_tariff)
            row_id = str(item.get("row_id") or identity.get("sku") or f"saved_{index}")[:64]
            if any(existing.get("row_id") == row_id for existing in rows):
                row_id = f"saved_{index}_{uuid4().hex[:8]}"
            identity_record = {
                "product_id": product_id, "offer_id": offer_id, "catalog_sku": sku,
            }
            result = scenario_service.calculate(
                inputs,
                identity={**snapshot_identity, "batch_id": "saved", "batch_version": 1, "row_id": row_id,
                          **({"owner_id": scope["owner_id"],
                             "sale_schema": str(identity.get("scheme") or "FBO").upper()}
                             if extended_scenario is not None else {})},
                provenance=provenance,
                sources={"periods": periods, "as_of": sources.get("as_of"),
                         "completeness": snapshot["source_completeness"]},
                **self._extended_scenario_kwargs({
                    "extended_scenario": extended_scenario,
                    "strict_return_evidence": strict_return_evidence,
                }),
            )
            if extended_scenario is not None and (
                result.get("available") is not True
                or (result.get("extended_calculation") or {}).get("status") != "APPLIED"
            ):
                return self._stale()
            manual = {
                field: {"value": value}
                for field, value in inputs.items()
                if provenance.get(field) in {
                    "manual", "manual_seller_assumption", "manual_unit_economics_input",
                }
            }
            rows.append({
                "row_id": row_id, "identity": identity_record, "scheme": identity.get("scheme") or "FBO",
                "status": "SOURCE_STALE", "snapshot_status": "SOURCE_STALE",
                "reason": "HISTORICAL_ASSUMPTIONS", "inputs": inputs,
                "provenance": provenance, "manual_assumptions": manual,
                "snapshot": snapshot, "scenario": result, "planning": {},
                "extended_scenario": deepcopy(extended_scenario),
                "strict_return_evidence": deepcopy(strict_return_evidence),
                "missing_inputs": result.get("missing_inputs") or [],
                "source_as_of": periods, "source_age_seconds_at_load": 0,
                "source_loaded_at": self.clock(), "source_ttl_seconds": 0,
                "frozen_tariff_resolution": deepcopy(frozen_tariff),
                "legacy_tariff_price_cents": (
                    UnitPriceTariffSnapshotAdapter.price_to_cents(inputs.get("price"))
                    if frozen_tariff is None and inputs.get("commission_rate") is not None
                    else None
                ),
            })
        target = payload.get("target_margin_percent")
        if target is None:
            target = "0"
        batch = {
            "error": False, "kind": "UNIT_PRICE_BATCH_PLAN",
            "batch_id": uuid4().hex[:20], "version": 1,
            "owner_id": scope["owner_id"], "store_id": scope["store_id"],
            "tenant_scope": scope["tenant_scope"],
            "target_margin_percent": str(target), "rows": rows,
            "rows_selected": len(rows), "rows_attempted": len(rows),
            "rows_completed": len(rows), "evaluation_count": 0,
            "evaluation_limit": self.batch_plan_service.BATCH_CALCULATION_LIMIT,
            "read_only": True, "executed": False,
            "restored_from_saved_plan": True,
        }
        key = scope["key"]
        with self._lock:
            self._store_batch_locked(key, batch)
        return self._render(
            scope, batch,
            notice="Открыты сохранённые допущения. Снимки источников помечены как исторические; для актуальных данных нажмите «Обновить источники».",
        )

    def edit_saved_plan_field(self, payload, row_id, field, user_id=None):
        """Open one exact restored batch row and start one field edit locally."""
        if field not in self.FIELD_LABELS:
            return self._error("BATCH_PLAN_FIELD_UNSUPPORTED")
        opened = self.restore_saved_plan(payload, user_id=user_id)
        batch = opened.get("batch_plan") if isinstance(opened, dict) else None
        if not isinstance(batch, dict) or batch.get("error") is True:
            return opened
        scope = self._scope(user_id)
        if scope.get("error"):
            return self._context_error()
        selected = [row for row in batch.get("rows", []) if row.get("row_id") == row_id]
        if len(selected) != 1:
            return self._stale()
        menu = self._row_edit_menu(scope, batch, row_id)
        label = self.FIELD_LABELS[field]
        callback = next((
            button.get("callback") for button in (menu.get("keyboard") or {}).get("buttons", [])
            if button.get("text") == label
        ), None)
        if not callback:
            return self._error("BATCH_PLAN_FIELD_UNSUPPORTED")
        result = self.handle_callback(callback, user_id=user_id)
        return {**result, "plan_editor": {
            "kind": "batch", "id": batch["batch_id"], "version": batch["version"],
        }}

    def apply_sensitivity_candidate(self, source_context, cell, user_id=None):
        """Re-read the same batch row and open a selected sweep cell locally."""
        origin = source_context.get("origin") if isinstance(source_context, dict) else None
        if not isinstance(origin, dict) or origin.get("kind") != "batch":
            return self._stale()
        current = self.get_sensitivity_context(
            origin.get("batch_id"),
            origin.get("batch_version"),
            origin.get("row_id"),
            user_id=user_id,
        )
        if (
            current.get("error") is True
            or current.get("source_version") != source_context.get("source_version")
            or current.get("identity") != source_context.get("identity")
            or current.get("inputs") != source_context.get("inputs")
            or current.get("provenance") != source_context.get("provenance")
            or current.get("sources") != source_context.get("sources")
            or current.get("extended_scenario") != source_context.get("extended_scenario")
            or current.get("strict_return_evidence") != source_context.get("strict_return_evidence")
            or current.get("source_age_seconds", float("inf"))
            >= current.get("source_ttl_seconds", 0)
            or current.get("source_ttl_seconds", 0) > self.SNAPSHOT_TTL_SECONDS
            or not isinstance(cell, dict)
            or cell.get("status") != "AVAILABLE"
            or cell.get("base_input_signature") != source_context.get("base_input_signature")
        ):
            return self._stale()
        current["base_input_signature"] = source_context["base_input_signature"]
        opener = getattr(self.single_price_runtime_service, "open_sensitivity_candidate", None)
        if not callable(opener):
            return self._error("UNIT_PRICE_SCENARIO_HANDOFF_UNAVAILABLE")
        return opener(current, cell, user_id=user_id)

    def show_sensitivity_origin(self, origin, user_id=None):
        scope = self._scope(user_id)
        if scope.get("error") or not isinstance(origin, dict):
            return self._context_error()
        batch = self._get_batch(
            scope, origin.get("batch_id"), origin.get("batch_version")
        )
        if batch is None:
            return self._stale()
        context = self.get_sensitivity_context(
            origin.get("batch_id"), origin.get("batch_version"),
            origin.get("row_id"), user_id=user_id,
        )
        if context.get("error") is True:
            return self._stale()
        return self._render(scope, batch, notice="Возврат к исходной строке плана.")

    def clear_pending(self, user_id):
        owner = str(user_id or "").strip()
        if not owner:
            return
        with self._lock:
            for key in [key for key in self._pending if key[0] == owner]:
                self._pending.pop(key, None)
            for key in [key for key in self._batches if key[0] == owner]:
                self._batches.pop(key, None)
            for key in [key for key in self._refresh_tickets if key[0] == owner]:
                self._refresh_tickets.pop(key, None)
            for token, action in list(self._actions.items()):
                if action.get("owner_id") == owner:
                    self._actions.pop(token, None)

    def clear_user_state(self, user_id):
        """Clear all transient batch state for an owner across every store."""
        self.clear_pending(user_id)

    def _begin_batch_input(self, scope, batch, kind, **fields):
        ticket = token_hex(8)
        pending = {
            "ticket": ticket,
            "kind": kind,
            "batch_id": batch["batch_id"],
            "batch_version": batch["version"],
            "created_at": self.clock(),
            "processing": False,
            **fields,
        }
        with self._lock:
            self._pending[scope["key"]] = pending
            self._pending.move_to_end(scope["key"])
            self._evict_locked(self._pending, self.MAX_PENDING)
        if kind == "target_edit":
            text = "Введите новую целевую маржу от 0 до 100%. Изменение пересчитает только сохранённые снимки."
        elif kind == "row_edit":
            label = self.FIELD_LABELS.get(fields.get("field"), "значение")
            text = f"Введите новое значение: {label}. Оно останется локальным допущением этого пакетного сценария."
        else:
            text = "Введите общую рекламную долю от 0 до 100%. Перед применением бот покажет изменяемые товары и запросит подтверждение."
        return self._result("UNIT_PRICE_BATCH_INPUT_REQUIRED", text, self._cancel_keyboard())

    def _show_advertising_preview(self, scope, batch, preview):
        action = self._register_action(
            scope,
            batch,
            "advertising_confirm",
            row_ids=[item["row_id"] for item in preview["rows"]],
            rate=preview["rows"][0]["new_value"],
        )
        lines = ["Проверьте общую рекламную долю перед применением:"]
        for item in preview["rows"]:
            lines.append(
                f"• {self._label(item)}: {self._number(item.get('previous_value'), '%')} → {self._number(item.get('new_value'), '%')}"
            )
        lines.append("Значение изменит только выбранные строки локального плана.")
        return self._result(
            "UNIT_PRICE_BATCH_ADVERTISING_CONFIRMATION_REQUIRED",
            "\n".join(lines),
            self._keyboard([
                {"text": "Подтвердить", "callback": action},
                {"text": "Отмена", "callback": self._register_action(
                    scope, batch, "advertising_cancel"
                )},
            ]),
        )

    def _row_edit_menu(self, scope, batch, row_id):
        rows = [row for row in batch.get("rows", []) if row.get("row_id") == row_id]
        row = rows[0] if len(rows) == 1 else None
        if row is None or not isinstance(row.get("snapshot"), dict):
            return self._stale()
        buttons = []
        for field, label in self.FIELD_LABELS.items():
            callback = self._register_action(
                scope, batch, "row_edit", row_id=row_id, field=field
            )
            buttons.append({"text": label, "callback": callback})
        buttons.append({"text": "К пакетному плану", "callback": self._register_action(scope, batch, "page", page=1)})
        return self._result(
            "UNIT_PRICE_BATCH_ROW_EDIT_MENU",
            "Выберите допущение для точечного изменения этой строки.",
            self._keyboard(buttons),
        )

    def _render(self, scope, batch, page=1, sort_by="selection", notice=None):
        batch = self._get_batch(scope, batch.get("batch_id"), batch.get("version")) or batch
        display_batch = self._project_batch_freshness(batch)
        rows = list(display_batch.get("rows") or [])
        if sort_by == "target_price":
            rows.sort(key=lambda row: self._sort_number(
                ((row.get("planning") or {}).get("target") or {}).get("price")
            ))
        elif sort_by == "profit":
            rows.sort(key=lambda row: self._sort_number(
                ((row.get("scenario") or {}).get("calculated") or {}).get("profit")
            ))
        page_count = max(1, (len(rows) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(1, min(int(page or 1), page_count))
        shown = rows[(page - 1) * self.PAGE_SIZE:page * self.PAGE_SIZE]
        status_counts = {}
        for row in rows:
            status_counts[row.get("status")] = status_counts.get(row.get("status"), 0) + 1
        lines = ["🧮 Пакетный план цены", f"Целевая маржа: {batch.get('target_margin_percent')}%", ""]
        lines.append(
            f"Товаров: {batch.get('rows_selected', len(rows))}; готово: {status_counts.get('READY', 0)}; неполно: {status_counts.get('INCOMPLETE_INPUTS', 0)}; требуется проверка: {len(rows) - status_counts.get('READY', 0) - status_counts.get('INCOMPLETE_INPUTS', 0)}."
        )
        if notice:
            lines.extend(["", notice])
        for index, row in enumerate(shown, start=(page - 1) * self.PAGE_SIZE + 1):
            inputs = row.get("inputs") or {}
            current = (row.get("scenario") or {}).get("calculated") or {}
            planning = row.get("planning") or {}
            break_even = planning.get("break_even") or {}
            target = planning.get("target") or {}
            lines.extend([
                "",
                f"{index}. {self._label(row)} — {self.STATUS_LABELS.get(row.get('status'), row.get('status', 'неизвестно'))}",
            ])
            if current.get("profit") is not None and current.get("margin_percent") is not None:
                lines.append(
                    f"Цена {self._number(inputs.get('price'), ' ₽')}; прибыль {self._number(current.get('profit'), ' ₽/шт.')} ({self._number(current.get('margin_percent'), '%')})."
                )
            if break_even.get("status") == "FOUND":
                lines.append(f"Безубыточность: {self._number(break_even.get('price'), ' ₽')}.")
            if target.get("status") == "FOUND" and row.get("status") == "READY":
                lines.append(
                    f"Для цели: {self._number(target.get('price'), ' ₽')}; прибыль {self._number(target.get('profit'), ' ₽/шт.')}; маржа {self._number(target.get('margin_percent'), '%')}."
                )
            if row.get("missing_inputs"):
                lines.append("Нужно указать: " + ", ".join(self.FIELD_LABELS.get(item, item) for item in row["missing_inputs"][:8]) + ".")
            if row.get("reason") and row.get("reason") != "NOT_STARTED":
                lines.append("Причина: " + str(row["reason"])[:90] + ".")
            periods = row.get("source_as_of") or {}
            commission_as_of = periods.get("commission_rate_as_of") or periods.get("seller_price_as_of")
            commission_provenance = (row.get("provenance") or {}).get("commission_rate", "unknown")
            lines.append(f"Источник комиссии: {commission_provenance}; на {commission_as_of or 'дата не указана'}.")
            if row.get("_display_source_age") is not None:
                lines.append(f"Возраст снимка: {int(row['_display_source_age'])} сек.")
            lines.append("Сценарий: одна успешная продажа FBO; спрос и общий итог магазина не прогнозируются.")
        lines.extend(["", f"Страница {page} из {page_count}. Сортировка применяется только к этому снимку; прибыль по SKU не суммируется."])
        text = "\n".join(lines)
        if len(text.encode("utf-16-le")) // 2 > self.TEXT_LIMIT_UTF16:
            # Rows are bounded to five and all source labels are already
            # projected to safe limits; this is a defensive fallback.
            suffix = "\nЭкран сокращён; полные строки доступны постранично."
            text = self._truncate_utf16(text, self.TEXT_LIMIT_UTF16 - len(suffix)) + suffix
        buttons = []
        for row in shown:
            buttons.append({
                "text": f"Изменить · {self._label(row)[:30]}",
                "callback": self._register_action(scope, batch, "row_edit_menu", row_id=row["row_id"]),
            })
            if row.get("status") == "READY":
                buttons.append({
                    "text": f"Открыть план · {self._label(row)[:28]}",
                    "callback": self._register_action(
                        scope, batch, "open_candidate", row_id=row["row_id"]
                    ),
                })
            if row.get("status") in {"READY", "INCOMPLETE_INPUTS"}:
                if self.advertising_cap_service is not None:
                    buttons.append({
                        "text": f"Рекламный предел · {self._label(row)[:24]}",
                        "callback": self._register_action(
                            scope, batch, "advertising_cap", row_id=row["row_id"]
                        ),
                    })
                buttons.append({
                    "text": f"Чувствительность · {self._label(row)[:24]}",
                    "callback": self._register_action(
                        scope, batch, "sensitivity", row_id=row["row_id"]
                    ),
                })
        eligible_rows = [row for row in rows if row.get("status") in {"READY", "INCOMPLETE_INPUTS"}]
        buttons.extend([
            {"text": "💾 Сохранить план", "callback": f"upp:b:{batch['batch_id']}:{batch['version']}"},
            {"text": "📚 Мои планы", "callback": "upp:m"},
            {"text": "Изменить цель", "callback": self._register_action(scope, batch, "target_edit")},
            {"text": "Обновить источники", "callback": self._register_action(scope, batch, "refresh")},
            {"text": "Сортировать по целевой цене", "callback": self._register_action(scope, batch, "sort", sort_by="target_price")},
            {"text": "Сортировать по прибыли/шт.", "callback": self._register_action(scope, batch, "sort", sort_by="profit")},
            {"text": "⬇️ CSV", "callback": self._register_action(scope, batch, "export", file_format="csv", sort_by=sort_by)},
            {"text": "⬇️ JSON", "callback": self._register_action(scope, batch, "export", file_format="json", sort_by=sort_by)},
        ])
        if eligible_rows:
            buttons.insert(1, {
                "text": "Реклама для выбранных строк",
                "callback": self._register_action(
                    scope, batch, "advertising_rate",
                    row_ids=[row["row_id"] for row in eligible_rows],
                ),
            })
        if page > 1:
            buttons.append({"text": "Предыдущая", "callback": self._register_action(scope, batch, "page", page=page - 1, sort_by=sort_by)})
        if page < page_count:
            buttons.append({"text": "Следующая", "callback": self._register_action(scope, batch, "page", page=page + 1, sort_by=sort_by)})
        buttons.extend([
            {"text": "К обзору", "callback": "product_overview"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return self._result("UNIT_PRICE_BATCH_PLAN_READY", text, self._keyboard(buttons), batch=batch)

    def _store_batch_locked(self, key, batch):
        self._refresh_tickets.pop(key, None)
        self._batches[key] = {
            "batch": deepcopy(batch),
            "stored_at": self.clock(),
        }
        self._batches.move_to_end(key)
        self._evict_locked(self._batches, self.MAX_BATCHES)

    def _valid_published_batch(self, scope, batch, batch_id, version):
        return (
            isinstance(batch, dict)
            and batch.get("kind") == "UNIT_PRICE_BATCH_PLAN"
            and isinstance(batch_id, str)
            and bool(batch_id)
            and batch.get("batch_id") == batch_id
            and type(batch.get("version")) is int
            and batch.get("version") == version
            and batch.get("owner_id") == scope["owner_id"]
            and batch.get("tenant_scope") == scope["tenant_scope"]
        )

    def _publish_initial_batch(self, scope, pending, batch):
        active_scope = self._scope(scope["owner_id"])
        if active_scope.get("error") or active_scope.get("tenant_scope") != scope["tenant_scope"]:
            return False
        key = scope["key"]
        with self._lock:
            current_pending = self._pending.get(key)
            entry = self._batches.get(key)
            current = entry.get("batch") if isinstance(entry, dict) else None
            stored_at = entry.get("stored_at", 0) if isinstance(entry, dict) else 0
            if entry is not None and self.clock() - stored_at >= self.SNAPSHOT_TTL_SECONDS:
                current = None
                self._batches.pop(key, None)
            expected_id = pending.get("base_batch_id")
            expected_version = pending.get("base_batch_version")
            current_matches = (
                current is None and expected_id is None and expected_version is None
            ) or (
                isinstance(current, dict)
                and current.get("batch_id") == expected_id
                and current.get("version") == expected_version
            )
            ticket_matches = (
                isinstance(current_pending, dict)
                and current_pending.get("ticket") == pending.get("ticket")
                and self.clock() - current_pending.get("created_at", 0)
                <= self.PENDING_TTL_SECONDS
            )
            if (
                not ticket_matches
                or not current_matches
                or (
                    expected_id is not None
                    and isinstance(batch, dict)
                    and batch.get("batch_id") == expected_id
                )
                or not self._valid_published_batch(
                    scope, batch, batch.get("batch_id") if isinstance(batch, dict) else None, 1
                )
            ):
                if ticket_matches:
                    self._pending.pop(key, None)
                return False
            self._pending.pop(key, None)
            self._store_batch_locked(key, batch)
            return True

    def _publish_batch_update(
        self,
        scope,
        batch,
        expected_batch_id,
        expected_version,
        pending_ticket=None,
    ):
        active_scope = self._scope(scope["owner_id"])
        if active_scope.get("error") or active_scope.get("tenant_scope") != scope["tenant_scope"]:
            return False
        if type(expected_version) is not int or expected_version < 1:
            return False
        key = scope["key"]
        with self._lock:
            entry = self._batches.get(key)
            current = entry.get("batch") if isinstance(entry, dict) else None
            stored_at = entry.get("stored_at", 0) if isinstance(entry, dict) else 0
            current_matches = (
                isinstance(current, dict)
                and self.clock() - stored_at < self.SNAPSHOT_TTL_SECONDS
                and current.get("batch_id") == expected_batch_id
                and current.get("version") == expected_version
            )
            pending_matches = True
            if pending_ticket is not None:
                pending = self._pending.get(key)
                pending_matches = (
                    isinstance(pending, dict)
                    and pending.get("ticket") == pending_ticket
                    and pending.get("batch_id") == expected_batch_id
                    and pending.get("batch_version") == expected_version
                    and self.clock() - pending.get("created_at", 0)
                    <= self.PENDING_TTL_SECONDS
                )
            result_matches = self._valid_published_batch(
                scope, batch, expected_batch_id, expected_version + 1
            )
            if not (current_matches and pending_matches and result_matches):
                if pending_ticket is not None:
                    pending = self._pending.get(key)
                    if isinstance(pending, dict) and pending.get("ticket") == pending_ticket:
                        self._pending.pop(key, None)
                return False
            if pending_ticket is not None:
                self._pending.pop(key, None)
            self._store_batch_locked(key, batch)
            return True

    def _begin_refresh(self, scope, batch):
        key = scope["key"]
        with self._lock:
            entry = self._batches.get(key)
            current = entry.get("batch") if isinstance(entry, dict) else None
            if (
                not isinstance(current, dict)
                or current.get("batch_id") != batch.get("batch_id")
                or current.get("version") != batch.get("version")
            ):
                return None
            ticket = token_hex(8)
            self._refresh_tickets[key] = ticket
            self._refresh_tickets.move_to_end(key)
            self._evict_locked(self._refresh_tickets, self.MAX_BATCHES)
            return ticket

    def _publish_refresh(self, scope, base_batch, ticket, refreshed_batch):
        active_scope = self._scope(scope["owner_id"])
        if (
            active_scope.get("error")
            or active_scope.get("tenant_scope") != scope["tenant_scope"]
        ):
            self._finish_refresh_error(scope, ticket)
            return False
        key = scope["key"]
        with self._lock:
            entry = self._batches.get(key)
            current = entry.get("batch") if isinstance(entry, dict) else None
            stored_at = entry.get("stored_at", 0) if isinstance(entry, dict) else 0
            if (
                self._refresh_tickets.get(key) != ticket
                or not isinstance(current, dict)
                or self.clock() - stored_at >= self.SNAPSHOT_TTL_SECONDS
                or current.get("batch_id") != base_batch.get("batch_id")
                or current.get("version") != base_batch.get("version")
                or type(base_batch.get("version")) is not int
                or not self._valid_published_batch(
                    scope,
                    refreshed_batch,
                    base_batch.get("batch_id"),
                    base_batch.get("version") + 1,
                )
            ):
                if self._refresh_tickets.get(key) == ticket:
                    self._refresh_tickets.pop(key, None)
                return False
            self._refresh_tickets.pop(key, None)
            pending = self._pending.get(key)
            if (
                isinstance(pending, dict)
                and pending.get("batch_id") == base_batch.get("batch_id")
                and pending.get("batch_version") == base_batch.get("version")
            ):
                self._pending.pop(key, None)
            self._batches[key] = {
                "batch": deepcopy(refreshed_batch),
                "stored_at": self.clock(),
            }
            self._batches.move_to_end(key)
            self._evict_locked(self._batches, self.MAX_BATCHES)
            return True

    def _finish_refresh_error(self, scope, ticket):
        with self._lock:
            if self._refresh_tickets.get(scope["key"]) == ticket:
                self._refresh_tickets.pop(scope["key"], None)

    def _project_batch_freshness(self, batch):
        projected = deepcopy(batch)
        now = self.clock()
        stale_count = 0
        for row in projected.get("rows") or []:
            original_status = row.get("status")
            age_at_load = self._seconds(row.get("source_age_seconds_at_load"), 0.0)
            loaded_at = self._seconds(row.get("source_loaded_at"), now)
            ttl = min(self._seconds(row.get("source_ttl_seconds"), 600.0), 600.0)
            age = age_at_load + max(0.0, now - loaded_at)
            is_stale = (
                age >= ttl
                and original_status not in {
                    "SOURCE_UNAVAILABLE", "UNSUPPORTED_SCHEME", "BUDGET_EXHAUSTED"
                }
            )
            row["snapshot_status"] = original_status
            row["source_age_seconds_at_evaluation"] = int(age)
            row["source_ttl_seconds"] = int(ttl)
            row["source_freshness_status"] = "STALE" if is_stale else "CURRENT"
            if is_stale:
                stale_count += 1
                row.update(status="SOURCE_STALE", reason="SOURCE_CACHE_EXPIRED")
        projected["source_freshness_status"] = (
            "STALE" if stale_count else "CURRENT"
        )
        projected["source_stale_row_count"] = stale_count
        projected["freshness_checked_at_export"] = True
        return projected

    def _get_batch(self, scope, batch_id, version):
        key = scope["key"]
        with self._lock:
            entry = self._batches.get(key)
            if not isinstance(entry, dict):
                return None
            age = max(0.0, float(self.clock()) - entry.get("stored_at", 0))
            batch = entry.get("batch")
            if age >= self.SNAPSHOT_TTL_SECONDS:
                self._batches.pop(key, None)
                return None
            if (
                not isinstance(batch, dict)
                or batch.get("batch_id") != batch_id
                or batch.get("version") != version
                or batch.get("owner_id") != scope["owner_id"]
                or batch.get("tenant_scope") != scope["tenant_scope"]
            ):
                return None
            self._batches.move_to_end(key)
            return deepcopy(batch)

    def _register_action(self, scope, batch, kind, **parameters):
        with self._lock:
            token = token_hex(4)
            while token in self._actions:
                token = token_hex(4)
            self._actions[token] = {
                "owner_id": scope["owner_id"],
                "tenant_scope": scope["tenant_scope"],
                "batch_id": batch["batch_id"],
                "batch_version": batch["version"],
                "kind": kind,
                "created_at": self.clock(),
                **deepcopy(parameters),
            }
            self._actions.move_to_end(token)
            self._evict_locked(self._actions, self.MAX_ACTIONS)
        callback = "upb:a:" + token
        return callback if len(callback.encode("utf-8")) <= 64 else "upb:c"

    def _revoke_batch_actions(self, scope, batch_id, version, kinds):
        with self._lock:
            for token, action in list(self._actions.items()):
                if (
                    action.get("owner_id") == scope["owner_id"]
                    and action.get("tenant_scope") == scope["tenant_scope"]
                    and action.get("batch_id") == batch_id
                    and action.get("batch_version") == version
                    and action.get("kind") in kinds
                ):
                    self._actions.pop(token, None)

    def _consume_action(self, token, scope):
        with self._lock:
            action = self._actions.pop(str(token or ""), None)
        if (
            not isinstance(action, dict)
            or action.get("owner_id") != scope["owner_id"]
            or action.get("tenant_scope") != scope["tenant_scope"]
            or self.clock() - action.get("created_at", 0) > self.PENDING_TTL_SECONDS
        ):
            return None
        return action

    def _claim_pending(self, key):
        now = self.clock()
        with self._lock:
            pending = self._pending.get(key)
            if pending is None:
                return None, "OTHER_SCOPE" if any(item[0] == key[0] for item in self._pending) else None
            if now - pending.get("created_at", 0) > self.PENDING_TTL_SECONDS:
                self._pending.pop(key, None)
                return None, "EXPIRED"
            if pending.get("processing"):
                return None, "BUSY"
            pending["processing"] = True
            return deepcopy(pending), None

    def _release_pending(self, key, ticket):
        with self._lock:
            pending = self._pending.get(key)
            if isinstance(pending, dict) and pending.get("ticket") == ticket:
                pending["processing"] = False

    def _complete_pending(self, key, ticket):
        with self._lock:
            pending = self._pending.get(key)
            if isinstance(pending, dict) and pending.get("ticket") == ticket:
                self._pending.pop(key, None)

    def _batch_for_pending(self, scope, pending):
        return self._get_batch(
            scope, pending.get("batch_id"), pending.get("batch_version")
        )

    def _finish_mutation(self, scope, pending, result):
        key = scope["key"]
        if result.get("error") is True:
            self._release_pending(key, pending["ticket"])
            return self._error(result.get("code"), keyboard=self._cancel_keyboard())
        if not self._publish_batch_update(
            scope,
            result,
            expected_batch_id=pending.get("batch_id"),
            expected_version=pending.get("batch_version"),
            pending_ticket=pending.get("ticket"),
        ):
            return self._stale()
        return self._render(scope, result)

    def _scope(self, user_id):
        owner = str(user_id or "").strip()
        tenant_scope = str(self.tenant_scope_provider() or "").strip()
        scoped_owner, store_id = split_store_tenant_scope(tenant_scope)
        if not owner or not tenant_scope or scoped_owner != owner:
            return {"error": True, "owner_id": owner, "tenant_scope": tenant_scope}
        return {
            "error": False,
            "owner_id": owner,
            "store_id": store_id,
            "tenant_scope": tenant_scope,
            "key": (owner, tenant_scope),
        }

    def _clear_other_scopes(self, owner, tenant_scope):
        with self._lock:
            for mapping in (self._pending, self._batches, self._refresh_tickets):
                for key in [
                    key for key in mapping
                    if key[0] == owner and key[1] != tenant_scope
                ]:
                    mapping.pop(key, None)
            for token, action in list(self._actions.items()):
                if action.get("owner_id") == owner and action.get("tenant_scope") != tenant_scope:
                    self._actions.pop(token, None)

    def _evict_locked(self, mapping, limit):
        while len(mapping) > limit:
            mapping.popitem(last=False)

    def _prompt_keyboard(self):
        return self._keyboard([
            {"text": "Отмена", "callback": "upb:c"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])

    def _cancel_keyboard(self):
        return self._prompt_keyboard()

    def _main_keyboard(self):
        return self.keyboard_service.build_main_keyboard()

    def _keyboard(self, buttons):
        builder = getattr(self.keyboard_service, "build_unit_price_batch_keyboard", None)
        if callable(builder):
            return builder(buttons)
        safe = [
            item for item in buttons
            if isinstance(item, dict)
            and isinstance(item.get("callback"), str)
            and len(item["callback"].encode("utf-8")) <= 64
        ]
        return {"error": False, "type": "inline_keyboard", "buttons": safe}

    def _result(self, status, message, keyboard, batch=None):
        result = {
            "error": False,
            "status": status,
            "message": message,
            "keyboard": keyboard,
            "read_only": True,
            "executed": False,
        }
        if batch is not None:
            result["batch_plan"] = deepcopy(batch)
        return result

    def _error(self, code, keyboard=None):
        return {
            "error": True,
            "code": str(code or "BATCH_PLAN_UNAVAILABLE"),
            "message": "Пакетный план цен сейчас недоступен. Откройте обзор товаров и повторите действие.",
            "keyboard": keyboard or self._main_keyboard(),
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _extended_scenario_kwargs(value):
        if not isinstance(value, dict):
            return {}
        extended = value.get("extended_scenario")
        strict = value.get("strict_return_evidence")
        if extended is None and strict is None:
            return {}
        return {
            "extended_scenario": deepcopy(extended),
            "strict_return_evidence": deepcopy(strict),
        }

    def _context_error(self):
        return self._result(
            "UNIT_PRICE_BATCH_CONTEXT_UNAVAILABLE",
            "Не удалось подтвердить активный магазин. Пакетный план не изменён.",
            self._main_keyboard(),
        )

    def _stale(self):
        return self._result(
            "UNIT_PRICE_BATCH_ACTION_STALE",
            "Кнопка устарела или относится к другому магазину. Откройте пакетный план заново.",
            self._main_keyboard(),
        )

    @staticmethod
    def _label(row):
        identity = row.get("identity") or {}
        label = identity.get("offer_id") or identity.get("catalog_sku") or "Товар"
        return str(label).replace("\n", " ").replace("\r", " ")[:72]

    @staticmethod
    def _number(value, suffix=""):
        if isinstance(value, bool) or value is None:
            return "нет данных"
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return "нет данных"
        if not number.is_finite():
            return "нет данных"
        return f"{number:,.2f}".replace(",", " ") + suffix

    @staticmethod
    def _sort_number(value):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("Infinity")
        return number if number.is_finite() else Decimal("Infinity")

    @staticmethod
    def _seconds(value, default):
        if isinstance(value, bool):
            return default
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not number == number or number in (float("inf"), float("-inf")):
            return default
        return max(0.0, number)

    @staticmethod
    def _truncate_utf16(value, limit):
        output = []
        used = 0
        for char in str(value or ""):
            width = 2 if ord(char) > 0xFFFF else 1
            if used + width > max(0, int(limit)):
                break
            output.append(char)
            used += width
        return "".join(output)
