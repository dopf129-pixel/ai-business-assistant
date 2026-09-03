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
    return_cogs_recovery_evidence=None,
    external_expense_evidence=None,
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
    return_cogs = dict(
        return_cogs_recovery_evidence or {}
    )
    return_cogs_ready = (
        return_cogs.get("status")
        == "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY"
        and return_cogs.get("error") is False
    )
    external = dict(
        external_expense_evidence or {}
    )
    external_valid = (
        external.get("error") is False
        and external.get("status")
        in {
            "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
            "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
        }
    )
    external_complete = (
        external_valid
        and external.get(
            "coverage_complete"
        )
        is True
    )
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
        "account_level_ozon_accruals_included": (
            source.get("account_level_ozon_accruals_included")
            is True
        ),
        "product_revenue_reconciled": source.get(
            "product_revenue_reconciled"
        ),
        "ozon_account_reconciliation": source.get(
            "ozon_account_reconciliation"
        ),
        "return_cogs_recovery_evidence_status": (
            "READY"
            if return_cogs_ready
            else "UNAVAILABLE"
        ),
        "return_cogs_candidate_units": (
            int(
                return_cogs.get(
                    "candidate_recovery_units"
                )
                or 0
            )
            if return_cogs_ready
            else 0
        ),
        "return_cogs_candidate_value": (
            float(
                return_cogs.get(
                    "candidate_value_at_current_cost"
                )
                or 0
            )
            if return_cogs_ready
            else 0.0
        ),
        "return_cogs_profit_adjustment_allowed": False,
        "external_expense_evidence_status": (
            "COMPLETE"
            if external_complete
            else (
                "PARTIAL"
                if external_valid
                else "UNAVAILABLE"
            )
        ),
        "external_expense_coverage_complete": (
            external_complete
        ),
        "external_expense_observed_total": (
            external.get(
                "observed_expense_total"
            )
            if external_valid
            else None
        ),
        "external_expense_complete_total": (
            external.get(
                "complete_expense_total"
            )
            if external_complete
            else None
        ),
        "external_expense_adjustment_complete": (
            external_complete
        ),
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
