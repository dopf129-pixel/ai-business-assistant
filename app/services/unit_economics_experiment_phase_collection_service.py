"""Collect and atomically freeze completed price-experiment phase evidence."""

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)


class UnitEconomicsExperimentPhaseCollectionService:
    """Collect one exact completed phase window; never runs a retry loop."""

    TIME_BUDGET_SECONDS = 120
    HTTP_ATTEMPT_BUDGET = 128
    _MONEY_KEYS = (
        "gross_seller_revenue", "discount_points", "finance_net", "acquiring",
        "commission", "logistics", "other_fees", "cpc_spend",
    )
    _COUNT_KEYS = (
        "successful_sale_units", "ordered_units", "delivered_units",
        "cancelled_units", "returned_units", "buyout_sample_size",
    )
    _SAFE_SOURCE_REASONS = frozenset({
        "NONE",
        "FINANCE_READ_SESSION_UNAVAILABLE", "FINANCE_RESPONSE_INVALID",
        "FINANCE_COMPONENTS_INCOMPLETE",
        "RETURNS_BUYOUT_SOURCE_NOT_CONFIGURED", "RETURNS_BUYOUT_SOURCE_UNAVAILABLE",
        "RETURNS_BUYOUT_ANALYSIS_INVALID", "FBO_BUYOUT_SAMPLE_NOT_FINAL_OR_CLASSIFIED",
        "PERFORMANCE_CREDENTIALS_NOT_CONFIGURED", "PERFORMANCE_EVIDENCE_INCOMPLETE",
    })

    def __init__(self, repository, observation_collection_service, clock=None):
        self.repository = repository
        self.observation_collection_service = observation_collection_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def collect_phase(
        self, experiment_id, phase_id, *, expected_state_revision,
        expected_phase_state_revision, expected_result_revision,
        idempotency_key, owner_id, store_id, operation_trace=None,
    ):
        """Read a full planned local window then CAS-append evidence and result."""
        if not isinstance(owner_id, str) or not owner_id.strip() or not isinstance(store_id, str) or not store_id.strip():
            return self._error("EXPERIMENT_SCOPE_INVALID")
        if operation_trace is not None and not isinstance(operation_trace, PeriodProfitOperationTrace):
            return self._error("EXPERIMENT_TRACE_INVALID")
        replay = self.repository.get_price_experiment_phase_collection_replay(
            experiment_id, phase_id,
            expected_state_revision=expected_state_revision,
            expected_phase_state_revision=expected_phase_state_revision,
            expected_result_revision=expected_result_revision,
            idempotency_key=idempotency_key, owner_id=owner_id, store_id=store_id,
        )
        if replay.get("error"):
            return replay
        if replay.get("found") is True:
            return {**replay["result"], "idempotent_replay": True, "read_only": True}
        experiment_result = self.repository.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if experiment_result.get("error"):
            return experiment_result
        experiment = experiment_result.get("experiment")
        if not isinstance(experiment, dict):
            return self._error("EXPERIMENT_RECORD_INVALID")
        phases = self.repository.list_price_experiment_phases(
            experiment_id, limit=10, owner_id=owner_id, store_id=store_id,
        )
        if phases.get("error"):
            return phases
        phase = next((item for item in phases.get("items", [])
                      if item.get("phase_id") == phase_id), None)
        if phase is None:
            return self._error("EXPERIMENT_PHASE_NOT_FOUND")
        expected_status = {
            "BASELINE": "BASELINE_ACTIVE", "CANDIDATE": "CANDIDATE_ACTIVE",
        }.get(phase.get("kind"))
        if (phase.get("status") != "ACTIVE"
                or experiment.get("status") != expected_status
                or phase.get("observation_id") is None
                or phase.get("confirmation") is None):
            return self._error("EXPERIMENT_PHASE_NOT_ACTIVE")
        if (type(expected_state_revision) is not int
                or type(expected_phase_state_revision) is not int
                or type(expected_result_revision) is not int
                or experiment.get("state_revision") != expected_state_revision
                or phase.get("state_revision") != expected_phase_state_revision
                or phase.get("result_revision") != expected_result_revision):
            return self._error("EXPERIMENT_PHASE_STALE_REVISION")

        config = phase.get("config")
        confirmation = phase.get("confirmation")
        try:
            zone = ZoneInfo(config["timezone"])
            now = self.clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("aware clock required")
            local_today = now.astimezone(zone).date()
            start = datetime.fromisoformat(config["planned_from_date"]).date()
            end = datetime.fromisoformat(config["planned_to_date"]).date()
            first_full_day = datetime.fromisoformat(
                confirmation["first_full_local_day"],
            ).date()
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError, OSError):
            return self._error("EXPERIMENT_PHASE_WINDOW_INVALID")
        if start < first_full_day:
            return self._error("EXPERIMENT_PHASE_WINDOW_BEFORE_FIRST_FULL_DAY")
        if start > end or end >= local_today:
            return self._error("EXPERIMENT_PHASE_WINDOW_NOT_COMPLETED")
        if (end - start).days + 1 < 3 or (end - start).days + 1 > 28:
            return self._error("EXPERIMENT_PHASE_WINDOW_LENGTH_INVALID")

        observation_id = phase["observation_id"]
        loaded_observation = self.repository.get_unit_price_observation(
            observation_id, owner_id=owner_id, store_id=store_id,
        )
        if loaded_observation.get("error"):
            return loaded_observation
        observation = loaded_observation.get("observation")
        if not isinstance(observation, dict) or not self._same_observation(
            observation, experiment, phase,
        ):
            return self._error("EXPERIMENT_PHASE_OBSERVATION_MISMATCH")
        if observation.get("status") != "ACTIVE":
            return self._error("EXPERIMENT_PHASE_OBSERVATION_NOT_ACTIVE")

        parent = operation_trace or current_period_profit_trace()
        time_budget_seconds, request_budget = self._effective_budgets(
            parent, self.observation_collection_service,
        )
        if time_budget_seconds < 1 or request_budget < 1:
            return self._error("EXPERIMENT_COLLECTION_BUDGET_UNAVAILABLE")
        trace = PeriodProfitOperationTrace(
            operation="unit_economics_experiment_phase_collection",
            time_budget_seconds=time_budget_seconds,
            ozon_request_budget=request_budget,
            parent=parent,
        )
        token = activate_period_profit_trace(trace)
        try:
            evidence = self.observation_collection_service.collect_window(
                observation_id,
                date_from=start.isoformat(), date_to=end.isoformat(),
            )
        finally:
            reset_period_profit_trace(token)
        if trace.is_cancelled():
            return self._error("EXPERIMENT_COLLECTION_CANCELLED")
        if (trace.budget_reason_code == "TIME_BUDGET_EXHAUSTED"
                or trace.remaining_seconds() <= 0):
            return self._error("EXPERIMENT_COLLECTION_TIME_BUDGET_EXHAUSTED")
        if not isinstance(evidence, dict) or evidence.get("error") is not False:
            return self._error("EXPERIMENT_COLLECTION_SOURCE_UNAVAILABLE")
        if not self._same_collection_window(evidence, start, end, config["timezone"]):
            return self._error("EXPERIMENT_COLLECTION_WINDOW_MISMATCH")
        if (evidence.get("identity") != {
            key: experiment[key] for key in (
                "store_id", "product_id", "offer_id", "sku", "sale_schema",
            )
        } or evidence.get("seller_price_cents") != config["planned_price_cents"]):
            return self._error("EXPERIMENT_COLLECTION_IDENTITY_OR_PRICE_MISMATCH")

        collection = self._collection_projection(
            evidence, trace, experiment, phase, observation_id,
        )
        normalized_collection = PlanningUnitEconomicsExperimentAdapter.normalize_phase_collection(
            collection, {"owner_id": owner_id, "store_id": store_id},
        )
        if normalized_collection is None:
            return self._error("EXPERIMENT_COLLECTION_PROJECTION_INVALID")
        encoded_collection = json.dumps(
            normalized_collection, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        collection_id = hashlib.sha256(encoded_collection.encode("utf-8")).hexdigest()
        experiment_snapshot_id = experiment.get("config", {}).get(
            "source_references", {},
        ).get("expense_snapshot_id")
        phase_snapshot_id = config.get("expense_snapshot_id")
        refs = sorted(set((experiment_snapshot_id, phase_snapshot_id, collection_id)))
        if collection_id not in refs:
            return self._error("EXPERIMENT_COLLECTION_SNAPSHOT_REFERENCE_INVALID")
        result_payload = self._pending_result(normalized_collection, refs)
        saved = self.repository.append_price_experiment_phase_collection_result(
            experiment_id, phase_id, normalized_collection, result_payload,
            expected_state_revision=expected_state_revision,
            expected_phase_state_revision=expected_phase_state_revision,
            expected_result_revision=expected_result_revision,
            idempotency_key=idempotency_key, owner_id=owner_id, store_id=store_id,
        )
        if saved.get("error"):
            return saved
        return {
            **saved, "status": normalized_collection["status"],
            "result_status": result_payload["status"],
            "outcome": result_payload["outcome"], "read_only": True,
            "source_io": True,
        }

    @staticmethod
    def _same_observation(observation, experiment, phase):
        identity = observation.get("identity")
        confirmation = phase.get("confirmation")
        config = phase.get("config")
        timezone_name = config.get("timezone") if isinstance(config, dict) else None
        observed_effective = UnitEconomicsExperimentPhaseCollectionService._aware_datetime(
            observation.get("effective_from"),
        )
        confirmed_effective = (
            UnitEconomicsExperimentPhaseCollectionService._aware_datetime(
                confirmation.get("effective_from"),
            ) if isinstance(confirmation, dict) else None
        )
        return isinstance(identity, dict) and (
            observation.get("store_id") == experiment.get("store_id")
            and all(identity.get(key) == experiment.get(key) for key in (
                "product_id", "offer_id", "sku", "sale_schema",
            ))
        ) and (
            observation.get("seller_price_cents") == phase.get("config", {}).get("planned_price_cents")
            and observation.get("observation_id") == phase.get("observation_id")
            and observation.get("window_timezone") == timezone_name
            and observed_effective is not None
            and confirmed_effective is not None
            and observed_effective == confirmed_effective
        )

    @staticmethod
    def _aware_datetime(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

    @classmethod
    def _effective_budgets(cls, parent, collection_service):
        """Return the strictest configured collection cap and parent remainder."""
        request_limit = min(
            cls.HTTP_ATTEMPT_BUDGET,
            getattr(collection_service, "HTTP_ATTEMPT_BUDGET", cls.HTTP_ATTEMPT_BUDGET),
        )
        time_limit = min(
            cls.TIME_BUDGET_SECONDS,
            getattr(collection_service, "TIME_BUDGET_SECONDS", cls.TIME_BUDGET_SECONDS),
        )
        current = parent
        while current is not None:
            request_limit = min(
                request_limit,
                max(0, current.ozon_request_budget - current.ozon_requests_reserved),
            )
            time_limit = min(time_limit, max(0.0, current.remaining_seconds()))
            current = current.parent
        return int(time_limit), int(request_limit)

    @staticmethod
    def _same_collection_window(evidence, start, end, timezone_name):
        window = evidence.get("window")
        return isinstance(window, dict) and (
            window.get("from") == start.isoformat()
            and window.get("to") == end.isoformat()
            and window.get("timezone") == timezone_name
        )

    @classmethod
    def _collection_projection(cls, evidence, trace, experiment, phase, observation_id):
        sources = []
        source_names = {
            "FINANCE": "FINANCE", "PERFORMANCE": "PERFORMANCE", "RETURNS": "RETURNS",
            "OWNER_DECLARED_PRICE": "OWNER_DECLARED_PRICE", "SELLER_PRICE": "SELLER_PRICE",
            "ANALYTICS": "ANALYTICS", "TARIFF": "TARIFF", "COST": "COST", "TAX": "TAX",
        }
        raw_sources = evidence.get("sources")
        if not isinstance(raw_sources, list):
            raw_sources = []
        for raw in raw_sources:
            if not isinstance(raw, dict) or raw.get("name") not in source_names:
                continue
            status = raw.get("status")
            if status not in {"COMPLETE", "PARTIAL", "SOURCE_UNAVAILABLE", "RATE_LIMITED", "NOT_REQUESTED"}:
                status = "SOURCE_UNAVAILABLE"
            reason = raw.get("reason")
            reason_code = (
                reason.upper() if isinstance(reason, str)
                and reason.upper() in cls._SAFE_SOURCE_REASONS
                else "UNCLASSIFIED_SOURCE_REASON"
            )
            sources.append({
                "source_key": source_names[raw["name"]], "status": status,
                "reason_code": reason_code,
            })
        if len({item["source_key"] for item in sources}) != len(sources):
            sources = list({item["source_key"]: item for item in sources}.values())
        sources.sort(key=lambda item: item["source_key"])
        metrics = evidence.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        normalized_metrics = {}
        for key in cls._MONEY_KEYS:
            normalized_metrics[key] = cls._metric_money(metrics.get(key))
        for key in cls._COUNT_KEYS:
            normalized_metrics[key] = metrics.get(key) if type(metrics.get(key)) is int else None
        normalized_metrics["buyout_rate_percent"] = cls._metric_money(
            metrics.get("buyout_rate_percent"), nonnegative=True,
        )
        source_by_key = {item["source_key"]: item["status"] for item in sources}
        required_complete = all(source_by_key.get(name) == "COMPLETE" for name in (
            "FINANCE", "RETURNS", "PERFORMANCE",
        )) and trace.budget_reason_code == "NONE"
        if required_complete:
            status = "COMPLETE"
        elif source_by_key.get("FINANCE") == "SOURCE_UNAVAILABLE":
            status = "UNAVAILABLE"
        else:
            status = "PARTIAL"
        limitations = {
            "PRICE_HISTORY_UNCONFIRMED",
            "FINANCE_USES_ACCRUAL_DATE_BASIS",
            "PERFORMANCE_USES_REPORT_DATE_BASIS",
            "FINANCE_AND_PERFORMANCE_COSTS_MAY_OVERLAP",
            "SAVED_COST_BASIS_IS_NOT_OBSERVED_COGS",
        }
        if source_by_key.get("RETURNS") != "COMPLETE":
            limitations.add("SUCCESSFUL_UNIT_DENOMINATOR_UNAVAILABLE")
        if source_by_key.get("PERFORMANCE") != "COMPLETE":
            limitations.add("CPC_NOT_CONFIRMED_AS_ZERO")
        budget_reason = trace.budget_reason_code
        if not isinstance(budget_reason, str) or not re.fullmatch(r"[A-Z0-9_]{1,64}", budget_reason):
            budget_reason = "NONE"
        time_budget_seconds = int(min(
            cls.TIME_BUDGET_SECONDS,
            getattr(trace, "time_budget_seconds", cls.TIME_BUDGET_SECONDS),
        ))
        elapsed = max(0, min(time_budget_seconds, int(trace.clock() - trace.started_at)))
        return {
            "schema_version": 1, "experiment_id": experiment["experiment_id"],
            "phase_id": phase["phase_id"], "observation_id": observation_id,
            "identity": {key: experiment[key] for key in (
                "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
            )},
            "status": status,
            "collected_at": evidence.get("collected_at"),
            "window": {
                "from_date": evidence.get("window", {}).get("from"),
                "to_date": evidence.get("window", {}).get("to"),
                "timezone": phase["config"]["timezone"],
                "date_basis": "SOURCE_CALENDAR_DATE",
            },
            "seller_price_cents": phase["config"]["planned_price_cents"],
            "source_statuses": sources, "metrics": normalized_metrics,
            "price_history_verified": False,
            "limitations": sorted(limitations),
            "budget": {
                "http_attempts": min(cls.HTTP_ATTEMPT_BUDGET, trace.ozon_requests_reserved),
                "http_attempt_limit": min(cls.HTTP_ATTEMPT_BUDGET, trace.ozon_request_budget),
                "elapsed_seconds": elapsed,
                "time_budget_seconds": time_budget_seconds,
                "reason_code": budget_reason,
            },
        }

    @staticmethod
    def _metric_money(value, *, nonnegative=False):
        if value is None or isinstance(value, bool):
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if not amount.is_finite() or (nonnegative and amount < 0):
            return None
        try:
            return format(amount.quantize(Decimal("0.01")), ".2f")
        except InvalidOperation:
            return None

    @staticmethod
    def _pending_result(collection, refs):
        sources = {item["source_key"]: item["status"]
                   for item in collection["source_statuses"]}
        gates = [
            {"gate": "FINANCE_COVERAGE",
             "status": "PASS" if sources.get("FINANCE") == "COMPLETE" else "FAIL",
             "reason_code": "COMPLETE" if sources.get("FINANCE") == "COMPLETE" else "FINANCE_PARTIAL_OR_UNAVAILABLE"},
            {"gate": "UNIT_QUANTITY_COVERAGE",
             "status": "PASS" if sources.get("RETURNS") == "COMPLETE"
             and collection["metrics"]["successful_sale_units"] is not None else "UNKNOWN",
             "reason_code": "COMPLETE" if sources.get("RETURNS") == "COMPLETE"
             and collection["metrics"]["successful_sale_units"] is not None else "SUCCESSFUL_UNITS_UNCONFIRMED"},
            {"gate": "ADVERTISING_COVERAGE",
             "status": "PASS" if sources.get("PERFORMANCE") == "COMPLETE" else "UNKNOWN",
             "reason_code": "COMPLETE" if sources.get("PERFORMANCE") == "COMPLETE" else "CPC_NOT_CONFIRMED"},
            {"gate": "PRICE_HISTORY",
             "status": "UNKNOWN", "reason_code": "OWNER_DECLARED_PRICE_ONLY"},
            {"gate": "OBSERVED_COGS",
             "status": "UNKNOWN", "reason_code": "SAVED_COST_IS_NOT_OBSERVED_COGS"},
        ]
        quantity = (
            "SOLD_UNITS_WINDOW"
            if sources.get("RETURNS") == "COMPLETE"
            and collection["metrics"]["successful_sale_units"] is not None else None
        )
        return {
            "schema_version": 1, "status": "WAITING_FOR_DATA",
            "source_as_of": collection["collected_at"], "snapshot_refs": refs,
            "baseline_profit_per_unit_rub": None,
            "candidate_profit_per_unit_rub": None,
            "delta_profit_per_unit_rub": None,
            "quantity_basis": quantity,
            "window": {
                "from_date": collection["window"]["from_date"],
                "to_date": collection["window"]["to_date"],
                "timezone": collection["window"]["timezone"],
            },
            "quality_gates": gates,
            "limitations": collection["limitations"],
            "outcome": "CONTINUE_COLLECTING",
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True}
