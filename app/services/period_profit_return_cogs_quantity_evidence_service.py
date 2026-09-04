class PeriodProfitReturnCogsQuantityEvidenceService:
    """Decorate conservative Return COGS evidence with sale quantity facts."""

    def __init__(
        self,
        base_service,
        sale_quantity_evidence_service,
    ):
        self.base_service = base_service
        self.sale_quantity_evidence_service = (
            sale_quantity_evidence_service
        )

    def analyze(
        self,
        return_evidence,
        products,
    ):
        base = self.base_service.analyze(
            return_evidence,
            products,
        )
        if not isinstance(base, dict):
            return self._unavailable(
                "RETURN_COGS_BASE_EVIDENCE_INVALID"
            )
        if base.get("error") is True:
            return dict(base)

        candidates = base.get(
            "candidate_records"
        )
        if not isinstance(candidates, list):
            return self._unavailable(
                "RETURN_COGS_CANDIDATES_INVALID"
            )

        service = (
            self.sale_quantity_evidence_service
        )
        analyzer = getattr(
            service,
            "analyze",
            None,
        )

        if not callable(analyzer):
            quantity = self._quantity_unavailable(
                "RETURN_SALE_QUANTITY_EVIDENCE_SERVICE_UNAVAILABLE"
            )
        else:
            try:
                quantity = analyzer(
                    candidates,
                    return_schema=(
                        dict(return_evidence or {})
                        .get("return_schema")
                        or "FBO"
                    ),
                )
            except Exception:
                quantity = self._quantity_unavailable(
                    "RETURN_SALE_QUANTITY_EVIDENCE_EXCEPTION"
                )

        if not isinstance(quantity, dict):
            quantity = self._quantity_unavailable(
                "RETURN_SALE_QUANTITY_EVIDENCE_INVALID"
            )

        result = dict(base)
        available = (
            quantity.get("error") is False
            and quantity.get("status")
            in {
                "PERIOD_PROFIT_RETURN_SALE_QUANTITY_EVIDENCE_READY",
                "PERIOD_PROFIT_RETURN_SALE_QUANTITY_EVIDENCE_PARTIAL",
            }
        )

        result[
            "originating_sale_quantity_evidence_available"
        ] = available
        result[
            "originating_sale_quantity_evidence_status"
        ] = quantity.get("status")
        result[
            "originating_sale_quantity_evidence_confirmed"
        ] = (
            quantity.get(
                "quantity_consistency_confirmed"
            )
            is True
            if available
            else False
        )
        result[
            "originating_sale_quantity_evidence_records"
        ] = (
            list(quantity.get("records") or [])
            if available
            else []
        )
        result[
            "originating_sale_quantity_candidate_group_count"
        ] = (
            quantity.get("candidate_group_count")
            if available
            else None
        )
        result[
            "originating_sale_quantity_confirmed_group_count"
        ] = (
            quantity.get("confirmed_group_count")
            if available
            else None
        )
        result[
            "originating_sale_quantity_exceeding_group_count"
        ] = (
            quantity.get("exceeding_group_count")
            if available
            else None
        )
        result[
            "originating_sale_quantity_missing_group_count"
        ] = (
            quantity.get("missing_group_count")
            if available
            else None
        )
        result[
            "originating_sale_quantity_ambiguous_group_count"
        ] = (
            quantity.get("ambiguous_group_count")
            if available
            else None
        )
        result[
            "originating_sale_quantity_unavailable_group_count"
        ] = (
            quantity.get("unavailable_group_count")
            if available
            else None
        )
        result[
            "originating_sale_quantity_matching_basis"
        ] = (
            quantity.get("matching_basis")
            if available
            else None
        )

        # v1301-v1310 deliberately adds source evidence only. The existing
        # accounting gate is not promoted until timing and compensation
        # treatment are independently evidence-bound in a later package.
        result[
            "originating_sale_quantity_confirmed"
        ] = False
        result[
            "originating_sale_quantity_gate_promoted"
        ] = False
        result[
            "period_cogs_recovery_confirmed"
        ] = False
        result[
            "accounting_cogs_recovery_confirmed"
        ] = False
        result[
            "confirmed_cogs_recovery_amount"
        ] = 0.0
        result[
            "profit_adjustment_allowed"
        ] = False
        result[
            "automatic_recovery_allowed"
        ] = False
        result[
            "read_only"
        ] = True
        result[
            "executed"
        ] = False

        return result

    @staticmethod
    def _quantity_unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "PERIOD_PROFIT_RETURN_SALE_QUANTITY_EVIDENCE_UNAVAILABLE"
            ),
            "quantity_consistency_confirmed": False,
        }

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_UNAVAILABLE"
            ),
            "originating_sale_quantity_confirmed": False,
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
