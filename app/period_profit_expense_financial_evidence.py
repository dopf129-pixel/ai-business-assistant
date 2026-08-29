ALLOWED_SCOPES = {"ADVERTISING", "STORAGE"}


def build_period_profit_expense_financial_evidence(
    fee_breakdown,
    scope,
    allowed_operation_names,
):
    normalized_scope = str(scope or "").strip().upper()
    if normalized_scope not in ALLOWED_SCOPES:
        return {
            "error": True,
            "code": "PERIOD_PROFIT_EXPENSE_EVIDENCE_SCOPE_INVALID",
            "status": "PERIOD_PROFIT_EXPENSE_EVIDENCE_UNAVAILABLE",
        }

    allowed = {str(name) for name in (allowed_operation_names or []) if str(name)}
    if not allowed:
        return {
            "error": False,
            "status": "PERIOD_PROFIT_EXPENSE_EVIDENCE_READY",
            "scope": normalized_scope,
            "policy_configured": False,
            "matched_operation_count": 0,
            "matched_amount": 0.0,
            "matched_operations": [],
            "expense_already_in_net_accrual": True,
            "profit_adjustment_allowed": False,
            "automatic_classification_allowed": False,
            "read_only": True,
            "executed": False,
        }

    breakdown = dict(fee_breakdown or {})
    matched = []
    total = 0.0
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
        "status": "PERIOD_PROFIT_EXPENSE_EVIDENCE_READY",
        "scope": normalized_scope,
        "policy_configured": True,
        "allowed_operation_names": sorted(allowed),
        "matched_operation_count": len(matched),
        "matched_amount": round(total, 2),
        "matched_operations": matched,
        "expense_already_in_net_accrual": True,
        "profit_adjustment_allowed": False,
        "automatic_classification_allowed": False,
        "read_only": True,
        "executed": False,
    }
