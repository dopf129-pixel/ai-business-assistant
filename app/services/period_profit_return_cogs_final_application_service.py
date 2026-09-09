from math import isfinite


class PeriodProfitReturnCogsFinalApplicationService:
    """Apply already-committed Return COGS to a read-only Period Profit result."""

    APPLIED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_APPLIED"
    NOT_APPLIED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_NOT_APPLIED"
    ACCOUNTING_READY = "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY"
    RECOGNITION_READY = "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    APPLICATION_READY = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY"
    COMMIT_CONFIRMED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED"
    RECOGNITION_RECORD_READY = "RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    RECOGNIZED = "COGS_RECOVERY_RECOGNIZED"
    AUTHORIZATION_RECORD_READY = "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY"
    AUTHORIZED = "PROFIT_APPLICATION_AUTHORIZED"

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
        if self._text(evidence.get("return_cogs_profit_application_commit_status")).upper() != self.COMMIT_CONFIRMED:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_STATUS_REQUIRED")
        if evidence.get("return_cogs_profit_application_eligibility_confirmed") is not True:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_ELIGIBILITY_REQUIRED")
        if self._text(evidence.get("return_cogs_profit_application_eligibility_status")).upper() != self.APPLICATION_READY:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_ELIGIBILITY_STATUS_REQUIRED")
        if evidence.get("return_cogs_accounting_recognition_evidence_confirmed") is not True:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_REQUIRED")
        if self._text(evidence.get("return_cogs_accounting_recognition_status")).upper() != self.RECOGNITION_READY:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_STATUS_REQUIRED")
        if evidence.get("accounting_attribution_evidence_confirmed") is not True:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_ACCOUNTING_ATTRIBUTION_REQUIRED")
        if self._text(evidence.get("accounting_attribution_evidence_status")).upper() != self.ACCOUNTING_READY:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_ACCOUNTING_STATUS_REQUIRED")

        records = evidence.get("return_cogs_profit_application_commit_records")
        if not isinstance(records, list) or not records:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_RECORDS_REQUIRED")

        chain = self._validate_chain_records(evidence, records)
        if chain.get("error") is True:
            return self._unavailable(chain.get("code"))

        committed_total = chain.get("committed_total")
        if committed_total is None:
            return self._unavailable("RETURN_COGS_FINAL_APPLICATION_COMMIT_AMOUNT_INVALID")
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
        adjusted_evidence["return_cogs_final_application_chain_bound"] = True
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
            "return_cogs_final_application_chain_bound": True,
            "tax_recomputed": True,
            "read_only": True,
            "executed": False,
        }

    def _validate_chain_records(self, evidence, commit_records):
        recognition_records = evidence.get("return_cogs_accounting_recognition_evidence_records")
        authorization_records = evidence.get("return_cogs_profit_application_authorization_records")
        if not isinstance(recognition_records, list) or not recognition_records:
            return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_RECORDS_REQUIRED")
        if not isinstance(authorization_records, list) or not authorization_records:
            return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_RECORDS_REQUIRED")

        recognition_index = {}
        for record in recognition_records:
            if not isinstance(record, dict):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_RECORD_INVALID")
            history_id = self._positive_int(record.get("history_id"))
            if history_id is None or history_id in recognition_index:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_VERSION_INVALID")
            if record.get("error") is not False:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_RECORD_INVALID")
            if self._text(record.get("status")).upper() != self.RECOGNITION_RECORD_READY:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_RECORD_STATUS_REQUIRED")
            if record.get("accounting_recognition_confirmed") is not True:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_RECORD_CONFIRMATION_REQUIRED")
            if self._text(record.get("recognition_state")).upper() != self.RECOGNIZED:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_STATE_REQUIRED")
            if self._identity(record) is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_IDENTITY_INVALID")
            if self._money(record.get("recognized_amount")) is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_AMOUNT_INVALID")
            if self._text(record.get("currency")).upper() != "RUB":
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_CURRENCY_INVALID")
            if not self._text(record.get("recovery_accounting_date")):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_DATE_INVALID")
            recognition_index[history_id] = record

        authorization_index = {}
        for record in authorization_records:
            if not isinstance(record, dict):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_RECORD_INVALID")
            history_id = self._positive_int(record.get("history_id"))
            if history_id is None or history_id in authorization_index:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_VERSION_INVALID")
            if record.get("error") is not False:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_RECORD_INVALID")
            if self._text(record.get("status")).upper() != self.AUTHORIZATION_RECORD_READY:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_RECORD_STATUS_REQUIRED")
            if record.get("application_authorization_confirmed") is not True:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_CONFIRMATION_REQUIRED")
            if self._text(record.get("application_state")).upper() != self.AUTHORIZED:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_STATE_REQUIRED")
            if record.get("application_already_applied") is not False:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_ALREADY_APPLIED_INVALID")
            if self._identity(record) is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_IDENTITY_INVALID")
            if self._money(record.get("authorized_amount")) is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_AMOUNT_INVALID")
            if self._text(record.get("currency")).upper() != "RUB":
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_CURRENCY_INVALID")
            if not self._text(record.get("recovery_accounting_date")):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_DATE_INVALID")
            authorization_index[history_id] = record

        committed_total = 0.0
        seen_recognitions = set()
        seen_authorizations = set()
        for record in commit_records:
            if not isinstance(record, dict) or record.get("application_commit_confirmed") is not True:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_COMMIT_INVALID")
            recognition_id = self._positive_int(record.get("recognition_history_id"))
            authorization_id = self._positive_int(record.get("authorization_history_id"))
            amount = self._money(record.get("committed_amount"))
            currency = self._text(record.get("currency")).upper()
            accounting_date = self._text(record.get("recovery_accounting_date"))
            identity = self._identity(record)
            if recognition_id is None or recognition_id in seen_recognitions:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_COMMIT_VERSION_INVALID")
            if authorization_id is None or authorization_id in seen_authorizations:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_VERSION_INVALID")
            recognition = recognition_index.get(recognition_id)
            authorization = authorization_index.get(authorization_id)
            if recognition is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_COMMIT_RECOGNITION_BINDING_REQUIRED")
            if authorization is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_COMMIT_AUTHORIZATION_BINDING_REQUIRED")
            if identity is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_COMMIT_IDENTITY_INVALID")
            if identity != self._identity(recognition) or identity != self._identity(authorization):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_CHAIN_IDENTITY_MISMATCH")
            if self._positive_int(authorization.get("recognition_history_id")) != recognition_id:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_CHAIN_VERSION_MISMATCH")
            if accounting_date != self._text(recognition.get("recovery_accounting_date")):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_CHAIN_DATE_MISMATCH")
            if accounting_date != self._text(authorization.get("recovery_accounting_date")):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_CHAIN_DATE_MISMATCH")
            if amount is None or currency != "RUB":
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_COMMIT_AMOUNT_INVALID")
            recognized_amount = self._money(recognition.get("recognized_amount"))
            authorized_amount = self._money(authorization.get("authorized_amount"))
            if recognized_amount is None or authorized_amount is None:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_CHAIN_AMOUNT_INVALID")
            if abs(amount - recognized_amount) > 0.01 or abs(amount - authorized_amount) > 0.01:
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_CHAIN_AMOUNT_MISMATCH")
            seen_recognitions.add(recognition_id)
            seen_authorizations.add(authorization_id)
            committed_total += amount
            if not isfinite(committed_total):
                return self._chain_error("RETURN_COGS_FINAL_APPLICATION_COMMIT_AMOUNT_INVALID")

        if seen_recognitions != set(recognition_index):
            return self._chain_error("RETURN_COGS_FINAL_APPLICATION_RECOGNITION_COVERAGE_MISMATCH")
        if seen_authorizations != set(authorization_index):
            return self._chain_error("RETURN_COGS_FINAL_APPLICATION_AUTHORIZATION_COVERAGE_MISMATCH")

        return {
            "error": False,
            "committed_total": round(committed_total, 2),
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

    @classmethod
    def _identity(cls, record):
        if not isinstance(record, dict):
            return None
        values = tuple(
            cls._text(record.get(key))
            for key in ("return_id", "posting_number", "sku")
        )
        return values if all(values) else None

    @staticmethod
    def _margin(profit, revenue):
        if revenue == 0.0:
            return 0.0
        margin = profit / revenue * 100.0
        return round(margin, 2) if isfinite(margin) else None

    @staticmethod
    def _chain_error(code):
        return {"error": True, "code": code}

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
