"""Read-only batch price planning over exact products from one catalog snapshot."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from time import monotonic
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.period_profit_operation_diagnostics import PeriodProfitOperationTrace
from services.tenant_context import get_current_tenant_user_id


class UnitPriceBatchPlanService:
    """Build bounded per-SKU plans without writing seller or accounting data."""

    MIN_ITEMS = 2
    MAX_ITEMS = 10
    TIME_BUDGET_SECONDS = 120
    HTTP_ATTEMPT_BUDGET = 128
    TARGET_CALCULATION_LIMIT = 128
    BATCH_CALCULATION_LIMIT = MAX_ITEMS * TARGET_CALCULATION_LIMIT
    SOURCE_TTL_SECONDS = 600
    ROW_STATUSES = {
        "READY",
        "INCOMPLETE_INPUTS",
        "SOURCE_UNAVAILABLE",
        "SOURCE_STALE",
        "UNSUPPORTED_SCHEME",
        "TARGET_NOT_CONFIRMED",
        "BUDGET_EXHAUSTED",
    }
    EDITABLE_FIELDS = {
        "price",
        "cost",
        "commission_rate",
        "advertising_rate",
        "discount_points_rate",
        "logistics_per_unit",
        "last_mile_per_unit",
        "acquiring_per_unit",
    }

    def __init__(
        self,
        source,
        scenario_service,
        target_planning_service,
        clock=None,
        tenant_scope_provider=None,
    ):
        self.source = source
        self.scenario_service = scenario_service
        self.target_planning_service = target_planning_service
        self.clock = clock or monotonic
        self.tenant_scope_provider = (
            tenant_scope_provider or get_current_tenant_user_id
        )

    def build_from_overview_selection(
        self,
        overview_service,
        user_id,
        target_margin_percent,
        parent_trace=None,
    ):
        """Read the overview's public exact-identity selection and plan it."""
        reader = getattr(overview_service, "get_price_plan_selection", None)
        if not callable(reader):
            return self._error("BATCH_PLAN_SELECTION_UNAVAILABLE")
        try:
            selection = reader()
        except Exception:
            return self._error("BATCH_PLAN_SELECTION_UNAVAILABLE")
        if not isinstance(selection, dict) or selection.get("error") is True:
            return self._error("BATCH_PLAN_SELECTION_UNAVAILABLE")
        return self.build(
            selection.get("items"),
            user_id=user_id,
            target_margin_percent=target_margin_percent,
            parent_trace=parent_trace,
        )

    def build(
        self,
        items,
        user_id,
        target_margin_percent,
        parent_trace=None,
        force_refresh=False,
        previous_batch=None,
        batch_id=None,
        version=1,
    ):
        user, tenant_scope, store_id, scope_error = self._scope(user_id)
        if scope_error:
            return self._error(scope_error)
        if parent_trace is not None and not isinstance(
            parent_trace, PeriodProfitOperationTrace
        ):
            return self._error("BATCH_PLAN_OPERATION_CONTEXT_INVALID")
        parsed_target = self.target_planning_service.parse_target_margin(
            str(target_margin_percent)
        )
        if parsed_target.get("error"):
            return self._error("BATCH_PLAN_TARGET_INVALID")
        normalized = self._normalize_selection(items)
        if isinstance(normalized, dict):
            return normalized

        target = parsed_target["value"]
        batch_id = batch_id or uuid4().hex[:20]
        previous_batch_rows = (
            previous_batch.get("rows") or []
            if isinstance(previous_batch, dict)
            else []
        )
        previous_rows = {
            row.get("row_id"): row
            for row in previous_batch_rows
            if isinstance(row, dict)
        }
        rows = [self._pending_row(item) for item in normalized]
        for row in rows:
            previous = previous_rows.get(row["row_id"])
            if isinstance(previous, dict):
                row["manual_assumptions"] = deepcopy(
                    previous.get("manual_assumptions") or {}
                )
        batch = {
            "error": False,
            "kind": "UNIT_PRICE_BATCH_PLAN",
            "batch_id": batch_id,
            "version": max(1, int(version)),
            "owner_id": user,
            "store_id": store_id,
            "tenant_scope": tenant_scope,
            "target_margin_percent": format(target, "f"),
            "rows": rows,
            "rows_selected": len(rows),
            "rows_attempted": 0,
            "rows_completed": 0,
            "evaluation_count": 0,
            "evaluation_limit": self.BATCH_CALCULATION_LIMIT,
            "read_only": True,
            "executed": False,
        }

        trace = PeriodProfitOperationTrace(
            operation="unit_price_batch_plan",
            time_budget_seconds=self.TIME_BUDGET_SECONDS,
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            parent=parent_trace,
        )
        try:
            catalog = self.source.product_service.load_products()
        except Exception:
            catalog = None
        if not isinstance(catalog, (list, tuple)):
            for row in batch["rows"]:
                row.update(status="SOURCE_UNAVAILABLE", reason="CATALOG_UNAVAILABLE")
            return self._finish(batch, trace)

        catalog_index = self._index_catalog(catalog)
        total_calculations = 0
        for row in batch["rows"]:
            if trace.is_budget_exhausted():
                row.update(status="BUDGET_EXHAUSTED", reason="SHARED_OPERATION_BUDGET")
                continue
            row["_attempted"] = True
            batch["rows_attempted"] += 1
            product, resolution = self._resolve_catalog_product(
                catalog_index, row["identity"]
            )
            if product is None:
                row.update(status="SOURCE_UNAVAILABLE", reason=resolution)
                continue
            raw_scheme = product.get("scheme") or product.get("fulfillment_scheme")
            scheme = str(raw_scheme or "FBO").strip().upper()
            row["scheme"] = scheme
            if scheme != "FBO":
                row.update(status="UNSUPPORTED_SCHEME", reason="SCHEME_NOT_SUPPORTED")
                continue
            if trace.is_budget_exhausted():
                row.update(status="BUDGET_EXHAUSTED", reason="SHARED_OPERATION_BUDGET")
                continue
            try:
                snapshot = self.source.load_snapshot(
                    row["identity"]["catalog_sku"],
                    user_id=user,
                    operation_trace=trace,
                    catalog_product=product,
                    force_refresh=bool(force_refresh),
                )
            except Exception:
                snapshot = self._error("UNIT_PRICE_SCENARIO_SOURCE_UNAVAILABLE")
            if not isinstance(snapshot, dict) or snapshot.get("error") is True:
                code = snapshot.get("code") if isinstance(snapshot, dict) else None
                status = (
                    "BUDGET_EXHAUSTED"
                    if code in {
                        "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED",
                        "OZON_OPERATION_TIME_BUDGET_EXHAUSTED",
                        "OZON_OPERATION_CANCELLED",
                    }
                    else "SOURCE_UNAVAILABLE"
                )
                row.update(status=status, reason=code or "SOURCE_UNAVAILABLE")
                continue
            returned_identity = snapshot.get("identity") or {}
            if not self._same_identity(returned_identity, row["identity"]):
                row.update(status="SOURCE_UNAVAILABLE", reason="SOURCE_IDENTITY_MISMATCH")
                continue

            source_age, source_ttl = self._cache_freshness(snapshot)
            row.update({
                "snapshot": deepcopy(snapshot),
                "inputs": deepcopy(snapshot.get("suggested_inputs") or {}),
                "provenance": deepcopy(snapshot.get("input_provenance") or {}),
                "source_age_seconds_at_load": source_age,
                "source_ttl_seconds": source_ttl,
                "source_loaded_at": self.clock(),
                "source_as_of": deepcopy(snapshot.get("source_periods") or {}),
            })
            self._restore_manual_assumptions(
                batch, row, previous_rows.get(row["row_id"])
            )
            source_completeness = snapshot.get("source_completeness") or {}
            source_is_stale = source_age >= source_ttl
            if source_is_stale:
                row.update(status="SOURCE_STALE", reason="SOURCE_CACHE_EXPIRED")
                continue
            scenario = self.scenario_service.calculate(
                row["inputs"],
                identity=self._scenario_identity(batch, row),
                provenance=row["provenance"],
                sources=self._scenario_sources(snapshot),
            )
            if not self._source_scheme_supported(source_completeness, scheme):
                row.update(status="UNSUPPORTED_SCHEME", reason="SOURCE_SCHEME_UNCONFIRMED")
                continue
            if scenario.get("available") is not True:
                row.update(
                    status="INCOMPLETE_INPUTS",
                    reason="REQUIRED_ASSUMPTIONS_MISSING" if scenario.get("missing_inputs") else "INPUTS_INVALID",
                    missing_inputs=list(scenario.get("missing_inputs") or []),
                    invalid_inputs=list(scenario.get("invalid_inputs") or []),
                    scenario=scenario,
                )
                continue

            planning = self.target_planning_service.solve(
                row["inputs"],
                target,
                identity=self._scenario_identity(batch, row),
                provenance=row["provenance"],
                sources=self._scenario_sources(snapshot),
            )
            row["evaluation_count"] = int(planning.get("evaluation_count") or 0)
            total_calculations += row["evaluation_count"]
            if total_calculations > self.BATCH_CALCULATION_LIMIT:
                row.update(status="BUDGET_EXHAUSTED", reason="BATCH_CALCULATION_LIMIT")
                continue
            row["scenario"] = scenario
            row["planning"] = planning
            target_result = planning.get("target") or {}
            if planning.get("error") or target_result.get("status") != "FOUND":
                row.update(status="TARGET_NOT_CONFIRMED", reason=target_result.get("reason") or target_result.get("status") or planning.get("code") or "TARGET_NOT_CONFIRMED")
            elif not self._candidate_reaches_target(target_result, target):
                row.update(status="TARGET_NOT_CONFIRMED", reason="FINAL_FORWARD_CHECK_FAILED")
            else:
                row.update(status="READY", reason=None)
            batch["rows_completed"] += 1

        batch["evaluation_count"] = total_calculations
        return self._finish(batch, trace)

    def refresh(self, batch, parent_trace=None):
        """Explicitly refresh source facts while retaining local assumptions."""
        current = self._copy_valid_batch(batch)
        if not isinstance(current, dict) or current.get("error") is True:
            return current
        selection = [
            {"identity": deepcopy(row["identity"])} for row in current["rows"]
        ]
        return self.build(
            selection,
            user_id=current["owner_id"],
            target_margin_percent=current["target_margin_percent"],
            parent_trace=parent_trace,
            force_refresh=True,
            previous_batch=current,
            batch_id=current["batch_id"],
            version=int(current["version"]) + 1,
        )

    def edit_row_assumption(self, batch, row_id, field, value):
        """Change one local assumption and recalculate only from its snapshot."""
        cloned = self._copy_valid_batch(batch)
        if not isinstance(cloned, dict) or cloned.get("error") is True:
            return cloned
        if not isinstance(field, str) or field not in self.EDITABLE_FIELDS or isinstance(value, bool):
            return self._error("BATCH_PLAN_ASSUMPTION_INVALID")
        if not isinstance(value, (str, int, float, Decimal)):
            return self._error("BATCH_PLAN_ASSUMPTION_INVALID")
        row = self._find_row(cloned, row_id)
        if row is None or not isinstance(row.get("snapshot"), dict):
            return self._error("BATCH_PLAN_ROW_STALE")
        if not self._row_is_fresh(row):
            cloned["version"] += 1
            row.update(status="SOURCE_STALE", reason="SOURCE_CACHE_EXPIRED", planning=None)
            return self._finish_edit(cloned)
        inputs = dict(row.get("inputs") or {})
        candidate = dict(inputs)
        candidate[field] = value
        validation = self.scenario_service.calculate(
            candidate,
            identity=self._scenario_identity(cloned, row),
            provenance=row.get("provenance") or {},
            sources=self._scenario_sources(row["snapshot"]),
        )
        if field in (validation.get("invalid_inputs") or []):
            return self._error("BATCH_PLAN_ASSUMPTION_INVALID")
        row["inputs"] = candidate
        cloned["version"] += 1
        row.setdefault("provenance", {})[field] = "manual_seller_assumption"
        row.setdefault("manual_assumptions", {})[field] = {
            "value": value,
            "provenance": "manual_seller_assumption",
        }
        self._recalculate_row(cloned, row)
        return self._finish_edit(cloned)

    def set_target_margin(self, batch, target_margin_percent):
        """Update target locally; no source call is made by this operation."""
        cloned = self._copy_valid_batch(batch)
        if not isinstance(cloned, dict) or cloned.get("error") is True:
            return cloned
        parsed = self.target_planning_service.parse_target_margin(
            str(target_margin_percent)
        )
        if parsed.get("error"):
            return self._error("BATCH_PLAN_TARGET_INVALID")
        cloned["version"] += 1
        cloned["target_margin_percent"] = format(parsed["value"], "f")
        for row in cloned["rows"]:
            if isinstance(row.get("snapshot"), dict) and row.get("status") not in {
                "SOURCE_UNAVAILABLE", "UNSUPPORTED_SCHEME", "BUDGET_EXHAUSTED"
            }:
                self._recalculate_row(cloned, row)
        return self._finish_edit(cloned)

    def preview_advertising_rate(self, batch, row_ids, value):
        """Return the exact rows/value that a separate confirmation will edit."""
        cloned = self._copy_valid_batch(batch)
        if not isinstance(cloned, dict) or cloned.get("error") is True:
            return cloned
        selected = self._selected_rows(cloned, row_ids)
        if selected is None or isinstance(value, bool) or not isinstance(
            value, (str, int, float, Decimal)
        ):
            return self._error("BATCH_PLAN_ADVERTISING_PREVIEW_INVALID")
        preview = []
        for row in selected:
            if not isinstance(row.get("snapshot"), dict) or not self._row_is_fresh(row):
                return self._error("BATCH_PLAN_ROW_STALE")
            candidate = dict(row.get("inputs") or {})
            candidate["advertising_rate"] = value
            checked = self.scenario_service.calculate(
                candidate,
                identity=self._scenario_identity(cloned, row),
                provenance=row.get("provenance") or {},
                sources=self._scenario_sources(row["snapshot"]),
            )
            if "advertising_rate" in (checked.get("invalid_inputs") or []):
                return self._error("BATCH_PLAN_ADVERTISING_PREVIEW_INVALID")
            preview.append({
                "row_id": row["row_id"],
                "offer_id": row["identity"]["offer_id"],
                "catalog_sku": row["identity"]["catalog_sku"],
                "previous_value": (row.get("inputs") or {}).get("advertising_rate"),
                "new_value": value,
            })
        return {
            "error": False,
            "kind": "UNIT_PRICE_BATCH_ASSUMPTION_PREVIEW",
            "batch_id": cloned["batch_id"],
            "batch_version": cloned["version"],
            "rows": preview,
            "requires_confirmation": True,
            "read_only": True,
            "executed": False,
        }

    def apply_advertising_rate(
        self,
        batch,
        row_ids,
        value,
        confirmed=False,
        expected_batch_id=None,
        expected_batch_version=None,
    ):
        """Apply one reviewed local rate to selected rows of the batch."""
        if confirmed is not True:
            return self._error("BATCH_PLAN_CONFIRMATION_REQUIRED")
        cloned = self._copy_valid_batch(batch)
        if not isinstance(cloned, dict) or cloned.get("error") is True:
            return cloned
        if (
            expected_batch_id != cloned.get("batch_id")
            or expected_batch_version != cloned.get("version")
        ):
            return self._error("BATCH_PLAN_CONFIRMATION_STALE")
        selected = self._selected_rows(cloned, row_ids)
        if selected is None:
            return self._error("BATCH_PLAN_ADVERTISING_PREVIEW_INVALID")
        # Validate every row before changing any row.
        for row in selected:
            if not isinstance(row.get("snapshot"), dict) or not self._row_is_fresh(row):
                return self._error("BATCH_PLAN_ROW_STALE")
            candidate = dict(row.get("inputs") or {})
            candidate["advertising_rate"] = value
            checked = self.scenario_service.calculate(
                candidate,
                identity=self._scenario_identity(cloned, row),
                provenance=row.get("provenance") or {},
                sources=self._scenario_sources(row["snapshot"]),
            )
            if "advertising_rate" in (checked.get("invalid_inputs") or []):
                return self._error("BATCH_PLAN_ADVERTISING_PREVIEW_INVALID")
        cloned["version"] += 1
        for row in selected:
            row.setdefault("inputs", {})["advertising_rate"] = value
            row.setdefault("provenance", {})["advertising_rate"] = "manual_seller_assumption"
            row.setdefault("manual_assumptions", {})["advertising_rate"] = {
                "value": value,
                "provenance": "manual_seller_assumption",
            }
            self._recalculate_row(cloned, row)
        return self._finish_edit(cloned)

    def _finish(self, batch, trace):
        batch["rows_completed"] = sum(
            1 for row in batch["rows"] if row.pop("_attempted", False)
        )
        batch["operation_diagnostics"] = {
            "http_attempts": trace.ozon_requests_reserved,
            "http_attempt_limit": self.HTTP_ATTEMPT_BUDGET,
            "elapsed_seconds": round(max(0.0, self.clock() - trace.started_at), 3),
            "time_limit_seconds": self.TIME_BUDGET_SECONDS,
        }
        batch["status"] = (
            "COMPLETED"
            if all(row.get("status") != "BUDGET_EXHAUSTED" for row in batch["rows"])
            else "PARTIAL_BUDGET_EXHAUSTED"
        )
        return batch

    def _finish_edit(self, batch):
        batch["read_only"] = True
        batch["executed"] = False
        batch["evaluation_count"] = sum(
            int(row.get("evaluation_count") or 0) for row in batch["rows"]
        )
        if batch["evaluation_count"] > self.BATCH_CALCULATION_LIMIT:
            return self._error("BATCH_PLAN_CALCULATION_LIMIT_EXCEEDED")
        batch["status"] = (
            "PARTIAL_BUDGET_EXHAUSTED"
            if any(row.get("status") == "BUDGET_EXHAUSTED" for row in batch["rows"])
            else "COMPLETED"
        )
        return batch

    def _recalculate_row(self, batch, row):
        row["missing_inputs"] = []
        row["invalid_inputs"] = []
        if not self._row_is_fresh(row):
            row.update(status="SOURCE_STALE", reason="SOURCE_CACHE_EXPIRED", planning=None)
            return
        scenario = self.scenario_service.calculate(
            row.get("inputs") or {},
            identity=self._scenario_identity(batch, row),
            provenance=row.get("provenance") or {},
            sources=self._scenario_sources(row["snapshot"]),
        )
        row["scenario"] = scenario
        row["missing_inputs"] = list(scenario.get("missing_inputs") or [])
        row["invalid_inputs"] = list(scenario.get("invalid_inputs") or [])
        if scenario.get("available") is not True:
            row.update(
                status="INCOMPLETE_INPUTS",
                reason="REQUIRED_ASSUMPTIONS_MISSING" if scenario.get("missing_inputs") else "INPUTS_INVALID",
                planning=None,
                evaluation_count=0,
            )
            return
        planning = self.target_planning_service.solve(
            row["inputs"],
            batch["target_margin_percent"],
            identity=self._scenario_identity(batch, row),
            provenance=row.get("provenance") or {},
            sources=self._scenario_sources(row["snapshot"]),
        )
        row["planning"] = planning
        row["evaluation_count"] = int(planning.get("evaluation_count") or 0)
        outcome = planning.get("target") or {}
        if planning.get("error") or outcome.get("status") != "FOUND":
            row.update(
                status="TARGET_NOT_CONFIRMED",
                reason=outcome.get("reason") or outcome.get("status") or planning.get("code") or "TARGET_NOT_CONFIRMED",
            )
            return
        if not self._candidate_reaches_target(
            outcome, Decimal(str(batch["target_margin_percent"]))
        ):
            row.update(
                status="TARGET_NOT_CONFIRMED",
                reason="FINAL_FORWARD_CHECK_FAILED",
            )
            return
        row.update(status="READY", reason=None)

    def _copy_valid_batch(self, batch):
        if not isinstance(batch, dict) or batch.get("kind") != "UNIT_PRICE_BATCH_PLAN":
            return self._error("BATCH_PLAN_STALE")
        if (
            batch.get("read_only") is not True
            or batch.get("executed") is not False
            or not isinstance(batch.get("rows"), list)
            or not self.MIN_ITEMS <= len(batch["rows"]) <= self.MAX_ITEMS
        ):
            return self._error("BATCH_PLAN_STALE")
        user, scope, store, error = self._scope(batch.get("owner_id"))
        if error or user != batch.get("owner_id") or scope != batch.get("tenant_scope") or store != batch.get("store_id"):
            return self._error("BATCH_PLAN_STALE")
        return deepcopy(batch)

    @staticmethod
    def _find_row(batch, row_id):
        matches = [row for row in batch["rows"] if row.get("row_id") == row_id]
        return matches[0] if len(matches) == 1 else None

    def _selected_rows(self, batch, row_ids):
        if not isinstance(row_ids, (list, tuple)) or not row_ids or len(row_ids) > self.MAX_ITEMS:
            return None
        if any(not isinstance(row_id, str) for row_id in row_ids) or len(set(row_ids)) != len(row_ids):
            return None
        selected = [self._find_row(batch, row_id) for row_id in row_ids]
        return selected if all(row is not None for row in selected) else None

    def _row_is_fresh(self, row):
        age_at_load = self._safe_seconds(row.get("source_age_seconds_at_load"), 0.0)
        loaded_at = self._safe_seconds(row.get("source_loaded_at"), 0.0)
        ttl = min(
            self._safe_seconds(row.get("source_ttl_seconds"), self.SOURCE_TTL_SECONDS),
            self.SOURCE_TTL_SECONDS,
        )
        return age_at_load + max(0.0, float(self.clock()) - loaded_at) < ttl

    @staticmethod
    def _candidate_reaches_target(outcome, target):
        forward = outcome.get("forward_result")
        if not isinstance(forward, dict) or forward.get("available") is not True:
            return False
        try:
            profit = Decimal(str(forward["calculated"]["profit"]))
            price = Decimal(str(outcome["price"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return False
        return (
            profit.is_finite()
            and price.is_finite()
            and price > 0
            and profit * Decimal("100") >= target * price
        )

    def _scope(self, user_id):
        user = str(user_id or "").strip()
        tenant_scope = str(self.tenant_scope_provider() or "").strip()
        scoped_user, store_id = split_store_tenant_scope(tenant_scope)
        if not user or not tenant_scope or scoped_user != user:
            return user, tenant_scope, store_id, "BATCH_PLAN_TENANT_MISMATCH"
        return user, tenant_scope, store_id, None

    def _normalize_selection(self, items):
        if not isinstance(items, (list, tuple)):
            return self._error("BATCH_PLAN_SELECTION_INVALID")
        if not self.MIN_ITEMS <= len(items) <= self.MAX_ITEMS:
            return self._error("BATCH_PLAN_SELECTION_SIZE_INVALID")
        rows = []
        seen = set()
        for item in items:
            identity = item.get("identity") if isinstance(item, dict) else None
            if not isinstance(identity, dict):
                return self._error("BATCH_PLAN_EXACT_CATALOG_ID_REQUIRED")
            raw_values = tuple(
                identity.get(field) for field in ("product_id", "offer_id", "catalog_sku")
            )
            if any(
                isinstance(value, bool) or not isinstance(value, (str, int))
                for value in raw_values
            ):
                return self._error("BATCH_PLAN_EXACT_CATALOG_ID_REQUIRED")
            values = tuple(str(value).strip() for value in raw_values)
            if any(
                not value
                or len(value) > 128
                or any(ord(char) < 32 or ord(char) == 127 for char in value)
                for value in values
            ):
                return self._error("BATCH_PLAN_EXACT_CATALOG_ID_REQUIRED")
            if values in seen:
                return self._error("BATCH_PLAN_DUPLICATE_IDENTITY")
            seen.add(values)
            row_id = "row_" + sha256("|".join(values).encode("utf-8")).hexdigest()[:20]
            rows.append({
                "row_id": row_id,
                "identity": {
                    "product_id": values[0],
                    "offer_id": values[1],
                    "catalog_sku": values[2],
                },
                "status": "SOURCE_UNAVAILABLE",
                "reason": "NOT_STARTED",
            })
        return rows

    @staticmethod
    def _pending_row(item):
        return {
            **deepcopy(item),
            "status": "SOURCE_UNAVAILABLE",
            "reason": "NOT_STARTED",
            "inputs": {},
            "provenance": {},
            "manual_assumptions": {},
            "source_as_of": {},
            "snapshot": None,
            "scenario": None,
            "planning": None,
            "_attempted": False,
        }

    def _restore_manual_assumptions(self, batch, row, previous):
        if not isinstance(previous, dict):
            return
        assumptions = previous.get("manual_assumptions") or {}
        for field, record in assumptions.items():
            if field not in self.EDITABLE_FIELDS or not isinstance(record, dict):
                continue
            value = record.get("value")
            if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
                continue
            row.setdefault("manual_assumptions", {})[field] = deepcopy(record)
            if not isinstance(row.get("snapshot"), dict):
                continue
            candidate = dict(row.get("inputs") or {})
            candidate[field] = value
            checked = self.scenario_service.calculate(
                candidate,
                identity=self._scenario_identity(batch, row),
                provenance=row.get("provenance") or {},
                sources=self._scenario_sources(row["snapshot"]),
            )
            if field in (checked.get("invalid_inputs") or []):
                continue
            row["inputs"] = candidate
            row.setdefault("provenance", {})[field] = "manual_seller_assumption"

    @staticmethod
    def _index_catalog(catalog):
        index = {}
        for raw in catalog:
            if isinstance(raw, dict):
                product = dict(raw)
            elif isinstance(raw, (list, tuple)) and len(raw) >= 3:
                product = {"product_id": raw[0], "offer_id": raw[1], "sku": raw[2]}
            else:
                continue
            raw_identity = (
                product.get("product_id"),
                product.get("offer_id"),
                product.get("sku"),
            )
            if any(
                isinstance(value, bool) or not isinstance(value, (str, int))
                for value in raw_identity
            ):
                continue
            identity = tuple(str(value).strip() for value in raw_identity)
            if all(
                value
                and len(value) <= 128
                and not any(ord(char) < 32 or ord(char) == 127 for char in value)
                for value in identity
            ):
                index.setdefault(identity, []).append(product)
        return index

    def _resolve_catalog_product(self, catalog_index, identity):
        key = (
            identity["product_id"], identity["offer_id"], identity["catalog_sku"]
        )
        matches = catalog_index.get(key) or []
        if len(matches) == 1:
            return matches[0], None
        return None, "CATALOG_IDENTITY_AMBIGUOUS" if matches else "CATALOG_IDENTITY_NOT_FOUND"

    @staticmethod
    def _same_identity(source_identity, selected_identity):
        return (
            str(source_identity.get("product_id") or "") == selected_identity["product_id"]
            and str(source_identity.get("offer_id") or "") == selected_identity["offer_id"]
            and str(source_identity.get("sku") or "") == selected_identity["catalog_sku"]
        )

    @staticmethod
    def _cache_freshness(snapshot):
        cache = snapshot.get("cache") or {}
        age = UnitPriceBatchPlanService._safe_seconds(cache.get("age_seconds"), 0.0)
        ttl = UnitPriceBatchPlanService._safe_seconds(
            cache.get("ttl_seconds"), UnitPriceBatchPlanService.SOURCE_TTL_SECONDS
        )
        return age, min(ttl, UnitPriceBatchPlanService.SOURCE_TTL_SECONDS)

    @staticmethod
    def _safe_seconds(value, default):
        if isinstance(value, bool):
            return default
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if number != number or number in (float("inf"), float("-inf")):
            return default
        return max(0.0, number)

    @staticmethod
    def _source_scheme_supported(completeness, scheme):
        # The established single-SKU source models FBO tariffs. A catalog row
        # without a fulfillment field retains that existing FBO contract.
        declared = completeness.get("scheme") if isinstance(completeness, dict) else None
        return scheme == "FBO" and declared not in {"FBS", "UNKNOWN"}

    @staticmethod
    def _scenario_identity(batch, row):
        return {
            "user_id": batch["owner_id"],
            "store_id": batch["store_id"],
            "tenant_scope": batch["tenant_scope"],
            "product_id": row["identity"]["product_id"],
            "offer_id": row["identity"]["offer_id"],
            "sku": row["identity"]["catalog_sku"],
            "batch_id": batch["batch_id"],
            "batch_version": batch["version"],
            "row_id": row["row_id"],
        }

    @staticmethod
    def _scenario_sources(snapshot):
        periods = snapshot.get("source_periods") or {}
        return {
            "periods": periods,
            "as_of": periods.get("seller_price_as_of"),
            "completeness": snapshot.get("source_completeness") or {},
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
