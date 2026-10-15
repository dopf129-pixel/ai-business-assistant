"""Pure arithmetic view over the normalized finalized-period contract."""

from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from math import isfinite


_PERIOD_BLOCKERS = {
    "PERIOD_PROFIT_COMPARISON_PERIOD_LENGTH_MISMATCH",
    "PERIOD_PROFIT_COMPARISON_PERIODS_NOT_ADJACENT",
    "PERIOD_PROFIT_COMPARISON_PERIOD_INVALID",
    "PERIOD_PROFIT_COMPARISON_TENANT_MISMATCH",
    "PERIOD_PROFIT_COMPARISON_TENANT_SCOPE_UNKNOWN",
    "PERIOD_PROFIT_COMPARISON_CURRENCY_MISMATCH",
}
_ACCOUNT_SCOPE_BLOCKERS = {
    "PERIOD_PROFIT_COMPARISON_PROFIT_SCOPE_UNKNOWN",
    "PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH",
    "PERIOD_PROFIT_COMPARISON_COMPONENT_SCOPE_UNKNOWN",
    "PERIOD_PROFIT_COMPARISON_COMPONENT_SCOPE_MISMATCH",
}
_CENT = Decimal("0.01")


def build_period_profit_comparison_metrics(contract):
    """Compare confirmed metrics without changing canonical financial results."""
    if not _valid_contract(contract):
        return _error("PERIOD_PROFIT_COMPARISON_METRICS_CONTRACT_INVALID")

    current = contract["current"]
    previous = contract["previous"]
    reasons = contract["profit_compatibility"].get("reason_codes") or []
    reason_set = set(reasons)
    periods_tenant_compatible = not bool(reason_set & _PERIOD_BLOCKERS)
    account_scope_compatible = not bool(reason_set & _ACCOUNT_SCOPE_BLOCKERS)
    b_compatible = contract["profit_bases"]["B"].get("status") == "CONFIRMED"
    e_compatible = contract["profit_bases"]["E"].get("status") == "CONFIRMED"
    tax_compatible = (
        current["tax_policy"].get("status") == "CONFIRMED"
        and previous["tax_policy"].get("status") == "CONFIRMED"
        and _same_tax_policy(current["tax_policy"], previous["tax_policy"])
    )

    specs = {
        "revenue": ("RUB", "independent"),
        "discount_points": ("RUB", "independent"),
        "revenue_tax_base": ("RUB", "independent"),
        "net_accrual": ("RUB", "account"),
        "product_cost": ("RUB", "account"),
        "tax": ("RUB", "tax"),
        "return_cogs_adjustment": ("RUB", "B"),
        "profit": ("RUB", "B"),
        "margin_percent": ("PERCENT", "B"),
        "external_expenses": ("RUB", "external"),
        "profit_after_external_expenses": ("RUB", "E"),
        "margin_after_external_expenses": ("PERCENT", "E"),
        "units_sold": ("UNIT", "independent"),
    }

    metrics = {}
    for name, (unit, gate) in specs.items():
        left = current["metrics"].get(name)
        right = previous["metrics"].get(name)
        if not isinstance(left, dict) or not isinstance(right, dict):
            return _error("PERIOD_PROFIT_COMPARISON_METRICS_SHAPE_INVALID")
        comparable = periods_tenant_compatible and _gate_allows(
            gate,
            account_scope_compatible,
            b_compatible,
            e_compatible,
            tax_compatible,
        )
        metrics[name] = _metric_pair(
            name,
            left,
            right,
            unit,
            comparable,
            current["metrics"].get("revenue"),
            previous["metrics"].get("revenue"),
        )

    return {
        "error": False,
        "status": "PERIOD_PROFIT_COMPARISON_METRICS_READY",
        "schema_version": contract["schema_version"],
        "scope": contract["scope"],
        "periods": {
            "current": current["period"],
            "previous": previous["period"],
        },
        "generated_at": contract["generated_at"],
        "profit_compatibility": contract["profit_compatibility"],
        "profit_bases": contract["profit_bases"],
        "metrics": metrics,
        "read_only": True,
        "executed": False,
    }


def _valid_contract(contract):
    if not (
        isinstance(contract, dict)
        and contract.get("error") is False
        and contract.get("status") == "PERIOD_PROFIT_COMPARISON_CONTRACT_READY"
        and type(contract.get("schema_version")) is int
        and contract.get("schema_version") == 1
        and contract.get("read_only") is True
        and contract.get("executed") is False
        and isinstance(contract.get("scope"), dict)
        and isinstance(contract.get("generated_at"), str)
        and isinstance(contract.get("current"), dict)
        and isinstance(contract.get("previous"), dict)
        and isinstance(contract.get("profit_bases"), dict)
        and isinstance(contract.get("profit_compatibility"), dict)
        and isinstance(contract["current"].get("metrics"), dict)
        and isinstance(contract["previous"].get("metrics"), dict)
        and isinstance(contract["current"].get("period"), dict)
        and isinstance(contract["previous"].get("period"), dict)
        and isinstance(contract["current"].get("tax_policy"), dict)
        and isinstance(contract["previous"].get("tax_policy"), dict)
        and isinstance(contract["profit_compatibility"].get("reason_codes"), list)
        and isinstance(contract["profit_bases"].get("B"), dict)
        and isinstance(contract["profit_bases"].get("E"), dict)
    ):
        return False
    return True


