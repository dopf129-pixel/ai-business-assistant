from services.period_profit_realization_offer_quantity_summary_service import (
    PeriodProfitRealizationOfferQuantitySummaryService,
)


class PeriodProfitDiagnosticQuantitySummaryService(
    PeriodProfitRealizationOfferQuantitySummaryService
):
    """Expose the exact safe effective-cost blocker without leaking seller data.

    The effective-cost reconciliation historically collapsed every cost failure into
    PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE. That made live diagnosis impossible:
    missing history, a not-yet-effective row, identity ambiguity, and storage errors
    all looked identical. This adapter preserves the same fail-closed behavior while
    carrying only the existing machine-readable error code to the final result.
    """

    GENERIC_EFFECTIVE_COST_CODE = "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"
    MISSING_EFFECTIVE_COST_CODE = "PERIOD_PROFIT_COST_HISTORY_MISSING"

    def _effective_cost_evidence(self, row, accrual_date):
        self._effective_cost_diagnostic_code = None
        getter = getattr(self.cost_service, "get_effective_cost_evidence", None)
        if not callable(getter):
            self._effective_cost_diagnostic_code = (
                "PERIOD_PROFIT_COST_SERVICE_UNAVAILABLE"
            )
            return None

        try:
            evidence = getter(
                accrual_date,
                product_id=row.get("product_id"),
                sku=row.get("sku"),
                offer_id=row.get("offer_id"),
            )
        except Exception:
            self._effective_cost_diagnostic_code = (
                "PERIOD_PROFIT_COST_SERVICE_EXCEPTION"
            )
            return None

        if not isinstance(evidence, dict):
            self._effective_cost_diagnostic_code = (
                "PERIOD_PROFIT_COST_RESPONSE_INVALID"
            )
            return None

        # A historical finance SKU can be retired while the already-proven product
        # identity carries a newer catalog SKU.  Cost storage may therefore only know
        # that catalog SKU.  Retry through it strictly after a pure missing result;
        # ambiguous, not-effective, malformed, or unavailable evidence must remain
        # fail-closed and must never be bypassed by an alias lookup.
        first_code = str(evidence.get("code") or "").strip()
        catalog_sku = self._text(row.get("catalog_sku"))
        finance_sku = self._text(row.get("sku"))
        if (
            evidence.get("error") is True
            and first_code == self.MISSING_EFFECTIVE_COST_CODE
            and catalog_sku
            and catalog_sku != finance_sku
        ):
            try:
                evidence = getter(
                    accrual_date,
                    product_id=row.get("product_id"),
                    sku=catalog_sku,
                    offer_id=row.get("offer_id"),
                )
            except Exception:
                self._effective_cost_diagnostic_code = (
                    "PERIOD_PROFIT_COST_SERVICE_EXCEPTION"
                )
                return None
            if not isinstance(evidence, dict):
                self._effective_cost_diagnostic_code = (
                    "PERIOD_PROFIT_COST_RESPONSE_INVALID"
                )
                return None

        if (
            evidence.get("error") is True
            or evidence.get("effective_cost_confirmed") is not True
            or evidence.get("historical_cost_confirmed") is not True
        ):
            code = str(evidence.get("code") or "").strip()
            if code.startswith(("PERIOD_PROFIT_", "PRODUCT_COST_")):
                self._effective_cost_diagnostic_code = code
            else:
                self._effective_cost_diagnostic_code = self.GENERIC_EFFECTIVE_COST_CODE
            return None

        return evidence

    def _quantity_error(self, code):
        diagnostic_code = code
        if code == self.GENERIC_EFFECTIVE_COST_CODE:
            candidate = str(
                getattr(self, "_effective_cost_diagnostic_code", None) or ""
            ).strip()
            if candidate.startswith(("PERIOD_PROFIT_", "PRODUCT_COST_")):
                diagnostic_code = candidate

        return {
            "error": True,
            "code": diagnostic_code,
            "status": "PERIOD_PROFIT_SALE_QUANTITY_UNAVAILABLE",
            "message": "Данные о количестве проданных товаров недоступны",
            "complete": False,
            "read_only": True,
            "executed": False,
        }
