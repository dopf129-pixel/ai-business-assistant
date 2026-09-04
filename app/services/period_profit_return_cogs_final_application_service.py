from math import isfinite


class PeriodProfitReturnCogsFinalApplicationService:
    """Apply already-committed Return COGS to a read-only Period Profit result."""

    APPLIED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_APPLIED"
    NOT_APPLIED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_NOT_APPLIED"

    def __init__(self, tax_service, tax_policy_result):
        self.tax_service = tax_service
        self.tax_policy_result = tax_policy_result

    def apply(self, summary, evidence):
        if not isinstance(summary, dict) or summary.get("error") is not False:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_SUMMARY_INVALID")
        if evidence is None:
            return self._not_applied(summary, None)
        if not isinstance(evidence, dict):
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_EVIDENCE_INVALID")
        if evidence.get("error") is True:
            return self._not_applied(summary, evidence)
        if evidence.get("error") is not False:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_EVIDENCE_INVALID")

        if evidence.get("return_cogs_profit_application_commit_confirmed") is not True:
            return self._not_applied(summary, evidence)
        if evidence.get("return_cogs_profit_application_eligibility_confirmed") is not True:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_ELIGIBILITY_REQUIRED")

        records = evidence.get("return_cogs_profit_application_commit_records")
        if not isinstance(records, list) or not records:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_RECORDS_REQUIRED")

        committed_total = 0.0
        seen_recognitions = set()
        for record in records:
            if not isinstance(record, dict) or record.get("application_commit_confirmed") is not True:
                return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_INVALID")
            recognition_id = self._positive_int(record.get("recognition_history_id"))
            amount = self._money(record.get("committed_amount"))
            currency = self._text(record.get("currency")).upper()
            if recognition_id is None or recognition_id in seen_recognitions:
                return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_VERSION_INVALID")
            if amount is None or currency != "RUB":
                return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_AMOUNT_INVALID")
            seen_recognitions.add(recognition_id)
            committed_total += amount
            if not isfinite(committed_total):
                return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_AMOUNT_INVALID")

        committed_total = round(committed_total, 2)
        eligible_total = self._money(evidence.get("return_cogs_profit_application_eligible_amount"))
        if eligible_total is None or abs(committed_total - eligible_total) > 0.01:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_TOTAL_MISMATCH")

        revenue = self._number(summary.get("revenue"))
        net_accrual = self._number(summary.get("net_accrual"))
        product_cost = self._number(summary.get("product_cost"))
        original_profit = self._number(summary.get("profit"))
        if None in (revenue, net_accrual, product_cost, original_profit):
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_SUMMARY_MONETARY_INVALID")

        pre_tax_profit = net_accrual - product_cost + committed_total
        if not isfinite(pre_tax_profit):
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_SUMMARY_MONETARY_INVALID")

        policy = self._policy()
        if policy is None:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_TAX_POLICY_UNAVAILABLE")
        tax = self._calculate_tax(policy, revenue, pre_tax_profit)
        if tax is None:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_TAX_UNAVAILABLE")
        tax_amount = self._number(tax.get("tax_amount"))
        if tax_amount is None or tax_amount < 0.0:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_TAX_INVALID")

        profit = pre_tax_profit - tax_amount
        if not isfinite(profit):
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_PROFIT_INVALID")
        margin = self._margin(profit, revenue)
        if margin is None:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_PROFIT_INVALID")

        adjusted_summary = dict(summary)
        adjusted_summary["period_profit_before_return_cogs"] = round(original_profit, 2)
        adjusted_summary["return_cogs_profit_application_amount"] = committed_total
        adjusted_summary["return_cogs_profit_applied"] = True
        adjusted_summary["tax"] = round(tax_amount, 2)
        adjusted_summary["profit"] = round(profit, 2)
        adjusted_summary["margin_percent"] = margin
        adjusted_summary["tax_mode"] = tax.get("mode")
        adjusted_summary["tax_base"] = tax.get("tax_base")
        adjusted_summary["tax_rate_percent"] = tax.get("tax_rate")
        adjusted_summary["minimum_tax_rate_percent"] = tax.get("minimum_tax_rate")
        adjusted_summary["regular_tax"] = tax.get("regular_tax")
        adjusted_summary["minimum_tax"] = tax.get("minimum_tax")
        adjusted_summary["return_cogs_profit_tax_recomputed"] = True
        adjusted_summary["profit_scope"] = "OZON_ACCOUNT_ACCRUALS_COST_COMMITTED_RETURN_COGS_AND_CONFIGURED_TAX_V4"

        adjusted_evidence = dict(evidence)
        adjusted_evidence["return_cogs_profit_applied"] = True
        adjusted_evidence["return_cogs_profit_application_amount"] = committed_total
        adjusted_evidence["profit_adjustment_allowed"] = True
        adjusted_evidence["automatic_recovery_allowed"] = False
        adjusted_evidence["compensation_profit_adjustment_allowed"] = False
        adjusted_evidence["read_only"] = True
        adjusted_evidence["executed"] = False

        return {
            "error": False,
            "status": self.APPLIED,
            "summary": adjusted_summary,
            "evidence": adjusted_evidence,
            "return_cogs_profit_applied": True,
            "return_cogs_profit_application_amount": committed_total,
            "tax_recomputed": True,
            "read_only": True,
            "executed": False,
        }

    def _not_applied(self, summary, evidence):
        adjusted_summary = dict(summary)
        adjusted_summary["period_profit_before_return_cogs"] = None
        adjusted_summary["return_cogs_profit_application_amount"] = None
        adjusted_summary["return_cogs_profit_applied"] = False
        adjusted_summary["return_cogs_profit_tax_recomputed"] = False
        adjusted_evidence = dict(evidence) if isinstance(evidence, dict) else evidence
        return {
            "error": False,
            "status": self.NOT_APPLIED,
            "summary": adjusted_summary,
            "evidence": adjusted_evidence,
            "return_cogs_profit_applied": False,
            "return_cogs_profit_application_amount": None,
            "tax_recomputed": False,
            "read_only": True,
            "executed": False,
        }

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

    @staticmethod
    def _positive_int(value):
        if isinstance(value, bool):
            return None
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _money(value):
        value = PeriodProfitReturnCogsFinalApplicationService._number(value)
        if value is None or value < 0.0:
            return None
        return round(value, 2)

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
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_UNAVAILABLE",
            "return_cogs_profit_applied": False,
            "return_cogs_profit_application_amount": None,
            "read_only": True,
            "executed": False,
        }
