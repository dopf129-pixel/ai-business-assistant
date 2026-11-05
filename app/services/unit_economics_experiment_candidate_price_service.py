"""Bounded candidate generation over the existing unit-price solvers."""


from decimal import Decimal, InvalidOperation

from services.unit_economics_experiment_plan_service import (
    UnitEconomicsExperimentPlanService,
)


class UnitEconomicsExperimentCandidatePriceService:
    """Build a small tariff-aware price set and compare it canonically."""

    MIN_CANDIDATES = 2
    MAX_CANDIDATES = 10

    def __init__(self, target_planning_service):
        self.target_planning_service = target_planning_service

    def select_candidates(
        self, inputs, price_bounds_cents, *, identity=None,
        requested_count=10, frozen_tariff_snapshot=None,
        extended_scenario=None, strict_return_evidence=None,
        advertising_mode="SAME_DRR", provenance=None, sources=None,
    ):
        bounds = UnitEconomicsExperimentPlanService.normalize_price_bounds(
            price_bounds_cents,
        )
        if bounds is None:
            return self._error("INVALID_PRICE_BOUNDS")
        if (type(requested_count) is not int
                or not self.MIN_CANDIDATES <= requested_count <= self.MAX_CANDIDATES):
            return self._error("INVALID_CANDIDATE_COUNT")
        if not isinstance(inputs, dict):
            return self._error("INVALID_INPUTS")
        minimum = bounds["min_price_cents"]
        maximum = bounds["max_price_cents"]
        if minimum >= maximum:
            return self._incomplete("PRICE_RANGE_TOO_NARROW")
        if maximum > self.target_planning_service.max_price_cents:
            return self._error("PRICE_BOUNDS_EXCEED_CALCULATOR_LIMIT")

        span = maximum - minimum
        point_count = min(requested_count, span + 1)
        intervals = point_count - 1
        step_cents = (span + intervals - 1) // intervals
        grid = self.target_planning_service.build_price_grid(
            ";".join((self._price(minimum), self._price(maximum), self._price(step_cents))),
            frozen_tariff_snapshot=frozen_tariff_snapshot,
            identity=identity,
            inputs=inputs,
        )
        candidate_prices = list(grid.get("prices") or [])
        candidate_cents = [self._cents(price) for price in candidate_prices]
        metadata = grid.get("metadata") or {}
        if grid.get("code") == "INVALID_TARIFF_SNAPSHOT":
            return self._incomplete("TARIFF_SNAPSHOT_INVALID")
        if grid.get("code") in {"PRICE_GRID_LIMIT", "PRICE_GRID_TARIFF_RULE_LIMIT"}:
            return self._incomplete(
                "TARIFF_BOUNDARIES_EXCEED_CANDIDATE_LIMIT",
                required_count=(grid.get("required_candidates")
                                or grid.get("required_candidates_at_least")),
                candidate_limit=self.MAX_CANDIDATES,
            )
        if grid.get("valid") is not True:
            return self._error("PRICE_GRID_UNAVAILABLE", grid_reason=grid.get("code"))
        if (len(candidate_cents) < self.MIN_CANDIDATES
                or len(candidate_cents) > self.MAX_CANDIDATES
                or any(value is None for value in candidate_cents)
                or candidate_cents != sorted(set(candidate_cents))
                or candidate_cents[0] != minimum or candidate_cents[-1] != maximum
                or any(value < minimum or value > maximum for value in candidate_cents)):
            return self._incomplete(
                "TARIFF_BOUNDARIES_EXCEED_CANDIDATE_LIMIT",
                required_count=len(candidate_cents), candidate_limit=self.MAX_CANDIDATES,
            )

        comparison_provenance = dict(provenance or {})
        if frozen_tariff_snapshot is None:
            comparison_provenance.setdefault(
                "commission_rate", "manual_seller_assumption",
            )
        comparison = self.target_planning_service.compare_prices(
            inputs, candidate_prices, identity=identity,
            provenance=comparison_provenance,
            sources=sources, frozen_tariff_snapshot=frozen_tariff_snapshot,
            tariff_resolution_required=frozen_tariff_snapshot is not None,
            advertising_mode=advertising_mode,
            extended_scenario=extended_scenario,
            strict_return_evidence=strict_return_evidence,
        )
        if comparison.get("error") is True:
            return self._error(
                "CANDIDATE_COMPARISON_UNAVAILABLE",
                comparison_reason=comparison.get("code"),
            )
        rows = comparison.get("rows")
        if not isinstance(rows, list) or len(rows) != len(candidate_prices):
            return self._incomplete("CANDIDATE_COMPARISON_INCOMPLETE")
        if any(row.get("available") is not True for row in rows):
            reasons = {
                self._candidate_reason(row) for row in rows
                if row.get("available") is not True
            }
            return self._incomplete(
                "CANDIDATE_SCENARIO_INCOMPLETE",
                reason_codes=sorted(reasons),
                candidate_count=len(candidate_prices),
            )

        profits = [self._decimal(row.get("profit")) for row in rows]
        if any(value is None for value in profits):
            return self._incomplete("CANDIDATE_PROFIT_UNAVAILABLE")
        best_profit = max(profits)
        best_prices = [
            candidate_cents[index]
            for index, profit in enumerate(profits) if profit == best_profit
        ]
        candidates = [
            self._candidate_projection(row, candidate_cents[index], best_profit)
            for index, row in enumerate(rows)
        ]
        tariff_status = metadata.get("tariff_source_status")
        tariff_basis = (
            "FROZEN_TARIFF_SNAPSHOT" if frozen_tariff_snapshot is not None
            else "MANUAL_OR_SCENARIO_RATE_ASSUMPTION"
        )
        limitations = [
            "NO_PRICE_DEMAND_PREDICTION",
            "BOUNDED_GRID_NOT_GLOBAL_OPTIMUM",
            "NO_CAUSAL_PRICE_EFFECT_CLAIM",
        ]
        if frozen_tariff_snapshot is None:
            limitations.append("COMMISSION_RATE_IS_NOT_TARIFF_VERIFIED")
        search = {
            "price_bounds_cents": {
                "min_price_cents": minimum, "max_price_cents": maximum,
            },
            "requested_count": requested_count,
            "base_grid_step_cents": step_cents,
            "base_grid_candidate_count": metadata.get("base_grid_count"),
            "tariff_rule_count": metadata.get("tariff_rule_count"),
            "tariff_source_status": tariff_status,
            "tariff_boundary_prices_cents": [
                self._cents(value) for value in metadata.get(
                    "tariff_boundary_prices", [],
                )
            ],
            "selected_candidate_count": len(candidate_cents),
            "global_optimum_claimed": False,
        }
        if search["tariff_boundary_prices_cents"]:
            search["inserted_tariff_boundary_prices_cents"] = [
                self._cents(value) for value in metadata.get(
                    "inserted_tariff_boundary_prices", [],
                )
            ]
        return {
            "error": False,
            "status": "TIED_MAXIMUM" if len(best_prices) > 1 else "AVAILABLE",
            "target_metric": UnitEconomicsExperimentPlanService.TARGET_METRIC,
            "candidate_prices_cents": candidate_cents,
            "candidate_count": len(candidate_cents),
            "best_profit_per_unit_rub": format(best_profit, ".2f"),
            "best_candidate_prices_cents": best_prices,
            "candidates": candidates,
            "search": search,
            "tariff_basis": tariff_basis,
            "advertising_mode": comparison.get("advertising_basis", {}).get("mode"),
            "model_limitations": sorted(limitations),
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _candidate_projection(cls, row, price_cents, best_profit):
        profit = cls._decimal(row.get("profit"))
        thresholds = row.get("compensation_thresholds")
        if isinstance(thresholds, dict):
            thresholds = {
                "status": thresholds.get("status"),
                "non_worse": cls._threshold_projection(thresholds.get("non_worse")),
                "strictly_better": cls._threshold_projection(
                    thresholds.get("strictly_better"),
                ),
                "evaluation_count": thresholds.get("evaluation_count"),
            }
        else:
            thresholds = None
        return {
            "price_cents": price_cents,
            "profit_per_unit_rub": format(profit, ".2f") if profit is not None else None,
            "profit_delta_vs_baseline_rub": row.get("profit_delta_vs_baseline"),
            "commission_rate_percent": row.get("commission_rate"),
            "commission_status": row.get("commission_status"),
            "commission_origin": row.get("commission_origin"),
            "advertising_rate_percent": row.get("advertising_rate"),
            "advertising_per_unit_rub": row.get("advertising_per_unit"),
            "compensation_thresholds": thresholds,
            "is_best_in_candidate_set": profit == best_profit,
            "evidence_basis": row.get("evidence_basis"),
        }

    @classmethod
    def _threshold_projection(cls, value):
        if not isinstance(value, dict):
            return None
        return {
            key: value.get(key) for key in (
                "status", "available", "advertising_rate", "advertising_per_unit",
                "profit_per_unit", "tax_per_unit", "goal_reached", "next_tick_rate",
            )
        }

    @classmethod
    def _candidate_reason(cls, row):
        status = row.get("commission_status")
        if status in {"UNKNOWN", "UNRESOLVED", "SOURCE_UNAVAILABLE"}:
            return "CANDIDATE_COMMISSION_UNAVAILABLE"
        if row.get("status") == "INVALID_ADVERTISING_RATE":
            return "CANDIDATE_ADVERTISING_INPUT_INVALID"
        return "CANDIDATE_FORWARD_UNAVAILABLE"

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            result = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result.is_finite() else None

    @classmethod
    def _cents(cls, value):
        price = cls._decimal(value)
        if price is None:
            return None
        return int((price * Decimal("100")).to_integral_value())

    @classmethod
    def _price(cls, cents):
        return format(Decimal(cents) / Decimal("100"), ".2f")

    @staticmethod
    def _error(code, **details):
        return {"error": True, "code": code, **details}

    @staticmethod
    def _incomplete(code, **details):
        return {"error": False, "status": "INCOMPLETE", "reason_code": code, **details}
