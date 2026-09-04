class PeriodProfitReturnCogsAccountingReadinessService:
    """Promote independently proven Return COGS facts into readiness gates."""

    REQUIRED_FOUNDATION = (
        "return_sample_complete",
        "originating_sale_period_confirmed",
        "historical_cost_basis_confirmed",
        "saleable_inventory_recovery_confirmed",
    )

    def __init__(self, base_service):
        self.base_service = base_service

    def analyze(self, return_evidence, products):
        analyzer = getattr(self.base_service, "analyze", None)
        if not callable(analyzer):
            return self._unavailable("RETURN_COGS_READINESS_BASE_UNAVAILABLE")

        try:
            base = analyzer(return_evidence, products)
        except Exception:
            return self._unavailable("RETURN_COGS_READINESS_BASE_EXCEPTION")

        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_READINESS_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._unavailable("RETURN_COGS_READINESS_RESULT_INVALID")

        candidates = base.get("candidate_records")
        if not isinstance(candidates, list):
            return self._unavailable("RETURN_COGS_READINESS_CANDIDATES_INVALID")
        has_candidates = bool(candidates)

        foundation = {
            key: base.get(key) is True
            for key in self.REQUIRED_FOUNDATION
        }

        quantity_source = (
            has_candidates
            and base.get("originating_sale_quantity_evidence_confirmed") is True
        )
        period_source = (
            has_candidates
            and base.get("recovery_period_attribution_evidence_confirmed") is True
        )
        compensation_source = (
            has_candidates
            and base.get("compensation_accounting_treatment_evidence_confirmed")
            is True
        )
        double_count_clear = (
            compensation_source
            and base.get("compensation_double_count_clear") is True
        )
        accounting_attribution_source = (
            has_candidates
            and base.get("accounting_attribution_evidence_confirmed") is True
        )

        quantity_gate = quantity_source
        period_gate = period_source
        compensation_gate = compensation_source and double_count_clear

        readiness = (
            has_candidates
            and all(foundation.values())
            and quantity_gate
            and period_gate
            and compensation_gate
            and accounting_attribution_source
        )

        blockers = []
        if not has_candidates:
            blockers.append("RETURN_COGS_CANDIDATES_REQUIRED")
        for key, confirmed in foundation.items():
            if not confirmed:
                blockers.append(key.upper() + "_REQUIRED")
        if not quantity_gate:
            blockers.append("ORIGINATING_SALE_QUANTITY_EVIDENCE_REQUIRED")
        if not period_gate:
            blockers.append("RECOVERY_PERIOD_ATTRIBUTION_EVIDENCE_REQUIRED")
        if not compensation_source:
            blockers.append("COMPENSATION_ACCOUNTING_TREATMENT_EVIDENCE_REQUIRED")
        elif not double_count_clear:
            blockers.append("COMPENSATION_DOUBLE_COUNT_CLEARANCE_REQUIRED")
        if not accounting_attribution_source:
            blockers.append("ACCOUNTING_ATTRIBUTION_EVIDENCE_REQUIRED")

        result = dict(base)
        result["originating_sale_quantity_confirmed"] = quantity_gate
        result["originating_sale_quantity_gate_promoted"] = quantity_gate
        result["recovery_period_attribution_confirmed"] = period_gate
        result["compensation_accounting_treatment_confirmed"] = compensation_gate
        result["return_cogs_accounting_readiness_confirmed"] = readiness
        result["return_cogs_accounting_readiness_status"] = (
            "RETURN_COGS_ACCOUNTING_READINESS_READY"
            if readiness
            else "RETURN_COGS_ACCOUNTING_READINESS_BLOCKED"
        )
        result["return_cogs_accounting_readiness_blockers"] = blockers

        # v1321-v1330 promotes evidence readiness only. Monetary recovery and
        # Period Profit adjustment remain a separate, later accounting contract.
        result["period_cogs_recovery_confirmed"] = False
        result["accounting_cogs_recovery_confirmed"] = False
        result["confirmed_cogs_recovery_amount"] = 0.0
        result["profit_adjustment_allowed"] = False
        result["automatic_recovery_allowed"] = False
        result["compensation_profit_adjustment_allowed"] = False
        result["read_only"] = True
        result["executed"] = False
        return result

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_UNAVAILABLE",
            "originating_sale_quantity_confirmed": False,
            "originating_sale_quantity_gate_promoted": False,
            "recovery_period_attribution_confirmed": False,
            "compensation_accounting_treatment_confirmed": False,
            "return_cogs_accounting_readiness_confirmed": False,
            "return_cogs_accounting_readiness_status": (
                "RETURN_COGS_ACCOUNTING_READINESS_UNAVAILABLE"
            ),
            "return_cogs_accounting_readiness_blockers": [
                "RETURN_COGS_READINESS_EVIDENCE_UNAVAILABLE"
            ],
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
