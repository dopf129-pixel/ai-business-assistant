"""Reconcile profit movement from already-finalized canonical components."""

from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from math import isfinite


_CENT = Decimal("0.01")
_SUPPORTED_SCOPES = {
    "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V3",
    "OZON_ACCOUNT_ACCRUALS_COST_COMMITTED_RETURN_COGS_AND_CONFIGURED_TAX_V4",
}
_B_FIELDS = (
    "net_accrual",
    "product_cost",
    "return_cogs_adjustment",
    "tax",
    "profit",
)


def build_period_profit_comparison_bridge(contract):
    """Build ΔN/ΔC/ΔK/ΔT/ΔE without recalculating canonical profit or tax."""
    if not _valid_contract(contract):
        return _error("PERIOD_PROFIT_COMPARISON_BRIDGE_CONTRACT_INVALID")

    current = contract["current"]
    previous = contract["previous"]
    scope = current.get("profit_scope")
    reasons = contract["profit_compatibility"].get("reason_codes") or []
    if (
        contract["profit_bases"]["B"].get("status") != "CONFIRMED"
        or contract["profit_compatibility"].get("status") != "CONFIRMED"
    ):
        return _unavailable(
            "PERIOD_PROFIT_COMPARISON_BRIDGE_PROFIT_BASIS_UNAVAILABLE",
            reasons,
        )
    if scope not in _SUPPORTED_SCOPES or previous.get("profit_scope") != scope:
        return _unavailable(
            "PERIOD_PROFIT_COMPARISON_BRIDGE_SCOPE_UNSUPPORTED",
            ["PERIOD_PROFIT_COMPARISON_BRIDGE_SCOPE_UNSUPPORTED"],
        )

    current_values = _confirmed_values(current, _B_FIELDS)
    previous_values = _confirmed_values(previous, _B_FIELDS)
    if current_values is None or previous_values is None:
        return _unavailable(
            "PERIOD_PROFIT_COMPARISON_BRIDGE_COMPONENT_UNCONFIRMED",
            ["PERIOD_PROFIT_COMPARISON_BRIDGE_COMPONENT_UNCONFIRMED"],
        )

    try:
        with localcontext() as context:
            context.prec = 64
            changes = {
                name: current_values[name] - previous_values[name]
                for name in _B_FIELDS
            }
            authoritative_b_delta = changes["profit"]
            current_formula_profit = (
                current_values["net_accrual"]
                - current_values["product_cost"]
                + current_values["return_cogs_adjustment"]
                - current_values["tax"]
            )
            previous_formula_profit = (
                previous_values["net_accrual"]
                - previous_values["product_cost"]
                + previous_values["return_cogs_adjustment"]
                - previous_values["tax"]
            )
            current_period_difference = (
                current_values["profit"] - current_formula_profit
            )
            previous_period_difference = (
                previous_values["profit"] - previous_formula_profit
            )
            raw_b_sum = (
                changes["net_accrual"]
                - changes["product_cost"]
                + changes["return_cogs_adjustment"]
                - changes["tax"]
            )
            raw_b_difference = authoritative_b_delta - raw_b_sum
            displayed_b_delta = _rounded(authoritative_b_delta)
            b_contributions = {
                "net_accrual_change": _rounded(changes["net_accrual"]),
                "product_cost_contribution": _rounded(-changes["product_cost"]),
                "return_cogs_contribution": _rounded(
                    changes["return_cogs_adjustment"]
                ),
                "tax_contribution": _rounded(-changes["tax"]),
            }
            b_rounding = displayed_b_delta - sum(
                b_contributions.values(), Decimal(0)
            )
            if (
                abs(current_period_difference) > _CENT
                or abs(previous_period_difference) > _CENT
                or abs(raw_b_difference) > _CENT
                or abs(b_rounding) > _CENT
            ):
                return {
                    "error": False,
                    "status": "PERIOD_PROFIT_COMPARISON_BRIDGE_PARTIAL",
                    "code": "PERIOD_PROFIT_COMPARISON_BRIDGE_RECONCILIATION_FAILED",
                    "profit_scope": scope,
                    "B": {
                        "status": "UNAVAILABLE",
                        "authoritative_delta": _public(displayed_b_delta),
                        "component_delta": _public(_rounded(raw_b_sum)),
                        "unreconciled_difference": _public(_rounded(raw_b_difference)),
                        "current_period_difference": _public(
                            _rounded(current_period_difference)
                        ),
                        "previous_period_difference": _public(
                            _rounded(previous_period_difference)
                        ),
                    },
                    "E": _e_unavailable(
                        "PERIOD_PROFIT_COMPARISON_BRIDGE_B_RECONCILIATION_REQUIRED"
                    ),
                    "read_only": True,
                    "executed": False,
                }

            try:
                net_detail = _net_accrual_detail(
                    current,
                    previous,
                    changes["net_accrual"],
                )
            except (ArithmeticError, DecimalException, OverflowError, TypeError, ValueError):
                net_detail = {
                    "status": "UNAVAILABLE",
                    "reason_code": "PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT",
                }
            public_b_contributions = {
                name: _public(value)
                for name, value in b_contributions.items()
            }
            if (
                _public(displayed_b_delta) is None
                or any(value is None for value in public_b_contributions.values())
            ):
                return _unavailable(
                    "PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT",
                    ["PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT"],
                )
            b = {
                "status": "CONFIRMED",
                "authoritative_delta": _public(displayed_b_delta),
                "contributions": {
                    **public_b_contributions,
                    "rounding_adjustment": _public(b_rounding),
                },
                "net_accrual_detail": net_detail,
                "reconciled": True,
                "unreconciled_difference": 0.0,
            }
            try:
                e = _build_e_bridge(contract, authoritative_b_delta)
            except (ArithmeticError, DecimalException, OverflowError, TypeError, ValueError):
                e = _e_unavailable(
                    "PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT"
                )
    except (ArithmeticError, DecimalException, OverflowError, TypeError, ValueError):
        return _unavailable(
            "PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT",
            ["PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT"],
        )

    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_COMPARISON_BRIDGE_READY"
            if e.get("status") == "CONFIRMED"
            else "PERIOD_PROFIT_COMPARISON_BRIDGE_PARTIAL"
        ),
        "profit_scope": scope,
        "B": b,
        "E": e,
        "read_only": True,
        "executed": False,
    }


