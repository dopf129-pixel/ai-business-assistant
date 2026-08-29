def build_period_profit_return_financial_evidence(finance_rows, allowed_operation_names):
    """Build read-only return-related financial evidence from exact allowed labels.

    No fuzzy matching is used. A financial operation is treated as return-related only
    when its exact name is explicitly supplied by the caller policy.
    """
    allowed = {str(name) for name in (allowed_operation_names or []) if str(name)}
    if not allowed:
        return {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_FINANCIAL_EVIDENCE_READY",
            "policy_configured": False,
            "matched_operation_count": 0,
            "matched_amount": 0.0,
            "matched_operations": [],
            "financial_impact_supported": False,
            "returns_profit_adjustment_allowed": False,
            "read_only": True,
            "executed": False,
        }

    matched = []
    total = 0.0
    for row in finance_rows or []:
        if not isinstance(row, dict):
            continue
        breakdown = row.get("fee_breakdown")
        if not isinstance(breakdown, dict):
            continue
        for name, amount in breakdown.items():
            if str(name) not in allowed:
                continue
            value = float(amount or 0)
            matched.append({
                "operation_name": str(name),
                "amount": round(value, 2),
                "source": "OZON_FINANCE_FEE_BREAKDOWN",
            })
            total += value

    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_FINANCIAL_EVIDENCE_READY",
        "policy_configured": True,
        "allowed_operation_names": sorted(allowed),
        "matched_operation_count": len(matched),
        "matched_amount": round(total, 2),
        "matched_operations": matched,
        "financial_impact_supported": bool(matched),
        "returns_profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }
