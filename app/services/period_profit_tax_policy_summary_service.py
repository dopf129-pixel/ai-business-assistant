from math import isfinite


class PeriodProfitTaxPolicySummaryService:
    """Recompute Period Profit tax from the configured tax policy, read-only."""

    SUPPORTED_MODES = {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}

    def __init__(self, base_service, tax_service, tax_policy_result):
        self.base_service = base_service
        self.tax_service = tax_service
        self.tax_policy_result = tax_policy_result
        self.tax_rate = self._compatibility_tax_fraction()

    def calculate(self, date_from, date_to, products):
        calculator = getattr(self.base_service, "calculate", None)
        if not callable(calculator):
            return self._error("PERIOD_PROFIT_TAX_BASE_UNAVAILABLE")
        try:
            base = calculator(date_from, date_to, products)
        except Exception:
            return self._error("PERIOD_PROFIT_TAX_BASE_EXCEPTION")
        if not isinstance(base, dict):
            return self._error("PERIOD_PROFIT_TAX_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._error("PERIOD_PROFIT_TAX_BASE_INVALID")

        policy = self._policy()
        if policy is None:
            return self._error("PERIOD_PROFIT_TAX_POLICY_UNAVAILABLE")

        mode = self._text(policy.get("mode")).upper()
        if mode not in self.SUPPORTED_MODES:
            return self._error("PERIOD_PROFIT_TAX_MODE_UNSUPPORTED")

        result = dict(base)
        products_result = []
        for product in base.get("products") or []:
            if not isinstance(product, dict):
                return self._error("PERIOD_PROFIT_TAX_PRODUCT_INVALID")
            adjusted = self._recalculate_record(dict(product), policy)
            if adjusted.get("error") is True:
                return adjusted
            products_result.append(adjusted)

        adjusted_total = self._recalculate_record(result, policy)
        if adjusted_total.get("error") is True:
            return adjusted_total
        adjusted_total["products"] = products_result
        adjusted_total["tax_policy_mode"] = mode
        adjusted_total["tax_policy_applied"] = True
        adjusted_total["profit_scope"] = (
            "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V3"
            if adjusted_total.get("account_level_ozon_accruals_included") is True
            else "OZON_ACCRUALS_COST_AND_CONFIGURED_TAX_V3"
        )
        return adjusted_total

    def _recalculate_record(self, record, policy):
        revenue = self._number(record.get("revenue"))
        net_accrual = self._number(record.get("net_accrual"))
        product_cost = self._number(record.get("product_cost"))
        if revenue is None or net_accrual is None or product_cost is None:
            return self._error("PERIOD_PROFIT_TAX_INPUT_INVALID")

        pre_tax_profit = net_accrual - product_cost
        if not isfinite(pre_tax_profit):
            return self._error("PERIOD_PROFIT_TAX_INPUT_INVALID")

        calculation = self._calculate_tax(policy, revenue, pre_tax_profit)
        if calculation is None:
            return self._error("PERIOD_PROFIT_TAX_CALCULATION_UNAVAILABLE")

        tax_amount = self._number(calculation.get("tax_amount"))
        if tax_amount is None or tax_amount < 0.0:
            return self._error("PERIOD_PROFIT_TAX_CALCULATION_INVALID")
        profit = pre_tax_profit - tax_amount
        if not isfinite(profit):
            return self._error("PERIOD_PROFIT_TAX_CALCULATION_INVALID")

        adjusted = dict(record)
        adjusted["tax"] = round(tax_amount, 2)
        adjusted["profit"] = round(profit, 2)
        adjusted["margin_percent"] = self._margin(profit, revenue)
        adjusted["tax_mode"] = calculation.get("mode")
        adjusted["tax_base"] = calculation.get("tax_base")
        adjusted["tax_rate_percent"] = calculation.get("tax_rate")
        adjusted["minimum_tax_rate_percent"] = calculation.get("minimum_tax_rate")
        adjusted["regular_tax"] = calculation.get("regular_tax")
        adjusted["minimum_tax"] = calculation.get("minimum_tax")
        return adjusted

    def _calculate_tax(self, policy, revenue, pre_tax_profit):
        calculate = getattr(self.tax_service, "calculate", None)
        if not callable(calculate):
            return None
        try:
            result = calculate(
                policy.get("mode"),
                revenue,
                pre_tax_profit,
                tax_rate=policy.get("tax_rate"),
                minimum_tax_rate=policy.get("minimum_tax_rate", 1.0),
            )
        except Exception:
            return None
        if not isinstance(result, dict) or result.get("error") is not False:
            return None
        return result

    def _policy(self):
        source = self.tax_policy_result
        if not isinstance(source, dict):
            return None
        if source.get("error") is not False or source.get("configured") is not True:
            return None
        policy = source.get("policy")
        return dict(policy) if isinstance(policy, dict) else None

    def _compatibility_tax_fraction(self):
        policy = self._policy()
        if policy is None:
            return None
        mode = self._text(policy.get("mode")).upper()
        if mode == "NONE":
            return 0.0
        if mode != "USN_INCOME":
            return None
        rate = self._number(policy.get("tax_rate"))
        if rate is None or rate < 0.0 or rate > 100.0:
            return None
        return rate / 100.0

    @staticmethod
    def _number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if isfinite(number) else None

    @staticmethod
    def _text(value):
        return "" if value is None else str(value).strip()

    @staticmethod
    def _margin(profit, revenue):
        if revenue == 0.0:
            return 0.0
        margin = profit / revenue * 100.0
        return round(margin, 2) if isfinite(margin) else None

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
        }
