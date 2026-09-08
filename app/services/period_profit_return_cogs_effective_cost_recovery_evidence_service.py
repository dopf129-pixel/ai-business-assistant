from services.period_profit_return_cogs_recovery_evidence_service import (
    PeriodProfitReturnCogsRecoveryEvidenceService,
)


class PeriodProfitReturnCogsEffectiveCostRecoveryEvidenceService(
    PeriodProfitReturnCogsRecoveryEvidenceService
):
    """Resolve originating-sale COGS through the same effective-cost authority.

    Return COGS must use the seller-confirmed cost version that was effective on
    the matched originating-sale accrual date. That authority can be either a
    bounded historical interval or an append-only operational cost switch.

    Mutable current ``product_costs`` values are never accepted here.
    """

    def _historical_cost_evidence(self, record, sale_date):
        getter = getattr(
            self.cost_service,
            "get_effective_cost_evidence",
            None,
        )
        if not callable(getter):
            return self._unavailable_effective_cost(
                "PERIOD_PROFIT_RETURN_COGS_EFFECTIVE_COST_RESOLVER_UNAVAILABLE"
            )

        try:
            result = getter(
                at_date=sale_date,
                product_id=record.get("product_id"),
                sku=record.get("sku"),
                offer_id=record.get("offer_id"),
            )
        except Exception:
            return self._unavailable_effective_cost(
                "PERIOD_PROFIT_RETURN_COGS_EFFECTIVE_COST_RESOLVER_EXCEPTION"
            )

        if not isinstance(result, dict):
            return self._unavailable_effective_cost(
                "PERIOD_PROFIT_RETURN_COGS_EFFECTIVE_COST_RESULT_INVALID"
            )

        evidence = dict(result)
        if (
            evidence.get("error") is False
            and evidence.get("effective_cost_confirmed") is True
            and evidence.get("historical_cost_confirmed") is True
            and evidence.get("cost_basis")
            in {
                "SELLER_CONFIRMED_BOUNDED_PERIOD",
                "SELLER_CONFIRMED_OPERATIONAL_SWITCH",
            }
        ):
            original_status = evidence.get("status")
            evidence["effective_cost_evidence_status"] = original_status
            # The base recovery service's historical_* fields mean
            # "originating-sale cost basis", not "row came from history table".
            # Normalize the ready status so the existing conservative gate can
            # consume either approved effective-cost evidence form.
            evidence["status"] = "PRODUCT_COST_HISTORY_READY"
            return evidence

        return evidence

    @staticmethod
    def _unavailable_effective_cost(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE",
            "effective_cost_confirmed": False,
            "historical_cost_confirmed": False,
            "cost_price": None,
            "effective_from": None,
            "effective_through": None,
            "source": None,
            "cost_basis": None,
        }
