"""Pure validation for fixed-scope unit-economics experiment plans."""


from decimal import Decimal, InvalidOperation


class UnitEconomicsExperimentPlanService:
    """Validate the plan gates before a draft can enter READY."""

    TARGET_METRIC = "MAX_RUB_PER_UNIT"
    MIN_DURATION_DAYS = 3
    MAX_DURATION_DAYS = 28
    DEFAULT_DURATION_DAYS = 7
    MIN_MATURITY_DAYS = 7
    MIN_MATURITY_UNITS = 30
    MIN_PRICE_CENTS = 1
    MAX_PRICE_CENTS = 99_999_999_999_999
    MIN_DECISION_THRESHOLD_RUB = Decimal("0.01")

    @classmethod
    def normalize_price_bounds(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {
            "min_price_cents", "max_price_cents",
        }:
            return None
        minimum = value.get("min_price_cents")
        maximum = value.get("max_price_cents")
        if (type(minimum) is not int or type(maximum) is not int
                or not cls.MIN_PRICE_CENTS <= minimum <= cls.MAX_PRICE_CENTS
                or not cls.MIN_PRICE_CENTS <= maximum <= cls.MAX_PRICE_CENTS
                or minimum > maximum):
            return None
        return {"min_price_cents": minimum, "max_price_cents": maximum}

    @classmethod
    def evaluate(cls, config):
        """Return an allowlisted readiness projection; never activate anything."""
        if not isinstance(config, dict):
            return cls._invalid("EXPERIMENT_PLAN_INVALID")

        reasons = []
        if config.get("metric") != cls.TARGET_METRIC:
            reasons.append("EXPERIMENT_TARGET_METRIC_UNSUPPORTED")
        duration = config.get("planned_duration_days")
        if (type(duration) is not int
                or not cls.MIN_DURATION_DAYS <= duration <= cls.MAX_DURATION_DAYS):
            reasons.append("EXPERIMENT_DURATION_OUT_OF_RANGE")
        try:
            threshold = Decimal(str(config.get("decision_threshold_rub")))
        except (InvalidOperation, ValueError, TypeError):
            threshold = Decimal("NaN")
        if (not threshold.is_finite()
                or threshold < cls.MIN_DECISION_THRESHOLD_RUB):
            reasons.append("EXPERIMENT_DECISION_THRESHOLD_INVALID")
        if config.get("maturity_min_days") != cls.MIN_MATURITY_DAYS:
            reasons.append("EXPERIMENT_MATURITY_DAYS_INVALID")
        if config.get("maturity_min_units") != cls.MIN_MATURITY_UNITS:
            reasons.append("EXPERIMENT_MATURITY_UNITS_INVALID")

        bounds = cls.normalize_price_bounds(config.get("candidate_price_bounds_cents"))
        if bounds is None:
            reasons.append("EXPERIMENT_PRICE_BOUNDS_REQUIRED")
        prices = config.get("candidate_prices_cents")
        if not isinstance(prices, list) or not 2 <= len(prices) <= 10:
            reasons.append("EXPERIMENT_CANDIDATES_REQUIRED")
        elif any(type(price) is not int for price in prices):
            reasons.append("EXPERIMENT_CANDIDATE_PRICE_INVALID")
        elif (len(set(prices)) != len(prices)
              or any(price < cls.MIN_PRICE_CENTS or price > cls.MAX_PRICE_CENTS
                     for price in prices)):
            reasons.append("EXPERIMENT_CANDIDATE_PRICE_INVALID")
        elif bounds is not None and any(
            price < bounds["min_price_cents"] or price > bounds["max_price_cents"]
            for price in prices
        ):
            reasons.append("EXPERIMENT_CANDIDATE_OUTSIDE_BOUNDS")

        reasons = sorted(set(reasons))
        return {
            "error": False,
            "status": "READY" if not reasons else "INCOMPLETE",
            "eligible_for_ready": not reasons,
            "target_metric": cls.TARGET_METRIC,
            "planned_duration_days": duration if type(duration) is int else None,
            "minimum_maturity_days": cls.MIN_MATURITY_DAYS,
            "minimum_maturity_units": cls.MIN_MATURITY_UNITS,
            "reason_codes": reasons,
        }

    @staticmethod
    def _invalid(code):
        return {"error": True, "code": code}
