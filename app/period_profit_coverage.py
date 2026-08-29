COVERAGE_FIELDS = (
    ("fee_components_included", "ozon_fee_components"),
    ("returns_included", "returns"),
    ("advertising_included", "advertising"),
    ("storage_included", "storage"),
)


def build_period_profit_coverage(
    summary,
    return_financial_evidence=None,
    advertising_financial_evidence=None,
    storage_financial_evidence=None,
):
    source = dict(summary or {})
    if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_COVERAGE_SUMMARY_REQUIRED", "status": "PERIOD_PROFIT_COVERAGE_UNAVAILABLE"}

    included = []
    missing = []
    for field, name in COVERAGE_FIELDS:
        if source.get(field) is True:
            included.append(name)
        else:
            missing.append(name)

    return_evidence = dict(return_financial_evidence or {})
    return_status = "NOT_CONFIGURED"
    if return_evidence.get("status") == "PERIOD_PROFIT_RETURN_FINANCIAL_EVIDENCE_READY":
        if return_evidence.get("authorized_mapping_applied") is True:
            return_status = "AUTHORIZED_MAPPING_APPLIED"
        elif return_evidence.get("policy_configured") is True:
            return_status = "POLICY_CONFIGURED"

    advertising = _expense_status(advertising_financial_evidence)
    storage = _expense_status(storage_financial_evidence)
    all_tracked_components_included = not missing
    return {
        "error": False,
        "status": "PERIOD_PROFIT_COVERAGE_READY",
        "coverage_status": "COMPLETE" if all_tracked_components_included else "PARTIAL",
        "included_components": included,
        "missing_components": missing,
        "included_count": len(included),
        "missing_count": len(missing),
        "all_tracked_components_included": all_tracked_components_included,
        "return_financial_evidence_status": return_status,
        "return_financial_evidence_available": return_evidence.get("financial_impact_supported") is True,
        "return_financial_evidence_changes_profit": False,
        "advertising_financial_evidence_status": advertising["status"],
        "advertising_financial_evidence_available": advertising["available"],
        "advertising_financial_evidence_changes_profit": False,
        "storage_financial_evidence_status": storage["status"],
        "storage_financial_evidence_available": storage["available"],
        "storage_financial_evidence_changes_profit": False,
        "accounting_net_profit_claim_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _expense_status(evidence):
    source = dict(evidence or {})
    if source.get("status") != "PERIOD_PROFIT_EXPENSE_EVIDENCE_READY":
        return {"status": "NOT_CONFIGURED", "available": False}
    if source.get("authorized_mapping_applied") is True:
        return {"status": "AUTHORIZED_MAPPING_APPLIED", "available": source.get("matched_operation_count", 0) > 0}
    if source.get("policy_configured") is True:
        return {"status": "POLICY_CONFIGURED", "available": source.get("matched_operation_count", 0) > 0}
    return {"status": "NOT_CONFIGURED", "available": False}
