"""Pure maturity and evidence gates for a stored experiment phase collection."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UnitEconomicsExperimentPhaseMaturityService:
    """Evaluate one immutable collection without reading providers or computing profit."""

    MIN_MATURITY_DAYS = 7
    MIN_MATURITY_UNITS = 30
    _FINANCE_METRICS = (
        "gross_seller_revenue", "discount_points", "finance_net", "acquiring",
        "commission", "logistics", "other_fees",
    )

    @classmethod
    def evaluate(cls, experiment, phase, collection, collection_id, events, now):
        if not isinstance(experiment, dict) or not isinstance(phase, dict):
            return cls._error("EXPERIMENT_PHASE_INPUT_INVALID")
        if not isinstance(collection, dict) or not isinstance(collection_id, str):
            return cls._error("EXPERIMENT_PHASE_COLLECTION_INVALID")
        if not isinstance(events, list) or not isinstance(now, datetime):
            return cls._error("EXPERIMENT_PHASE_EVALUATION_TIME_INVALID")
        if now.tzinfo is None or now.utcoffset() is None:
            return cls._error("EXPERIMENT_PHASE_EVALUATION_TIME_INVALID")

        experiment_config = experiment.get("config")
        config = phase.get("config")
        confirmation = phase.get("confirmation")
        identity = {
            key: experiment.get(key) for key in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            )
        }
        collection_identity = collection.get("identity")
        if (not isinstance(experiment_config, dict) or not isinstance(config, dict)
                or not isinstance(confirmation, dict)
                or collection.get("experiment_id") != experiment.get("experiment_id")
                or collection.get("phase_id") != phase.get("phase_id")
                or collection.get("observation_id") != phase.get("observation_id")
                or collection_identity != identity):
            return cls._error("EXPERIMENT_PHASE_COLLECTION_SCOPE_MISMATCH")

        try:
            timezone_name = config["timezone"]
            zone = ZoneInfo(timezone_name)
            start = date.fromisoformat(config["planned_from_date"])
            end = date.fromisoformat(config["planned_to_date"])
            observed_start = date.fromisoformat(collection["window"]["from_date"])
            observed_end = date.fromisoformat(collection["window"]["to_date"])
            local_today = now.astimezone(zone).date()
            source_as_of = cls._aware(collection.get("collected_at"))
            source_as_of_local_date = (
                source_as_of.astimezone(zone).date() if source_as_of is not None else None
            )
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError, OSError):
            return cls._error("EXPERIMENT_PHASE_WINDOW_INVALID")
        if (source_as_of is None or source_as_of > now
                or start > end or end >= local_today
                or observed_start > observed_end):
            return cls._error("EXPERIMENT_PHASE_WINDOW_INVALID")
        if (collection["window"].get("timezone") != timezone_name
                or observed_start != start or observed_end != end
                or collection.get("seller_price_cents") != config.get("planned_price_cents")
                or confirmation.get("seller_price_cents") != config.get("planned_price_cents")
                or confirmation.get("timezone") != timezone_name
                or confirmation.get("owner_confirmed") is not True
                or confirmation.get("price_history_verified") is not False
                or not isinstance(confirmation.get("first_full_local_day"), str)):
            return cls._error("EXPERIMENT_PHASE_PRICE_OR_WINDOW_MISMATCH")
        try:
            first_full_day = date.fromisoformat(confirmation["first_full_local_day"])
        except ValueError:
            return cls._error("EXPERIMENT_PHASE_CONFIRMATION_INVALID")
        if start < first_full_day:
            return cls._error("EXPERIMENT_PHASE_WINDOW_BEFORE_CONFIRMED_PRICE")

        minimum_days = experiment_config.get("maturity_min_days")
        minimum_units = experiment_config.get("maturity_min_units")
        if (minimum_days != cls.MIN_MATURITY_DAYS
                or minimum_units != cls.MIN_MATURITY_UNITS):
            return cls._error("EXPERIMENT_MATURITY_POLICY_INVALID")
        # Maturity belongs to the evidence snapshot. Evaluating an old snapshot
        # again later must not make late returns/corrections appear to have been
        # included in that snapshot.
        elapsed_completed_days = max(0, (source_as_of_local_date - end).days - 1)
        maturity_ready = elapsed_completed_days >= minimum_days

        source_statuses = collection.get("source_statuses")
        if not isinstance(source_statuses, list):
            return cls._error("EXPERIMENT_PHASE_COLLECTION_INVALID")
        sources = {
            item["source_key"]: item["status"] for item in source_statuses
            if isinstance(item, dict) and isinstance(item.get("source_key"), str)
        }
        metrics = collection.get("metrics")
        if not isinstance(metrics, dict):
            return cls._error("EXPERIMENT_PHASE_COLLECTION_INVALID")
        complete_finance = (
            sources.get("FINANCE") == "COMPLETE"
            and all(isinstance(metrics.get(key), str) for key in cls._FINANCE_METRICS)
        )
        complete_returns = sources.get("RETURNS") == "COMPLETE"
        complete_advertising = (
            sources.get("PERFORMANCE") == "COMPLETE"
            and cls._nonnegative_money(metrics.get("cpc_spend"))
        )
        collection_budget = collection.get("budget")
        budget_complete = (
            collection.get("status") == "COMPLETE"
            and isinstance(collection_budget, dict)
            and collection_budget.get("reason_code") == "NONE"
            and type(collection_budget.get("http_attempts")) is int
            and type(collection_budget.get("http_attempt_limit")) is int
            and collection_budget["http_attempts"] <= collection_budget["http_attempt_limit"]
            and collection_budget.get("elapsed_seconds", 10**9)
            <= collection_budget.get("time_budget_seconds", -1)
        )

        successful = cls._count(metrics.get("successful_sale_units"))
        delivered = cls._count(metrics.get("delivered_units"))
        sample = cls._count(metrics.get("buyout_sample_size"))
        returns_complete = complete_returns
        if not returns_complete:
            sample_status, sample_reason = "UNKNOWN", "RETURN_SOURCE_INCOMPLETE"
            sold_status, sold_reason = "UNKNOWN", "RETURN_SOURCE_INCOMPLETE"
        elif (sample is not None and delivered is not None and sample < delivered
              or successful is not None and delivered is not None
              and successful != delivered):
            sample_status, sample_reason = "FAIL", "UNIT_COUNTS_INCONSISTENT"
            sold_status, sold_reason = "FAIL", "UNIT_COUNTS_INCONSISTENT"
        else:
            if sample is None:
                sample_status, sample_reason = "UNKNOWN", "ELIGIBLE_UNITS_NOT_CONFIRMED"
            elif sample == 0:
                sample_status, sample_reason = "FAIL", "ZERO_ELIGIBLE_UNITS"
            else:
                sample_status = "PASS" if sample >= minimum_units else "FAIL"
                sample_reason = (
                    "MINIMUM_REACHED" if sample >= minimum_units else "SAMPLE_BELOW_MINIMUM"
                )
            if delivered is None or successful is None:
                sold_status, sold_reason = "UNKNOWN", "SOLD_UNITS_NOT_CONFIRMED"
            else:
                sold_status = "PASS" if successful >= minimum_units else "FAIL"
                if successful == 0:
                    sold_reason = "ZERO_SOLD_UNITS"
                elif successful < minimum_units:
                    sold_reason = "SOLD_SAMPLE_BELOW_MINIMUM"
                else:
                    sold_reason = "MINIMUM_REACHED"

        controls = config.get("control_flags")
        control_warnings = not isinstance(controls, dict) or any(
            value in {"CHANGED", "UNKNOWN"}
            for value in controls.values()
        )
        control_warnings = control_warnings or any(
            cls._has_incompatible_control_event(event)
            for event in events
        )
        quality_gates = [
            cls._gate("COLLECTION_COVERAGE", budget_complete, "COMPLETE", "COLLECTION_PARTIAL_OR_BUDGET_LIMIT"),
            cls._gate("FINANCE_COVERAGE", complete_finance, "COMPLETE", "FINANCE_PARTIAL_OR_UNAVAILABLE"),
            cls._gate("RETURNS_COVERAGE", complete_returns, "COMPLETE", "RETURNS_PARTIAL_OR_UNAVAILABLE"),
            cls._gate("ADVERTISING_COVERAGE", complete_advertising, "COMPLETE", "CPC_NOT_CONFIRMED"),
            cls._gate("MATURITY_DELAY", maturity_ready, "MATURITY_REACHED", "MATURITY_PENDING"),
            {
                "gate": "PRICE_CONFIRMATION", "status": "PASS",
                "reason_code": "OWNER_CONFIRMED",
            },
            {
                "gate": "WINDOW_COMPATIBILITY", "status": "PASS",
                "reason_code": "EXACT_LOCAL_WINDOW_AND_TIMEZONE",
            },
            {"gate": "ELIGIBLE_UNIT_SAMPLE", "status": sample_status, "reason_code": sample_reason},
            {"gate": "SOLD_UNIT_DENOMINATOR", "status": sold_status, "reason_code": sold_reason},
            {
                "gate": "PRICE_HISTORY", "status": "WARNING",
                "reason_code": "OWNER_DECLARED_PRICE_ONLY",
            },
            {
                "gate": "PRICE_STABILITY", "status": "WARNING",
                "reason_code": "MIXED_PRICES_NOT_VERIFIABLE_FROM_AVAILABLE_SOURCE",
            },
            {
                "gate": "SOURCE_DATE_BASES", "status": "WARNING",
                "reason_code": "SOURCE_DATE_BASES_DIFFER",
            },
            {
                "gate": "CONTROL_CONDITIONS",
                "status": "WARNING" if control_warnings else "PASS",
                "reason_code": (
                    "OWNER_REPORTED_CONDITIONS_CHANGED_OR_UNKNOWN"
                    if control_warnings else "UNCHANGED_OR_NOT_APPLICABLE"
                ),
            },
            {
                "gate": "OBSERVED_COGS", "status": "UNKNOWN",
                "reason_code": "SAVED_COST_IS_NOT_OBSERVED_COGS",
            },
        ]
        quality_gates.sort(key=lambda gate: gate["gate"])
        required_pass = {
            "COLLECTION_COVERAGE", "FINANCE_COVERAGE", "RETURNS_COVERAGE",
            "ADVERTISING_COVERAGE", "MATURITY_DELAY", "ELIGIBLE_UNIT_SAMPLE",
            "SOLD_UNIT_DENOMINATOR", "PRICE_CONFIRMATION", "WINDOW_COMPATIBILITY",
        }
        gates_by_name = {gate["gate"]: gate for gate in quality_gates}
        ready = all(gates_by_name[name]["status"] == "PASS" for name in required_pass)
        waiting_only = (
            not ready
            and all(
                gate["status"] == "PASS"
                or gate["gate"] in {"MATURITY_DELAY", "ELIGIBLE_UNIT_SAMPLE"}
                and gate["status"] in {"FAIL", "UNKNOWN"}
                or gate["gate"] == "SOLD_UNIT_DENOMINATOR"
                and gate["reason_code"] == "SOLD_SAMPLE_BELOW_MINIMUM"
                and gate["status"] == "FAIL"
                for gate in quality_gates
                if gate["gate"] in required_pass
            )
        )
        status = (
            "READY" if ready
            else "WAITING_FOR_DATA" if waiting_only
            else "INSUFFICIENT_DATA"
        )
        outcome = "CONTINUE_COLLECTING" if ready or waiting_only else "FIX_DATA_OR_CONDITIONS"
        quantity_basis = (
            "SOLD_UNITS_WINDOW" if returns_complete and successful is not None and successful > 0
            else None
        )
        limitations = set(collection.get("limitations", []))
        limitations.update({
            "OWNER_PRICE_IS_NOT_API_PRICE_HISTORY",
            "MIXED_PRICES_CANNOT_BE_VERIFIED_FROM_AVAILABLE_SOURCE",
            "SOURCE_DATE_BASES_ARE_NOT_IDENTICAL",
            "NO_STATISTICAL_CONFIDENCE_FROM_MINIMUM_SAMPLE",
            "SAVED_COST_IS_NOT_OBSERVED_COGS",
        })
        if control_warnings:
            limitations.add("OWNER_REPORTED_PHASE_CONDITIONS_CHANGED_OR_UNKNOWN")
        if not ready:
            limitations.add("PHASE_NOT_READY_FOR_CROSS_PHASE_COMPARISON")
        refs = sorted({
            experiment_config["source_references"]["expense_snapshot_id"],
            config["expense_snapshot_id"], collection_id,
        })
        return {
            "error": False,
            "status": status,
            "outcome": outcome,
            "payload": {
                "schema_version": 1, "status": status,
                "source_as_of": collection["collected_at"],
                "snapshot_refs": refs,
                "baseline_profit_per_unit_rub": None,
                "candidate_profit_per_unit_rub": None,
                "delta_profit_per_unit_rub": None,
                "quantity_basis": quantity_basis,
                "window": {
                    "from_date": start.isoformat(), "to_date": end.isoformat(),
                    "timezone": timezone_name,
                },
                "quality_gates": quality_gates,
                "limitations": sorted(limitations),
                "outcome": outcome,
            },
        }

    @staticmethod
    def _gate(name, passed, pass_reason, fail_reason):
        return {
            "gate": name, "status": "PASS" if passed else "FAIL",
            "reason_code": pass_reason if passed else fail_reason,
        }

    @staticmethod
    def _has_incompatible_control_event(event):
        if not isinstance(event, dict):
            return False
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return False
        compatibility = payload.get("compatibility")
        return (
            isinstance(compatibility, dict)
            and compatibility.get("status") == "INCOMPATIBLE"
        )

    @staticmethod
    def _count(value):
        return value if type(value) is int and 0 <= value <= 1_000_000_000 else None

    @staticmethod
    def _nonnegative_money(value):
        if not isinstance(value, str):
            return False
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            return False
        return amount.is_finite() and amount >= 0

    @staticmethod
    def _aware(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True}
