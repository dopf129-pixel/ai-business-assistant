from copy import deepcopy
from decimal import Decimal, InvalidOperation
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramUnitPriceCalculatorRuntimeService:
    """Owns short-lived Telegram planning scenarios and their text stages."""

    SESSION_TTL_SECONDS = 600
    MAX_SCENARIOS = 128
    MAX_CATALOG_SELECTIONS = 512
    MAX_SELECTIONS = 512
    EDITABLE_FIELDS = {
        "price": ("Цена продавца", "₽/шт.", True),
        "cost": ("Себестоимость", "₽/шт.", False),
        "commission_rate": ("Комиссия Ozon", "%", False),
        "advertising_rate": ("Реклама", "% от цены", False),
        "discount_points_rate": ("Баллы за скидки", "% от цены", False),
        "logistics_per_unit": ("Логистика", "₽/шт.", False),
        "last_mile_per_unit": ("Последняя миля", "₽/шт.", False),
        "acquiring_per_unit": ("Эквайринг", "₽/шт.", False),
    }

    def __init__(
        self,
        source,
        scenario_service,
        keyboard_service,
        clock=None,
        session_ttl_seconds=SESSION_TTL_SECONDS,
        max_scenarios=MAX_SCENARIOS,
        max_catalog_selections=MAX_CATALOG_SELECTIONS,
    ):
        self.source = source
        self.scenario_service = scenario_service
        self.keyboard_service = keyboard_service
        self.clock = clock or monotonic
        self.session_ttl_seconds = max(1, int(session_ttl_seconds))
        self.max_scenarios = max(1, int(max_scenarios))
        self.max_catalog_selections = max(1, int(max_catalog_selections))
        self._scenarios = {}
        self._active = {}
        self._pending = {}
        self._catalog_selection = {}
        self._selections = {}
        self._selection_order = []
        self._operation_tokens = {}
        self._lock = RLock()

    def begin_catalog_selection(self, user_id):
        user, scope, context_error = self._context(user_id)
        if context_error:
            return self._friendly_error(context_error)
        self._clear_pending_for_other_scopes(user, scope)
        self._deactivate(user, scope)
        with self._lock:
            key = (user, scope)
            self._catalog_selection[key] = {
                "selection_id": uuid4().hex[:10],
                "created_at": self.clock(),
            }
            while len(self._catalog_selection) > self.max_catalog_selections:
                self._catalog_selection.pop(next(iter(self._catalog_selection)))
        return {
            "error": False,
            "status": "UNIT_PRICE_SCENARIO_CATALOG_SELECTION_PENDING",
            "message": "Выберите товар в существующем списке юнит-экономики для планирования цены.",
            "read_only": True,
            "executed": False,
        }

    def open_menu(self, user_id):
        """Compatibility alias; the handler supplies the existing catalog picker."""
        return self.begin_catalog_selection(user_id)

    def has_catalog_selection(self, user_id):
        user, scope, context_error = self._context(user_id)
        if context_error:
            return False
        with self._lock:
            return (user, scope) in self._catalog_selection

    def build_catalog_product_callback(self, user_id, product_reference):
        user, scope, context_error = self._context(user_id)
        if context_error:
            return None
        with self._lock:
            selection = self._catalog_selection.get((user, scope))
            if not isinstance(selection, dict):
                return None
            if self.clock() - selection.get("created_at", 0) > self.session_ttl_seconds:
                self._catalog_selection.pop((user, scope), None)
                return None
            token = self._register_selection_locked(
                user,
                scope,
                product_reference,
                kind="catalog",
                catalog_selection_id=selection.get("selection_id"),
            )
        return "upc:s:" + token if token else None

    def handle_catalog_selection(self, product_reference, user_id=None):
        # Legacy factual callbacks cannot implicitly select a calculator SKU.
        return None

    def build_product_entry_button(self, user_id, product_reference):
        user, scope, context_error = self._context(user_id)
        if context_error:
            return None
        token = self._register_selection(user, scope, str(product_reference or "").strip())
        if not token:
            return None
        return {
            "text": "🧮 Подставить свою цену",
            "callback": "upc:p:" + token,
        }

    def handle_callback(self, button_id, user_id=None):
        user, scope, context_error = self._context(user_id)
        if context_error:
            return self._friendly_error(context_error)
        parts = str(button_id or "").split(":")
        if parts == ["upc", "m"]:
            return self.begin_catalog_selection(user)
        if len(parts) == 3 and parts[0:2] == ["upc", "p"]:
            return self._select_product(parts[2], user, scope)
        if len(parts) == 3 and parts[0:2] == ["upc", "s"]:
            return self._select_product(parts[2], user, scope, expected_kind="catalog")
        if len(parts) < 3 or parts[0] != "upc":
            return self._stale_result()
        action = parts[1]
        if action in {"e", "f", "z", "b", "r", "a", "v", "c"}:
            if len(parts) < 4:
                return self._stale_result()
            try:
                expected_version = int(parts[3])
            except (TypeError, ValueError):
                return self._stale_result()
            session = self._get_session(parts[2], expected_version, user, scope)
            if session is None:
                return self._stale_result()
            if action == "e" and len(parts) == 5:
                return self._begin_edit(session, parts[4], user, scope, expected_version)
            if action == "f":
                return self._show_fee_menu(session, expected_version)
            if action == "z":
                return self._set_field(session, "advertising_rate", "0", user, scope, expected_version)
            if action == "b":
                return self._restore_discount_points_average(session, user, scope, expected_version)
            if action == "r":
                return self._refresh(session, user, scope, expected_version)
            if action == "a":
                return self._show_assumptions(session)
            if action == "v":
                return self._scenario_screen(session)
            if action == "c":
                if not self._clear_pending_for_session(session, user, scope, expected_version):
                    return self._stale_result()
                updated = self._get_session(
                    session["scenario_id"], expected_version + 1, user, scope
                )
                return self._scenario_screen(updated, notice="Ввод отменён.")
        return self._stale_result()

    def handle_text(self, text, user_id=None):
        user, scope, context_error = self._context(user_id)
        if context_error:
            stale = self._clear_pending_for_user(user)
            return self._friendly_error(context_error) if stale else None
        key = (user, scope)
        with self._lock:
            pending = deepcopy(self._pending.get(key))
        if pending is None:
            stale = self._clear_pending_for_other_scopes(user, scope)
            if stale:
                return {
                    "error": False,
                    "status": "UNIT_PRICE_SCENARIO_CONTEXT_CHANGED",
                    "message": "Магазин изменился. Начните калькулятор заново для выбранного магазина.",
                    "keyboard": self.keyboard_service.build_main_keyboard(),
                    "read_only": True,
                    "executed": False,
                }
            with self._lock:
                scenario_id = self._active.get(key)
                active = self._scenarios.get(scenario_id) if scenario_id else None
                version = active.get("version") if isinstance(active, dict) else None
            if version is None:
                return None
            session = self._get_session(scenario_id, version, user, scope)
            if session is None:
                return self._stale_result()
            return self._scenario_screen(
                session,
                notice="Выберите параметр на кнопках ниже. Этот текст не изменил расчёт.",
            )
        session = self._get_session(
            pending.get("scenario_id"),
            pending.get("version"),
            user,
            scope,
        )
        if session is None or pending.get("field") not in self.EDITABLE_FIELDS:
            self._clear_pending_for_key(key)
            return self._stale_result()
        candidate_text = str(text or "").strip()
        if not candidate_text or len(candidate_text) > 80:
            return self._edit_prompt(session, pending["field"],
                                     notice="Введите число не длиннее 80 символов.")
        candidate = dict(session["inputs"])
        candidate[pending["field"]] = candidate_text
        validation = self.scenario_service.calculate(
            candidate,
            identity=self._scenario_identity(session),
            provenance=session["provenance"],
            sources=self._scenario_sources(session),
        )
        if pending["field"] in validation.get("invalid_inputs", []):
            return self._edit_prompt(
                session,
                pending["field"],
                notice="Значение некорректно. Проверьте формат и допустимый диапазон.",
            )
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                not isinstance(current, dict)
                or self._active.get(key) != session["scenario_id"]
                or current.get("version") != pending["version"]
            ):
                return self._stale_result()
            current["inputs"][pending["field"]] = candidate_text
            current["provenance"][pending["field"]] = "manual_seller_assumption"
            current["overrides"].add(pending["field"])
            current["version"] += 1
            current["updated_at"] = self.clock()
            session = deepcopy(current)
            self._pending.pop(key, None)
        return self._scenario_screen(session)

    def clear_pending(self, user_id):
        user = str(user_id or "").strip()
        if not user:
            return
        with self._lock:
            for key in [key for key in self._pending if key[0] == user]:
                self._pending.pop(key, None)
            for key in [key for key in self._active if key[0] == user]:
                self._active.pop(key, None)
            for key in [key for key in self._operation_tokens if key[0] == user]:
                self._operation_tokens.pop(key, None)
            for key in [key for key in self._catalog_selection if key[0] == user]:
                self._catalog_selection.pop(key, None)
            for scenario_id, session in list(self._scenarios.items()):
                if session.get("user_id") == user:
                    self._scenarios.pop(scenario_id, None)
            for token, selection in list(self._selections.items()):
                if selection.get("user_id") == user:
                    self._selections.pop(token, None)
            self._selection_order = [token for token in self._selection_order if token in self._selections]

    def _select_product(self, token, user, scope, expected_kind="product_entry"):
        with self._lock:
            token = str(token)
            selection = self._selections.get(token)
            if not isinstance(selection, dict):
                return self._stale_result()
            if selection.get("user_id") != user or selection.get("tenant_scope") != scope:
                return self._stale_result()
            catalog = self._catalog_selection.get((user, scope))
            catalog_valid = (
                expected_kind != "catalog"
                or (
                    isinstance(catalog, dict)
                    and catalog.get("selection_id") == selection.get("catalog_selection_id")
                )
            )
            if (
                selection.get("kind", "product_entry") != expected_kind
                or not catalog_valid
                or self.clock() - selection.get("created_at", 0) > self.session_ttl_seconds
            ):
                self._remove_selection_locked(token)
                return self._stale_result()
            self._remove_selection_locked(token)
            if expected_kind == "catalog":
                self._catalog_selection.pop((user, scope), None)
            operation_token = self._begin_source_operation_locked(user, scope)
        return self._start_product_selection(
            selection.get("product_reference"),
            user,
            scope,
            operation_token=operation_token,
        )

    def _start_product_selection(
        self, product_reference, user, scope, operation_token=None
    ):
        if operation_token is None:
            operation_token = self._begin_source_operation(user, scope)
        product = self._resolve_product(product_reference)
        if product is None:
            return self._finish_source_operation_error(
                user, scope, operation_token, "UNIT_PRICE_SCENARIO_SKU_NOT_FOUND"
            )
        if not self._source_operation_is_current(user, scope, operation_token):
            return self._stale_result()
        try:
            snapshot = self.source.load_snapshot(str(product["sku"]), user_id=user)
        except Exception:
            return self._finish_source_operation_error(
                user,
                scope,
                operation_token,
                "UNIT_PRICE_SCENARIO_SOURCE_UNAVAILABLE",
            )
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("error") is True
            or snapshot.get("identity", {}).get("tenant_scope") != scope
        ):
            code = snapshot.get("code") if isinstance(snapshot, dict) else None
            return self._finish_source_operation_error(
                user,
                scope,
                operation_token,
                code or "UNIT_PRICE_SCENARIO_SOURCE_UNAVAILABLE",
            )
        scenario_id = uuid4().hex[:10]
        session = {
            "scenario_id": scenario_id,
            "version": 1,
            "user_id": user,
            "tenant_scope": scope,
            "sku": str(product["sku"]),
            "snapshot": deepcopy(snapshot),
            "inputs": deepcopy(snapshot.get("suggested_inputs") or {}),
            "provenance": deepcopy(snapshot.get("input_provenance") or {}),
            "overrides": set(),
            "created_at": self.clock(),
            "updated_at": self.clock(),
            "source_loaded_at": self.clock(),
        }
        with self._lock:
            key = (user, scope)
            if not self._operation_is_current_locked(key, operation_token):
                return self._stale_result()
            self._scenarios[scenario_id] = session
            self._active[key] = scenario_id
            self._pending.pop(key, None)
            self._operation_tokens.pop(key, None)
            self._evict_scenarios()
        return self._scenario_screen(session)

    def _begin_source_operation(self, user, scope):
        with self._lock:
            return self._begin_source_operation_locked(user, scope)

    def _begin_source_operation_locked(self, user, scope):
        key = (user, scope)
        token = uuid4().hex
        self._active.pop(key, None)
        self._pending.pop(key, None)
        self._catalog_selection.pop(key, None)
        for selection_token, selection in list(self._selections.items()):
            if selection.get("user_id") == user and selection.get("tenant_scope") == scope:
                self._remove_selection_locked(selection_token)
        self._operation_tokens.pop(key, None)
        self._operation_tokens[key] = {"token": token, "created_at": self.clock()}
        return token

    def _source_operation_is_current(self, user, scope, token):
        with self._lock:
            return self._operation_is_current_locked((user, scope), token)

    def _operation_is_current_locked(self, key, token):
        operation = self._operation_tokens.get(key)
        return (
            isinstance(operation, dict)
            and operation.get("token") == token
            and self.clock() - operation.get("created_at", 0) <= self.session_ttl_seconds
        )

    def _finish_source_operation_error(self, user, scope, token, code):
        with self._lock:
            key = (user, scope)
            if not self._operation_is_current_locked(key, token):
                return self._stale_result()
            self._operation_tokens.pop(key, None)
        return self._friendly_error(code)

    def _resolve_product(self, reference):
        target = str(reference or "").strip()
        try:
            products = self.source.product_service.load_products()
        except Exception:
            return None
        matches = []
        for item in products or []:
            product = self._normalize_product(item)
            if product and target in {
                str(product.get("sku") or ""),
                str(product.get("offer_id") or ""),
            }:
                matches.append(product)
        return matches[0] if len(matches) == 1 else None

    def _begin_edit(self, session, field, user, scope, expected_version):
        field = str(field)
        if field not in self.EDITABLE_FIELDS:
            return self._stale_result()
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                self._active.get((user, scope)) != session["scenario_id"]
                or not isinstance(current, dict)
                or current["version"] != expected_version
            ):
                return self._stale_result()
            current["version"] += 1
            current["updated_at"] = self.clock()
            self._pending[(user, scope)] = {
                "scenario_id": current["scenario_id"],
                "version": current["version"],
                "field": field,
            }
            session = deepcopy(current)
        return self._edit_prompt(session, field)

    def _set_field(self, session, field, value, user, scope, expected_version):
        candidate = dict(session["inputs"])
        candidate[field] = value
        validation = self.scenario_service.calculate(
            candidate,
            identity=self._scenario_identity(session),
            provenance=session["provenance"],
            sources=self._scenario_sources(session),
        )
        if field in validation.get("invalid_inputs", []):
            return self._stale_result()
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                self._active.get((user, scope)) != session["scenario_id"]
                or not isinstance(current, dict)
                or current["version"] != expected_version
            ):
                return self._stale_result()
            current["inputs"][field] = value
            current["provenance"][field] = "manual_seller_assumption"
            current["overrides"].add(field)
            current["version"] += 1
            current["updated_at"] = self.clock()
            session = deepcopy(current)
            self._pending.pop((user, scope), None)
        return self._scenario_screen(session)

    def _restore_discount_points_average(self, session, user, scope, expected_version):
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                self._active.get((user, scope)) != session["scenario_id"]
                or not isinstance(current, dict)
                or current["version"] != expected_version
            ):
                return self._stale_result()
            value = current["snapshot"].get("suggested_inputs", {}).get("discount_points_rate")
            current["inputs"]["discount_points_rate"] = value
            current["provenance"]["discount_points_rate"] = (
                current["snapshot"].get("input_provenance", {}).get("discount_points_rate", "unknown")
            )
            current["overrides"].discard("discount_points_rate")
            current["version"] += 1
            current["updated_at"] = self.clock()
            session = deepcopy(current)
        return self._scenario_screen(session, notice="Средняя доля баллов восстановлена из источника, если она доступна.")

    def _refresh(self, session, user, scope, expected_version):
        key = (user, scope)
        operation_token = uuid4().hex
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                not isinstance(current, dict)
                or self._active.get(key) != session["scenario_id"]
                or current.get("version") != expected_version
            ):
                return self._stale_result()
            snapshot_session = deepcopy(current)
            self._operation_tokens[key] = {
                "token": operation_token,
                "created_at": self.clock(),
            }
        try:
            fresh = self.source.load_snapshot(
                snapshot_session["sku"], user_id=user, force_refresh=True
            )
        except Exception:
            fresh = None
        if not isinstance(fresh, dict) or fresh.get("error") is True:
            with self._lock:
                current = self._scenarios.get(snapshot_session["scenario_id"])
                if (
                    not self._operation_is_current_locked(key, operation_token)
                    or not isinstance(current, dict)
                    or self._active.get(key) != snapshot_session["scenario_id"]
                    or current.get("version") != expected_version
                ):
                    return self._stale_result()
                self._operation_tokens.pop(key, None)
                current["updated_at"] = self.clock()
                snapshot_session = deepcopy(current)
            return self._scenario_screen(
                snapshot_session,
                notice="Не удалось обновить источники. Текущие допущения сохранены.",
            )
        if fresh.get("identity", {}).get("tenant_scope") != scope:
            return self._finish_refresh_as_stale(key, operation_token)
        inputs = deepcopy(fresh.get("suggested_inputs") or {})
        provenance = deepcopy(fresh.get("input_provenance") or {})
        for field in snapshot_session["overrides"]:
            inputs[field] = snapshot_session["inputs"].get(field)
            provenance[field] = "manual_seller_assumption"
        with self._lock:
            current = self._scenarios.get(snapshot_session["scenario_id"])
            if (
                not self._operation_is_current_locked(key, operation_token)
                or not isinstance(current, dict)
                or self._active.get(key) != snapshot_session["scenario_id"]
                or current.get("version") != expected_version
            ):
                return self._stale_result()
            current["snapshot"] = deepcopy(fresh)
            current["inputs"] = inputs
            current["provenance"] = provenance
            current["version"] += 1
            current["updated_at"] = self.clock()
            current["source_loaded_at"] = self.clock()
            session = deepcopy(current)
            self._operation_tokens.pop(key, None)
        return self._scenario_screen(session, notice="Источники обновлены; ручные допущения сохранены.")

    def _finish_refresh_as_stale(self, key, operation_token):
        with self._lock:
            if self._operation_is_current_locked(key, operation_token):
                self._operation_tokens.pop(key, None)
        return self._stale_result()

    def _show_fee_menu(self, session, expected_version):
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if not isinstance(current, dict) or current["version"] != expected_version:
                return self._stale_result()
            current["version"] += 1
            current["updated_at"] = self.clock()
            version = current["version"]
        return {
            "error": False,
            "status": "UNIT_PRICE_SCENARIO_FEE_INPUT_REQUIRED",
            "message": "Введите фактические расходы на одну успешную продажу. Значение фиксируется только в этом сценарии:",
            "keyboard": self.keyboard_service.build_unit_price_fee_keyboard(
                session["scenario_id"], version
            ),
            "read_only": True,
            "executed": False,
        }

    def _show_assumptions(self, session):
        snapshot = session["snapshot"]
        period = snapshot.get("source_periods", {}).get("discount_points", {})
        completeness = snapshot.get("source_completeness", {}).get("discount_points", {})
        points = session["inputs"].get("discount_points_rate")
        source_loaded_at = session.get("source_loaded_at", session.get("created_at", 0))
        source_age = max(0, self.clock() - source_loaded_at)
        source_fresh = source_age <= self.session_ttl_seconds
        seller_price_as_of = (
            snapshot.get("source_periods", {}).get("seller_price_as_of")
            or "дата в источнике не указана"
        )
        source_line = (
            "Снимок цены/FBO-тарифа из карточки Ozon на "
            + str(seller_price_as_of)[:40]
            + "; источники актуальны."
            if source_fresh
            else "Снимок цены/FBO-тарифа из карточки Ozon на "
            + str(seller_price_as_of)[:40]
            + "; источники устарели, сравнение скрыто. Обновите источники."
        )
        if completeness.get("complete") is True:
            point_line = (
                "Баллы: взвешенная доля по точному SKU за "
                + str(period.get("from") or "?") + " — " + str(period.get("to") or "?")
                + "; наблюдений продаж: "
                + str(completeness.get("positive_sale_observations") or 0)
                + ". Изменяемое допущение: " + self._percent(points) + "."
            )
        else:
            point_line = "Баллы: автоматическая выборка неполная; используйте ручное значение."
        provenance = session.get("provenance") or {}
        lines = [
            "Допущения планового сценария",
            source_line,
            "Новый тариф не запрашивается при изменении цены сценария.",
            "Калькулятор считает только FBO. Ставка — оценка: Ozon может изменить её при новой цене; FBS не поддержан.",
            point_line,
            "Себестоимость: " + self._source_label(provenance.get("cost")) + ".",
            "Логистика, последняя миля, эквайринг и реклама: ручные значения сценария.",
            "Налоговый режим и ставки: политика активного магазина.",
            "Не включены постоянные расходы, хранение, кросс-докинг, возвраты и отмены.",
        ]
        return {
            "error": False,
            "status": "UNIT_PRICE_SCENARIO_ASSUMPTIONS_READY",
            "message": "\n".join(lines),
            "keyboard": self.keyboard_service.build_unit_price_scenario_keyboard(
                session["scenario_id"], session["version"],
                include_return_mean=completeness.get("complete") is True,
            ),
            "read_only": True,
            "executed": False,
        }

    def _scenario_screen(self, session, notice=None):
        session = deepcopy(session)
        snapshot = session["snapshot"]
        identity = self._scenario_identity(session)
        sources = self._scenario_sources(session)
        source_loaded_at = session.get("source_loaded_at", session.get("created_at", 0))
        source_fresh = self.clock() - source_loaded_at <= self.session_ttl_seconds
        result = self.scenario_service.calculate(
            session["inputs"],
            identity=identity,
            provenance=session["provenance"],
            sources=sources,
        )
        current_price = snapshot.get("suggested_inputs", {}).get("price")
        if current_price is not None and source_fresh:
            result = self.scenario_service.compare(
                session["inputs"],
                current_price=current_price,
                identity=identity,
                provenance=session["provenance"],
                sources=sources,
            )
        elif current_price is not None:
            result["comparison"] = {
                "kind": "same_assumptions_at_expired_source_price",
                "available": False,
                "reason": "SOURCE_SNAPSHOT_EXPIRED",
            }
        result["source_freshness"] = {
            "status": "FRESH" if source_fresh else "STALE",
            "age_seconds": max(0, self.clock() - source_loaded_at),
            "ttl_seconds": self.session_ttl_seconds,
        }
        text = self._format_result(session, result, notice)
        include_return_mean = (
            snapshot.get("source_completeness", {})
            .get("discount_points", {})
            .get("complete") is True
        )
        return {
            "error": False,
            "status": (
                "UNIT_PRICE_SCENARIO_READY"
                if result.get("available") is True
                else "UNIT_PRICE_SCENARIO_INPUT_REQUIRED"
            ),
            "message": text[:3500],
            "keyboard": self.keyboard_service.build_unit_price_scenario_keyboard(
                session["scenario_id"], session["version"],
                include_return_mean=include_return_mean,
            ),
            "price_scenario": result,
            "read_only": True,
            "executed": False,
        }

    def _format_result(self, session, result, notice=None):
        snapshot = session["snapshot"]
        product = snapshot.get("product") or {}
        identity = snapshot.get("identity") or {}
        store_label = str(
            identity.get("store_name")
            or identity.get("store_label")
            or identity.get("store_id")
            or "активный"
        )[:60]
        points_period = snapshot.get("source_periods", {}).get("discount_points") or {}
        points_period_label = (
            str(points_period.get("from") or "?")
            + " — "
            + str(points_period.get("to") or "?")
        )
        inputs = session["inputs"]
        values = result.get("calculated") or {}
        sku = session["sku"]
        lines = [
            "🧮 Плановая юнит-экономика",
            str(product.get("name") or "Товар")[:90] + " · SKU " + str(sku),
            "Магазин: " + store_label + " · схема FBO",
            "Источник цены/тарифа на: " + str(snapshot.get("source_periods", {}).get("seller_price_as_of") or "дата не указана")[:40],
            "Период среднего баллов: " + points_period_label,
            "",
            "Цена продавца: " + self._money(inputs.get("price")),
            "Себестоимость: " + self._money(inputs.get("cost")),
            "Комиссия " + self._percent(inputs.get("commission_rate")) + ": " + self._money(values.get("commission")),
            "Логистика / последняя миля / эквайринг: " + "/".join(
                self._money(inputs.get(field))
                for field in ("logistics_per_unit", "last_mile_per_unit", "acquiring_per_unit")
            ),
            "Реклама " + self._percent(inputs.get("advertising_rate")) + ": " + self._money(values.get("advertising")),
            "Баллы, оценка " + self._percent(inputs.get("discount_points_rate")) + ": " + self._money(values.get("discount_points")),
            "Выручка для налога: " + self._money(values.get("taxable_revenue")),
            "Налог: " + self._money(values.get("tax")) + " (" + self._percent(values.get("effective_tax_rate")) + " цены)",
            "",
        ]
        if result.get("available") is True:
            lines.extend([
                "Плановая прибыль: " + self._money(values.get("profit")) + "/шт.",
                "Плановая маржа: " + self._percent(values.get("margin_percent")),
            ])
            comparison = result.get("comparison") or {}
            if comparison.get("available") is True:
                lines.append(
                    "При текущей цене " + self._money(comparison.get("price"))
                    + " с теми же допущениями: " + self._money(comparison.get("profit"))
                    + "/шт., " + self._percent(comparison.get("margin_percent")) + "."
                )
        else:
            missing = result.get("missing_inputs") or []
            labels = [self.EDITABLE_FIELDS[item][0] for item in missing if item in self.EDITABLE_FIELDS]
            if "tax_mode" in missing or "tax_rate" in missing:
                labels.append("налоговая политика магазина")
            if "minimum_tax_rate" in missing:
                labels.append("минимальная ставка налога")
            invalid = result.get("invalid_inputs") or []
            if invalid:
                labels.extend(self.EDITABLE_FIELDS[item][0] for item in invalid if item in self.EDITABLE_FIELDS)
            if "calculation" in invalid:
                labels.append("числовое значение вне технического диапазона расчёта")
            if "tax_calculation" in invalid:
                labels.append("налоговый расчёт")
            lines.append("Чтобы получить прибыль и маржу, заполните: " + (", ".join(dict.fromkeys(labels)) or "проверьте налоговые настройки") + ".")
        if (result.get("source_freshness") or {}).get("status") == "STALE":
            lines.append(
                "Снимок цены и тарифов устарел; сравнение с текущей ценой скрыто. Обновите источники."
            )
        if notice:
            lines.insert(0, notice)
        lines.extend([
            "",
            "Оценка одной успешной продажи FBO. Ставка комиссии взята из текущей карточки и может измениться при новой цене; FBS не поддержан.",
            "Хранение, общие расходы магазина и возвраты не включены.",
        ])
        return "\n".join(lines)

    def _edit_prompt(self, session, field, notice=None):
        label, unit, positive = self.EDITABLE_FIELDS[field]
        prompt = f"Введите {label.lower()} ({unit})."
        if field in {"advertising_rate", "discount_points_rate", "commission_rate"}:
            prompt += " Допустимо от 0 до 100."
        elif positive:
            prompt += " Значение должно быть больше нуля."
        else:
            prompt += " Значение не может быть отрицательным."
        current = session["inputs"].get(field)
        if current is not None:
            prompt += " Сейчас: " + self._display_value(current, unit) + "."
        if notice:
            prompt = notice + "\n" + prompt
        return {
            "error": False,
            "status": "UNIT_PRICE_SCENARIO_INPUT_PENDING",
            "message": prompt,
            "keyboard": self.keyboard_service.build_unit_price_cancel_keyboard(
                session["scenario_id"], session["version"]
            ),
            "read_only": True,
            "executed": False,
        }

    def _scenario_identity(self, session):
        identity = dict(session["snapshot"].get("identity") or {})
        identity.update({
            "user_id": session["user_id"],
            "store_id": identity.get("store_id"),
            "sku": session["sku"],
            "scenario_id": session["scenario_id"],
            "scenario_version": session["version"],
        })
        return identity

    def _scenario_sources(self, session):
        snapshot = session["snapshot"]
        return {
            "periods": snapshot.get("source_periods") or {},
            "as_of": snapshot.get("source_periods", {}).get("seller_price_as_of"),
            "completeness": snapshot.get("source_completeness") or {},
        }

    def _register_selection(self, user, scope, product_reference):
        if not product_reference:
            return None
        with self._lock:
            return self._register_selection_locked(user, scope, product_reference)

    def _register_selection_locked(
        self, user, scope, product_reference, kind="product_entry",
        catalog_selection_id=None,
    ):
        if not str(product_reference or "").strip():
            return None
        token = uuid4().hex[:10]
        self._selections[token] = {
            "user_id": user,
            "tenant_scope": scope,
            "product_reference": str(product_reference).strip(),
            "created_at": self.clock(),
            "kind": kind,
            "catalog_selection_id": catalog_selection_id,
        }
        self._selection_order.append(token)
        while len(self._selection_order) > self.MAX_SELECTIONS:
            expired = self._selection_order.pop(0)
            self._selections.pop(expired, None)
        return token

    def _remove_selection_locked(self, token):
        self._selections.pop(str(token), None)
        try:
            self._selection_order.remove(str(token))
        except ValueError:
            pass

    def _context(self, user_id):
        user = str(user_id or "").strip()
        scope = str(get_current_tenant_user_id() or "").strip()
        scoped_user, _ = split_store_tenant_scope(scope)
        if not user or not scope or scoped_user != user:
            return user, scope, "UNIT_PRICE_SCENARIO_TENANT_MISMATCH"
        return user, scope, None

    def _get_session(self, scenario_id, version, user, scope):
        with self._lock:
            session = self._scenarios.get(str(scenario_id or ""))
            if not isinstance(session, dict):
                return None
            try:
                requested_version = int(version)
            except (TypeError, ValueError):
                return None
            if (
                session.get("user_id") != user
                or session.get("tenant_scope") != scope
                or self._active.get((user, scope)) != session.get("scenario_id")
                or session.get("version") != requested_version
                or self.clock() - session.get("updated_at", 0) > self.session_ttl_seconds
            ):
                return None
            session["updated_at"] = self.clock()
            return deepcopy(session)

    def _deactivate(self, user, scope):
        with self._lock:
            key = (user, scope)
            self._active.pop(key, None)
            self._pending.pop(key, None)
            self._catalog_selection.pop(key, None)
            self._operation_tokens.pop(key, None)
            for token, selection in list(self._selections.items()):
                if (
                    selection.get("user_id") == user
                    and selection.get("tenant_scope") == scope
                ):
                    self._selections.pop(token, None)
            self._selection_order = [
                token for token in self._selection_order
                if token in self._selections
            ]

    def _clear_pending_for_session(self, session, user, scope, expected_version):
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                self._active.get((user, scope)) != session["scenario_id"]
                or not isinstance(current, dict)
                or current["version"] != expected_version
            ):
                return False
            self._pending.pop((user, scope), None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            return True

    def _clear_pending_for_key(self, key):
        with self._lock:
            self._pending.pop(key, None)

    def _clear_pending_for_user(self, user):
        with self._lock:
            keys = [key for key in self._pending if key[0] == user]
            for key in keys:
                self._pending.pop(key, None)
            return bool(keys)

    def _clear_pending_for_other_scopes(self, user, scope):
        with self._lock:
            keys = [key for key in self._pending if key[0] == user and key[1] != scope]
            changed = bool(keys)
            for key in keys:
                self._pending.pop(key, None)
            keys = [key for key in self._catalog_selection if key[0] == user and key[1] != scope]
            changed = changed or bool(keys)
            for key in keys:
                self._catalog_selection.pop(key, None)
            keys = [key for key in self._operation_tokens if key[0] == user and key[1] != scope]
            changed = changed or bool(keys)
            for key in keys:
                self._operation_tokens.pop(key, None)
            keys = [key for key in self._active if key[0] == user and key[1] != scope]
            changed = changed or bool(keys)
            for key in keys:
                self._active.pop(key, None)
            return changed

    def _evict_scenarios(self):
        while len(self._scenarios) > self.max_scenarios:
            scenario_id = next(iter(self._scenarios))
            session = self._scenarios.pop(scenario_id)
            key = (session.get("user_id"), session.get("tenant_scope"))
            if self._active.get(key) == scenario_id:
                self._active.pop(key, None)
            pending = self._pending.get(key)
            if isinstance(pending, dict) and pending.get("scenario_id") == scenario_id:
                self._pending.pop(key, None)

    def _normalize_product(self, item):
        if isinstance(item, dict):
            return dict(item)
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            return {"product_id": item[0], "offer_id": item[1], "sku": item[2]}
        return None

    def _format_result_error(self, code):
        labels = {
            "UNIT_PRICE_SCENARIO_TENANT_MISMATCH": "Сначала выберите активный магазин и откройте калькулятор заново.",
            "UNIT_PRICE_SCENARIO_SKU_NOT_FOUND": "Товар больше не найден в активном каталоге. Выберите его заново.",
            "UNIT_PRICE_SCENARIO_SKU_AMBIGUOUS": "Не удалось однозначно определить товар. Проверьте каталог SKU.",
            "UNIT_PRICE_SCENARIO_CATALOG_UNAVAILABLE": "Не удалось загрузить каталог товаров. Попробуйте позже.",
            "UNIT_PRICE_SCENARIO_PRODUCT_IDENTITY_INCOMPLETE": "Для товара не хватает данных карточки. Выберите другой товар или обновите каталог.",
        }
        return labels.get(code, "Не удалось загрузить исходные данные. Заполните расчёт заново позже.")

    def _friendly_error(self, code):
        return {
            "error": True,
            "status": "UNIT_PRICE_SCENARIO_UNAVAILABLE",
            "code": str(code or "UNIT_PRICE_SCENARIO_SOURCE_UNAVAILABLE"),
            "message": self._format_result_error(code),
            "read_only": True,
            "executed": False,
        }

    def _stale_result(self):
        return {
            "error": False,
            "status": "UNIT_PRICE_SCENARIO_STALE",
            "message": "Этот экран устарел или относится к другому магазину. Откройте калькулятор заново.",
            "keyboard": self.keyboard_service.build_main_keyboard(),
            "read_only": True,
            "executed": False,
        }

    def _money(self, value):
        number = self._decimal(value)
        if number is None:
            return "не задано"
        if number == 0:
            number = Decimal("0")
        return format(number.quantize(Decimal("0.01")), ",.2f").replace(",", " ").replace(".", ",") + " ₽"

    def _percent(self, value):
        number = self._decimal(value)
        if number is None:
            return "не задано"
        if number == 0:
            number = Decimal("0")
        return format(number.quantize(Decimal("0.01")), ",.2f").replace(",", " ").replace(".", ",") + "%"

    def _display_value(self, value, unit):
        return self._money(value) if "₽" in unit else self._percent(value)

    def _decimal(self, value):
        if isinstance(value, bool) or value in (None, ""):
            return None
        text = str(value).strip().replace("\u00a0", "").replace(" ", "")
        if "," in text and "." in text:
            return None
        try:
            number = Decimal(text.replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return number if number.is_finite() else None

    def _source_label(self, source):
        labels = {
            "confirmed_store_cost": "подтверждённая себестоимость магазина",
            "manual_seller_assumption": "ручное допущение",
            "unknown": "не задана",
        }
        return labels.get(str(source or "unknown"), "данные источника")