def _build_e_bridge(contract, authoritative_b_delta):
    basis = contract["profit_bases"].get("E", {})
    if basis.get("status") != "CONFIRMED":
        return _e_unavailable(
            "PERIOD_PROFIT_COMPARISON_BRIDGE_EXTERNAL_COVERAGE_REQUIRED"
        )

    current = contract["current"]["metrics"]
    previous = contract["previous"]["metrics"]
    current_expenses = _confirmed_metric(current.get("external_expenses"))
    previous_expenses = _confirmed_metric(previous.get("external_expenses"))
    current_e = _confirmed_metric(current.get("profit_after_external_expenses"))
    previous_e = _confirmed_metric(previous.get("profit_after_external_expenses"))
    current_b = _confirmed_metric(current.get("profit"))
    previous_b = _confirmed_metric(previous.get("profit"))
    if None in (
        current_expenses,
        previous_expenses,
        current_e,
        previous_e,
        current_b,
        previous_b,
    ):
        return _e_unavailable(
            "PERIOD_PROFIT_COMPARISON_BRIDGE_EXTERNAL_COMPONENT_UNCONFIRMED"
        )

    with localcontext() as context:
        context.prec = 64
        if (
            abs(current_e - (current_b - current_expenses)) > _CENT
            or abs(previous_e - (previous_b - previous_expenses)) > _CENT
        ):
            return _e_unavailable(
                "PERIOD_PROFIT_COMPARISON_BRIDGE_EXTERNAL_RECONCILIATION_FAILED"
            )

        authoritative_e_delta = current_e - previous_e
        expense_delta = current_expenses - previous_expenses
        raw_e_sum = authoritative_b_delta - expense_delta
        raw_difference = authoritative_e_delta - raw_e_sum
        displayed_e_delta = _rounded(authoritative_e_delta)
        external_contribution = _rounded(-expense_delta)
        b_delta = _rounded(authoritative_b_delta)
        rounding = displayed_e_delta - b_delta - external_contribution
        if abs(raw_difference) > _CENT or abs(rounding) > _CENT:
            return _e_unavailable(
                "PERIOD_PROFIT_COMPARISON_BRIDGE_EXTERNAL_RECONCILIATION_FAILED"
            )
        public_e_delta = _public(displayed_e_delta)
        public_b_delta = _public(b_delta)
        public_expense_contribution = _public(external_contribution)
        if None in (
            public_e_delta,
            public_b_delta,
            public_expense_contribution,
            _public(rounding),
        ):
            return _e_unavailable(
                "PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT"
            )
        return {
            "status": "CONFIRMED",
            "authoritative_delta": public_e_delta,
            "contributions": {
                "profit_before_external_expenses_delta": public_b_delta,
                "external_expenses_contribution": public_expense_contribution,
                "rounding_adjustment": _public(rounding),
            },
            "reconciled": True,
            "unreconciled_difference": 0.0,
        }


