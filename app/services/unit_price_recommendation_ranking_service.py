"""Rank only comparable seller-price observations by profit per unit."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class UnitPriceRecommendationRankingService:
    """Keep observed-price rankings separate from planning scenario rankings."""

    MONEY_QUANTUM = Decimal("0.01")
    PERCENT_QUANTUM = Decimal("0.01")

    def __init__(self, quality_service):
        self.quality_service = quality_service

    def rank_observations(self, candidates, *, now=None, baseline_index=None):
        """Return a ranking only if every supplied candidate passes Q21 gates.

        The candidate list is expected to be chronologically ordered; its first
        candidate is the baseline unless an explicit candidate index is given.
        No volume-weighted or total-profit ranking is performed.
        """
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 10:
            return self._error("UNIT_PRICE_RANKING_CANDIDATES_INVALID")
        normalized = []
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                return self._error("UNIT_PRICE_RANKING_CANDIDATE_INVALID")
            item = deepcopy(candidate)
            item.setdefault("index", index)
            normalized.append(item)
        indices = [candidate.get("index") for candidate in normalized]
        if (any(type(index) is not int or index < 0 for index in indices)
                or len(set(indices)) != len(indices)):
            return self._error("UNIT_PRICE_RANKING_CANDIDATE_INVALID")
        if baseline_index is None:
            baseline_index = indices[0]
        if type(baseline_index) is not int or baseline_index not in indices:
            return self._error("UNIT_PRICE_RANKING_BASELINE_INVALID")

        quality = self.quality_service.assess(normalized, now=now)
        if not isinstance(quality, dict) or quality.get("error") is True:
            return self._error("UNIT_PRICE_RANKING_QUALITY_CHECK_FAILED")
        result = {
            "error": False,
            "kind": "UNIT_PRICE_OBSERVATION_RANKING",
            "status": quality.get("status"),
            "evidence_basis": quality.get("evidence_basis"),
            "verified": quality.get("verified") is True,
            "baseline_index": baseline_index,
            "checked_candidate_count": len(candidates),
            "quality_assessment": quality,
            "ranking": [],
            "best_indices": [],
            "best_profit_per_unit": None,
            "read_only": True,
            "executed": False,
        }
        if quality.get("status") != "COMPARABLE":
            return result

        basis = quality.get("evidence_basis")
        profit_field = (
            "observed_profit_per_unit"
            if basis == "CANONICAL_FACT_COMPARABLE"
            else "profit_per_unit"
            if basis == "MODELLED_FROM_OBSERVED_INPUTS"
            else None
        )
        rows = []
        for candidate in normalized:
            observation = candidate.get("result") or {}
            metrics = observation.get("metrics") or {}
            profit = self._money(metrics.get(profit_field)) if profit_field else None
            price_cents = observation.get("seller_price_cents")
            revision = candidate.get("result_revision")
            if (profit is None or type(price_cents) is not int or price_cents < 1
                    or type(revision) is not int or revision < 1):
                return self._error("UNIT_PRICE_RANKING_METRIC_INVALID")
            rows.append({
                "index": candidate["index"],
                "result_revision": revision,
                "seller_price_cents": price_cents,
                "profit_per_unit": format(profit, ".2f"),
                "delta_vs_baseline": None,
                "delta_percent_vs_baseline": None,
                "delta_percent_reason": None,
                "is_best": False,
            })

        baseline = next(row for row in rows if row["index"] == baseline_index)
        baseline_profit = Decimal(baseline["profit_per_unit"])
        for row in rows:
            profit = Decimal(row["profit_per_unit"])
            delta = (profit - baseline_profit).quantize(
                self.MONEY_QUANTUM, rounding=ROUND_HALF_UP,
            )
            row["delta_vs_baseline"] = format(delta, ".2f")
            if baseline_profit > 0:
                percent = (delta / baseline_profit * Decimal("100")).quantize(
                    self.PERCENT_QUANTUM, rounding=ROUND_HALF_UP,
                )
                row["delta_percent_vs_baseline"] = format(percent, ".2f")
            else:
                row["delta_percent_reason"] = "BASELINE_NOT_POSITIVE"

        best = max(Decimal(row["profit_per_unit"]) for row in rows)
        for row in rows:
            row["is_best"] = Decimal(row["profit_per_unit"]) == best
        rows.sort(key=lambda row: (
            -Decimal(row["profit_per_unit"]), row["seller_price_cents"], row["index"],
        ))
        result.update({
            "status": "RANKED",
            "ranking": rows,
            "best_indices": sorted(row["index"] for row in rows if row["is_best"]),
            "best_profit_per_unit": format(best, ".2f"),
            "recommendation_scope": "BEST_AMONG_COMPARABLE_CHECKED_OBSERVATIONS",
            "display_basis": (
                "OBSERVED_COMPARABLE_PERIODS"
                if basis == "CANONICAL_FACT_COMPARABLE"
                else "MODELLED_FROM_OBSERVED_INPUTS"
            ),
        })
        return result

    @classmethod
    def _money(cls, value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not amount.is_finite():
            return None
        try:
            return amount.quantize(cls.MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ArithmeticError):
            return None

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
