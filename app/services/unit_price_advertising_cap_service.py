"""Bounded advertising-rate limits for the existing one-unit calculator."""

from decimal import Decimal, InvalidOperation


class UnitPriceAdvertisingCapService:
    MAX_EVALUATIONS = 128
    MAX_TICK = 10_000  # 0.01 percentage-point grid from 0% through 100%.
    _HUNDRED = Decimal("100")

    def __init__(self, scenario_service):
        self.scenario_service = scenario_service

    def solve(self, inputs, target_margin_percent, identity=None, provenance=None, sources=None):
        target = self._decimal(target_margin_percent)
        if target is None or target < 0 or target > self._HUNDRED:
            return self._error("INVALID_TARGET")
        if not isinstance(inputs, dict):
            return self._error("INVALID_INPUTS")

        state = {"count": 1, "cache": {}}
        current = self._calculate(inputs, identity, provenance, sources)
        if current.get("available") is not True:
            status = "MISSING_INPUTS" if current.get("missing_inputs") else "INVALID_INPUTS"
            return {
                **self._error(status),
                "missing_inputs": list(current.get("missing_inputs") or []),
                "invalid_inputs": list(current.get("invalid_inputs") or []),
                "read_only": True,
                "executed": False,
            }
        current_rate = self._decimal(inputs.get("advertising_rate"))
        if current_rate is None or current_rate < 0 or current_rate > self._HUNDRED:
            return self._error("INVALID_INPUTS")

        monotonic = self._validate_monotonic(inputs, identity, provenance, sources, state)
        if monotonic is not True:
            return {
                **self._error("LIMIT_NOT_CONFIRMED"),
                "evaluation_count": state["count"],
                "evaluation_limit": self.MAX_EVALUATIONS,
                "read_only": True,
                "executed": False,
            }

        break_even = self._find_cap(
            inputs, Decimal("0"), identity, provenance, sources, state,
        )
        target_cap = self._find_cap(
            inputs, target, identity, provenance, sources, state,
        )
        if state["count"] > self.MAX_EVALUATIONS:
            return {
                **self._error("LIMIT_NOT_CONFIRMED"),
                "evaluation_count": state["count"],
                "evaluation_limit": self.MAX_EVALUATIONS,
                "read_only": True,
                "executed": False,
            }

        calculated = current.get("calculated") or {}
        current_spend = self._decimal(calculated.get("advertising"))
        result = {
            "error": False,
            "kind": "UNIT_PRICE_ADVERTISING_CAP",
            "status": "COMPLETED",
            "target_margin_percent": format(target, "f"),
            "current_advertising_rate": format(current_rate, ".2f"),
            "current_advertising_per_unit": self._format_money(current_spend),
            "break_even": self._with_headroom(break_even, current_rate, current_spend),
            "target": self._with_headroom(target_cap, current_rate, current_spend),
            "monotonicity": "VALIDATED_ON_BOUNDARY_PROBES",
            "evaluation_count": state["count"],
            "evaluation_limit": self.MAX_EVALUATIONS,
            "grid_step_percentage_points": "0.01",
            "read_only": True,
            "executed": False,
        }
        return result

    def _validate_monotonic(self, inputs, identity, provenance, sources, state):
        probes = [0, 2_500, 5_000, 7_500, self.MAX_TICK]
        previous_profit = None
        previous_margin = None
        for tick in probes:
            result = self._evaluate(inputs, tick, identity, provenance, sources, state)
            if result is None or result.get("available") is not True:
                return False
            values = result.get("calculated") or {}
            profit = self._decimal(values.get("profit"))
            margin = self._decimal(values.get("margin_percent"))
            if profit is None or margin is None:
                return False
            if previous_profit is not None and profit > previous_profit:
                return False
            if previous_margin is not None and margin > previous_margin:
                return False
            previous_profit, previous_margin = profit, margin
        return True

    def _find_cap(self, inputs, target, identity, provenance, sources, state):
        def reaches(result):
            if not isinstance(result, dict) or result.get("available") is not True:
                return None
            values = result.get("calculated") or {}
            profit = self._decimal(values.get("profit"))
            revenue = self._decimal(values.get("revenue"))
            if profit is None or revenue is None:
                return None
            if target == 0:
                return profit >= 0
            return profit * self._HUNDRED >= target * revenue

        zero = self._evaluate(inputs, 0, identity, provenance, sources, state)
        hundred = self._evaluate(inputs, self.MAX_TICK, identity, provenance, sources, state)
        if zero is None or hundred is None:
            return self._unavailable("LIMIT_NOT_CONFIRMED")
        zero_ok, hundred_ok = reaches(zero), reaches(hundred)
        if zero_ok is None or hundred_ok is None:
            return self._unavailable("LIMIT_NOT_CONFIRMED")
        if not zero_ok:
            return self._unavailable("NOT_REACHABLE")
        if hundred_ok:
            return self._outcome(self.MAX_TICK, hundred, "UPPER_BOUND_REACHED")

        low, high = 0, self.MAX_TICK  # low is feasible, high is not.
        while high - low > 1:
            middle = (low + high) // 2
            result = self._evaluate(inputs, middle, identity, provenance, sources, state)
            if result is None:
                return self._unavailable("LIMIT_NOT_CONFIRMED")
            feasible = reaches(result)
            if feasible is None:
                return self._unavailable("LIMIT_NOT_CONFIRMED")
            if feasible:
                low = middle
            else:
                high = middle

        cap = self._evaluate(inputs, low, identity, provenance, sources, state, force=True)
        next_tick = self._evaluate(inputs, low + 1, identity, provenance, sources, state, force=True)
        if cap is None or next_tick is None or reaches(cap) is not True or reaches(next_tick) is not False:
            return self._unavailable("LIMIT_NOT_CONFIRMED")
        return self._outcome(low, cap, "FOUND")

    def _evaluate(self, inputs, tick, identity, provenance, sources, state, force=False):
        if not force and tick in state["cache"]:
            return state["cache"][tick]
        if state["count"] >= self.MAX_EVALUATIONS:
            return None
        state["count"] += 1
        candidate = dict(inputs)
        candidate["advertising_rate"] = format(Decimal(tick) / Decimal("100"), ".2f")
        result = self._calculate(candidate, identity, provenance, sources)
        if not force:
            state["cache"][tick] = result
        return result

    def _calculate(self, inputs, identity, provenance, sources):
        try:
            return self.scenario_service.calculate(
                inputs, identity=identity, provenance=provenance, sources=sources,
            )
        except (ArithmeticError, OverflowError, TypeError, ValueError):
            return {"error": True, "available": False, "invalid_inputs": ["calculation"]}

    def _outcome(self, tick, result, status):
        values = result.get("calculated") or {}
        return {
            "status": status,
            "available": True,
            "advertising_rate": format(Decimal(tick) / Decimal("100"), ".2f"),
            "advertising_per_unit": self._format_money(values.get("advertising")),
            "profit_per_unit": self._format_money(values.get("profit")),
            "margin_percent": self._format_money(values.get("margin_percent")),
            "tax_per_unit": self._format_money(values.get("tax")),
            "goal_reached": True,
            "next_tick_rate": (
                format(Decimal(tick + 1) / Decimal("100"), ".2f")
                if tick < self.MAX_TICK and status == "FOUND" else None
            ),
        }

    @staticmethod
    def _unavailable(status):
        return {
            "status": status, "available": False,
            "advertising_rate": None, "advertising_per_unit": None,
            "profit_per_unit": None, "margin_percent": None,
            "tax_per_unit": None, "goal_reached": None, "next_tick_rate": None,
        }

    def _with_headroom(self, outcome, current_rate, current_spend):
        result = dict(outcome)
        if result.get("available") is not True:
            result.update({"headroom_percentage_points": None, "headroom_per_unit": None})
            return result
        cap_rate = self._decimal(result.get("advertising_rate"))
        cap_spend = self._decimal(result.get("advertising_per_unit"))
        result["headroom_percentage_points"] = format(cap_rate - current_rate, ".2f")
        result["headroom_per_unit"] = self._format_money(cap_spend - current_spend)
        return result

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return number if number.is_finite() else None

    @classmethod
    def _format_money(cls, value):
        number = cls._decimal(value)
        return format(number, ".2f") if number is not None else None

    @staticmethod
    def _error(code):
        return {
            "error": True, "code": code, "status": code,
            "available": False, "read_only": True, "executed": False,
        }
