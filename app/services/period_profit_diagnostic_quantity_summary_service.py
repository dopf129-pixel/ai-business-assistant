from services.period_profit_realization_offer_quantity_summary_service import (
    PeriodProfitRealizationOfferQuantitySummaryService,
)
from services.period_profit_cost_exclusion_context import cost_excluded


class PeriodProfitDiagnosticQuantitySummaryService(
    PeriodProfitRealizationOfferQuantitySummaryService
):
    """Expose safe Period Profit diagnostics without leaking seller identifiers."""

    GENERIC_EFFECTIVE_COST_CODE = "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE"
    MISSING_EFFECTIVE_COST_CODE = "PERIOD_PROFIT_COST_HISTORY_MISSING"

    def calculate(self, date_from, date_to, products):
        preparer = getattr(self.finance_service, "prepare_read_session", None)
        if callable(preparer):
            try:
                preparer(date_from, date_to)
            except Exception:
                return self._quantity_error(
                    "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE"
                )
        return super().calculate(date_from, date_to, products)

    def _effective_cost_evidence(self, row, accrual_date):
        if cost_excluded():
            return {
                "error": False,
                "effective_cost_confirmed": True,
                "historical_cost_confirmed": True,
                "cost_price": 0.0,
                "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
                "effective_from": str(accrual_date),
                "effective_through": str(accrual_date),
                "history_id": "PRE_COGS_VIEW",
                "source": "PERIOD_PROFIT_PRE_COGS_VIEW",
            }
        self._effective_cost_diagnostic_code = None
        self._effective_cost_trace = None
        getter = getattr(self.cost_service, "get_effective_cost_evidence", None)
        if not callable(getter):
            self._effective_cost_diagnostic_code = (
                "PERIOD_PROFIT_COST_SERVICE_UNAVAILABLE"
            )
            return None

        finance_sku = self._text(row.get("sku"))
        catalog_sku = self._text(row.get("catalog_sku"))
        product_id = self._text(row.get("product_id"))
        offer_id = self._text(row.get("offer_id"))

        trace = {
            "product_id_present": bool(product_id),
            "offer_id_present": bool(offer_id),
            "finance_sku_present": bool(finance_sku),
            "catalog_sku_present": bool(catalog_sku),
            "catalog_sku_differs": bool(
                catalog_sku and finance_sku and catalog_sku != finance_sku
            ),
            "identity_recovered": bool(row.get("historical_sku_identity_recovered")),
            "primary_lookup_code": None,
            "catalog_lookup_attempted": False,
            "catalog_lookup_code": None,
            "product_id_lookup_code": None,
            "offer_id_lookup_code": None,
            "finance_sku_lookup_code": None,
            "catalog_sku_lookup_code": None,
            "current_cost_present": None,
            "current_cost_date_relation": None,
        }

        try:
            evidence = getter(
                accrual_date,
                product_id=product_id or None,
                sku=finance_sku or None,
                offer_id=offer_id or None,
            )
        except Exception:
            self._effective_cost_diagnostic_code = (
                "PERIOD_PROFIT_COST_SERVICE_EXCEPTION"
            )
            self._effective_cost_trace = trace
            return None

        if not isinstance(evidence, dict):
            self._effective_cost_diagnostic_code = (
                "PERIOD_PROFIT_COST_RESPONSE_INVALID"
            )
            self._effective_cost_trace = trace
            return None

        first_code = str(evidence.get("code") or "").strip()
        trace["primary_lookup_code"] = first_code or "READY"

        if (
            evidence.get("error") is True
            and first_code == self.MISSING_EFFECTIVE_COST_CODE
            and catalog_sku
            and catalog_sku != finance_sku
        ):
            trace["catalog_lookup_attempted"] = True
            try:
                evidence = getter(
                    accrual_date,
                    product_id=product_id or None,
                    sku=catalog_sku,
                    offer_id=offer_id or None,
                )
            except Exception:
                self._effective_cost_diagnostic_code = (
                    "PERIOD_PROFIT_COST_SERVICE_EXCEPTION"
                )
                self._effective_cost_trace = trace
                return None
            if not isinstance(evidence, dict):
                self._effective_cost_diagnostic_code = (
                    "PERIOD_PROFIT_COST_RESPONSE_INVALID"
                )
                self._effective_cost_trace = trace
                return None
            trace["catalog_lookup_code"] = (
                str(evidence.get("code") or "").strip() or "READY"
            )

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

            trace.update(
                self._probe_cost_identities(
                    getter,
                    accrual_date,
                    product_id=product_id,
                    offer_id=offer_id,
                    finance_sku=finance_sku,
                    catalog_sku=catalog_sku,
                )
            )
            trace.update(
                self._probe_current_cost_relation(
                    accrual_date,
                    product_id=product_id,
                )
            )
            self._effective_cost_trace = trace
            return None

        return evidence

    def _probe_cost_identities(
        self,
        getter,
        accrual_date,
        product_id="",
        offer_id="",
        finance_sku="",
        catalog_sku="",
    ):
        result = {}
        probes = (
            ("product_id_lookup_code", {"product_id": product_id}) if product_id else None,
            ("offer_id_lookup_code", {"offer_id": offer_id}) if offer_id else None,
            ("finance_sku_lookup_code", {"sku": finance_sku}) if finance_sku else None,
            (
                "catalog_sku_lookup_code",
                {"sku": catalog_sku},
            )
            if catalog_sku
            else None,
        )
        for probe in probes:
            if probe is None:
                continue
            key, kwargs = probe
            try:
                evidence = getter(accrual_date, **kwargs)
            except Exception:
                result[key] = "EXCEPTION"
                continue
            if not isinstance(evidence, dict):
                result[key] = "INVALID"
                continue
            result[key] = str(evidence.get("code") or "").strip() or "READY"
        return result

    def _probe_current_cost_relation(self, accrual_date, product_id=""):
        if not product_id:
            return {}
        getter = getattr(self.cost_service, "get_cost", None)
        date_parser = getattr(self.cost_service, "_date", None)
        if not callable(getter) or not callable(date_parser):
            return {}
        try:
            row = getter(product_id)
        except Exception:
            return {"current_cost_present": "UNKNOWN"}
        if row is None:
            return {
                "current_cost_present": False,
                "current_cost_date_relation": "NO_CURRENT_ROW",
            }
        result = {"current_cost_present": True}
        if not isinstance(row, (tuple, list)) or len(row) < 6:
            result["current_cost_date_relation"] = "UNKNOWN"
            return result
        target = date_parser(accrual_date)
        updated_text = str(row[5] or "").strip()
        updated = date_parser(updated_text[:10]) if len(updated_text) >= 10 else None
        if target is None or updated is None:
            result["current_cost_date_relation"] = "UNKNOWN"
        elif updated <= target:
            result["current_cost_date_relation"] = "ON_OR_BEFORE_SALE"
        else:
            result["current_cost_date_relation"] = "AFTER_SALE"
        return result

    def _quantity_error(self, code):
        diagnostic_code = code
        if code == self.GENERIC_EFFECTIVE_COST_CODE:
            candidate = str(
                getattr(self, "_effective_cost_diagnostic_code", None) or ""
            ).strip()
            if candidate.startswith(("PERIOD_PROFIT_", "PRODUCT_COST_")):
                diagnostic_code = candidate

        result = {
            "error": True,
            "code": diagnostic_code,
            "status": "PERIOD_PROFIT_SALE_QUANTITY_UNAVAILABLE",
            "message": "Данные о количестве проданных товаров недоступны",
            "complete": False,
            "read_only": True,
            "executed": False,
        }
        trace = getattr(self, "_effective_cost_trace", None)
        if isinstance(trace, dict) and trace:
            result["cost_diagnostic_trace"] = dict(trace)
        return result
