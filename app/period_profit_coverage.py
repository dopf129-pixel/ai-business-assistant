COVERAGE_FIELDS = (
    ("fee_components_included", "ozon_fee_components"),
    ("returns_included", "returns"),
    ("advertising_included", "advertising"),
    ("storage_included", "storage"),
)


def build_period_profit_coverage(summary, return_financial_evidence=None):
    source = dict(summary or {})
    if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
        return {
            "error": True,
            "code": "PERIOD_PROFIT_COVERAGE_SUMMARY_REQUIRED",
            "status": "PERIOD_PROFIT_COVERAGE_UNAVAILABLE",
        }

    included = []
    missing = []
    for field, name in COVERAGE_FIELDS:
        if source.get(field) is True:
            included.append(name)
        else:
            missing.append(name)

    evidence = dict(return_financial_evidence or {})
    return_evidence_status = "NOT_CONFIGURED"
    if evidence.get("status") == "PERIOD_PROFIT_RETURN_FINANCIAL_EVIDENCE_READY":
        if evidence.get("authorized_mapping_applied") is True:
            return_evidence_status = "AUTHORIZED_MAPPING_APPLIED"
        elif evidence.get("policy_configured") is True:
            return_evidence_status = "POLICY_CONFIGURED"

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
        "return_financial_evidence_status": return_evidence_status,
        "return_financial_evidence_available": evidence.get("financial_impact_supported") is True,
        "return_financial_evidence_changes_profit": False,
        "accounting_net_profit_claim_allowed": False,
        "read_only": True,
        "executed": False,
    }
