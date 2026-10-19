from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import isfinite
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
        target_planning_service=None,
        advertising_cap_service=None,
    ):
        self.source = source
        self.scenario_service = scenario_service
        self.target_planning_service = target_planning_service
        self.advertising_cap_service = advertising_cap_service
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

    def active_scenario_identity(self, user_id):
        """Return the exact active scenario identity for guarded transitions."""
        user, scope, context_error = self._context(user_id)
        if context_error:
            return None
        with self._lock:
            scenario_id = self._active.get((user, scope))
            session = self._scenarios.get(scenario_id) if scenario_id else None
            if (
                not isinstance(session, dict)
                or session.get("user_id") != user
                or session.get("tenant_scope") != scope
                or self.clock() - session.get("updated_at", 0)
                > self.session_ttl_seconds
            ):
                return None
            return {
                "scenario_id": session.get("scenario_id"),
                "version": session.get("version"),
                "tenant_scope": scope,
            }

    def get_sensitivity_context(self, scenario_id, version, user_id=None):
        """Return a defensive source snapshot for a local sensitivity sweep."""
        user, scope, context_error = self._context(user_id)
        if context_error:
            return {"error": True, "code": context_error}
        session = self._get_session(scenario_id, version, user, scope)
        if session is None:
            return self._stale_result()
        snapshot = session.get("snapshot") or {}
        identity = deepcopy(snapshot.get("identity") or {})
        if identity.get("tenant_scope") != scope:
            return self._stale_result()
        freshness = self._source_freshness(session)
        return {
            "error": False,
            "snapshot": deepcopy(snapshot),
            "identity": identity,
            "inputs": deepcopy(session.get("inputs") or {}),
            "provenance": deepcopy(session.get("provenance") or {}),
            "sources": self._scenario_sources(session),
            "source_age_seconds": freshness["age_seconds"],
            "source_ttl_seconds": freshness["ttl_seconds"],
            "source_version": f"{session['scenario_id']}:{session['version']}",
            "source_as_of": deepcopy(snapshot.get("source_periods") or {}),
            "target_margin_percent": self._target_margin_assumption(session),
            "origin": {
                "kind": "single",
                "scenario_id": session["scenario_id"],
                "scenario_version": session["version"],
                "owner_id": user,
                "tenant_scope": scope,
            },
            "read_only": True,
            "executed": False,
        }

    def get_saved_plan_capture(self, scenario_id, version, user_id=None):
        """Return an allowlisted, version-bound planning recipe for explicit save."""
        user, scope, context_error = self._context(user_id)
        if context_error:
            return {"error": True, "code": context_error}
        session = self._get_session(scenario_id, version, user, scope)
        if session is None:
            return self._stale_result()
        snapshot = session.get("snapshot")
        if not isinstance(snapshot, dict):
            return self._stale_result()
        identity = snapshot.get("identity") or {}
        product = snapshot.get("product") or {}
        if (
            identity.get("tenant_scope") != scope
            or str(identity.get("store_id") or "") != str(split_store_tenant_scope(scope)[1] or "")
            or str(identity.get("sku") or "") != str(session.get("sku") or "")
            or not str(identity.get("product_id") or "").strip()
            or not str(identity.get("offer_id") or "").strip()
        ):
            return self._stale_result()
        sources = self._scenario_sources(session)
        calculated = self.scenario_service.calculate(
            session.get("inputs") or {},
            identity=self._scenario_identity(session),
            provenance=session.get("provenance") or {},
            sources=sources,
        )
        values = calculated.get("calculated") or {}
        allowed_projection = (
            "revenue", "discount_points", "taxable_revenue", "commission",
            "advertising", "fees", "profit_before_tax", "tax",
            "effective_tax_rate", "profit", "margin_percent",
        )
        projection = {
            "available": calculated.get("available") is True,
            "status": "READY" if calculated.get("available") is True else "INCOMPLETE_INPUTS",
            "missing_inputs": list(calculated.get("missing_inputs") or [])[:20],
            "invalid_inputs": list(calculated.get("invalid_inputs") or [])[:20],
        }
        projection.update({key: values.get(key) for key in allowed_projection})
        captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = {
            "plan_kind": "single",
            "schema_version": 1,
            "calculation_version": self.scenario_service.VERSION,
            "target_margin_percent": self._target_margin_assumption(session),
            "items": [{
                "identity": {
                    "product_id": str(identity.get("product_id") or ""),
                    "offer_id": str(identity.get("offer_id") or ""),
                    "sku": str(identity.get("sku") or ""),
                    "product_name": str(product.get("name") or "")[:160] or None,
                    "store_id": str(identity.get("store_id") or ""),
                    "scheme": str(product.get("scheme") or "FBO")[:24],
                },
                "inputs": deepcopy(session.get("inputs") or {}),
                "provenance": deepcopy(session.get("provenance") or {}),
                "sources": {
                    "periods": deepcopy(snapshot.get("source_periods") or {}),
                    "as_of": (snapshot.get("source_periods") or {}).get("seller_price_as_of"),
                    "loaded_at": captured_at,
                    "completeness": deepcopy(snapshot.get("source_completeness") or {}),
                },
                "projection": projection,
            }],
        }
        return {
            "error": False,
            "scenario_id": session["scenario_id"],
            "version": session["version"],
            "tenant_scope": scope,
            "payload": payload,
            "read_only": True,
            "executed": False,
        }

    def restore_saved_plan(self, payload, user_id=None):
        """Open stored assumptions as a new transient, explicitly stale scenario."""
        user, scope, context_error = self._context(user_id)
        if context_error:
            return self._friendly_error(context_error)
        if (
            not isinstance(payload, dict)
            or payload.get("plan_kind") != "single"
            or not isinstance(payload.get("items"), list)
            or len(payload["items"]) != 1
        ):
            return self._stale_result()
        item = payload["items"][0]
        identity = item.get("identity") if isinstance(item, dict) else None
        inputs = item.get("inputs") if isinstance(item, dict) else None
        provenance = item.get("provenance") if isinstance(item, dict) else None
        sources = item.get("sources") if isinstance(item, dict) else None
        target_margin = payload.get("target_margin_percent")
        if target_margin is not None:
            try:
                parsed_target = Decimal(str(target_margin))
            except (InvalidOperation, TypeError, ValueError):
                return self._stale_result()
            if not parsed_target.is_finite() or not Decimal("0") <= parsed_target <= Decimal("100"):
                return self._stale_result()
        if (
            not isinstance(identity, dict)
            or not isinstance(inputs, dict)
            or not isinstance(provenance, dict)
            or not isinstance(sources, dict)
            or not str(identity.get("sku") or "").strip()
            or not str(identity.get("product_id") or "").strip()
            or not str(identity.get("offer_id") or "").strip()
            or str(identity.get("store_id") or "") != str(split_store_tenant_scope(scope)[1] or "")
        ):
            return self._stale_result()
        periods = deepcopy(sources.get("periods") or {})
        snapshot = {
            "error": False,
            "identity": {
                "user_id": user,
                "store_id": identity.get("store_id"),
                "tenant_scope": scope,
                "product_id": str(identity["product_id"]),
                "offer_id": str(identity["offer_id"]),
                "sku": str(identity["sku"]),
            },
            "product": {
                "name": str(identity.get("product_name") or identity.get("offer_id"))[:160],
                "scheme": str(identity.get("scheme") or "FBO")[:24],
            },
            "suggested_inputs": deepcopy(inputs),
            "input_provenance": deepcopy(provenance),
            "source_periods": periods,
            "source_completeness": deepcopy(sources.get("completeness") or {}),
        }
        scenario_id = uuid4().hex[:10]
        now = self.clock()
        manual_fields = {
            field for field, value in provenance.items()
            if value in {"manual", "manual_seller_assumption", "manual_unit_economics_input"}
        }
        session = {
            "scenario_id": scenario_id, "version": 1, "user_id": user,
            "tenant_scope": scope, "sku": str(identity["sku"]),
            "snapshot": snapshot, "inputs": deepcopy(inputs),
            "provenance": deepcopy(provenance), "overrides": manual_fields,
            "created_at": now, "updated_at": now, "source_loaded_at": now,
            "source_age_seconds_at_load": 0, "source_ttl_seconds": 0,
            "restored_from_saved_plan": True,
            "price_planning_target_margin": (
                str(target_margin) if target_margin is not None else None
            ),
        }
        operation_token = self._begin_source_operation(user, scope)
        with self._lock:
            key = (user, scope)
            if not self._operation_is_current_locked(key, operation_token):
                return self._stale_result()
            self._scenarios[scenario_id] = session
            self._active[key] = scenario_id
            self._pending.pop(key, None)
            self._operation_tokens.pop(key, None)
            self._evict_scenarios()
        result = self._scenario_screen(
            session,
            notice="Открыты сохранённые допущения. Это исторический сценарий; для текущих данных обновите источники.",
        )
        result["scenario_id"] = scenario_id
        result["scenario_version"] = 1
        return result

    def edit_saved_plan_field(self, payload, field, user_id=None):
        """Restore a historical single plan and open one allowed input editor."""
        if field not in self.EDITABLE_FIELDS:
            return self._stale_result()
        opened = self.restore_saved_plan(payload, user_id=user_id)
        scenario_id = opened.get("scenario_id") if isinstance(opened, dict) else None
        version = opened.get("scenario_version") if isinstance(opened, dict) else None
        if not scenario_id or not version:
            return opened
        if field in {"logistics_per_unit", "last_mile_per_unit", "acquiring_per_unit"}:
            fee_screen = self.handle_callback(
                f"upc:f:{scenario_id}:{version}", user_id=user_id,
            )
            callback = next((
                button.get("callback") for button in (fee_screen.get("keyboard") or {}).get("buttons", [])
                if str(button.get("callback") or "").endswith(":" + field)
            ), None)
            if callback:
                result = self.handle_callback(callback, user_id=user_id)
                return {**result, "plan_editor": {"kind": "single", "id": scenario_id, "version": version}}
            return self._stale_result()
        result = self.handle_callback(
            f"upc:e:{scenario_id}:{version}:{field}", user_id=user_id,
        )
        return {**result, "plan_editor": {"kind": "single", "id": scenario_id, "version": version}}

    def apply_sensitivity_candidate(self, source_context, cell, user_id=None):
        """Apply one explicitly chosen fresh sweep cell to the active plan."""
        user, scope, context_error = self._context(user_id)
        if context_error:
            return self._friendly_error(context_error)
        origin = source_context.get("origin") if isinstance(source_context, dict) else None
        if not isinstance(origin, dict) or origin.get("kind") != "single":
            return self._stale_result()
        session = self._get_session(
            origin.get("scenario_id"), origin.get("scenario_version"), user, scope
        )
        if session is None or origin.get("tenant_scope") != scope:
            return self._stale_result()
        current = self.get_sensitivity_context(
            session["scenario_id"], session["version"], user_id=user
        )
        if not isinstance(cell, dict) or not isinstance(source_context, dict):
            return self._stale_result()
        if (
            current.get("error") is True
            or source_context.get("base_input_signature")
            != cell.get("base_input_signature")
            or current.get("source_version") != source_context.get("source_version")
            or current.get("identity") != source_context.get("identity")
            or current.get("inputs") != source_context.get("inputs")
            or current.get("provenance") != source_context.get("provenance")
            or current.get("sources") != source_context.get("sources")
            or current.get("source_age_seconds", float("inf"))
            >= current.get("source_ttl_seconds", 0)
            or current.get("source_ttl_seconds", 0) > self.session_ttl_seconds
            or cell.get("status") != "AVAILABLE"
        ):
            return self._stale_result()
        candidate = deepcopy(cell.get("inputs") or {})
        provenance = deepcopy(cell.get("provenance") or {})
        calculated = self.scenario_service.calculate(
            candidate,
            identity=self._scenario_identity(session),
            provenance=provenance,
            sources=self._scenario_sources(session),
        )
        if calculated.get("available") is not True:
            return self._stale_result()
        with self._lock:
            active = self._scenarios.get(session["scenario_id"])
            key = (user, scope)
            if (
                not isinstance(active, dict)
                or self._active.get(key) != session["scenario_id"]
                or active.get("version") != session["version"]
            ):
                return self._stale_result()
            active["inputs"] = candidate
            active["provenance"] = provenance
            active["overrides"].update(cell.get("coordinates", {}).keys())
            active.pop("price_planning_result", None)
            active["version"] += 1
            active["updated_at"] = self.clock()
            updated = deepcopy(active)
            self._pending.pop(key, None)
        return self._scenario_screen(
            updated,
            notice="Выбранная ячейка чувствительности перенесена в сценарий и проверена повторным расчётом. Цена в Ozon не менялась.",
        )

    def open_sensitivity_candidate(self, source_context, cell, user_id=None):
        """Open a verified cell from a batch without fetching or writing sources."""
        user, scope, context_error = self._context(user_id)
        if context_error:
            return self._friendly_error(context_error)
        if not isinstance(source_context, dict) or not isinstance(cell, dict):
            return self._stale_result()
        identity = source_context.get("identity")
        snapshot = source_context.get("snapshot")
        origin = source_context.get("origin")
        if (
            not isinstance(identity, dict)
            or not isinstance(snapshot, dict)
            or not isinstance(origin, dict)
            or origin.get("kind") != "batch"
            or origin.get("owner_id") != user
            or origin.get("tenant_scope") != scope
            or identity.get("tenant_scope") != scope
            or cell.get("status") != "AVAILABLE"
            or cell.get("base_input_signature") != source_context.get("base_input_signature")
            or source_context.get("source_age_seconds", float("inf"))
            >= source_context.get("source_ttl_seconds", 0)
            or source_context.get("source_ttl_seconds", 0) > self.session_ttl_seconds
        ):
            return self._stale_result()
        inputs = deepcopy(cell.get("inputs") or {})
        provenance = deepcopy(cell.get("provenance") or {})
        scenario_identity = {
            "user_id": user,
            "store_id": identity.get("store_id"),
            "tenant_scope": scope,
            "product_id": str(identity.get("product_id")),
            "offer_id": str(identity.get("offer_id") or ""),
            "sku": str(identity.get("sku") or ""),
            "sensitivity_origin": "batch",
            "batch_id": origin.get("batch_id"),
            "batch_version": origin.get("batch_version"),
            "row_id": origin.get("row_id"),
        }
        sources = deepcopy(source_context.get("sources") or {})
        result = self.scenario_service.calculate(
            inputs,
            identity=scenario_identity,
            provenance=provenance,
            sources=sources,
        )
        if result.get("available") is not True:
            return self._stale_result()
        now = self.clock()
        scenario_id = uuid4().hex[:10]
        age = self._nonnegative_seconds(source_context.get("source_age_seconds"), 0.0)
        ttl = self._nonnegative_seconds(source_context.get("source_ttl_seconds"), 0.0)
        session = {
            "scenario_id": scenario_id,
            "version": 1,
            "user_id": user,
            "tenant_scope": scope,
            "sku": str(identity.get("sku") or ""),
            "snapshot": deepcopy(snapshot),
            "inputs": inputs,
            "provenance": provenance,
            "overrides": set(cell.get("coordinates", {}).keys()),
            "created_at": now,
            "updated_at": now,
            "source_loaded_at": now,
            "source_age_seconds_at_load": age,
            "source_ttl_seconds": ttl,
        }
        operation_token = self._begin_source_operation(user, scope)
        with self._lock:
            key = (user, scope)
            if not self._operation_is_current_locked(key, operation_token):
                return self._stale_result()
            self._scenarios[scenario_id] = session
            self._active[key] = scenario_id
            self._pending.pop(key, None)
            self._operation_tokens.pop(key, None)
            self._evict_scenarios()
        return self._scenario_screen(
            session,
            notice="Открыт выбранный сценарий чувствительности из пакетного плана. Цена в Ozon не менялась.",
        )

    def open_batch_candidate(
        self,
        batch,
        row_id,
        user_id=None,
        expected_batch_version=None,
    ):
        """Open a fresh, validated batch candidate locally without source I/O."""
        user, scope, context_error = self._context(user_id)
        if context_error:
            return self._friendly_error(context_error)
        if not isinstance(batch, dict):
            return self._stale_result()
        if isinstance(expected_batch_version, bool) or not isinstance(
            expected_batch_version, int
        ):
            return self._stale_result()
        version = expected_batch_version
        if (
            batch.get("kind") != "UNIT_PRICE_BATCH_PLAN"
            or batch.get("version") != version
            or batch.get("owner_id") != user
            or batch.get("tenant_scope") != scope
            or batch.get("read_only") is not True
            or batch.get("executed") is not False
        ):
            return self._stale_result()
        rows = [
            item for item in batch.get("rows", [])
            if isinstance(item, dict) and item.get("row_id") == row_id
        ]
        if len(rows) != 1:
            return self._stale_result()
        row = rows[0]
        snapshot = row.get("snapshot")
        identity = row.get("identity")
        if not isinstance(snapshot, dict) or not isinstance(identity, dict):
            return self._stale_result()
        snapshot_product = snapshot.get("product") or {}
        declared_scheme = (
            snapshot_product.get("scheme")
            or snapshot_product.get("fulfillment_scheme")
            or row.get("scheme")
        )
        completeness = snapshot.get("source_completeness") or {}
        confirmed_scheme = str(completeness.get("scheme") or "").strip().upper()
        if (
            row.get("status") != "READY"
            or row.get("scheme") != "FBO"
            or str(declared_scheme or "").strip().upper() != "FBO"
            or confirmed_scheme in {"FBS", "UNKNOWN"}
        ):
            return self._stale_result()
        source_identity = snapshot.get("identity") or {}
        _scope_owner, scoped_store_id = split_store_tenant_scope(scope)
        if (
            source_identity.get("product_id") is None
            or str(source_identity.get("product_id")) != str(identity.get("product_id"))
            or str(source_identity.get("offer_id") or "") != str(identity.get("offer_id") or "")
            or str(source_identity.get("sku") or "") != str(identity.get("catalog_sku") or "")
            or source_identity.get("tenant_scope") != scope
            or str(source_identity.get("store_id") or "") != str(scoped_store_id or "")
        ):
            return self._stale_result()

        age_at_load = self._nonnegative_seconds(
            row.get("source_age_seconds_at_load"), default=float("inf")
        )
        loaded_at = self._nonnegative_seconds(
            row.get("source_loaded_at"), default=float("inf")
        )
        ttl = self._nonnegative_seconds(
            row.get("source_ttl_seconds"), default=0.0
        )
        ttl = min(ttl, float(self.session_ttl_seconds))
        source_age = age_at_load + max(0.0, float(self.clock()) - loaded_at)
        if not isfinite(source_age) or ttl <= 0 or source_age >= ttl:
            return {
                "error": False,
                "status": "UNIT_PRICE_SCENARIO_SOURCE_STALE",
                "message": "Снимок пакетного плана устарел. Обновите источники и откройте строку повторно.",
                "keyboard": self.keyboard_service.build_main_keyboard(),
                "read_only": True,
                "executed": False,
            }

        planning = row.get("planning") or {}
        candidate = planning.get("target") or {}
        try:
            target_margin = Decimal(str(batch.get("target_margin_percent")))
            candidate_price = Decimal(str(candidate.get("price")))
            forward = candidate.get("forward_result") or {}
            candidate_profit = Decimal(str(forward["calculated"]["profit"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return self._stale_result()
        if (
            candidate.get("status") != "FOUND"
            or forward.get("available") is not True
            or not target_margin.is_finite()
            or target_margin < 0
            or target_margin > 100
            or not candidate_price.is_finite()
            or not candidate_profit.is_finite()
            or candidate_price <= 0
            or candidate_profit * Decimal("100") < target_margin * candidate_price
        ):
            return self._stale_result()

        inputs = deepcopy(row.get("inputs") or {})
        provenance = deepcopy(row.get("provenance") or {})
        inputs["price"] = format(candidate_price, "f")
        provenance["price"] = "batch_target_candidate"
        scenario_identity = {
            "user_id": user,
            "store_id": source_identity.get("store_id"),
            "tenant_scope": scope,
            "product_id": str(identity["product_id"]),
            "offer_id": str(identity["offer_id"]),
            "sku": str(identity["catalog_sku"]),
            "batch_id": batch.get("batch_id"),
            "batch_version": version,
            "row_id": row_id,
        }
        scenario_sources = {
            "periods": snapshot.get("source_periods") or {},
            "as_of": (snapshot.get("source_periods") or {}).get("seller_price_as_of"),
            "completeness": snapshot.get("source_completeness") or {},
        }
        verified = self.scenario_service.calculate(
            inputs,
            identity=scenario_identity,
            provenance=provenance,
            sources=scenario_sources,
        )
        try:
            verified_profit = Decimal(str(verified["calculated"]["profit"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return self._stale_result()
        if (
            verified.get("available") is not True
            or not verified_profit.is_finite()
            or verified_profit * Decimal("100") < target_margin * candidate_price
        ):
            return self._stale_result()

        now = self.clock()
        scenario_id = uuid4().hex[:10]
        source_ttl = ttl
        operation_token = self._begin_source_operation(user, scope)
        session = {
            "scenario_id": scenario_id,
            "version": 1,
            "user_id": user,
            "tenant_scope": scope,
            "sku": str(identity["catalog_sku"]),
            "snapshot": deepcopy(snapshot),
            "inputs": inputs,
            "provenance": provenance,
            "overrides": {"price"},
            "created_at": now,
            "updated_at": now,
            "source_loaded_at": now,
            "source_age_seconds_at_load": source_age,
            "source_ttl_seconds": source_ttl,
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
        return self._scenario_screen(
            session,
            notice="Открыт локальный кандидат цены из пакетного плана. Передача не меняет цену в Ozon.",
        )

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
        if action in {"e", "f", "z", "b", "r", "a", "v", "c", "g", "q", "u", "j", "k"}:
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
                return self._return_to_scenario(session, user, scope, expected_version)
            if action in {"g", "q"}:
                return self._begin_price_planning_input(
                    session,
                    "target_margin" if action == "g" else "price_options",
                    user,
                    scope,
                    expected_version,
                )
            if action == "u" and len(parts) == 5:
                return self._apply_price_planning_result(
                    session, parts[4], user, scope, expected_version
                )
            if action == "j":
                return self._begin_advertising_cap_target(session, user, scope, expected_version)
            if action == "k" and len(parts) == 5:
                return self._apply_advertising_cap(session, parts[4], user, scope, expected_version)
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
        if session is None:
            self._clear_pending_for_key(key)
            return self._stale_result()
        if pending.get("stage") == "advertising_cap_target":
            return self._handle_advertising_cap_target_text(text, pending, session, user, scope, key)
        if pending.get("stage") in {"target_margin", "price_options"}:
            return self._handle_price_planning_text(
                text, pending, session, user, scope, key
            )
        if pending.get("field") not in self.EDITABLE_FIELDS:
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
            current.pop("price_planning_result", None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            self._operation_tokens.pop(key, None)
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
        source_age, source_ttl = self._snapshot_freshness_metadata(snapshot)
        loaded_at = self.clock()
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
            "created_at": loaded_at,
            "updated_at": loaded_at,
            "source_loaded_at": loaded_at,
            "source_age_seconds_at_load": source_age,
            "source_ttl_seconds": source_ttl,
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
            current.pop("price_planning_result", None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            self._operation_tokens.pop((user, scope), None)
            self._pending[(user, scope)] = {
                "scenario_id": current["scenario_id"],
                "version": current["version"],
                "field": field,
            }
            session = deepcopy(current)
        return self._edit_prompt(session, field)

    def _begin_price_planning_input(self, session, stage, user, scope, expected_version):
        if self.target_planning_service is None or stage not in {"target_margin", "price_options"}:
            return self._stale_result()
        key = (user, scope)
        refresh_in_progress = None
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                not isinstance(current, dict)
                or self._active.get(key) != session["scenario_id"]
                or current.get("version") != expected_version
            ):
                return self._stale_result()
            if key in self._operation_tokens:
                refresh_in_progress = deepcopy(current)
            else:
                current.pop("price_planning_result", None)
                current["version"] += 1
                current["updated_at"] = self.clock()
                self._pending[key] = {
                    "scenario_id": current["scenario_id"],
                    "version": current["version"],
                    "stage": stage,
                    "request_id": uuid4().hex,
                }
                session = deepcopy(current)
        if refresh_in_progress is not None:
            return self._scenario_screen(
                refresh_in_progress,
                notice="Источники ещё обновляются. Повторите расчёт после завершения обновления.",
            )
        return self._price_planning_prompt(session, stage)

    def _handle_price_planning_text(self, text, pending, session, user, scope, key):
        stage = pending["stage"]
        raw_text = str(text or "")
        if stage == "target_margin":
            parsed = self.target_planning_service.parse_target_margin(raw_text)
            if parsed.get("valid") is not True:
                return self._price_planning_prompt(
                    session,
                    stage,
                    notice="Некорректный процент. Введите значение от 0 до 100 с точностью до 0,01%.",
                )
            mode = "target_margin"
            target = parsed["value"]
            try:
                result = self.target_planning_service.solve(
                    session["inputs"],
                    target,
                    identity=self._scenario_identity(session),
                    provenance=session["provenance"],
                    sources=self._scenario_sources(session),
                )
            except Exception:
                return self._price_planning_prompt(
                    session, stage,
                    notice="Не удалось выполнить локальный расчёт. Сценарий не изменён; повторите ввод или вернитесь к расчёту.",
                )
            input_value = format(target, "f")
        elif stage == "price_options":
            parsed = self.target_planning_service.parse_price_list(raw_text)
            if parsed.get("valid") is not True:
                return self._price_planning_prompt(
                    session,
                    stage,
                    notice="Список не принят целиком. Укажите от 2 до 5 разных цен до копейки через точку с запятой или с новой строки.",
                )
            mode = "price_options"
            target = None
            try:
                result = self.target_planning_service.compare_prices(
                    session["inputs"],
                    parsed["prices"],
                    target_margin_percent=session.get("price_planning_target_margin"),
                    identity=self._scenario_identity(session),
                    provenance=session["provenance"],
                    sources=self._scenario_sources(session),
                )
            except Exception:
                return self._price_planning_prompt(
                    session, stage,
                    notice="Не удалось выполнить локальное сравнение. Сценарий не изменён; исправьте ввод или вернитесь к расчёту.",
                )
            input_value = list(parsed["normalized"])
        else:
            self._clear_pending_for_key(key)
            return self._stale_result()

        if not isinstance(result, dict) or result.get("error") is True:
            return self._price_planning_prompt(
                session, stage,
                notice="Расчёт не завершён. Текущие параметры сохранены; попробуйте ещё раз.",
            )

        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            active_pending = self._pending.get(key)
            if (
                not isinstance(current, dict)
                or self._active.get(key) != session["scenario_id"]
                or current.get("version") != pending.get("version")
                or active_pending != pending
            ):
                return self._stale_result()
            current["version"] += 1
            current["updated_at"] = self.clock()
            if mode == "target_margin":
                current["price_planning_target_margin"] = input_value
            current["price_planning_result"] = {
                "mode": mode,
                "input": input_value,
                "source_version": pending["version"],
                "result_version": current["version"],
                "user_id": current["user_id"],
                "tenant_scope": current["tenant_scope"],
                "sku": current["sku"],
                "snapshot_id": (current.get("snapshot") or {}).get("snapshot_id"),
                "result": deepcopy(result),
            }
            self._pending.pop(key, None)
            self._operation_tokens.pop(key, None)
            session = deepcopy(current)
        return self._price_planning_result_screen(session)

    def _price_planning_prompt(self, session, stage, notice=None):
        if stage == "target_margin":
            prompt = (
                "Введите целевую маржу от 0 до 100% (например, 20 или 19,5). "
                "Бот покажет ориентир безубыточности и цену для цели."
            )
        else:
            prompt = (
                "Введите 2–5 разных цен через точку с запятой или с новой строки. "
                "Например: 499,90; 549,90; 599,90."
            )
        prompt += " Цена основного сценария не изменится."
        if notice:
            prompt = notice + "\n" + prompt
        return {
            "error": False,
            "status": "UNIT_PRICE_SCENARIO_INPUT_PENDING",
            "stage": stage,
            "message": prompt,
            "keyboard": self.keyboard_service.build_unit_price_cancel_keyboard(
                session["scenario_id"], session["version"]
            ),
            "read_only": True,
            "executed": False,
        }

    def _price_planning_result_screen(self, session):
        stored = session.get("price_planning_result") or {}
        mode = stored.get("mode")
        result = stored.get("result") or {}
        identity = session.get("snapshot", {}).get("identity") or {}
        product = session.get("snapshot", {}).get("product") or {}
        title = (
            "Расчёт целевой маржи"
            if mode == "target_margin"
            else "Сравнение вариантов цены"
        )
        lines = [
            title,
            str(product.get("name") or "Товар")[:70]
            + " · SKU " + str(session["sku"])[:32],
            "Магазин: "
            + str(identity.get("store_name") or identity.get("store_id") or "активный")[:60],
        ]
        if mode == "target_margin":
            target = result.get("target_margin_percent")
            lines.append("Целевая маржа после налога: " + self._percent(target))
            lines.append(self._format_price_planning_outcome(
                "Ориентир безубыточности", result.get("break_even") or {}, "0"
            ))
            lines.append(self._format_price_planning_outcome(
                "Цена для цели", result.get("target") or {}, target
            ))
        else:
            goal = result.get("target_margin_percent")
            lines.append(
                "Цель маржи: " + self._percent(goal)
                if goal is not None
                else "Одинаковые допущения для всех вариантов; целевая маржа не задана."
            )
            for index, row in enumerate(result.get("rows") or [], start=1):
                if row.get("available") is not True:
                    missing = self._price_planning_missing_labels(
                        row.get("forward_result") or row
                    )
                    detail = "расчёт недоступен"
                    if missing:
                        detail += "; заполните " + ", ".join(missing)
                    lines.append(f"{index}. {self._money(row.get('price'))}: {detail}.")
                    continue
                line = (
                    f"{index}. {self._money(row.get('price'))}: прибыль "
                    f"{self._money(row.get('profit'))}/шт.; маржа "
                    f"{self._percent(row.get('margin_percent'))}; налог "
                    f"{self._money(row.get('tax'))}"
                )
                if goal is not None:
                    line += "; цель " + self._percent(goal) + (
                        " достигнута" if row.get("goal_reached") is True
                        else " не достигнута" if row.get("goal_reached") is False
                        else " не проверена"
                    )
                lines.append(line + ".")
        freshness = self._source_freshness(session)
        if freshness.get("status") == "STALE":
            lines.append(
                "Снимок источников устарел; оценка комиссии может отличаться. Обновите данные."
            )
        lines.extend([
            "Цена основного сценария не изменена.",
            "Оценка одной успешной продажи FBO. Комиссия Ozon может измениться при новой цене; FBS не поддержан.",
            "Общие расходы, хранение, кросс-докинг и возвраты не включены.",
        ])
        keyboard_builder = getattr(
            self.keyboard_service,
            "build_unit_price_planning_result_keyboard",
            None,
        )
        keyboard = (
            keyboard_builder(
                session["scenario_id"],
                session["version"],
                mode,
                planning_result=result,
                allow_apply=freshness.get("status") == "FRESH",
            )
            if callable(keyboard_builder)
            else self.keyboard_service.build_unit_price_scenario_keyboard(
                session["scenario_id"], session["version"]
            )
        )
        return {
            "error": False,
            "status": (
                "UNIT_PRICE_TARGET_MARGIN_RESULT"
                if mode == "target_margin"
                else "UNIT_PRICE_PRICE_COMPARISON_RESULT"
            ),
            "message": "\n".join(lines)[:3500],
            "keyboard": keyboard,
            "price_planning_result": deepcopy(result),
            "read_only": True,
            "executed": False,
        }

    def _apply_price_planning_result(self, session, selector, user, scope, expected_version):
        key = (user, scope)
        stored = session.get("price_planning_result")
        snapshot = session.get("snapshot") or {}
        result = (stored or {}).get("result") or {}
        result_identity = result.get("identity") or {}
        if (
            not isinstance(stored, dict)
            or stored.get("result_version") != expected_version
            or stored.get("user_id") != user
            or stored.get("tenant_scope") != scope
            or stored.get("sku") != session.get("sku")
            or stored.get("snapshot_id") != snapshot.get("snapshot_id")
            or result_identity.get("user_id") != user
            or result_identity.get("tenant_scope") != scope
            or result_identity.get("sku") != session.get("sku")
            or result_identity.get("scenario_id") != session.get("scenario_id")
            or result_identity.get("scenario_version") != stored.get("source_version")
        ):
            return self._stale_result()

        if self._source_freshness(session).get("status") != "FRESH":
            return self._invalidate_price_planning_result(
                session,
                user,
                scope,
                expected_version,
                "Снимок источников устарел. Обновите данные и выполните расчёт заново; эту цену не подставил.",
            )

        if key in self._operation_tokens:
            return self._invalidate_price_planning_result(
                session,
                user,
                scope,
                expected_version,
                "Идёт обновление источников. После его завершения повторите расчёт цены.",
            )

        mode = stored.get("mode")
        outcome = None
        if selector == "t" and mode == "target_margin":
            outcome = result.get("target")
            if not isinstance(outcome, dict) or outcome.get("goal_reached") is not True:
                return self._stale_result()
        elif mode == "price_options":
            try:
                index = int(selector)
            except (TypeError, ValueError):
                return self._stale_result()
            rows = result.get("rows") or []
            if str(index) != str(selector) or not 0 <= index < len(rows):
                return self._stale_result()
            outcome = rows[index]
        if not isinstance(outcome, dict) or outcome.get("available") is not True:
            return self._stale_result()

        candidate_price = outcome.get("price")
        if not isinstance(candidate_price, str):
            return self._stale_result()
        candidate_inputs = deepcopy(session.get("inputs") or {})
        candidate_inputs["price"] = candidate_price
        try:
            validation = self.scenario_service.calculate(
                candidate_inputs,
                identity=self._scenario_identity(session),
                provenance=session.get("provenance") or {},
                sources=self._scenario_sources(session),
            )
        except Exception:
            validation = None
        if not isinstance(validation, dict) or validation.get("available") is not True:
            return self._invalidate_price_planning_result(
                session,
                user,
                scope,
                expected_version,
                "Не удалось перепроверить цену прямым расчётом. Параметры сценария не изменены.",
            )

        expired_source = False
        expired_session = False
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            current_plan = current.get("price_planning_result") if isinstance(current, dict) else None
            if (
                not isinstance(current, dict)
                or self._active.get(key) != session["scenario_id"]
                or current.get("version") != expected_version
                or current_plan != stored
                or current.get("tenant_scope") != scope
                or current.get("user_id") != user
                or current.get("sku") != stored.get("sku")
                or (current.get("snapshot") or {}).get("snapshot_id") != stored.get("snapshot_id")
            ):
                return self._stale_result()
            if self.clock() - current.get("updated_at", 0) > self.session_ttl_seconds:
                self._scenarios.pop(session["scenario_id"], None)
                self._active.pop(key, None)
                self._pending.pop(key, None)
                self._operation_tokens.pop(key, None)
                expired_session = True
            elif self._source_freshness(current).get("status") != "FRESH":
                current.pop("price_planning_result", None)
                current["version"] += 1
                current["updated_at"] = self.clock()
                session = deepcopy(current)
                expired_source = True
            elif key in self._operation_tokens:
                return self._stale_result()
            else:
                current["inputs"]["price"] = candidate_price
                current["provenance"]["price"] = "manual_seller_assumption"
                current["overrides"].add("price")
                current.pop("price_planning_result", None)
                current["version"] += 1
                current["updated_at"] = self.clock()
                self._pending.pop(key, None)
                session = deepcopy(current)

        if expired_session:
            return self._stale_result()
        if expired_source:
            return self._scenario_screen(
                session,
                notice="Снимок источников устарел. Обновите данные и выполните расчёт заново; эту цену не подставил.",
            )
        return self._scenario_screen(
            session,
            notice=(
                "Цена " + self._money(candidate_price)
                + " подставлена только в текущий сценарий. Цена и данные в Ozon не изменены."
            ),
        )

    def _invalidate_price_planning_result(
        self, session, user, scope, expected_version, notice
    ):
        key = (user, scope)
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                not isinstance(current, dict)
                or self._active.get(key) != session["scenario_id"]
                or current.get("version") != expected_version
            ):
                return self._stale_result()
            current.pop("price_planning_result", None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            self._operation_tokens.pop(key, None)
            updated = deepcopy(current)
        return self._scenario_screen(updated, notice=notice)

    def _format_price_planning_outcome(self, label, outcome, target):
        if outcome.get("status") == "FOUND" and outcome.get("goal_reached") is True:
            return (
                f"{label}: {self._money(outcome.get('price'))}; прибыль "
                f"{self._money(outcome.get('profit'))}/шт.; маржа "
                f"{self._percent(outcome.get('margin_percent'))}; налог "
                f"{self._money(outcome.get('tax'))} — цель "
                f"{self._percent(target)} достигнута."
            )
        missing = self._price_planning_missing_labels(outcome)
        if outcome.get("status") == "MISSING_INPUTS":
            return "" + label + ": заполните " + (", ".join(missing) or "обязательные параметры") + "."
        if outcome.get("status") == "NOT_FOUND_IN_TESTED_RANGE":
            return label + ": не удалось подобрать цену в допустимом диапазоне при этих условиях."
        if outcome.get("status") == "SEARCH_BUDGET_EXHAUSTED":
            return label + ": лимит расчётов исчерпан; повторите попытку или проверьте допущения."
        if outcome.get("status") == "INVALID_INPUTS":
            return label + ": проверьте некорректные параметры сценария."
        return label + ": расчёт недоступен; проверьте параметры и попробуйте снова."

    def _price_planning_missing_labels(self, outcome):
        labels = [
            self.EDITABLE_FIELDS[field][0]
            for field in outcome.get("missing_inputs", [])
            if field in self.EDITABLE_FIELDS
        ]
        if "tax_mode" in outcome.get("missing_inputs", []) or "tax_rate" in outcome.get("missing_inputs", []):
            labels.append("налоговую политику магазина")
        if "minimum_tax_rate" in outcome.get("missing_inputs", []):
            labels.append("минимальную ставку налога")
        return list(dict.fromkeys(labels))

    def _begin_advertising_cap_target(self, session, user, scope, expected_version):
        if self.advertising_cap_service is None or self.target_planning_service is None:
            return self._friendly_error("UNIT_PRICE_ADVERTISING_CAP_UNAVAILABLE")
        key = (user, scope)
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (not isinstance(current, dict)
                    or self._active.get(key) != session["scenario_id"]
                    or current.get("version") != expected_version
                    or key in self._operation_tokens):
                return self._stale_result()
            current.pop("advertising_cap_result", None)
            current.pop("price_planning_result", None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            version = current["version"]
            self._pending[key] = {
                "scenario_id": session["scenario_id"],
                "version": version,
                "stage": "advertising_cap_target",
                "created_at": self.clock(),
            }
        return {
            "error": False,
            "status": "UNIT_PRICE_ADVERTISING_CAP_TARGET_REQUIRED",
            "message": "Введите целевую маржу от 0 до 100%. Бот отдельно найдёт предел безубыточности и предел для этой цели; расчёт не меняет кампании Ozon.",
            "keyboard": self.keyboard_service.build_unit_price_cancel_keyboard(
                session["scenario_id"], version
            ),
            "read_only": True,
            "executed": False,
        }

    def _handle_advertising_cap_target_text(self, text, pending, session, user, scope, key):
        target = self.target_planning_service.parse_target_margin(str(text or ""))
        if not isinstance(target, dict) or target.get("error"):
            return {
                "error": False,
                "status": "UNIT_PRICE_ADVERTISING_CAP_TARGET_REQUIRED",
                "message": "Цель не принята. Введите процент от 0 до 100, не более двух знаков после запятой.",
                "keyboard": self.keyboard_service.build_unit_price_cancel_keyboard(
                    session["scenario_id"], pending["version"]
                ),
                "read_only": True,
                "executed": False,
            }
        result = self.advertising_cap_service.solve(
            session.get("inputs"), target["normalized"],
            identity=self._scenario_identity(session),
            provenance=session.get("provenance"),
            sources=self._scenario_sources(session),
        )
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (not isinstance(current, dict)
                    or self._active.get(key) != session["scenario_id"]
                    or current.get("version") != pending["version"]
                    or self.clock() - pending.get("created_at", 0) > self.session_ttl_seconds):
                return self._stale_result()
            current.pop("price_planning_result", None)
            # The accepted advertising-cap target is a planning assumption,
            # not just part of this disposable screen. Keep it in the same
            # durable session field used by price-target planning and saved
            # recipe capture.
            current["price_planning_target_margin"] = target["normalized"]
            current["advertising_cap_result"] = {
                "result": deepcopy(result),
                "target": target["normalized"],
                "result_version": current["version"],
                "snapshot_id": (current.get("snapshot") or {}).get("snapshot_id"),
                "sku": current.get("sku"),
                "user_id": user,
                "tenant_scope": scope,
            }
            current["updated_at"] = self.clock()
            saved = deepcopy(current)
            self._pending.pop(key, None)
        return self._advertising_cap_screen(saved)

    @staticmethod
    def _format_advertising_cap_line(label, outcome):
        if not isinstance(outcome, dict) or outcome.get("available") is not True:
            status = outcome.get("status") if isinstance(outcome, dict) else "UNAVAILABLE"
            return f"{label}: предел не подтверждён ({status})."
        return (
            f"{label}: {outcome.get('advertising_rate')}% = {outcome.get('advertising_per_unit')} ₽/шт.; "
            f"прибыль {outcome.get('profit_per_unit')} ₽, налог {outcome.get('tax_per_unit')} ₽; "
            f"запас {outcome.get('headroom_percentage_points')} п.п. / {outcome.get('headroom_per_unit')} ₽/шт."
        )

    def _advertising_cap_screen(self, session):
        stored = session.get("advertising_cap_result") or {}
        result = stored.get("result") or {}
        freshness = self._source_freshness(session)
        direct = self.scenario_service.calculate(
            session.get("inputs"), identity=self._scenario_identity(session),
            provenance=session.get("provenance"), sources=self._scenario_sources(session),
        )
        price = ((direct.get("inputs") or {}).get("price") or {}).get("value")
        lines = [
            "Допустимые расходы на рекламу · один успешный заказ",
            f"Цена продавца: {price if price is not None else 'не задана'} ₽/шт.",
            f"Целевая маржа: {result.get('target_margin_percent', stored.get('target', '—'))}%",
            f"Текущая доля: {result.get('current_advertising_rate', '—')}% · {result.get('current_advertising_per_unit', '—')} ₽/шт.",
            self._format_advertising_cap_line("Безубыточность", result.get("break_even")),
            self._format_advertising_cap_line("Целевая маржа", result.get("target")),
            f"Исходные тарифы: {'актуальны' if freshness.get('status') == 'FRESH' else 'устарели; предел нельзя подставить'}.",
            "Плановая доля от цены продавца, не прогноз CPC/CPO и не гарантия результата рекламы.",
        ]
        if result.get("error") is True:
            lines.insert(1, "Результат не подтверждён: " + str(result.get("code") or result.get("status")))
        valid = (
            result.get("error") is False
            and freshness.get("status") == "FRESH"
            and stored.get("result_version") == session.get("version")
            and stored.get("snapshot_id") == (session.get("snapshot") or {}).get("snapshot_id")
            and stored.get("sku") == session.get("sku")
            and stored.get("user_id") == session.get("user_id")
            and stored.get("tenant_scope") == session.get("tenant_scope")
        )
        buttons = []
        if valid:
            for selector, key, label in (
                ("b", "break_even", "Подставить предел безубыточности"),
                ("t", "target", "Подставить предел целевой маржи"),
            ):
                outcome = result.get(key)
                if isinstance(outcome, dict) and outcome.get("available") is True:
                    buttons.append({"text": label, "callback": f"upc:k:{session['scenario_id']}:{session['version']}:{selector}"})
        buttons.extend([
            {"text": "Назад к расчёту", "callback": f"upc:v:{session['scenario_id']}:{session['version']}"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return {
            "error": False, "status": "UNIT_PRICE_ADVERTISING_CAP_RESULT",
            "message": "\n".join(lines)[:3000],
            "keyboard": {"error": False, "type": "inline_keyboard", "buttons": buttons},
            "advertising_cap_result": deepcopy(result),
            "read_only": True, "executed": False,
        }

    def _apply_advertising_cap(self, session, selector, user, scope, expected_version):
        key = (user, scope)
        stored = session.get("advertising_cap_result") or {}
        result = stored.get("result") or {}
        if (stored.get("result_version") != expected_version
                or stored.get("user_id") != user
                or stored.get("tenant_scope") != scope
                or stored.get("sku") != session.get("sku")
                or stored.get("snapshot_id") != (session.get("snapshot") or {}).get("snapshot_id")
                or self._source_freshness(session).get("status") != "FRESH"
                or key in self._operation_tokens):
            return self._stale_result()
        outcome = result.get("break_even") if selector == "b" else result.get("target") if selector == "t" else None
        if not isinstance(outcome, dict) or outcome.get("available") is not True:
            return self._stale_result()
        candidate = deepcopy(session.get("inputs") or {})
        candidate["advertising_rate"] = outcome.get("advertising_rate")
        verified = self.scenario_service.calculate(
            candidate, identity=self._scenario_identity(session),
            provenance=session.get("provenance"), sources=self._scenario_sources(session),
        )
        calculated = verified.get("calculated") or {}
        try:
            profit = Decimal(str(calculated.get("profit")))
            revenue = Decimal(str(calculated.get("revenue")))
            target = Decimal(str(stored.get("target")))
        except Exception:
            return self._stale_result()
        feasible = verified.get("available") is True and (
            profit >= 0 if selector == "b" else profit * 100 >= target * revenue
        )
        if not feasible:
            return self._stale_result()
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (not isinstance(current, dict)
                    or self._active.get(key) != session["scenario_id"]
                    or current.get("version") != expected_version):
                return self._stale_result()
            current["inputs"]["advertising_rate"] = outcome["advertising_rate"]
            current["provenance"]["advertising_rate"] = "manual_seller_assumption"
            current["overrides"].add("advertising_rate")
            current.pop("advertising_cap_result", None)
            current.pop("price_planning_result", None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            updated = deepcopy(current)
            self._pending.pop(key, None)
        return self._scenario_screen(updated, notice="Рекламный предел перенесён только в локальный сценарий и подтверждён прямым пересчётом. Кампании Ozon не менялись.")

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
            current.pop("price_planning_result", None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            self._operation_tokens.pop((user, scope), None)
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
            current.pop("price_planning_result", None)
            value = current["snapshot"].get("suggested_inputs", {}).get("discount_points_rate")
            current["inputs"]["discount_points_rate"] = value
            current["provenance"]["discount_points_rate"] = (
                current["snapshot"].get("input_provenance", {}).get("discount_points_rate", "unknown")
            )
            current["overrides"].discard("discount_points_rate")
            current["version"] += 1
            current["updated_at"] = self.clock()
            self._operation_tokens.pop((user, scope), None)
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
            current.pop("price_planning_result", None)
            current["version"] += 1
            current["updated_at"] = self.clock()
            expected_version = current["version"]
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
                    self._remove_operation_token_if_matches_locked(key, operation_token)
                    return self._stale_result()
                self._operation_tokens.pop(key, None)
                current["updated_at"] = self.clock()
                snapshot_session = deepcopy(current)
            return self._scenario_screen(
                snapshot_session,
                notice="Не удалось обновить источники. Текущие допущения сохранены.",
            )
        fresh_identity = fresh.get("identity")
        if not isinstance(fresh_identity, dict) or fresh_identity.get("tenant_scope") != scope:
            return self._finish_refresh_as_stale(key, operation_token)
        if not self._same_catalog_identity(
            (snapshot_session.get("snapshot") or {}).get("identity"),
            fresh_identity,
        ):
            return self._finish_refresh_as_identity_changed(key, operation_token)
        inputs = deepcopy(fresh.get("suggested_inputs") or {})
        provenance = deepcopy(fresh.get("input_provenance") or {})
        source_age, source_ttl = self._snapshot_freshness_metadata(fresh)
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
                self._remove_operation_token_if_matches_locked(key, operation_token)
                return self._stale_result()
            current["snapshot"] = deepcopy(fresh)
            current["inputs"] = inputs
            current["provenance"] = provenance
            current["updated_at"] = self.clock()
            current["source_loaded_at"] = current["updated_at"]
            current["source_age_seconds_at_load"] = source_age
            current["source_ttl_seconds"] = source_ttl
            current["version"] += 1
            session = deepcopy(current)
            self._operation_tokens.pop(key, None)
        return self._scenario_screen(session, notice="Источники обновлены; ручные допущения сохранены.")

    def _finish_refresh_as_stale(self, key, operation_token):
        with self._lock:
            self._remove_operation_token_if_matches_locked(key, operation_token)
        return self._stale_result()

    def _finish_refresh_as_identity_changed(self, key, operation_token):
        with self._lock:
            self._remove_operation_token_if_matches_locked(key, operation_token)
        return self._friendly_error("UNIT_PRICE_SCENARIO_IDENTITY_CHANGED")

    @staticmethod
    def _same_catalog_identity(previous, current):
        if not isinstance(previous, dict) or not isinstance(current, dict):
            return False
        for field in ("user_id", "tenant_scope", "product_id", "offer_id", "sku"):
            before = str(previous.get(field) or "").strip()
            after = str(current.get(field) or "").strip()
            if not before or before != after:
                return False
        return str(previous.get("store_id") or "").strip() == str(
            current.get("store_id") or ""
        ).strip()

    def _remove_operation_token_if_matches_locked(self, key, operation_token):
        operation = self._operation_tokens.get(key)
        if isinstance(operation, dict) and operation.get("token") == operation_token:
            self._operation_tokens.pop(key, None)
            return True
        return False

    def _return_to_scenario(self, session, user, scope, expected_version):
        key = (user, scope)
        with self._lock:
            current = self._scenarios.get(session["scenario_id"])
            if (
                not isinstance(current, dict)
                or self._active.get(key) != session["scenario_id"]
                or current.get("version") != expected_version
            ):
                return self._stale_result()
            if current.pop("price_planning_result", None) is not None:
                current["version"] += 1
                current["updated_at"] = self.clock()
            self._pending.pop(key, None)
            self._operation_tokens.pop(key, None)
            updated = deepcopy(current)
        return self._scenario_screen(updated)

    def _snapshot_freshness_metadata(self, snapshot):
        cache = snapshot.get("cache") if isinstance(snapshot, dict) else None
        cache = cache if isinstance(cache, dict) else {}
        age = self._nonnegative_seconds(cache.get("age_seconds"), default=0.0)
        ttl = self._nonnegative_seconds(
            cache.get("ttl_seconds"), default=float(self.session_ttl_seconds)
        )
        return age, min(ttl, float(self.session_ttl_seconds))

    @staticmethod
    def _nonnegative_seconds(value, default):
        if isinstance(value, bool):
            return default
        try:
            seconds = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not isfinite(seconds):
            return default
        return max(0.0, seconds)

    def _source_freshness(self, session):
        loaded_at = self._nonnegative_seconds(
            session.get("source_loaded_at", session.get("created_at", 0)),
            default=0.0,
        )
        elapsed = max(0.0, float(self.clock()) - loaded_at)
        age_at_load = self._nonnegative_seconds(
            session.get("source_age_seconds_at_load"), default=0.0
        )
        age = age_at_load + elapsed
        ttl = self._nonnegative_seconds(
            session.get("source_ttl_seconds"),
            default=float(self.session_ttl_seconds),
        )
        ttl = min(ttl, float(self.session_ttl_seconds))
        return {
            # UnitPriceScenarioSource reuses cache entries only while age < TTL;
            # the scenario must expire at the same boundary.
            "status": "FRESH" if age < ttl else "STALE",
            "age_seconds": age,
            "ttl_seconds": ttl,
        }

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
        source_freshness = self._source_freshness(session)
        source_fresh = source_freshness["status"] == "FRESH"
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
                include_price_planning=self.target_planning_service is not None,
            ),
            "read_only": True,
            "executed": False,
        }

    def _scenario_screen(self, session, notice=None):
        session = deepcopy(session)
        snapshot = session["snapshot"]
        identity = self._scenario_identity(session)
        sources = self._scenario_sources(session)
        source_freshness = self._source_freshness(session)
        source_fresh = source_freshness["status"] == "FRESH"
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
        result["source_freshness"] = source_freshness
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
                include_price_planning=self.target_planning_service is not None,
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

    @staticmethod
    def _target_margin_assumption(session):
        """Return the durable planning goal, independent of transient result UI."""
        target = session.get("price_planning_target_margin")
        if target is not None:
            return deepcopy(target)
        # Keep compatibility with an in-flight session created before the goal
        # was stored separately from its disposable result projection.
        result = (session.get("price_planning_result") or {}).get("result") or {}
        return deepcopy(result.get("target_margin_percent"))

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
            scenario_id = str(scenario_id or "")
            session = self._scenarios.get(scenario_id)
            if not isinstance(session, dict):
                return None
            try:
                requested_version = int(version)
            except (TypeError, ValueError):
                return None
            key = (user, scope)
            if (
                session.get("user_id") != user
                or session.get("tenant_scope") != scope
                or self._active.get(key) != session.get("scenario_id")
                or session.get("version") != requested_version
            ):
                return None
            if self.clock() - session.get("updated_at", 0) > self.session_ttl_seconds:
                self._scenarios.pop(scenario_id, None)
                self._active.pop(key, None)
                pending = self._pending.get(key)
                if isinstance(pending, dict) and pending.get("scenario_id") == scenario_id:
                    self._pending.pop(key, None)
                self._operation_tokens.pop(key, None)
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
            self._operation_tokens.pop((user, scope), None)
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
            "UNIT_PRICE_SCENARIO_IDENTITY_CHANGED": "Карточка товара изменилась после сохранения плана. Старые ручные значения не перенесены; откройте новый товар и создайте для него отдельный план.",
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
        if not self._is_displayable_decimal(number, max_digits=15):
            return "не задано"
        if number == 0:
            number = Decimal("0")
        try:
            formatted = format(
                number.quantize(Decimal("0.01")), ",.2f"
            ).replace(",", " ").replace(".", ",")
        except (InvalidOperation, ArithmeticError, OverflowError, ValueError):
            return "не задано"
        return formatted + " ₽"

    def _percent(self, value):
        number = self._decimal(value)
        if not self._is_displayable_decimal(number, max_digits=28):
            return "не задано"
        if number == 0:
            number = Decimal("0")
        try:
            formatted = format(
                number.quantize(Decimal("0.01")), ",.2f"
            ).replace(",", " ").replace(".", ",")
        except (InvalidOperation, ArithmeticError, OverflowError, ValueError):
            return "не задано"
        return formatted + "%"

    @staticmethod
    def _is_displayable_decimal(number, max_digits):
        if number is None:
            return False
        if number.is_zero():
            return True
        return (
            len(number.as_tuple().digits) <= max_digits
            and number.adjusted() <= 12
            and number.adjusted() >= -12
        )

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
