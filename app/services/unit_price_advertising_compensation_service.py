from decimal import Decimal, InvalidOperation


class UnitPriceAdvertisingCompensationService:
    """Find rounded non-worse and strictly-better ad-rate thresholds by forward."""

    MAX_EVALUATIONS = 64
    MAX_TICK = 10_000  # 0.01 percentage point on a 0–100% DRR grid.
    _HUNDRED = Decimal("100")

    def solve(self, candidate_inputs, baseline_profit, forward_calculator):
        baseline = self._decimal(baseline_profit)
        if not isinstance(candidate_inputs, dict) or baseline is None or not callable(forward_calculator):
            return self._unavailable("INVALID_INPUTS", 0)

        state = {"count": 0, "cache": {}}

        def evaluate(tick, *, direct=False):
            if not direct and tick in state["cache"]:
                return state["cache"][tick]
            if state["count"] >= self.MAX_EVALUATIONS:
                return None
            state["count"] += 1
            inputs = dict(candidate_inputs)
            inputs["advertising_rate"] = format(Decimal(tick) / Decimal("100"), ".2f")
            try:
                result = forward_calculator(inputs)
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                result = None
            if not direct:
                state["cache"][tick] = result
            return result

        probes = [0, 2_500, 5_000, 7_500, self.MAX_TICK]
        previous = None
        for tick in probes:
            result = evaluate(tick)
            profit = self._profit(result)
            if profit is None or (previous is not None and profit > previous):
                return {
                    "status": "LIMIT_NOT_CONFIRMED",
                    "non_worse": self._unavailable("LIMIT_NOT_CONFIRMED", state["count"]),
                    "strictly_better": self._unavailable("LIMIT_NOT_CONFIRMED", state["count"]),
                    "monotonicity": "NOT_CONFIRMED",
                    "evaluation_count": state["count"],
                    "evaluation_limit": self.MAX_EVALUATIONS,
                }
            previous = profit

        outcomes = {}
        for name, predicate in (
            ("non_worse", lambda profit: profit >= baseline),
            ("strictly_better", lambda profit: profit > baseline),
        ):
            zero = evaluate(0)
            upper = evaluate(self.MAX_TICK)
            zero_profit = self._profit(zero)
            upper_profit = self._profit(upper)
            if zero_profit is None or upper_profit is None:
                outcomes[name] = self._unavailable("LIMIT_NOT_CONFIRMED", state["count"])
                continue
            if not predicate(zero_profit):
                outcomes[name] = self._unavailable("NOT_REACHABLE", state["count"])
                continue
            if predicate(upper_profit):
                chosen = self._outcome(self.MAX_TICK, upper, "UPPER_BOUND_REACHED")
                outcomes[name] = chosen
                continue

            low, high = 0, self.MAX_TICK  # low is feasible; high is infeasible.
            exhausted = False
            while high - low > 1:
                middle = (low + high) // 2
                result = evaluate(middle)
                profit = self._profit(result)
                if profit is None:
                    exhausted = True
                    break
                if predicate(profit):
                    low = middle
                else:
                    high = middle
            if exhausted:
                outcomes[name] = self._unavailable("LIMIT_NOT_CONFIRMED", state["count"])
                continue

            final = evaluate(low, direct=True)
            next_tick = evaluate(low + 1, direct=True)
            final_profit = self._profit(final)
            next_profit = self._profit(next_tick)
            if (final_profit is None or next_profit is None
                    or not predicate(final_profit) or predicate(next_profit)):
                outcomes[name] = self._unavailable("FINAL_CHECK_FAILED", state["count"])
                continue
            outcomes[name] = self._outcome(low, final, "FOUND")

        complete = all(item.get("available") is True for item in outcomes.values())
        return {
            "status": "COMPLETED" if complete else "PARTIAL",
            **outcomes,
            "monotonicity": "VALIDATED_ON_BOUNDARY_PROBES",
            "evaluation_count": state["count"],
            "evaluation_limit": self.MAX_EVALUATIONS,
            "grid_step_percentage_points": "0.01",
            "comparison_basis": "CANONICAL_ROUNDED_UNIT_PROFIT",
            "read_only": True,
            "executed": False,
        }

    def _outcome(self, tick, result, status):
        calculated = result.get("calculated") or {}
        rate = Decimal(tick) / Decimal("100")
        return {
            "status": status,
            "available": True,
            "advertising_rate": format(rate, ".2f"),
            "advertising_per_unit": self._money(calculated.get("advertising")),
            "profit_per_unit": self._money(calculated.get("profit")),
            "tax_per_unit": self._money(calculated.get("tax")),
            "goal_reached": True,
            "next_tick_rate": format(rate + Decimal("0.01"), ".2f") if tick < self.MAX_TICK else None,
        }

    @staticmethod
    def _profit(result):
        if not isinstance(result, dict) or result.get("available") is not True:
            return None
        return UnitPriceAdvertisingCompensationService._decimal(
            (result.get("calculated") or {}).get("profit")
        )

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return number if number.is_finite() else None

    @classmethod
    def _money(cls, value):
        number = cls._decimal(value)
        return format(number, ".2f") if number is not None else None

    @staticmethod
    def _unavailable(status, evaluations):
        return {
            "status": status,
            "available": False,
            "advertising_rate": None,
            "advertising_per_unit": None,
            "profit_per_unit": None,
            "tax_per_unit": None,
            "goal_reached": None,
            "next_tick_rate": None,
            "evaluation_count": evaluations,
        }
