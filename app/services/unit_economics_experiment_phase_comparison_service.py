"""Compare mature, compatible price-experiment phase evidence without source I/O."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)
from services.tax_service import TaxService
from services.unit_economics_experiment_phase_maturity_service import (
    UnitEconomicsExperimentPhaseMaturityService,
)


class UnitEconomicsExperimentPhaseComparisonService:
    """Calculate and persist a bounded model comparison from immutable evidence."""

    MAX_PHASES = 10
    MAX_RESULTS = 20
    RESULT_PAGE_SIZE = 10
    MAX_SOURCE_AS_OF_LAG_DAYS = 1
    _CENT = Decimal("0.01")

    def __init__(self, repository, tax_service=None, clock=None):
        self.repository = repository
        self.tax_service = tax_service or TaxService()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def compare(
        self, experiment_id, baseline_phase_id, candidate_phase_id, *,
        expected_state_revision, expected_candidate_phase_state_revision,
        expected_candidate_result_revision, idempotency_key, owner_id, store_id,
    ):
        if (not isinstance(owner_id, str) or not owner_id.strip()
                or not isinstance(store_id, str) or not store_id.strip()
                or baseline_phase_id == candidate_phase_id
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_candidate_phase_state_revision) is not int
                or expected_candidate_phase_state_revision < 1
                or type(expected_candidate_result_revision) is not int
                or expected_candidate_result_revision < 0):
            return self._error("EXPERIMENT_PHASE_COMPARISON_INPUT_INVALID")
        loaded = self.repository.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if loaded.get("error"):
            return loaded
        experiment = loaded.get("experiment")
        if (not isinstance(experiment, dict)
                or experiment.get("state_revision") != expected_state_revision
                or experiment.get("status") in {"CANCELLED", "COMPLETED", "ARCHIVED"}):
            return self._error("EXPERIMENT_PHASE_COMPARISON_STALE_EXPERIMENT")
        listed = self.repository.list_price_experiment_phases(
            experiment_id, limit=self.MAX_PHASES, owner_id=owner_id, store_id=store_id,
        )
        if listed.get("error"):
            return listed
        phases = {phase.get("phase_id"): phase for phase in listed.get("items", [])}
        baseline = phases.get(baseline_phase_id)
        candidate = phases.get(candidate_phase_id)
        if baseline is None or candidate is None:
            return self._error("EXPERIMENT_PHASE_NOT_FOUND")
        if (baseline.get("kind") != "BASELINE" or candidate.get("kind") != "CANDIDATE"
                or baseline.get("status") not in {"ACTIVE", "PAUSED", "FINISHED"}
                or candidate.get("status") not in {"ACTIVE", "PAUSED", "FINISHED"}
                or candidate.get("state_revision") != expected_candidate_phase_state_revision
                or candidate.get("result_revision") not in {
                    expected_candidate_result_revision,
                    expected_candidate_result_revision + 1,
                }):
            return self._error("EXPERIMENT_PHASE_COMPARISON_STALE_PHASE")

        baseline_collection = self._latest_collection(experiment_id, baseline_phase_id, owner_id, store_id)
        candidate_collection = self._latest_collection(experiment_id, candidate_phase_id, owner_id, store_id)
        if baseline_collection.get("error") or candidate_collection.get("error"):
            return baseline_collection if baseline_collection.get("error") else candidate_collection
        if baseline_collection.get("item") is None or candidate_collection.get("item") is None:
            return self._error("EXPERIMENT_PHASE_COLLECTION_NOT_FOUND")
        baseline_item, candidate_item = baseline_collection["item"], candidate_collection["item"]
        baseline_events = self._phase_events(experiment_id, baseline_phase_id, owner_id, store_id)
        candidate_events = self._phase_events(experiment_id, candidate_phase_id, owner_id, store_id)
        if baseline_events.get("error") or candidate_events.get("error"):
            return baseline_events if baseline_events.get("error") else candidate_events
        baseline_ready = self._latest_ready_result(
            experiment_id, baseline_phase_id, baseline_item["collection_id"], owner_id, store_id,
        )
        candidate_ready = self._latest_ready_result(
            experiment_id, candidate_phase_id, candidate_item["collection_id"], owner_id, store_id,
        )
        if baseline_ready.get("error") or candidate_ready.get("error"):
            return baseline_ready if baseline_ready.get("error") else candidate_ready

        frozen = self.repository.get_price_experiment_frozen_snapshot(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if frozen.get("error"):
            return frozen
        now = self.clock()
        baseline_ready = self._fresh_readiness(
            experiment, baseline, baseline_item, baseline_events, baseline_ready, now,
        )
        candidate_ready = self._fresh_readiness(
            experiment, candidate, candidate_item, candidate_events, candidate_ready, now,
        )
        evaluated = self._evaluate(
            experiment, baseline, candidate, baseline_item, candidate_item,
            baseline_ready.get("item"), candidate_ready.get("item"),
            frozen.get("frozen_inputs"), now,
            baseline_events["latest_revision"], candidate_events["latest_revision"],
            self.tax_service,
        )
        if evaluated.get("error"):
            return evaluated

        refs = sorted({
            experiment["config"]["source_references"]["expense_snapshot_id"],
            baseline["config"]["expense_snapshot_id"],
            candidate["config"]["expense_snapshot_id"],
            baseline_item["collection_id"], candidate_item["collection_id"],
        })
        payload = {
            "schema_version": PlanningUnitEconomicsExperimentAdapter.RESULT_SCHEMA_VERSION,
            "status": evaluated["status"],
            "source_as_of": evaluated["source_as_of"],
            "snapshot_refs": refs,
            "baseline_profit_per_unit_rub": evaluated["baseline_profit_per_unit_rub"],
            "candidate_profit_per_unit_rub": evaluated["candidate_profit_per_unit_rub"],
            "delta_profit_per_unit_rub": evaluated["delta_profit_per_unit_rub"],
            "quantity_basis": evaluated["quantity_basis"],
            "window": {
                key: candidate_item["payload"]["window"][key]
                for key in ("from_date", "to_date", "timezone")
            } if isinstance(candidate_item["payload"].get("window"), dict)
            and all(key in candidate_item["payload"]["window"]
                    for key in ("from_date", "to_date", "timezone")) else None,
            "quality_gates": evaluated["quality_gates"],
            "limitations": evaluated["limitations"],
            "outcome": evaluated["outcome"],
            "comparison": evaluated["comparison"],
        }
        guard = {
            "baseline_phase_id": baseline_phase_id,
            "baseline_state_revision": baseline["state_revision"],
            "baseline_result_revision": baseline["result_revision"],
            "baseline_collection_id": baseline_item["collection_id"],
            "candidate_collection_id": candidate_item["collection_id"],
            "baseline_control_event_revision": baseline_events["latest_revision"],
            "candidate_control_event_revision": candidate_events["latest_revision"],
        }
        saved = self.repository.append_price_experiment_result(
            experiment_id, candidate_phase_id, payload,
            expected_state_revision=expected_state_revision,
            expected_phase_state_revision=expected_candidate_phase_state_revision,
            expected_result_revision=expected_candidate_result_revision,
            idempotency_key=idempotency_key, owner_id=owner_id, store_id=store_id,
            comparison_guard=guard,
        )
        if saved.get("error"):
            return saved
        return {
            **saved, "status": evaluated["status"], "outcome": evaluated["outcome"],
            "baseline_profit_per_unit_rub": evaluated["baseline_profit_per_unit_rub"],
            "candidate_profit_per_unit_rub": evaluated["candidate_profit_per_unit_rub"],
            "delta_profit_per_unit_rub": evaluated["delta_profit_per_unit_rub"],
            "quality_gates": evaluated["quality_gates"],
            "limitations": evaluated["limitations"],
            "read_only": True, "source_io": False,
        }

    @classmethod
    def _evaluate(
        cls, experiment, baseline, candidate, baseline_item, candidate_item,
        baseline_ready, candidate_ready, frozen, now,
        baseline_event_revision=0, candidate_event_revision=0, tax_service=None,
    ):
        reasons = []
        limitations = {
            "OBSERVED_WINDOW_MODEL_NOT_CAUSAL_PRICE_EFFECT",
            "SAVED_COST_IS_NOT_OBSERVED_COGS",
            "FINANCE_NET_ALREADY_INCLUDES_SELLER_FEES_AND_ADVERTISING",
            "PERFORMANCE_CPC_IS_RECONCILIATION_ONLY",
            "NO_STATISTICAL_CONFIDENCE_FROM_AGGREGATED_COUNTS",
            "OWNER_PRICE_IS_NOT_API_PRICE_HISTORY",
            "MIXED_PRICES_CANNOT_BE_VERIFIED_FROM_AVAILABLE_SOURCE",
            "SOURCE_DATE_BASES_ARE_NOT_IDENTICAL",
        }
        if experiment.get("config", {}).get("calculation_mode") != "WINDOW_COST_ALLOCATION":
            reasons.append("STRICT_RETAINED_COHORT_DISPOSITION_UNAVAILABLE")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            return cls._error("EXPERIMENT_PHASE_COMPARISON_CLOCK_INVALID")
        baseline_payload = baseline_item.get("payload", {})
        candidate_payload = candidate_item.get("payload", {})
        for source in (baseline_payload, candidate_payload):
            source_limitations = source.get("limitations", [])
            if isinstance(source_limitations, list):
                limitations.update(
                    code.upper()[:64] for code in source_limitations
                    if isinstance(code, str) and code.isascii()
                    and code.replace("_", "").isalnum()
                )
        compatible, reason = cls._compatible_windows(
            baseline_payload.get("window"), candidate_payload.get("window"),
            baseline_payload.get("collected_at"), candidate_payload.get("collected_at"), now,
        )
        if not compatible:
            reasons.append(reason)
        if baseline["config"].get("expense_snapshot_id") != candidate["config"].get("expense_snapshot_id"):
            reasons.append("COST_OR_EXPENSE_SNAPSHOT_CHANGED")
        if baseline["config"].get("control_flags") != candidate["config"].get("control_flags"):
            reasons.append("PHASE_CONTROL_FLAGS_DIFFER")
        if (not cls._all_controls_stable(baseline.get("config", {}).get("control_flags"))
                or not cls._all_controls_stable(candidate.get("config", {}).get("control_flags"))):
            reasons.append("PHASE_CONTROL_FLAGS_CHANGED_OR_UNKNOWN")
        for ready in (baseline_ready, candidate_ready):
            if ready is None or ready["payload"].get("status") != "READY":
                reasons.append("PHASE_NOT_MATURE_AND_READY")
                break
            ready_gates = {item["gate"]: item for item in ready["payload"].get("quality_gates", [])}
            if ready_gates.get("CONTROL_CONDITIONS", {}).get("status") != "PASS":
                reasons.append("PHASE_CONTROL_CONDITIONS_NOT_CONFIRMED")
                break
            if ready_gates.get("SOLD_UNIT_DENOMINATOR", {}).get("status") != "PASS":
                reasons.append("SOLD_UNIT_DENOMINATOR_UNCONFIRMED")
                break
        if frozen is None:
            reasons.append("FROZEN_PLAN_UNAVAILABLE")
        plan_inputs = cls._frozen_plan_inputs(frozen, experiment)
        if plan_inputs is None:
            reasons.append("FROZEN_COST_OR_TAX_INPUTS_UNAVAILABLE")
        if not reasons:
            baseline_calc = cls._calculate_phase(
                baseline_payload, baseline, plan_inputs, tax_service,
            )
            candidate_calc = cls._calculate_phase(
                candidate_payload, candidate, plan_inputs, tax_service,
            )
            if baseline_calc is None or candidate_calc is None:
                reasons.append("PHASE_FINANCIAL_OR_UNIT_DATA_INCOMPLETE")
            elif baseline_calc["returned_units"] > 0 or candidate_calc["returned_units"] > 0:
                reasons.append("RETURNED_UNIT_DISPOSITION_UNKNOWN")
                limitations.add("RETURNED_UNIT_INVENTORY_DISPOSITION_NOT_CAPTURED")
            elif baseline_calc["seller_price_cents"] == candidate_calc["seller_price_cents"]:
                reasons.append("BASELINE_AND_CANDIDATE_PRICE_ARE_EQUAL")
        else:
            baseline_calc = candidate_calc = None

        if reasons:
            outcome = cls._blocked_outcome(reasons, baseline_ready, candidate_ready)
            status = {
                "CONTINUE_COLLECTING": "WAITING_FOR_DATA",
                "FIX_DATA_OR_CONDITIONS": "INSUFFICIENT_DATA",
                "INCOMPARABLE": "INCOMPARABLE",
            }[outcome]
            gates = [
                {"gate": f"COMPARABILITY_{index:02d}", "status": "FAIL", "reason_code": item}
                for index, item in enumerate(reasons, start=1)
            ]
            return {
                "error": False, "status": status, "outcome": outcome,
                "source_as_of": cls._latest_source_as_of(baseline_payload, candidate_payload),
                "baseline_profit_per_unit_rub": None,
                "candidate_profit_per_unit_rub": None,
                "delta_profit_per_unit_rub": None, "quantity_basis": None,
                "quality_gates": gates, "limitations": sorted(limitations)[:32],
                "comparison": None,
            }

        baseline_profit = Decimal(baseline_calc["profit_per_unit_rub"])
        candidate_profit = Decimal(candidate_calc["profit_per_unit_rub"])
        delta = (candidate_profit - baseline_profit).quantize(cls._CENT, rounding=ROUND_HALF_UP)
        threshold = Decimal(experiment["config"]["decision_threshold_rub"])
        if delta == 0 or abs(delta) < threshold:
            outcome, status = "NO_CLEAR_DIFFERENCE", "NO_CLEAR_DIFFERENCE"
        elif delta > 0:
            outcome, status = "CANDIDATE_BETTER_IN_MODEL", "BETTER"
        else:
            outcome, status = "BASELINE_BETTER_IN_MODEL", "WORSE"
        relative = None
        if baseline_profit > 0:
            relative = format((delta / baseline_profit * Decimal("100")).quantize(
                cls._CENT, rounding=ROUND_HALF_UP,
            ), ".2f")
        comparison = {
            "schema_version": 1,
            "decision_threshold_rub": format(threshold, ".2f"),
            "profit_basis": "FINANCE_NET_MINUS_SAVED_COGS_AND_TAX",
            "relative_delta_percent": relative,
            "baseline_collection_hash": baseline_item["collection_id"],
            "candidate_collection_hash": candidate_item["collection_id"],
            "baseline_readiness_revision": baseline_ready["result_revision"],
            "candidate_readiness_revision": candidate_ready["result_revision"],
            "baseline_phase_state_revision": baseline["state_revision"],
            "candidate_phase_state_revision": candidate["state_revision"],
            "baseline_control_event_revision": baseline_event_revision,
            "candidate_control_event_revision": candidate_event_revision,
            "baseline": baseline_calc["payload"], "candidate": candidate_calc["payload"],
        }
        return {
            "error": False, "status": status, "outcome": outcome,
            "source_as_of": cls._latest_source_as_of(baseline_payload, candidate_payload),
            "baseline_profit_per_unit_rub": format(baseline_profit, ".2f"),
            "candidate_profit_per_unit_rub": format(candidate_profit, ".2f"),
            "delta_profit_per_unit_rub": format(delta, ".2f"),
            "quantity_basis": "SOLD_UNITS_WINDOW",
            "quality_gates": [{"gate": "CROSS_PHASE_COMPATIBILITY", "status": "PASS",
                               "reason_code": "COMPATIBLE_MATURE_PHASES"}],
            "limitations": sorted(limitations)[:32], "comparison": comparison,
        }

    @classmethod
    def _calculate_phase(cls, collection, phase, plan_inputs, tax_service=None):
        metrics = collection.get("metrics")
        statuses = {item.get("source_key"): item.get("status")
                    for item in collection.get("source_statuses", []) if isinstance(item, dict)}
        if (collection.get("status") != "COMPLETE"
                or not all(statuses.get(key) == "COMPLETE" for key in ("FINANCE", "RETURNS", "PERFORMANCE"))
                or not isinstance(metrics, dict)):
            return None
        units = metrics.get("successful_sale_units")
        if type(units) is not int or units < 30:
            return None
        money = {}
        for key in ("finance_net", "gross_seller_revenue", "discount_points", "acquiring",
                    "commission", "logistics", "other_fees", "cpc_spend"):
            amount = cls._decimal(metrics.get(key))
            if amount is None or (
                key in {"gross_seller_revenue", "discount_points", "cpc_spend"} and amount < 0
            ):
                return None
            money[key] = amount
        returned = metrics.get("returned_units")
        if type(returned) is not int or returned < 0 or returned > units:
            return None
        cost_per_unit = plan_inputs["cost"]
        cogs = (cost_per_unit * units).quantize(cls._CENT, rounding=ROUND_HALF_UP)
        profit_before_tax = (money["finance_net"] - cogs).quantize(cls._CENT, rounding=ROUND_HALF_UP)
        tax = cls._tax_service_calculate(plan_inputs, money, profit_before_tax, tax_service)
        if tax is None:
            return None
        profit_total = (profit_before_tax - tax).quantize(cls._CENT, rounding=ROUND_HALF_UP)
        per_unit = (profit_total / units).quantize(cls._CENT, rounding=ROUND_HALF_UP)
        parsed_as_of = cls._timestamp(collection.get("collected_at"))
        window = collection.get("window")
        if parsed_as_of is None or not isinstance(window, dict):
            return None
        payload = {
            "window": {key: window[key] for key in ("from_date", "to_date", "timezone")},
            "source_as_of": parsed_as_of.isoformat().replace("+00:00", "Z"),
            "seller_price_cents": phase["config"]["planned_price_cents"],
            "quantity_basis": "SOLD_UNITS_WINDOW", "sold_units": units,
            "tax_mode": plan_inputs["tax_mode"],
            "tax_rate_percent": plan_inputs["tax_rate_percent"],
            "minimum_tax_rate_percent": plan_inputs["minimum_tax_rate_percent"],
            "gross_seller_revenue_rub": cls._format_money(money["gross_seller_revenue"]),
            "discount_points_rub": cls._format_money(money["discount_points"]),
            "finance_net_rub": cls._format_money(money["finance_net"]),
            "acquiring_rub": cls._format_money(money["acquiring"]),
            "commission_rub": cls._format_money(money["commission"]),
            "logistics_rub": cls._format_money(money["logistics"]),
            "other_fees_rub": cls._format_money(money["other_fees"]),
            "performance_cpc_reconciliation_rub": cls._format_money(money["cpc_spend"]),
            "saved_cogs_per_unit_rub": cls._format_money(cost_per_unit),
            "saved_cogs_total_rub": cls._format_money(cogs),
            "tax_rub": cls._format_money(tax),
            "profit_before_tax_rub": cls._format_money(profit_before_tax),
            "profit_total_rub": cls._format_money(profit_total),
            "profit_per_unit_rub": cls._format_money(per_unit),
        }
        return {"payload": payload, "profit_per_unit_rub": cls._format_money(per_unit),
                "returned_units": returned, "seller_price_cents": phase["config"]["planned_price_cents"]}

    @classmethod
    def _tax_service_calculate(cls, plan_inputs, money, profit_before_tax, tax_service=None):
        mode = plan_inputs["tax_mode"]
        try:
            result = (tax_service or TaxService()).calculate(
                mode, float(money["gross_seller_revenue"]), float(profit_before_tax),
                tax_rate=(float(plan_inputs["tax_rate_percent"])
                          if plan_inputs["tax_rate_percent"] is not None else None),
                minimum_tax_rate=(float(plan_inputs["minimum_tax_rate_percent"])
                                  if plan_inputs["minimum_tax_rate_percent"] is not None else None),
                discount_points=float(money["discount_points"]),
            )
        except (TypeError, ValueError, OverflowError):
            return None
        if result.get("error") or result.get("configured") is not True:
            return None
        return cls._decimal(result.get("tax_amount"))

    @classmethod
    def _frozen_plan_inputs(cls, frozen, experiment):
        if (not isinstance(frozen, dict) or not isinstance(experiment, dict)
                or any(not isinstance(experiment.get(key), str) or not experiment[key]
                       for key in ("store_id", "offer_id", "sku", "sale_schema"))):
            return None
        plan = frozen.get("plan")
        payload = plan.get("payload") if isinstance(plan, dict) else None
        if not isinstance(payload, dict) or type(payload.get("calculation_version")) is not int:
            return None
        item_rows = payload.get("items")
        if not isinstance(item_rows, list):
            return None
        matches = [row for row in item_rows if isinstance(row, dict)
                   and isinstance(row.get("identity"), dict)
                   and isinstance(row.get("inputs"), dict)
                   and all(row["identity"].get(key) == value for key, value in (
                       ("store_id", experiment["store_id"]), ("offer_id", experiment["offer_id"]),
                       ("sku", experiment["sku"]), ("scheme", experiment["sale_schema"]),
                   ))]
        if len(matches) != 1:
            return None
        inputs = matches[0]["inputs"]
        cost = cls._decimal(inputs.get("cost"))
        mode = inputs.get("tax_mode")
        if cost is None or cost < 0 or mode not in TaxService.SUPPORTED_MODES:
            return None
        rate = cls._decimal(inputs.get("tax_rate")) if inputs.get("tax_rate") is not None else None
        minimum = cls._decimal(inputs.get("minimum_tax_rate")) if inputs.get("minimum_tax_rate") is not None else None
        if (mode == "USN_INCOME" and rate is None
                or mode == "USN_INCOME_MINUS_EXPENSES" and (rate is None or minimum is None)
                or any(value is not None and not Decimal("0") <= value <= Decimal("100")
                       for value in (rate, minimum))):
            return None
        return {
            "cost": cost.quantize(cls._CENT, rounding=ROUND_HALF_UP),
            "tax_mode": mode,
            "tax_rate_percent": cls._format_money(rate) if rate is not None else None,
            "minimum_tax_rate_percent": cls._format_money(minimum) if minimum is not None else None,
            "calculation_version": payload["calculation_version"],
        }

    @classmethod
    def _compatible_windows(cls, baseline, candidate, baseline_as_of, candidate_as_of, now):
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            return False, "WINDOW_DATA_MISSING"
        try:
            start_a, end_a = date.fromisoformat(baseline["from_date"]), date.fromisoformat(baseline["to_date"])
            start_b, end_b = date.fromisoformat(candidate["from_date"]), date.fromisoformat(candidate["to_date"])
            zone_a, zone_b = ZoneInfo(baseline["timezone"]), ZoneInfo(candidate["timezone"])
            as_of_a, as_of_b = cls._timestamp(baseline_as_of), cls._timestamp(candidate_as_of)
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError, OSError):
            return False, "WINDOW_DATA_INVALID"
        if start_a > end_a or start_b > end_b or baseline["timezone"] != candidate["timezone"]:
            return False, "TIMEZONE_OR_WINDOW_INVALID"
        if end_a >= start_b:
            return False, "PHASE_WINDOWS_OVERLAP_OR_REVERSED"
        days_a, days_b = (end_a - start_a).days + 1, (end_b - start_b).days + 1
        if days_a != days_b or cls._weekday_counts(start_a, end_a) != cls._weekday_counts(start_b, end_b):
            return False, "WINDOW_DURATION_OR_WEEKDAY_COVERAGE_DIFFERS"
        if as_of_a is None or as_of_b is None or as_of_a > now or as_of_b > now:
            return False, "SOURCE_AS_OF_INVALID"
        lag_a = (as_of_a.astimezone(zone_a).date() - end_a).days
        lag_b = (as_of_b.astimezone(zone_b).date() - end_b).days
        if lag_a < 0 or lag_b < 0 or abs(lag_a - lag_b) > cls.MAX_SOURCE_AS_OF_LAG_DAYS:
            return False, "SOURCE_AS_OF_MATURITY_DIFFERS"
        return True, None

    @staticmethod
    def _weekday_counts(start, end):
        counts = [0] * 7
        current = start
        while current <= end:
            counts[current.weekday()] += 1
            current = date.fromordinal(current.toordinal() + 1)
        return tuple(counts)

    @staticmethod
    def _all_controls_stable(flags):
        return isinstance(flags, dict) and bool(flags) and all(
            value in {"UNCHANGED", "NOT_APPLICABLE"} for value in flags.values()
        )

    @classmethod
    def _blocked_outcome(cls, reasons, baseline_ready, candidate_ready):
        incomparable = {
            "STRICT_RETAINED_COHORT_DISPOSITION_UNAVAILABLE", "COST_OR_EXPENSE_SNAPSHOT_CHANGED",
            "PHASE_CONTROL_FLAGS_DIFFER", "PHASE_CONTROL_FLAGS_CHANGED_OR_UNKNOWN",
            "PHASE_CONTROL_CONDITIONS_NOT_CONFIRMED", "SOURCE_AS_OF_MATURITY_DIFFERS",
            "PHASE_WINDOWS_OVERLAP_OR_REVERSED", "WINDOW_DURATION_OR_WEEKDAY_COVERAGE_DIFFERS",
            "TIMEZONE_OR_WINDOW_INVALID", "RETURNED_UNIT_DISPOSITION_UNKNOWN",
            "BASELINE_AND_CANDIDATE_PRICE_ARE_EQUAL",
        }
        if any(reason in incomparable for reason in reasons):
            return "INCOMPARABLE"
        if any(reason in {
            "FROZEN_PLAN_UNAVAILABLE", "FROZEN_COST_OR_TAX_INPUTS_UNAVAILABLE",
            "PHASE_FINANCIAL_OR_UNIT_DATA_INCOMPLETE",
        } for reason in reasons):
            return "FIX_DATA_OR_CONDITIONS"
        readiness = [item.get("payload", {}).get("status") for item in (baseline_ready, candidate_ready)
                     if item is not None]
        return "CONTINUE_COLLECTING" if not readiness or "WAITING_FOR_DATA" in readiness else "FIX_DATA_OR_CONDITIONS"

    def _latest_collection(self, experiment_id, phase_id, owner_id, store_id):
        listed = self.repository.list_price_experiment_phase_collections(
            experiment_id, phase_id, limit=1, offset=0, owner_id=owner_id, store_id=store_id,
        )
        if listed.get("error"):
            return listed
        return {"error": False, "item": listed["items"][0] if listed.get("items") else None}

    def _phase_events(self, experiment_id, phase_id, owner_id, store_id):
        listed = self.repository.list_price_experiment_events(
            experiment_id, phase_id=phase_id, limit=100, offset=0,
            owner_id=owner_id, store_id=store_id,
        )
        if listed.get("error"):
            return listed
        if listed.get("has_more") is True:
            return self._error("EXPERIMENT_PHASE_EVENT_HISTORY_INCOMPLETE")
        items = listed.get("items", [])
        revisions = [item.get("event_revision") for item in items
                     if type(item.get("event_revision")) is int]
        return {
            "error": False, "items": items,
            "latest_revision": max(revisions, default=0),
        }

    @staticmethod
    def _fresh_readiness(experiment, phase, collection_item, events, stored, now):
        stored_item = stored.get("item")
        if stored_item is None:
            return {"error": False, "item": None}
        evaluated = UnitEconomicsExperimentPhaseMaturityService.evaluate(
            experiment, phase, collection_item["payload"], collection_item["collection_id"],
            events["items"], now,
        )
        if evaluated.get("error"):
            return {"error": False, "item": {
                "result_revision": stored_item["result_revision"],
                "payload": {"status": "INSUFFICIENT_DATA", "quality_gates": []},
            }}
        return {
            "error": False, "item": {
                "result_revision": stored_item["result_revision"],
                "payload": evaluated["payload"],
            },
        }

    def _latest_ready_result(self, experiment_id, phase_id, collection_id, owner_id, store_id):
        offset, found, count = 0, None, 0
        while count < self.MAX_RESULTS:
            listed = self.repository.list_price_experiment_results(
                experiment_id, phase_id, limit=min(self.RESULT_PAGE_SIZE, self.MAX_RESULTS - count),
                offset=offset, owner_id=owner_id, store_id=store_id,
            )
            if listed.get("error"):
                return listed
            rows = listed.get("items", [])
            for item in rows:
                payload = item.get("payload", {})
                if (payload.get("status") == "READY" and payload.get("schema_version") == 1
                        and collection_id in payload.get("snapshot_refs", [])):
                    if found is None or item["result_revision"] > found["result_revision"]:
                        found = item
            count += len(rows)
            if listed.get("has_more") is not True:
                break
            offset = listed.get("next_offset")
        else:
            return self._error("EXPERIMENT_PHASE_RESULT_HISTORY_INCOMPLETE")
        return {"error": False, "item": found}

    @staticmethod
    def _latest_source_as_of(baseline, candidate):
        parsed = [UnitEconomicsExperimentPhaseComparisonService._timestamp(
            item.get("collected_at"),
        ) for item in (baseline, candidate)]
        parsed = [value for value in parsed if value is not None]
        return max(parsed).astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if parsed else None

    @staticmethod
    def _timestamp(value):
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

    @staticmethod
    def _decimal(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result.is_finite() else None

    @classmethod
    def _format_money(cls, amount):
        return format(Decimal(amount).quantize(cls._CENT, rounding=ROUND_HALF_UP), ".2f")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "source_io": False}
