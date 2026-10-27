"""Classify observation evidence and build a bounded model from compatible inputs."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation


class UnitPriceObservationResultService:
    """Keep canonical fact, observed-input model and incomplete evidence distinct.

    Current Ozon adapters do not establish per-sale seller prices, event-time
    price history, and all successful-unit costs. This service therefore never
    labels current aggregate evidence as canonical profit fact.
    """

    MAX_SUCCESSFUL_UNITS = 10_000
    MAX_PRICE_CENTS = 999_999_999_999_999
    _RESULT_STATUSES = frozenset({
        "AVAILABLE", "INSUFFICIENT_DATA", "SOURCE_UNAVAILABLE", "STALE",
        "INCOMPARABLE", "CONFLICT", "UNSUPPORTED_SCHEME",
    })

    def __init__(self, scenario_service, target_planning_service):
        self.scenario_service = scenario_service
        self.target_planning_service = target_planning_service

    def evaluate(
        self, evidence, *, scenario_inputs, identity, provenance=None,
        planning_sources=None,
    ):
        """Evaluate normalized Q18 evidence with frozen scenario assumptions.

        The persisted result uses PlanningWorkspaceRepository's v1 allowlist.
        `planning_sources` is provenance consumed by the existing forward
        planner; evidence `sources` remain the normalized source list.
        """
        base = self._base_result(evidence)
        if base is None:
            return self._error("OBSERVATION_EVIDENCE_INVALID")
        if not self._same_identity(base["identity"], identity):
            return self._result(
                base, status="INCOMPARABLE", evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["SCENARIO_IDENTITY_DOES_NOT_MATCH_OBSERVATION"],
            )
        if not self._scenario_price_matches(scenario_inputs, base["seller_price_cents"]):
            return self._result(
                base, status="INCOMPARABLE", evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["FROZEN_SCENARIO_SELLER_PRICE_DOES_NOT_MATCH_OBSERVATION"],
            )
        if base["status"] == "CONFLICT":
            return self._result(
                base, status="CONFLICT", evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["OBSERVATION_EVIDENCE_CONFLICT"],
            )

        readiness = self._model_readiness(base)
        if readiness["status"] != "READY":
            mapped_status = {
                "SOURCE_UNAVAILABLE": "SOURCE_UNAVAILABLE",
                "INCOMPARABLE": "INCOMPARABLE",
                "CONFLICT": "CONFLICT",
            }.get(readiness["status"], "INSUFFICIENT_DATA")
            return self._result(
                base, status=mapped_status, evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=readiness["reasons"],
            )

        metrics = base["metrics"]
        cpc = self._decimal(metrics.get("cpc_spend"))
        units = metrics["successful_sale_units"]
        cost_basis_result = self.target_planning_service.parse_advertising_cost_basis(
            f"{format(cpc, 'f')};{units}"
        )
        if cost_basis_result.get("valid") is not True:
            return self._result(
                base, status="INSUFFICIENT_DATA",
                evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["OBSERVED_CPC_COST_BASIS_INVALID"],
            )
        cost_basis = cost_basis_result["basis"]
        inputs = deepcopy(scenario_inputs)
        price = Decimal(base["seller_price_cents"]) / Decimal("100")
        cpc_per_unit = Decimal(cost_basis["amount_per_unit"])
        inputs["price"] = format(price, ".2f")
        inputs["advertising_rate"] = format(cpc_per_unit * Decimal("100") / price, "f")
        planner_provenance = deepcopy(provenance or {})
        if not isinstance(planner_provenance, dict):
            planner_provenance = {}
        planner_provenance.update({
            "price": "OWNER_DECLARED_OBSERVATION_PRICE",
            "advertising_rate": "OBSERVED_CPC_PER_SUCCESSFUL_UNIT",
        })
        try:
            forward_result = self.scenario_service.calculate(
                inputs,
                identity=identity,
                provenance=planner_provenance,
                sources=planning_sources if isinstance(planning_sources, dict) else {},
            )
        except (ArithmeticError, InvalidOperation, TypeError, ValueError):
            forward_result = None
        if not isinstance(forward_result, dict) or forward_result.get("error") is not False:
            return self._result(
                base, status="INSUFFICIENT_DATA",
                evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["CANONICAL_FORWARD_INPUTS_INCOMPLETE"],
            )
        if forward_result.get("available") is not True:
            return self._result(
                base, status="INSUFFICIENT_DATA",
                evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["CANONICAL_FORWARD_INPUTS_INCOMPLETE"],
            )
        calculated = forward_result.get("calculated")
        calculated = calculated if isinstance(calculated, dict) else {}
        observed_cpc_per_unit = cost_basis.get("amount_per_unit")
        calculated_cpc = self._money(calculated.get("advertising"))
        if calculated_cpc is None or calculated_cpc != observed_cpc_per_unit:
            return self._result(
                base, status="INSUFFICIENT_DATA",
                evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["OBSERVED_CPC_COST_NOT_REPRESENTABLE_BY_CANONICAL_FORWARD"],
            )
        profit = self._money(calculated.get("profit"))
        tax = self._money(calculated.get("tax"))
        unit_cost = self._money(inputs.get("cost"))
        if profit is None or tax is None or unit_cost is None:
            return self._result(
                base, status="INSUFFICIENT_DATA",
                evidence_basis="SCENARIO_ASSUMPTIONS",
                reasons=["CANONICAL_FORWARD_RESULT_INCOMPLETE"],
            )

        model_warnings = [
            "MODEL_USES_FROZEN_SCENARIO_ASSUMPTIONS; PROFIT_IS_NOT_OBSERVED.",
            "OBSERVED_ADVERTISING_INPUT_IS_CPC_ONLY; OTHER_ADVERTISING_TYPES_ARE_UNKNOWN.",
            "OWNER_DECLARED_PRICE_DOES_NOT_PROVE_PRICE_USED_BY_EVERY_HISTORICAL_SALE.",
            "NO_CAUSAL_CLAIM_ABOUT_PRICE_CHANGES_OR_ADVERTISING_EFFICIENCY_IS_MADE.",
            "FINANCE_WINDOW_TOTALS_ARE_CONTEXT_ONLY; THEY_ARE_NOT_SUBTRACTED_FROM_UNIT_PROFIT.",
            "CPC_PER_UNIT_IS_ROUNDED_TO_CENTS_BY_THE_CANONICAL_CALCULATOR; KEEP_NUMERATOR_AND_DENOMINATOR_VISIBLE.",
        ]
        if any(item.get("name") == "RETURNS" for item in base["sources"]):
            model_warnings.extend([
                "FBO_BUYOUT_RATE_IS_A_WINDOW_ESTIMATE_FROM_POSTING_AND_RETURN_STATUS_DATA.",
                "DELIVERED_UNITS_ARE_A_POINT_IN_TIME_STATUS_SNAPSHOT; LATER_RETURNS_MAY_CHANGE_THE_COHORT.",
                "FBO_RETURNED_UNITS_ARE_REPORTED_SEPARATELY; RETURN_COSTS_ARE_NOT_NETTED_FROM_MODELLED_UNIT_PROFIT.",
                "CPC_REPORT_DATE_AND_FBO_POSTING_COHORT_ARE_NOT_IDENTICAL; THIS_IS_A_MODEL_NOT_ATTRIBUTED_COST_PER_ORDER.",
            ])
        result = self._result(
            base,
            status="AVAILABLE",
            evidence_basis="MODELLED_FROM_OBSERVED_INPUTS",
            reasons=["CANONICAL_PER_SALE_PROFIT_NOT_AVAILABLE_FROM_CURRENT_SOURCES"],
            warnings=model_warnings,
        )
        result_metrics = result["metrics"]
        result_metrics.update({
            "scenario_profit_per_unit": profit,
            "profit_per_unit": profit,
            "observed_profit_per_unit": None,
            "tax_per_unit": tax,
            "unit_cost": unit_cost,
            "successful_sale_units": units,
            "successful_unit_denominator": units,
            "weighted_ad_spend_numerator": self._money(cpc),
            "advertising_status": "CPC_ONLY_MODEL",
            "revenue_basis": "MODELLED_SELLER_REVENUE; OBSERVED_CPC_PER_SUCCESSFUL_UNIT",
        })
        result["completeness"].update({
            "successful_units": "CONFIRMED",
            "advertising": "PARTIAL",
            "tariff": "MANUAL_ASSUMPTION",
            "tax": "MANUAL_ASSUMPTION",
            "unit_cost": "MANUAL_ASSUMPTION",
        })
        return result

    def _model_readiness(self, result):
        metrics = result["metrics"]
        completeness = result["completeness"]
        if completeness.get("price_history") == "MIXED_PRICES" or metrics.get(
            "price_evidence_status"
        ) == "MIXED_PRICES":
            return {"status": "INCOMPARABLE", "reasons": ["PRICE_WINDOW_IS_MIXED"]}
        units = metrics.get("successful_sale_units")
        denominator = metrics.get("successful_unit_denominator")
        if (
            type(units) is not int or not 1 <= units <= self.MAX_SUCCESSFUL_UNITS
            or type(denominator) is not int or denominator != units
            or completeness.get("successful_units") != "CONFIRMED"
        ):
            return {"status": "INCOMPLETE", "reasons": ["SUCCESSFUL_UNIT_DENOMINATOR_UNCONFIRMED"]}

        sources = result["sources"]
        performance = self._source(sources, "PERFORMANCE")
        returns_source = self._source(sources, "RETURNS")
        use_returns_units = bool(
            returns_source is not None
            and returns_source.get("complete") is True
            and returns_source.get("source_date_basis") == "FBO_POSTING_AND_RETURN_CHANGE_WINDOW"
            and completeness.get("returns") == "CONFIRMED"
        )
        unit_source = returns_source if use_returns_units else next((
            item for item in sources
            if item.get("name") in {"ANALYTICS", "FINANCE"}
            and item.get("complete") is True
        ), None)
        if performance is None or performance.get("complete") is not True:
            return {"status": "SOURCE_UNAVAILABLE", "reasons": ["PERFORMANCE_CPC_UNAVAILABLE"]}
        cpc = self._decimal(metrics.get("cpc_spend"))
        if cpc is None or cpc < 0:
            return {"status": "INCOMPLETE", "reasons": ["PERFORMANCE_CPC_AMOUNT_UNAVAILABLE"]}
        if unit_source is None:
            return {"status": "INCOMPLETE", "reasons": ["SUCCESSFUL_UNITS_SOURCE_UNAVAILABLE"]}
        required_window = result["window"]
        for source in (performance, unit_source):
            if (
                source.get("source_window_start") != required_window["from"]
                or source.get("source_window_end") != required_window["to"]
                or source.get("timezone") != required_window["timezone"]
                or not source.get("source_date_basis")
            ):
                return {"status": "INCOMPARABLE", "reasons": ["SOURCE_WINDOW_OR_DATE_BASIS_MISMATCH"]}
        date_bases_match = performance.get("source_date_basis") == unit_source.get("source_date_basis")
        returns_window_model = bool(
            use_returns_units
            and performance.get("source_date_basis") == "PERFORMANCE_REPORT_DATE"
            and unit_source.get("source_date_basis") == "FBO_POSTING_AND_RETURN_CHANGE_WINDOW"
        )
        if not date_bases_match and not returns_window_model:
            return {"status": "INCOMPARABLE", "reasons": ["CPC_AND_SUCCESSFUL_UNITS_USE_DIFFERENT_DATE_BASES"]}
        if result["status"] == "CONFLICT":
            return {"status": "CONFLICT", "reasons": ["OBSERVATION_EVIDENCE_CONFLICT"]}
        return {"status": "READY", "reasons": []}

    @classmethod
    def _base_result(cls, evidence):
        if (
            not isinstance(evidence, dict) or evidence.get("error") is not False
            or evidence.get("kind") != "NORMALIZED_OBSERVATION_EVIDENCE"
        ):
            return None
        identity = evidence.get("identity")
        expected_identity_keys = {"store_id", "product_id", "offer_id", "sku", "sale_schema"}
        if (
            not isinstance(identity, dict) or set(identity) != expected_identity_keys
            or any(not isinstance(identity.get(key), str) or not identity[key].strip()
                   for key in expected_identity_keys)
            or identity.get("sale_schema") != "FBO"
        ):
            return None
        price_cents = evidence.get("seller_price_cents")
        if type(price_cents) is not int or not 1 <= price_cents <= cls.MAX_PRICE_CENTS:
            return None
        window = evidence.get("window")
        metrics = evidence.get("metrics")
        sources = evidence.get("sources")
        completeness = evidence.get("completeness")
        status = evidence.get("status")
        if (
            not isinstance(window, dict) or set(window) != {"from", "to", "timezone", "date_basis"}
            or not isinstance(metrics, dict) or not isinstance(sources, list)
            or any(not isinstance(item, dict) for item in sources)
            or not isinstance(completeness, dict) or status not in cls._RESULT_STATUSES
        ):
            return None
        return {
            "identity": deepcopy(identity),
            "seller_price_cents": price_cents,
            "window": deepcopy(window),
            "sources": deepcopy(sources),
            "metrics": deepcopy(metrics),
            "completeness": deepcopy(completeness),
            "status": status,
            "warnings": list(evidence.get("warnings") or []),
        }

    @staticmethod
    def _result(base, *, status, evidence_basis, reasons, warnings=None):
        metrics = deepcopy(base["metrics"])
        metrics["observed_profit_per_unit"] = None
        metrics.pop("profit_per_unit", None)
        metrics.pop("scenario_profit_per_unit", None)
        metrics.pop("tax_per_unit", None)
        metrics.pop("unit_cost", None)
        return {
            "schema_version": 1,
            "identity": deepcopy(base["identity"]),
            "seller_price_cents": base["seller_price_cents"],
            "status": status,
            "evidence_basis": evidence_basis,
            "window": deepcopy(base["window"]),
            "sources": deepcopy(base["sources"]),
            "metrics": metrics,
            "completeness": deepcopy(base["completeness"]),
            "reasons": list(reasons)[:32],
            "warnings": (list(warnings) if warnings is not None else list(base["warnings"]))[:32],
        }

    @classmethod
    def _same_identity(cls, evidence_identity, scenario_identity):
        if not isinstance(scenario_identity, dict):
            return False
        schema = scenario_identity.get("sale_schema", scenario_identity.get("scheme"))
        return all(
            str(scenario_identity.get(key) or "").strip() == evidence_identity.get(key)
            for key in ("store_id", "product_id", "offer_id", "sku")
        ) and str(schema or "").strip().upper() == evidence_identity.get("sale_schema")

    @classmethod
    def _scenario_price_matches(cls, inputs, expected_cents):
        if not isinstance(inputs, dict):
            return False
        price = cls._decimal(inputs.get("price"))
        return price is not None and price > 0 and price * Decimal("100") == expected_cents

    @staticmethod
    def _source(sources, name):
        return next((item for item in sources if item.get("name") == name), None)


    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result.is_finite() else None

    @classmethod
    def _money(cls, value):
        amount = cls._decimal(value)
        if amount is None:
            return None
        try:
            return format(amount.quantize(Decimal("0.01")), ".2f")
        except (InvalidOperation, ArithmeticError):
            return None

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
