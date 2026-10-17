"""Short-lived, tenant-scoped Telegram flow for batch seller-price plans."""

from collections import OrderedDict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from secrets import token_hex
from threading import RLock
from time import monotonic

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


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
    ):
        self.batch_plan_service = batch_plan_service
        self.product_overview_service = product_overview_service
        self.keyboard_service = keyboard_service
        self.single_price_runtime_service = single_price_runtime_service
        self.sensitivity_runtime_service = sensitivity_runtime_service
        self.analytics_export_service = analytics_export_service
        self.clock = clock or monotonic
        self.tenant_scope_provider = tenant_scope_provider or get_current_tenant_user_id
        self._pending = OrderedDict()
        self._batches = OrderedDict()
        self._actions = OrderedDict()
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
            self._pending[key] = {
                "ticket": ticket,
                "kind": "batch_target",
                "items": deepcopy(items),
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
            )
            if result.get("error") is True:
                self._release_pending(key, pending["ticket"])
                return self._error(result.get("code"), keyboard=self._prompt_keyboard())
            if not self._pending_is_current(key, pending["ticket"], scope):
                return self._result(
                    "UNIT_PRICE_BATCH_RESULT_STALE",
                    "Запрос устарел после смены магазина или нового действия. Откройте обзор снова.",
                    self._main_keyboard(),
                )
            self._complete_pending(key, pending["ticket"])
            self._save_batch(scope, result)
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
            return self._finish_mutation(scope, key, pending, result)
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
            return self._finish_mutation(scope, key, pending, result)
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
            return self.analytics_export_service.export_unit_price_batch(
                batch, action["file_format"], active_sort=action.get("sort_by", "selection")
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
            self._save_batch(scope, result)
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
            result = self.batch_plan_service.refresh(batch)
            if result.get("error") is True:
                return self._error(result.get("code"))
            self._save_batch(scope, result)
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
            "provenance": deepcopy(row.get("provenance") or {}),
            "sources": {
                "periods": periods,
                "as_of": periods.get("seller_price_as_of"),
                "completeness": deepcopy(snapshot.get("source_completeness") or {}),
            },
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
            for token, action in list(self._actions.items()):
                if action.get("owner_id") == owner:
                    self._actions.pop(token, None)

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
        display_batch = deepcopy(batch)
        rows = list(display_batch.get("rows") or [])
        now = self.clock()
        for row in rows:
            age_at_load = self._seconds(row.get("source_age_seconds_at_load"), 0.0)
            loaded_at = self._seconds(row.get("source_loaded_at"), now)
            ttl = min(
                self._seconds(row.get("source_ttl_seconds"), 600.0),
                600.0,
            )
            age = age_at_load + max(0.0, now - loaded_at)
            row["_display_source_age"] = age
            if (
                age >= ttl
                and row.get("status") not in {
                    "SOURCE_UNAVAILABLE", "UNSUPPORTED_SCHEME", "BUDGET_EXHAUSTED"
                }
            ):
                row.update(status="SOURCE_STALE", reason="SOURCE_CACHE_EXPIRED")
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
                buttons.append({
                    "text": f"Чувствительность · {self._label(row)[:24]}",
                    "callback": self._register_action(
                        scope, batch, "sensitivity", row_id=row["row_id"]
                    ),
                })
        eligible_rows = [row for row in rows if row.get("status") in {"READY", "INCOMPLETE_INPUTS"}]
        buttons.extend([
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

    def _save_batch(self, scope, batch):
        key = scope["key"]
        with self._lock:
            self._batches[key] = {
                "batch": deepcopy(batch),
                "stored_at": self.clock(),
            }
            self._batches.move_to_end(key)
            self._evict_locked(self._batches, self.MAX_BATCHES)

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

    def _pending_is_current(self, key, ticket, scope):
        current_scope = self._scope(scope["owner_id"])
        if current_scope.get("tenant_scope") != scope["tenant_scope"]:
            return False
        with self._lock:
            current = self._pending.get(key)
            return isinstance(current, dict) and current.get("ticket") == ticket

    def _batch_for_pending(self, scope, pending):
        return self._get_batch(
            scope, pending.get("batch_id"), pending.get("batch_version")
        )

    def _finish_mutation(self, scope, key, pending, result):
        if result.get("error") is True:
            self._release_pending(key, pending["ticket"])
            return self._error(result.get("code"), keyboard=self._cancel_keyboard())
        if not self._pending_is_current(key, pending["ticket"], scope):
            return self._stale()
        self._complete_pending(key, pending["ticket"])
        self._save_batch(scope, result)
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
            for mapping in (self._pending, self._batches):
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
