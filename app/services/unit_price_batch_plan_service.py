"""Read-only batch price planning over exact products from one catalog snapshot."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from time import monotonic
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.period_profit_operation_diagnostics import PeriodProfitOperationTrace
from services.tenant_context import get_current_tenant_user_id
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter


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
        tariff_profile_runtime_service=None,
    ):
        self.source = source
        self.scenario_service = scenario_service
        self.target_planning_service = target_planning_service
        self.clock = clock or monotonic
        self.tenant_scope_provider = (
            tenant_scope_provider or get_current_tenant_user_id
        )
        self.tariff_profile_runtime_service = tariff_profile_runtime_service

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
        extended_scenarios_by_sku=None,
        strict_return_evidence_by_sku=None,
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
        selected_skus = {item["identity"]["catalog_sku"] for item in normalized}
        for evidence_map in (extended_scenarios_by_sku, strict_return_evidence_by_sku):
            if evidence_map is not None and (
                not isinstance(evidence_map, dict)
                or any(not isinstance(key, str) or key not in selected_skus for key in evidence_map)
                or any(not isinstance(value, dict) for value in evidence_map.values())
            ):
                return self._error("BATCH_PLAN_EXTENDED_EVIDENCE_SCOPE_INVALID")
        if strict_return_evidence_by_sku and any(
            sku not in (extended_scenarios_by_sku or {})
            for sku in strict_return_evidence_by_sku
        ):
            return self._error("BATCH_PLAN_EXTENDED_EVIDENCE_SCOPE_INVALID")

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
                row["extended_scenario"] = deepcopy(previous.get("extended_scenario"))
                row["strict_return_evidence"] = deepcopy(previous.get("strict_return_evidence"))
            sku = row["identity"]["catalog_sku"]
            if extended_scenarios_by_sku is not None:
                row["extended_scenario"] = deepcopy(extended_scenarios_by_sku.get(sku))
                if strict_return_evidence_by_sku is None:
                    row["strict_return_evidence"] = None
            if strict_return_evidence_by_sku is not None:
                row["strict_return_evidence"] = deepcopy(strict_return_evidence_by_sku.get(sku))
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
            remaining_calculations = (
                self.BATCH_CALCULATION_LIMIT - total_calculations
            )
            if remaining_calculations <= 0:
                row.update(status="BUDGET_EXHAUSTED", reason="BATCH_CALCULATION_LIMIT")
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
            tariff_error = self._resolve_row_tariff(batch, row)
            if tariff_error is not None:
                row.update(status="SOURCE_UNAVAILABLE", reason=tariff_error)
                continue
            scenario = self.scenario_service.calculate(
                row["inputs"],
                identity=self._scenario_identity(batch, row),
                provenance=row["provenance"],
                sources=self._scenario_sources(snapshot),
                **self._extended_kwargs(row),
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

            evaluation_limit = min(
                self.TARGET_CALCULATION_LIMIT, remaining_calculations,
            )
            planning = self.target_planning_service.solve(
                row["inputs"],
                target,
                identity=self._scenario_identity(batch, row),
                provenance=row["provenance"],
                sources=self._scenario_sources(snapshot),
                max_evaluations=evaluation_limit,
                **self._extended_kwargs(row),
                **self._tariff_planning_kwargs(batch, row),
            )
            row["evaluation_count"] = int(planning.get("evaluation_count") or 0)
            total_calculations += row["evaluation_count"]
            if row["evaluation_count"] > evaluation_limit:
                row.update(status="BUDGET_EXHAUSTED", reason="BATCH_CALCULATION_LIMIT")
                continue
            row["scenario"] = scenario
            row["planning"] = planning
            target_result = planning.get("target") or {}
            if target_result.get("status") == "SEARCH_BUDGET_EXHAUSTED":
                row.update(status="BUDGET_EXHAUSTED", reason="TARGET_CALCULATION_LIMIT")
                continue
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
        next_tariff_snapshot = row.get("frozen_tariff_resolution")
        candidate_provenance = dict(row.get("provenance") or {})
        candidate_provenance[field] = "manual_seller_assumption"
        cents = (
            UnitPriceTariffSnapshotAdapter.price_to_cents(inputs.get("price"))
            if field == "commission_rate" else None
        )
        if field == "price" and isinstance(next_tariff_snapshot, dict):
            cents = UnitPriceTariffSnapshotAdapter.price_to_cents(value)
            resolution = (
                UnitPriceTariffSnapshotAdapter.resolve_frozen(
                    next_tariff_snapshot, self._scenario_identity(cloned, row), cents,
                ) if cents is not None else {"available": False}
            )
            if resolution.get("error") is True:
                return self._error("BATCH_PLAN_TARIFF_SNAPSHOT_INVALID")
            if resolution.get("available") is True:
                candidate["commission_rate"] = resolution.get("commission_rate")
                origin = (resolution.get("selected_profile") or {}).get("origin")
                candidate_provenance["commission_rate"] = {
                    "MANUAL_SELLER_ASSUMPTION": "manual_seller_assumption",
                    "CURRENT_PRICE_POINT": "current_price_point",
                    "CONFIRMED_OFFICIAL_SOURCE": "confirmed_official_source",
                }.get(origin, "unknown")
            else:
                candidate["commission_rate"] = None
                candidate_provenance["commission_rate"] = "unknown"
        elif field == "commission_rate" and isinstance(next_tariff_snapshot, dict):
            override = (
                UnitPriceTariffSnapshotAdapter.with_manual_point_override(
                    next_tariff_snapshot, self._scenario_identity(cloned, row), cents,
                    value, profile_id="manual-row-" + str(row.get("row_id") or "override"),
                ) if cents is not None else None
            )
            if override is None:
                return self._error("BATCH_PLAN_TARIFF_OVERRIDE_INVALID")
            next_tariff_snapshot = override
            candidate_provenance["commission_rate"] = "manual_seller_assumption"
        validation = self.scenario_service.calculate(
            candidate,
            identity=self._scenario_identity(cloned, row),
            provenance=candidate_provenance,
            sources=self._scenario_sources(row["snapshot"]),
            **self._extended_kwargs(row),
        )
        if field in (validation.get("invalid_inputs") or []):
            return self._error("BATCH_PLAN_ASSUMPTION_INVALID")
        row["inputs"] = candidate
        cloned["version"] += 1
        row["provenance"] = candidate_provenance
        if next_tariff_snapshot is not None:
            row["frozen_tariff_resolution"] = deepcopy(next_tariff_snapshot)
        row.setdefault("manual_assumptions", {})[field] = {
            "value": value,
            "provenance": "manual_seller_assumption",
            **({"seller_price_cents": cents}
               if field == "commission_rate" and cents is not None else {}),
        }
        if field == "price":
            manual_commission = row.get("manual_assumptions", {}).get("commission_rate")
            new_cents = UnitPriceTariffSnapshotAdapter.price_to_cents(value)
            if (isinstance(manual_commission, dict)
                    and manual_commission.get("seller_price_cents") != new_cents):
                row["manual_assumptions"].pop("commission_rate", None)
        self._recalculate_row(
            cloned, row,
            max_evaluations=self._remaining_evaluation_budget(
                cloned, {row.get("row_id")},
            ),
        )
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
        rows_to_recalculate = [
            row for row in cloned["rows"]
            if isinstance(row.get("snapshot"), dict) and row.get("status") not in {
                "SOURCE_UNAVAILABLE", "UNSUPPORTED_SCHEME"
            }
        ]
        remaining_evaluations = self._remaining_evaluation_budget(
            cloned, {row.get("row_id") for row in rows_to_recalculate},
        )
        for row in rows_to_recalculate:
            self._recalculate_row(
                cloned, row, max_evaluations=remaining_evaluations,
            )
            remaining_evaluations = max(
                0, remaining_evaluations - int(row.get("evaluation_count") or 0),
            )
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
                **self._extended_kwargs(row),
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
                **self._extended_kwargs(row),
            )
            if "advertising_rate" in (checked.get("invalid_inputs") or []):
                return self._error("BATCH_PLAN_ADVERTISING_PREVIEW_INVALID")
        cloned["version"] += 1
        selected_ids = {row.get("row_id") for row in selected}
        remaining_evaluations = self._remaining_evaluation_budget(
            cloned, selected_ids,
        )
        for row in selected:
            row.setdefault("inputs", {})["advertising_rate"] = value
            row.setdefault("provenance", {})["advertising_rate"] = "manual_seller_assumption"
            row.setdefault("manual_assumptions", {})["advertising_rate"] = {
                "value": value,
                "provenance": "manual_seller_assumption",
            }
            self._recalculate_row(
                cloned, row, max_evaluations=remaining_evaluations,
            )
            remaining_evaluations = max(
                0, remaining_evaluations - int(row.get("evaluation_count") or 0),
            )
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

    def _recalculate_row(self, batch, row, max_evaluations=None):
        row["missing_inputs"] = []
        row["invalid_inputs"] = []
        row["evaluation_count"] = 0
        row["planning"] = None
        if not self._row_is_fresh(row):
            row.update(status="SOURCE_STALE", reason="SOURCE_CACHE_EXPIRED", planning=None)
            return
        tariff_resolution = self._resolve_frozen_row_price(batch, row)
        if tariff_resolution is not None and tariff_resolution.get("error") is True:
            row.update(status="SOURCE_UNAVAILABLE", reason="TARIFF_SNAPSHOT_INVALID", planning=None)
            return
        scenario = self.scenario_service.calculate(
            row.get("inputs") or {},
            identity=self._scenario_identity(batch, row),
            provenance=row.get("provenance") or {},
            sources=self._scenario_sources(row["snapshot"]),
            **self._extended_kwargs(row),
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
        if max_evaluations is None:
            max_evaluations = self._remaining_evaluation_budget(
                batch, {row.get("row_id")},
            )
        if type(max_evaluations) is not int:
            max_evaluations = 0
        evaluation_limit = min(
            self.TARGET_CALCULATION_LIMIT, max(0, max_evaluations),
        )
        if evaluation_limit <= 0:
            row.update(
                status="BUDGET_EXHAUSTED",
                reason="BATCH_CALCULATION_LIMIT",
                planning=None,
            )
            return
        planning = self.target_planning_service.solve(
            row["inputs"],
            batch["target_margin_percent"],
            identity=self._scenario_identity(batch, row),
            provenance=row.get("provenance") or {},
            sources=self._scenario_sources(row["snapshot"]),
            max_evaluations=evaluation_limit,
            **self._extended_kwargs(row),
            **self._tariff_planning_kwargs(batch, row),
        )
        row["planning"] = planning
        row["evaluation_count"] = int(planning.get("evaluation_count") or 0)
        outcome = planning.get("target") or {}
        if row["evaluation_count"] > evaluation_limit:
            row.update(
                status="BUDGET_EXHAUSTED",
                reason="TARGET_CALCULATION_LIMIT",
            )
            return
        if outcome.get("status") == "SEARCH_BUDGET_EXHAUSTED":
            row.update(
                status="BUDGET_EXHAUSTED",
                reason="TARGET_CALCULATION_LIMIT",
            )
            return
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

    def _remaining_evaluation_budget(self, batch, replacing_row_ids):
        """Reserve the shared budget for rows whose calculations are retained."""
        replacing_row_ids = set(replacing_row_ids or ())
        retained = sum(
            row["evaluation_count"]
            for row in batch.get("rows", [])
            if isinstance(row, dict) and row.get("row_id") not in replacing_row_ids
            and type(row.get("evaluation_count")) is int
            and row["evaluation_count"] > 0
        )
        return max(0, self.BATCH_CALCULATION_LIMIT - retained)

    def _resolve_row_tariff(self, batch, row):
        resolver = getattr(self.tariff_profile_runtime_service, "resolve_for_product", None)
        if not callable(resolver):
            inputs = row.setdefault("inputs", {})
            provenance = row.setdefault("provenance", {})
            manual = (row.get("manual_assumptions") or {}).get("commission_rate")
            exact_price_cents = (
                manual.get("seller_price_cents")
                if isinstance(manual, dict) else None
            )
            origin = str(provenance.get("commission_rate") or "")
            if type(exact_price_cents) is not int or exact_price_cents < 1:
                if origin in {
                    "current_price_point", "ozon_current_fbo_rate",
                    "CURRENT_PRICE_POINT", "CONFIRMED_OFFICIAL_SOURCE",
                }:
                    exact_price_cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
                        (row.get("snapshot", {}).get("suggested_inputs") or {}).get("price")
                    )
            if type(exact_price_cents) is int and exact_price_cents > 0:
                row["legacy_tariff_price_cents"] = exact_price_cents
                row["tariff_scope"] = "EXACT_PRICE_ONLY"
                current_cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
                    inputs.get("price")
                )
                if current_cents != exact_price_cents:
                    inputs["commission_rate"] = None
                    provenance["commission_rate"] = "unknown"
                    row["tariff_resolution_status"] = "UNKNOWN"
                    row["tariff_resolution_reason"] = "COMMISSION_CONFIRMED_AT_DIFFERENT_PRICE"
                else:
                    row["tariff_resolution_status"] = "LEGACY_EXACT_PRICE_ONLY"
                    row["tariff_resolution_reason"] = None
            else:
                row["legacy_tariff_price_cents"] = None
                row["tariff_scope"] = "FIXED_RATE_ASSUMPTION"
            return None
        result = resolver(
            self._scenario_identity(batch, row),
            (row.get("inputs") or {}).get("price"),
            row.get("snapshot"),
            row.get("source_age_seconds_at_load"),
            row.get("source_ttl_seconds"),
            user_id=batch.get("owner_id"),
        )
        if not isinstance(result, dict) or result.get("error") is True:
            return (result.get("code") if isinstance(result, dict) else None) or "TARIFF_SOURCE_UNAVAILABLE"
        frozen = result.get("frozen_tariff_resolution")
        resolution = result.get("resolution") or {}
        if not isinstance(frozen, dict):
            return "TARIFF_SNAPSHOT_INVALID"
        row["frozen_tariff_resolution"] = deepcopy(frozen)
        row["tariff_scope"] = "FROZEN_PROFILE_SET"
        row["tariff_resolution_status"] = resolution.get("status")
        row["tariff_resolution_reason"] = resolution.get("reason")
        manual = (row.get("manual_assumptions") or {}).get("commission_rate")
        current_cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
            (row.get("inputs") or {}).get("price")
        )
        if isinstance(manual, dict) and current_cents is not None:
            if manual.get("seller_price_cents") != current_cents:
                row.setdefault("manual_assumptions", {}).pop("commission_rate", None)
            else:
                override = UnitPriceTariffSnapshotAdapter.with_manual_point_override(
                    frozen, self._scenario_identity(batch, row), current_cents,
                    manual.get("value"),
                    profile_id="manual-row-" + str(row.get("row_id") or "override"),
                )
                if override is None:
                    return "TARIFF_MANUAL_OVERRIDE_INVALID"
                row["frozen_tariff_resolution"] = override
                row["tariff_resolution_status"] = "MANUAL_POINT_OVERRIDE"
                row.setdefault("inputs", {})["commission_rate"] = manual.get("value")
                row.setdefault("provenance", {})["commission_rate"] = "manual_seller_assumption"
                return None
        self._resolve_frozen_row_price(batch, row)
        return None

    def _resolve_frozen_row_price(self, batch, row):
        frozen = row.get("frozen_tariff_resolution")
        if frozen is None:
            exact_cents = row.get("legacy_tariff_price_cents")
            if type(exact_cents) is int and exact_cents > 0:
                cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
                    (row.get("inputs") or {}).get("price")
                )
                if cents != exact_cents:
                    row.setdefault("inputs", {})["commission_rate"] = None
                    row.setdefault("provenance", {})["commission_rate"] = "unknown"
                    row["tariff_resolution_status"] = "UNKNOWN"
                    row["tariff_resolution_reason"] = "COMMISSION_CONFIRMED_AT_DIFFERENT_PRICE"
                else:
                    row["tariff_resolution_status"] = "LEGACY_EXACT_PRICE_ONLY"
                    row["tariff_resolution_reason"] = None
            return None
        cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
            (row.get("inputs") or {}).get("price")
        )
        if cents is None:
            return {"error": True, "code": "SELLER_PRICE_INVALID"}
        resolution = UnitPriceTariffSnapshotAdapter.resolve_frozen(
            frozen, self._scenario_identity(batch, row), cents,
        )
        if resolution.get("error") is True:
            return resolution
        row["tariff_resolution_status"] = resolution.get("status")
        row["tariff_resolution_reason"] = resolution.get("reason")
        if resolution.get("available") is True:
            row.setdefault("inputs", {})["commission_rate"] = resolution.get("commission_rate")
            origin = (resolution.get("selected_profile") or {}).get("origin")
            row.setdefault("provenance", {})["commission_rate"] = {
                "MANUAL_SELLER_ASSUMPTION": "manual_seller_assumption",
                "CURRENT_PRICE_POINT": "current_price_point",
                "CONFIRMED_OFFICIAL_SOURCE": "confirmed_official_source",
            }.get(origin, "unknown")
        else:
            row.setdefault("inputs", {})["commission_rate"] = None
            row.setdefault("provenance", {})["commission_rate"] = "unknown"
        return resolution

    @staticmethod
    def _tariff_planning_kwargs(batch, row):
        frozen = row.get("frozen_tariff_resolution")
        if isinstance(frozen, dict):
            return {
                "frozen_tariff_snapshot": deepcopy(frozen),
                "tariff_resolution_required": True,
            }
        exact_cents = row.get("legacy_tariff_price_cents")
        if type(exact_cents) is int and exact_cents > 0:
            return {
                "tariff_resolution_required": True,
                "exact_price_rate_cents": exact_cents,
            }
        return {}

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
        ordered_fields = [field for field in assumptions if field != "commission_rate"]
        if "commission_rate" in assumptions:
            ordered_fields.append("commission_rate")
        for field in ordered_fields:
            record = assumptions.get(field)
            if field not in self.EDITABLE_FIELDS or not isinstance(record, dict):
                continue
            value = record.get("value")
            if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
                continue
            if field == "commission_rate":
                current_cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
                    (row.get("inputs") or {}).get("price")
                )
                if current_cents is None or record.get("seller_price_cents") != current_cents:
                    row.setdefault("manual_assumptions", {}).pop("commission_rate", None)
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
                **self._extended_kwargs(row),
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
        identity = {
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
        if row.get("extended_scenario") is not None:
            identity.update({
                "owner_id": batch["owner_id"],
                "sale_schema": str(row.get("scheme") or "FBO").upper(),
            })
        return identity

    @staticmethod
    def _extended_kwargs(row):
        extended = row.get("extended_scenario")
        strict = row.get("strict_return_evidence")
        if extended is None and strict is None:
            return {}
        return {
            "extended_scenario": deepcopy(extended),
            "strict_return_evidence": deepcopy(strict),
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
