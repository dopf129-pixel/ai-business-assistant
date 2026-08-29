COVERAGE_FIELDS = (
    ("fee_components_included", "ozon_fee_components"),
    ("returns_included", "returns"),
    ("advertising_included", "advertising"),
    ("storage_included", "storage"),
)


def build_period_profit_coverage(summary):
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

    return {
        "error": False,
        "status": "PERIOD_PROFIT_COVERAGE_READY",
        "coverage_status": "COMPLETE" if not missing else "PARTIAL",
        "included_components": included,
        "missing_components": missing,
        "included_count": len(included),
        "missing_count": len(missing),
        "accounting_net_profit_claim_allowed": not missing,
        "read_only": True,
        "executed": False,
    }
