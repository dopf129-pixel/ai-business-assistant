"""Build a historical pre-ad projection from exact, already-included ads only."""

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class ProductUnitEconomicsHistoricalPreAdMarginService:
    ADVERTISING_KINDS = ("CPC", "CPO", "OTHER")
    IDENTITY_FIELDS = (
        "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
    )
    MAX_AMOUNT = Decimal("999999999999.99")

    def build(self, metric, advertising_evidence=None, expected_identity=None, period=None):
        """Return UNAVAILABLE unless evidence proves exact identity, period, and ownership."""
        source_periods = self._periods(period)
        common = {
            "schema_version": 1,
            "basis": "HISTORICAL_RECONCILIATION",
            "tax_basis": "AS_RECORDED_IN_PERIOD_RESULT",
            "tax_provenance": "EXISTING_HISTORICAL_QUERY_RESULT",
            "revenue_basis": "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS",
            "currency": "RUB",
            "unit_basis": "SUCCESSFUL_UNITS_IN_PERIOD",
            "source_periods": source_periods,
            "after_ad": self._after_values(metric),
            "read_only": True,
            "executed": False,
        }

        if not isinstance(metric, dict):
            return self._unavailable(common, metric, "HISTORICAL_PERIOD_RESULT_UNAVAILABLE")
        units = metric.get("units_sold")
        if type(units) is not int or units <= 0:
            return self._unavailable(common, metric, "HISTORICAL_SUCCESSFUL_UNITS_UNAVAILABLE")
        revenue = self._amount(metric.get("revenue"))
        if revenue is None or revenue <= 0:
            return self._unavailable(common, metric, "HISTORICAL_SELLER_REVENUE_UNAVAILABLE")
        net_profit = self._amount(metric.get("net_profit"))
        tax = self._amount(metric.get("tax"))
        if net_profit is None or tax is None:
            return self._unavailable(common, metric, "HISTORICAL_PERIOD_RESULT_INCOMPLETE")
        if not isinstance(advertising_evidence, dict):
            return self._unavailable(common, metric, "HISTORICAL_ADVERTISING_EVIDENCE_NOT_CONNECTED")
        if not self._identity_matches(
            advertising_evidence.get("identity"), expected_identity, metric,
        ):
            return self._unavailable(common, metric, "HISTORICAL_ADVERTISING_IDENTITY_UNCONFIRMED")
        financial = advertising_evidence.get("financial")
        if not isinstance(financial, dict) or advertising_evidence.get("error") is not False:
            return self._unavailable(common, metric, "HISTORICAL_ADVERTISING_EVIDENCE_INVALID")
        if not self._window_matches(financial.get("source_window"), period):
            return self._unavailable(common, metric, "HISTORICAL_ADVERTISING_PERIOD_MISMATCH")
        if (
            advertising_evidence.get("status") != "COMPLETE"
            or financial.get("complete_for_sku") is not True
            or financial.get("exact_sku_attribution_complete") is not True
            or financial.get("source_complete") is not True
            or financial.get("status") != "COMPLETE"
        ):
            return self._unavailable(common, metric, "HISTORICAL_ADVERTISING_SCOPE_INCOMPLETE")

        ad_total = self._already_included_ad_total(financial)
        if isinstance(ad_total, str):
            return self._unavailable(common, metric, ad_total)

        # Historical reconciliation deliberately preserves the existing tax.
        # It does not call TaxService or substitute a no-ad scenario tax.
        before_profit = (net_profit + ad_total).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        before_per_unit = (before_profit / Decimal(units)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        margin = (before_profit / revenue * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        result = self._unavailable(common, metric, None)
        result.update({
            "status": "AVAILABLE",
            "profit_rub": float(before_profit),
            "profit_per_unit_rub": float(before_per_unit),
            "margin_percent": float(margin),
            "tax_rub": float(tax),
            "advertising_status": "CONFIRMED_INCLUDED_IN_NET",
            "advertising": {
                "status": "COMPLETE",
                "amount_rub": float(ad_total),
                "source": "EXACT_SKU_SELLER_FINANCE",
                "included_in_net": True,
                "corrections_included_once": True,
                "performance_cpc_added": False,
            },
            "revenue_rub": float(revenue),
            "units_sold": units,
            "expense_scope": self._available_expense_scope(metric),
            "reason": None,
        })
        return result

    def _already_included_ad_total(self, financial):
        components = financial.get("component_status")
        if not isinstance(components, dict):
            return "HISTORICAL_ADVERTISING_COMPONENTS_INCOMPLETE"
        total = Decimal("0.00")
        for kind in self.ADVERTISING_KINDS:
            item = components.get(kind)
            if not isinstance(item, dict) or item.get("status") != "COMPLETE":
                return "HISTORICAL_ADVERTISING_SCOPE_INCOMPLETE"
            base = self._amount(item.get("base_included_expense_rub"))
            if base is None:
                return "HISTORICAL_ADVERTISING_COMPONENTS_INCOMPLETE"
            if base < 0:
                return "HISTORICAL_ADVERTISING_NET_CREDIT_REQUIRES_REVIEW"
            for key in (
                "additional_sku_expense_rub",
                "reconciliation_only_expense_rub",
                "account_level_expense_rub",
                "window_allocated_expense_rub",
            ):
                amount = self._amount(item.get(key))
                if amount is None or amount != 0:
                    return "HISTORICAL_ADVERTISING_OWNERSHIP_MISMATCH"
            total += base

        for key in (
            "account_component_count", "unmapped_account_component_count",
            "window_component_count", "unmapped_advertising_count",
        ):
            if type(financial.get(key)) is not int or financial[key] != 0:
                return "HISTORICAL_ADVERTISING_OWNERSHIP_MISMATCH"
        for key in ("account_level_expense_rub", "window_allocated_expense_rub"):
            amount = self._amount(financial.get(key))
            if amount is None or amount != 0:
                return "HISTORICAL_ADVERTISING_OWNERSHIP_MISMATCH"
        primary = self._amount(financial.get("sku_primary_expense_rub"))
        known = self._amount(financial.get("known_sku_scoped_expense_rub"))
        if primary != 0 or known != total:
            return "HISTORICAL_ADVERTISING_OWNERSHIP_MISMATCH"
        return total

    def _unavailable(self, common, metric, reason):
        tax = self._amount(metric.get("tax")) if isinstance(metric, dict) else None
        cost = self._amount(metric.get("product_cost")) if isinstance(metric, dict) else None
        return {
            **common,
            "status": "UNAVAILABLE",
            "profit_rub": None,
            "profit_per_unit_rub": None,
            "margin_percent": None,
            "tax_rub": float(tax) if tax is not None else None,
            "advertising_status": "UNKNOWN",
            "advertising": {
                "status": "UNKNOWN", "amount_rub": None,
                "source": "EXACT_SKU_SELLER_FINANCE", "included_in_net": None,
                "corrections_included_once": False, "performance_cpc_added": False,
            },
            "expense_scope": {
                "status": "UNKNOWN",
                "known_non_ad_expenses_rub": {"COGS": float(cost)} if cost is not None else {},
                "included_expense_keys": ["COGS"] if cost is not None else [],
                "confirmed_zero_expense_keys": [],
                "unknown_non_ad_expense_keys": [
                    "STORAGE", "RETURNS_AND_CANCELLATIONS", "UNMAPPED_NON_AD_EXPENSES",
                ],
                "excluded_expense_keys": ["FIXED_STORE_OVERHEAD"],
                "excluded_expense_reasons": {
                    "FIXED_STORE_OVERHEAD": "OUTSIDE_SKU_CONTRIBUTION_SCOPE",
                },
            },
            "reason": reason,
        }

    def _available_expense_scope(self, metric):
        scope = self._unavailable({}, metric, None)["expense_scope"]
        scope["status"] = "PARTIAL"
        return scope

    @classmethod
    def _identity_matches(cls, actual, expected, metric):
        if (
            not isinstance(actual, dict) or not isinstance(expected, dict)
            or set(actual) != set(cls.IDENTITY_FIELDS)
            or set(expected) != set(cls.IDENTITY_FIELDS)
            or any(not isinstance(actual.get(k), str) or not actual[k].strip() for k in cls.IDENTITY_FIELDS)
            or any(not isinstance(expected.get(k), str) or not expected[k].strip() for k in cls.IDENTITY_FIELDS)
        ):
            return False
        return (
            actual == expected
            and actual["sku"] == str(metric.get("sku") or "").strip()
            and actual["product_id"] == str(metric.get("product_id") or "").strip()
        )

    @classmethod
    def _window_matches(cls, actual, period):
        if not isinstance(actual, dict) or not isinstance(period, dict):
            return False
        date_from = period.get("date_from")
        date_to = period.get("date_to")
        timezone = actual.get("timezone")
        return (
            cls._valid_date(date_from) and cls._valid_date(date_to)
            and date_from <= date_to
            and actual.get("from_date") == date_from
            and actual.get("to_date") == date_to
            and actual.get("date_basis") == "OZON_ACCRUAL_DATE"
            and isinstance(timezone, str) and bool(timezone.strip()) and timezone != "UNKNOWN"
        )

    @staticmethod
    def _periods(period):
        if not isinstance(period, dict):
            return {}
        date_from = period.get("date_from")
        date_to = period.get("date_to")
        if not ProductUnitEconomicsHistoricalPreAdMarginService._valid_date(date_from):
            return {}
        if not ProductUnitEconomicsHistoricalPreAdMarginService._valid_date(date_to):
            return {}
        if date_from > date_to:
            return {}
        return {"historical_window": {
            "date_from": date_from, "date_to": date_to,
            "date_basis": "OZON_ACCRUAL_DATE",
        }}

    @staticmethod
    def _valid_date(value):
        if not isinstance(value, str) or len(value) != 10:
            return False
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat() == value
        except ValueError:
            return False

    @classmethod
    def _amount(cls, value):
        if isinstance(value, bool) or value in (None, "") or len(str(value)) > 32:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        if not amount.is_finite() or abs(amount) > cls.MAX_AMOUNT:
            return None
        try:
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None

    @staticmethod
    def _after_values(metric):
        if not isinstance(metric, dict):
            return {"profit_rub": None, "profit_per_unit_rub": None, "margin_percent": None}
        return {
            "profit_rub": metric.get("net_profit"),
            "profit_per_unit_rub": metric.get("profit_per_unit"),
            "margin_percent": metric.get("margin_percent"),
        }