def _same_tax_policy(current, previous):
    fields = (
        "mode",
        "rate_percent",
        "minimum_tax_rate_percent",
        "minimum_rate_applicable",
    )
    return all(current.get(field) == previous.get(field) for field in fields)


def _gate_allows(gate, account_scope, basis_b, basis_e, tax_policy):
    if gate == "independent":
        return True
    if gate == "account":
        return account_scope
    if gate == "tax":
        return basis_b and tax_policy
    if gate == "B":
        return basis_b
    if gate == "E":
        return basis_e
    if gate == "external":
        return True
    return False


def _metric_pair(name, current, previous, unit, scope_compatible, current_revenue, previous_revenue):
    current_value = current.get("value")
    previous_value = previous.get("value")
    current_status = current.get("status")
    previous_status = previous.get("status")
    reasons = []
    delta = None
    relative = None
    relative_status = "UNAVAILABLE"
    relative_basis = None
    comparison_status = "UNAVAILABLE"

    current_decimal = (
        _decimal(current_value)
        if current_status in {"CONFIRMED", "PARTIAL"}
        else None
    )
    previous_decimal = (
        _decimal(previous_value)
        if previous_status in {"CONFIRMED", "PARTIAL"}
        else None
    )
    current_confirmed = current_status == "CONFIRMED" and current_decimal is not None
    previous_confirmed = previous_status == "CONFIRMED" and previous_decimal is not None
    if not current_confirmed:
        reasons.append("PERIOD_PROFIT_COMPARISON_CURRENT_METRIC_UNCONFIRMED")
    if not previous_confirmed:
        reasons.append("PERIOD_PROFIT_COMPARISON_PREVIOUS_METRIC_UNCONFIRMED")

    if scope_compatible and current_confirmed and previous_confirmed:
        try:
            with localcontext() as context:
                context.prec = 64
                delta_decimal = current_decimal - previous_decimal
                rounded_delta = _rounded(delta_decimal, unit)
                delta = (
                    int(rounded_delta)
                    if unit == "UNIT"
                    else _public_number(rounded_delta)
                )
                if delta is None:
                    raise ArithmeticError
                comparison_status = "COMPARABLE"
                if unit == "PERCENT":
                    relative_status = "NOT_APPLICABLE"
                elif previous_decimal == 0:
                    relative_status = "UNDEFINED_PREVIOUS_ZERO"
                else:
                    relative_decimal = delta_decimal / abs(previous_decimal) * Decimal(100)
                    relative = _public_number(_rounded(relative_decimal, "PERCENT"))
                    if relative is None:
                        relative_status = "UNAVAILABLE_ARITHMETIC_LIMIT"
                        reasons.append("PERIOD_PROFIT_COMPARISON_ARITHMETIC_LIMIT")
                    else:
                        relative_status = "CALCULATED"
                        relative_basis = (
                            "ABSOLUTE_PREVIOUS_VALUE"
                            if previous_decimal < 0
                            else "PREVIOUS_VALUE"
                        )
        except (ArithmeticError, DecimalException, OverflowError, ValueError):
            delta = None
            relative = None
            comparison_status = "UNAVAILABLE"
            relative_status = "UNAVAILABLE_ARITHMETIC_LIMIT"
            reasons.append("PERIOD_PROFIT_COMPARISON_ARITHMETIC_LIMIT")
    elif not scope_compatible:
        reasons.append("PERIOD_PROFIT_COMPARISON_SCOPE_NOT_COMPARABLE")

    if comparison_status == "COMPARABLE" and unit == "PERCENT":
        delta_unit = "PERCENTAGE_POINT"
    else:
        delta_unit = unit

    return {
        "unit": unit,
        "current_value": current_value if current_decimal is not None else None,
        "current_status": current_status,
        "previous_value": previous_value if previous_decimal is not None else None,
        "previous_status": previous_status,
        "comparison_status": comparison_status,
        "delta": delta,
        "delta_unit": delta_unit,
        "relative_change_percent": relative,
        "relative_change_status": relative_status,
        "relative_change_basis": relative_basis,
        "current_share_of_revenue_percent": (
            _share(current_decimal, current_revenue) if unit == "RUB" else None
        ),
        "previous_share_of_revenue_percent": (
            _share(previous_decimal, previous_revenue) if unit == "RUB" else None
        ),
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def _share(value, revenue_metric):
    if not isinstance(revenue_metric, dict) or revenue_metric.get("status") != "CONFIRMED":
        return None
    revenue = _decimal(revenue_metric.get("value"))
    if value is None or revenue is None or revenue <= 0:
        return None
    try:
        with localcontext() as context:
            context.prec = 64
            return _public_number(_rounded(value / revenue * Decimal(100), "PERCENT"))
    except (ArithmeticError, DecimalException, OverflowError, ValueError):
        return None


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _rounded(value, unit):
    quantum = Decimal("1") if unit == "UNIT" else _CENT
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _public_number(value):
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not isfinite(result):
        return None
    return int(result) if result.is_integer() else result


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_COMPARISON_METRICS_UNAVAILABLE",
        "read_only": True,
        "executed": False,
    }