def _net_accrual_detail(current, previous, net_accrual_change):
    current_values = current["metrics"]
    previous_values = previous["metrics"]
    current_revenue = _confirmed_metric(current_values.get("revenue"))
    previous_revenue = _confirmed_metric(previous_values.get("revenue"))
    if current_revenue is None or previous_revenue is None:
        return {
            "status": "UNAVAILABLE",
            "reason_code": "PERIOD_PROFIT_COMPARISON_BRIDGE_REVENUE_UNCONFIRMED",
        }
    revenue_change = current_revenue - previous_revenue
    other_change = net_accrual_change - revenue_change
    rounded_total = _rounded(net_accrual_change)
    rounded_revenue = _rounded(revenue_change)
    rounded_other = rounded_total - rounded_revenue
    public_total = _public(rounded_total)
    public_revenue = _public(rounded_revenue)
    public_other = _public(rounded_other)
    if None in (public_total, public_revenue, public_other):
        return {
            "status": "UNAVAILABLE",
            "reason_code": "PERIOD_PROFIT_COMPARISON_BRIDGE_ARITHMETIC_LIMIT",
        }
    return {
        "status": "CONFIRMED",
        "meaning": "NET_ACCRUAL_SPLIT_ONLY_NOT_ADDITIONAL_EXPENSE",
        "revenue_change": public_revenue,
        "other_net_accrual_change": public_other,
        "net_accrual_change": public_total,
        "reconciled": abs(other_change - rounded_other) <= _CENT,
    }


def _confirmed_values(period, names):
    metrics = period.get("metrics")
    if not isinstance(metrics, dict):
        return None
    output = {}
    for name in names:
        value = _confirmed_metric(metrics.get(name))
        if value is None:
            return None
        output[name] = value
    return output


def _confirmed_metric(metric):
    if not isinstance(metric, dict) or metric.get("status") != "CONFIRMED":
        return None
    value = metric.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, TypeError, ValueError):
        return None
    return decimal if decimal.is_finite() else None


def _valid_contract(contract):
    if (
        not isinstance(contract, dict)
        or contract.get("error") is not False
        or contract.get("status") != "PERIOD_PROFIT_COMPARISON_CONTRACT_READY"
        or contract.get("read_only") is not True
        or contract.get("executed") is not False
        or not isinstance(contract.get("current"), dict)
        or not isinstance(contract.get("previous"), dict)
        or not isinstance(contract.get("profit_bases"), dict)
        or not isinstance(contract.get("profit_compatibility"), dict)
    ):
        return False
    return all(
        isinstance(contract[side].get("metrics"), dict)
        and isinstance(contract[side].get("profit_scope"), str)
        for side in ("current", "previous")
    )


def _rounded(value):
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _public(value):
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not isfinite(result):
        return None
    return int(result) if result.is_integer() else result


def _e_unavailable(code):
    return {
        "status": "UNAVAILABLE",
        "reason_code": code,
        "authoritative_delta": None,
        "contributions": None,
        "reconciled": False,
        "unreconciled_difference": None,
    }


def _unavailable(code, reasons):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_COMPARISON_BRIDGE_UNAVAILABLE",
        "code": code,
        "reason_codes": list(dict.fromkeys(reasons or [code])),
        "B": _e_unavailable(code),
        "E": _e_unavailable(
            "PERIOD_PROFIT_COMPARISON_BRIDGE_BASIS_REQUIRED"
        ),
        "read_only": True,
        "executed": False,
    }


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_COMPARISON_BRIDGE_UNAVAILABLE",
        "read_only": True,
        "executed": False,
    }
