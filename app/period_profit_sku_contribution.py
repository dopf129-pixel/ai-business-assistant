"""Read-only SKU contribution view over two finalized store-profit summaries."""

from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from math import isfinite


_CENT = Decimal("0.01")


def build_period_profit_sku_contribution(contract, current_summary, previous_summary):
    """Rank exact, uniquely matched SKU profit changes and reconcile to store."""
    if not _contract_ready(contract):
        return _unavailable("PERIOD_PROFIT_SKU_COMPARISON_BASIS_UNAVAILABLE")
    current = _summary_rows(current_summary)
    previous = _summary_rows(previous_summary)
    if current is None or previous is None:
        return _unavailable("PERIOD_PROFIT_SKU_SUMMARY_COVERAGE_UNAVAILABLE")

    current_profit = _number(current_summary.get("profit"))
    previous_profit = _number(previous_summary.get("profit"))
    contract_current = _number(
        contract["profit_bases"]["B"].get("current_value")
    )
    contract_previous = _number(
        contract["profit_bases"]["B"].get("previous_value")
    )
    if None in (current_profit, previous_profit, contract_current, contract_previous):
        return _unavailable("PERIOD_PROFIT_SKU_STORE_PROFIT_INVALID")
    rounded_values = tuple(
        _rounded(value)
        for value in (current_profit, previous_profit, contract_current, contract_previous)
    )
    if any(value is None for value in rounded_values):
        return _unavailable("PERIOD_PROFIT_SKU_ARITHMETIC_LIMIT")
    if (
        abs(rounded_values[0] - rounded_values[2]) > _CENT
        or abs(rounded_values[1] - rounded_values[3]) > _CENT
    ):
        return _unavailable("PERIOD_PROFIT_SKU_STORE_PROFIT_MISMATCH")

    current_rows = current["rows"]
    previous_rows = previous["rows"]
    edges = _candidate_edges(current_rows, previous_rows)
    current_degree = {}
    previous_degree = {}
    for current_index, previous_index in edges:
        current_degree[current_index] = current_degree.get(current_index, 0) + 1
        previous_degree[previous_index] = previous_degree.get(previous_index, 0) + 1

    matches = []
    ambiguous_current = set()
    ambiguous_previous = set()
    for current_index, previous_index in edges:
        if current_degree[current_index] == 1 and previous_degree[previous_index] == 1:
            matches.append((current_index, previous_index))
        else:
            ambiguous_current.add(current_index)
            ambiguous_previous.add(previous_index)

    contributions = []
    invalid_current = set(current["invalid_profit_indexes"])
    invalid_previous = set(previous["invalid_profit_indexes"])
    matched_current = {left for left, _right in matches}
    matched_previous = {right for _left, right in matches}
    if matched_current & invalid_current or matched_previous & invalid_previous:
        return _unavailable("PERIOD_PROFIT_SKU_ROW_PROFIT_INVALID")
    for current_index, previous_index in matches:
        current_row = current_rows[current_index]
        previous_row = previous_rows[previous_index]
        current_amount = current_row["profit"]
        previous_amount = previous_row["profit"]
        delta = _rounded(current_amount - previous_amount)
        public_delta = _public(delta)
        public_previous = _public(_rounded(previous_amount))
        public_current = _public(_rounded(current_amount))
        if public_delta is None or public_previous is None or public_current is None:
            return _unavailable("PERIOD_PROFIT_SKU_ARITHMETIC_LIMIT")
        contributions.append(
            {
                "sku": current_row["display_sku"] or previous_row["display_sku"],
                "previous_sku": previous_row["sku"],
                "current_sku": current_row["sku"],
                "offer_id": current_row["offer_id"] or previous_row["offer_id"],
                "previous_profit": public_previous,
                "current_profit": public_current,
                "delta": public_delta,
                "status": "CONFIRMED",
            }
        )

    # If a matched identity contains an invalid profit, do not advertise it as
    # an unexplained no-op or silently place it outside the reconciliation.
    contributions.sort(key=lambda row: (-Decimal(str(row["delta"])), row["sku"] or ""))
    delta_total = _rounded(current_profit - previous_profit)
    sku_delta = _rounded(
        sum((Decimal(str(row["delta"])) for row in contributions), Decimal(0))
    )
    if delta_total is None or sku_delta is None:
        return _unavailable("PERIOD_PROFIT_SKU_ARITHMETIC_LIMIT")
    residual = _rounded(delta_total - sku_delta)
    if any(value is None for value in (delta_total, sku_delta, residual)):
        return _unavailable("PERIOD_PROFIT_SKU_ARITHMETIC_LIMIT")
    public_store_delta = _public(delta_total)
    public_sku_delta = _public(sku_delta)
    public_residual = _public(residual)
    if any(value is None for value in (public_store_delta, public_sku_delta, public_residual)):
        return _unavailable("PERIOD_PROFIT_SKU_ARITHMETIC_LIMIT")

    unmatched_current = len(current_rows) - len(matches)
    unmatched_previous = len(previous_rows) - len(matches)
    ambiguous_count = len(ambiguous_current) + len(ambiguous_previous)
    invalid_count = len(invalid_current) + len(invalid_previous)
    identity_coverage_complete = (
        unmatched_current == 0
        and unmatched_previous == 0
        and ambiguous_count == 0
        and invalid_count == 0
    )
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_SKU_CONTRIBUTION_READY"
            if identity_coverage_complete
            else "PERIOD_PROFIT_SKU_CONTRIBUTION_PARTIAL"
        ),
        "coverage_status": "COMPLETE" if identity_coverage_complete else "PARTIAL",
        "basis": "FINALIZED_SKU_ATTRIBUTED_PROFIT_B",
        "store_profit_delta": public_store_delta,
        "matched_sku_profit_delta": public_sku_delta,
        "store_minus_sku_delta": public_residual,
        "reconciliation_status": "ARITHMETICALLY_RECONCILED",
        "matched_sku_count": len(matches),
        "unmatched_current_count": unmatched_current,
        "unmatched_previous_count": unmatched_previous,
        "ambiguous_identity_count": ambiguous_count,
        "invalid_row_count": invalid_count,
        "unmatched_current": _unmatched_preview(
            current_rows,
            set(range(len(current_rows))) - matched_current,
            ambiguous_current,
            invalid_current,
        ),
        "unmatched_previous": _unmatched_preview(
            previous_rows,
            set(range(len(previous_rows))) - matched_previous,
            ambiguous_previous,
            invalid_previous,
        ),
        "unmatched_preview_limit": 5,
        "unmatched_rows_are_zero": False,
        "limitations": (
            []
            if identity_coverage_complete
            else ["PERIOD_PROFIT_SKU_IDENTITY_OR_ROW_COVERAGE_INCOMPLETE"]
        ),
        "top_growth": [row for row in contributions if row["delta"] > 0][:5],
        "top_decline": sorted(
            (row for row in contributions if row["delta"] < 0),
            key=lambda row: (Decimal(str(row["delta"])), row["sku"] or ""),
        )[:5],
        "read_only": True,
        "executed": False,
    }


def _contract_ready(contract):
    if not isinstance(contract, dict) or contract.get("error") is not False:
        return False
    bases = contract.get("profit_bases")
    basis = bases.get("B") if isinstance(bases, dict) else None
    return (
        isinstance(basis, dict)
        and basis.get("status") == "CONFIRMED"
        and contract.get("read_only") is True
        and contract.get("executed") is False
    )


def _summary_rows(summary):
    if (
        not isinstance(summary, dict)
        or summary.get("error") is not False
        or summary.get("status") != "PERIOD_PROFIT_SUMMARY_READY"
        or summary.get("finance_sku_scope_applied") is not True
        or summary.get("product_revenue_reconciled") is not True
    ):
        return None
    rows = summary.get("products")
    count = summary.get("product_count")
    if (
        not isinstance(rows, list)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count != len(rows)
    ):
        return None
    normalized = []
    invalid_profit_indexes = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            return None
        sku = _text(row.get("sku"))
        offer_id = _text(row.get("offer_id"))
        product_id = _text(row.get("product_id"))
        catalog_sku = _text(row.get("catalog_sku"))
        profit = _number(row.get("profit"))
        if profit is None:
            invalid_profit_indexes.add(index)
        normalized.append(
            {
                "sku": sku,
                "offer_id": offer_id,
                "product_id": product_id,
                "catalog_sku": catalog_sku,
                "display_sku": catalog_sku or sku,
                "profit": profit,
                "index": index,
            }
        )
    return {"rows": normalized, "invalid_profit_indexes": invalid_profit_indexes}


def _candidate_edges(current_rows, previous_rows):
    edges = []
    for current_index, current in enumerate(current_rows):
        current_keys = _identity_keys(current)
        if not current_keys:
            continue
        for previous_index, previous in enumerate(previous_rows):
            if not _identity_compatible(current, previous):
                continue
            if current_keys.intersection(_identity_keys(previous)):
                edges.append((current_index, previous_index))
    return edges


def _identity_keys(row):
    keys = set()
    if row.get("product_id") and row.get("offer_id"):
        keys.add(("product_offer", row["product_id"], row["offer_id"]))
    for value in (row.get("sku"), row.get("catalog_sku")):
        if value:
            keys.add(("sku", value))
    if row.get("offer_id"):
        keys.add(("offer", row["offer_id"]))
    return keys


def _identity_compatible(left, right):
    for field in ("product_id", "offer_id"):
        first = left.get(field)
        second = right.get(field)
        if first and second and first != second:
            return False
    return True


def _unmatched_preview(rows, indexes, ambiguous, invalid):
    output = []
    for index in sorted(indexes, key=lambda value: rows[value]["display_sku"] or "")[:5]:
        row = rows[index]
        reason = (
            "PERIOD_PROFIT_SKU_ROW_PROFIT_INVALID"
            if index in invalid
            else "PERIOD_PROFIT_SKU_IDENTITY_AMBIGUOUS"
            if index in ambiguous
            else "PERIOD_PROFIT_SKU_COUNTERPART_NOT_PROVEN"
        )
        output.append(
            {
                "sku": row["display_sku"] or row["sku"],
                "status": "UNAVAILABLE",
                "reason_code": reason,
                "missing_period_is_zero": False,
            }
        )
    return output


def _text(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except (DecimalException, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    try:
        return number
    except (ArithmeticError, DecimalException, OverflowError, TypeError, ValueError):
        return None


def _rounded(value):
    try:
        with localcontext() as context:
            context.prec = 64
            result = value.quantize(_CENT, rounding=ROUND_HALF_UP)
        return result if result.is_finite() else None
    except (ArithmeticError, DecimalException, OverflowError, TypeError, ValueError):
        return None


def _public(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not isfinite(result):
        return None
    displayed = _rounded(Decimal(str(result)))
    expected = _rounded(value)
    return result if displayed is not None and displayed == expected else None


def _unavailable(code):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SKU_CONTRIBUTION_UNAVAILABLE",
        "code": code,
        "coverage_status": "UNAVAILABLE",
        "top_growth": [],
        "top_decline": [],
        "read_only": True,
        "executed": False,
    }
