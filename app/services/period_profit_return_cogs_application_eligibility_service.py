from math import isfinite


class PeriodProfitReturnCogsApplicationEligibilityService:
    """Prove Return COGS profit-application eligibility without changing profit."""

    READY = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY"
    BLOCKED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_BLOCKED"
    AUTHORIZATION_READY = "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY"
    AUTHORIZED = "PROFIT_APPLICATION_AUTHORIZED"
    MONETARY_AUTHORITY_EXCLUDED = "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL"

    def __init__(self, base_service, application_authorization_repository):
        self.base_service = base_service
        self.application_authorization_repository = application_authorization_repository

    def analyze(self, return_evidence, products):
        analyzer = getattr(self.base_service, "analyze", None)
        if not callable(analyzer):
            return self._unavailable("RETURN_COGS_APPLICATION_BASE_UNAVAILABLE")
        try:
            base = analyzer(return_evidence, products)
        except Exception:
            return self._unavailable("RETURN_COGS_APPLICATION_BASE_EXCEPTION")

        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_APPLICATION_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._unavailable("RETURN_COGS_APPLICATION_RESULT_INVALID")

        result = dict(base)
        blockers = []

        if base.get("return_cogs_accounting_recognition_evidence_confirmed") is not True:
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_REQUIRED")
        if base.get("period_cogs_recovery_confirmed") is not True:
            blockers.append("RETURN_COGS_PERIOD_RECOGNITION_REQUIRED")
        if base.get("accounting_cogs_recovery_confirmed") is not True:
            blockers.append("RETURN_COGS_ACCOUNTING_RECOVERY_REQUIRED")

        recognized_total = self._money(base.get("confirmed_cogs_recovery_amount"))
        if recognized_total is None:
            blockers.append("RETURN_COGS_RECOGNIZED_AMOUNT_REQUIRED")

        candidates = base.get("candidate_records")
        recognition_records = base.get("return_cogs_accounting_recognition_evidence_records")
        attribution_records = base.get("accounting_attribution_evidence_records")
        if not isinstance(candidates, list) or not candidates:
            blockers.append("RETURN_COGS_APPLICATION_CANDIDATES_REQUIRED")
            candidates = []
        if not isinstance(recognition_records, list):
            blockers.append("RETURN_COGS_APPLICATION_RECOGNITION_RECORDS_REQUIRED")
            recognition_records = []
        if not isinstance(attribution_records, list):
            blockers.append("RETURN_COGS_APPLICATION_ATTRIBUTION_RECORDS_REQUIRED")
            attribution_records = []

        candidate_index, issues = self._index(candidates, "CANDIDATE")
        blockers.extend(issues)
        recognition_index, issues = self._index(recognition_records, "RECOGNITION")
        blockers.extend(issues)
        attribution_index, issues = self._index(attribution_records, "ATTRIBUTION")
        blockers.extend(issues)
        candidate_keys = set(candidate_index)
        if set(recognition_index) != candidate_keys:
            blockers.append("RETURN_COGS_APPLICATION_RECOGNITION_COVERAGE_REQUIRED")
        if set(attribution_index) != candidate_keys:
            blockers.append("RETURN_COGS_APPLICATION_ATTRIBUTION_COVERAGE_REQUIRED")

        getter = getattr(
            self.application_authorization_repository,
            "get_application_authorization",
            None,
        )
        if not callable(getter):
            blockers.append("RETURN_COGS_APPLICATION_AUTHORIZATION_REPOSITORY_REQUIRED")

        authorization_records = []
        authorization_total = 0.0
        for key in sorted(candidate_keys):
            recognition = recognition_index.get(key)
            attribution = attribution_index.get(key)
            if recognition is None or attribution is None or not callable(getter):
                continue

            history_id = self._positive_int(recognition.get("history_id"))
            recognized_amount = self._money(recognition.get("recognized_amount"))
            recognized_currency = self._text(recognition.get("currency")).upper()
            recognized_date = self._text(recognition.get("recovery_accounting_date"))
            if history_id is None:
                blockers.append("RETURN_COGS_APPLICATION_RECOGNITION_VERSION_REQUIRED")
                continue
            if recognition.get("accounting_recognition_confirmed") is not True:
                blockers.append("RETURN_COGS_APPLICATION_ACTIVE_RECOGNITION_REQUIRED")
            if self._text(recognition.get("recognition_state")).upper() != "COGS_RECOVERY_RECOGNIZED":
                blockers.append("RETURN_COGS_APPLICATION_ACTIVE_RECOGNITION_REQUIRED")
            if recognized_amount is None:
                blockers.append("RETURN_COGS_APPLICATION_RECOGNIZED_AMOUNT_REQUIRED")
            if recognized_currency != "RUB":
                blockers.append("RETURN_COGS_APPLICATION_RECOGNIZED_CURRENCY_RUB_REQUIRED")
            if not recognized_date:
                blockers.append("RETURN_COGS_APPLICATION_RECOGNIZED_PERIOD_REQUIRED")
            if attribution.get("recovery_accounting_period_matches_request") is not True:
                blockers.append("RETURN_COGS_APPLICATION_PERIOD_MATCH_REQUIRED")
            if self._text(attribution.get("recovery_accounting_date")) != recognized_date:
                blockers.append("RETURN_COGS_APPLICATION_PERIOD_RECONCILIATION_REQUIRED")
            if attribution.get("compensation_double_count_clear") is not True:
                blockers.append("RETURN_COGS_APPLICATION_COMPENSATION_DOUBLE_COUNT_CLEAR_REQUIRED")

            try:
                record = getter(history_id, *key)
            except Exception:
                blockers.append("RETURN_COGS_APPLICATION_AUTHORIZATION_REPOSITORY_EXCEPTION")
                continue
            if not isinstance(record, dict):
                blockers.append("RETURN_COGS_APPLICATION_AUTHORIZATION_RECORD_INVALID")
                continue

            normalized = dict(record)
            authorization_records.append(normalized)
            if record.get("error") is True:
                blockers.append("RETURN_COGS_APPLICATION_AUTHORIZATION_UNAVAILABLE")
                continue
            if record.get("error") is not False:
                blockers.append("RETURN_COGS_APPLICATION_AUTHORIZATION_RECORD_INVALID")
                continue
            if record.get("status") != self.AUTHORIZATION_READY:
                blockers.append("RETURN_COGS_APPLICATION_AUTHORIZATION_READY_REQUIRED")
            if record.get("application_authorization_confirmed") is not True:
                blockers.append("RETURN_COGS_APPLICATION_EXPLICIT_AUTHORIZATION_REQUIRED")
            if self._text(record.get("application_state")).upper() != self.AUTHORIZED:
                blockers.append("RETURN_COGS_APPLICATION_AUTHORIZED_STATE_REQUIRED")
            if record.get("application_already_applied") is not False:
                blockers.append("RETURN_COGS_APPLICATION_ALREADY_APPLIED_BLOCKED")
            if self._positive_int(record.get("recognition_history_id")) != history_id:
                blockers.append("RETURN_COGS_APPLICATION_RECOGNITION_VERSION_MATCH_REQUIRED")
            if self._identity(record) != key:
                blockers.append("RETURN_COGS_APPLICATION_IDENTITY_MATCH_REQUIRED")

            authorized_amount = self._money(record.get("authorized_amount"))
            authorized_currency = self._text(record.get("currency")).upper()
            authorized_date = self._text(record.get("recovery_accounting_date"))
            if authorized_amount is None:
                blockers.append("RETURN_COGS_APPLICATION_AUTHORIZED_AMOUNT_REQUIRED")
            elif recognized_amount is None or abs(authorized_amount - recognized_amount) > 0.01:
                blockers.append("RETURN_COGS_APPLICATION_AMOUNT_MISMATCH")
            else:
                authorization_total += authorized_amount
            if authorized_currency != "RUB":
                blockers.append("RETURN_COGS_APPLICATION_CURRENCY_RUB_REQUIRED")
            if authorized_date != recognized_date:
                blockers.append("RETURN_COGS_APPLICATION_ACCOUNTING_DATE_MATCH_REQUIRED")
            if self._text(record.get("monetary_authority_treatment")).upper() != self.MONETARY_AUTHORITY_EXCLUDED:
                blockers.append("RETURN_COGS_APPLICATION_MONETARY_AUTHORITY_EXCLUSION_REQUIRED")
            if record.get("monetary_authority_non_overlap_confirmed") is not True:
                blockers.append("RETURN_COGS_APPLICATION_MONETARY_AUTHORITY_NON_OVERLAP_REQUIRED")
            if record.get("compensation_non_overlap_confirmed") is not True:
                blockers.append("RETURN_COGS_APPLICATION_COMPENSATION_NON_OVERLAP_REQUIRED")

        if len(authorization_records) != len(candidate_keys):
            blockers.append("RETURN_COGS_APPLICATION_AUTHORIZATION_COVERAGE_REQUIRED")

        if recognized_total is not None and isfinite(authorization_total):
            authorization_total = round(authorization_total, 2)
            if abs(authorization_total - recognized_total) > 0.01:
                blockers.append("RETURN_COGS_APPLICATION_TOTAL_MISMATCH")
        else:
            blockers.append("RETURN_COGS_APPLICATION_TOTAL_INVALID")

        blockers = self._dedupe(blockers)
        eligible = not blockers and bool(candidate_keys)

        result["return_cogs_profit_application_eligibility_status"] = (
            self.READY if eligible else self.BLOCKED
        )
        result["return_cogs_profit_application_eligibility_confirmed"] = eligible
        result["return_cogs_profit_application_eligible_amount"] = (
            recognized_total if eligible else None
        )
        result["return_cogs_profit_application_eligible_currency"] = (
            "RUB" if eligible else None
        )
        result["return_cogs_profit_application_authorization_records"] = authorization_records
        result["return_cogs_profit_application_blockers"] = blockers
        result["return_cogs_profit_application_identity_basis"] = (
            "RECOGNITION_HISTORY_ID_RETURN_ID_POSTING_NUMBER_SKU"
        )
        result["return_cogs_profit_application_monetary_authority_basis"] = (
            "EXPLICIT_EXCLUSION_FROM_ACCOUNT_NET_ACCRUAL_REQUIRED"
        )
        result["return_cogs_profit_applied"] = False
        result["return_cogs_profit_application_amount"] = None

        # v1361-v1370 proves eligibility only. The seller-facing Period Profit
        # arithmetic remains account_net_accrual - product_cost - configured_tax.
        result["profit_adjustment_allowed"] = False
        result["automatic_recovery_allowed"] = False
        result["compensation_profit_adjustment_allowed"] = False
        result["read_only"] = True
        result["executed"] = False
        return result

    @classmethod
    def _index(cls, records, prefix):
        result = {}
        blockers = []
        for record in records:
            key = cls._identity(record)
            if key is None:
                blockers.append(f"RETURN_COGS_APPLICATION_{prefix}_IDENTITY_REQUIRED")
                continue
            if key in result:
                blockers.append(f"RETURN_COGS_APPLICATION_{prefix}_IDENTITY_DUPLICATE")
                continue
            result[key] = record
        return result, blockers

    @classmethod
    def _identity(cls, record):
        if not isinstance(record, dict):
            return None
        return_id = cls._text(record.get("return_id"))
        posting_number = cls._text(record.get("posting_number"))
        sku = cls._text(record.get("sku"))
        if not return_id or not posting_number or not sku:
            return None
        return return_id, posting_number, sku

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
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not isfinite(number) or number < 0.0:
            return None
        return round(number, 2)

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _dedupe(values):
        result = []
        seen = set()
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_UNAVAILABLE",
            "return_cogs_profit_application_eligibility_status": (
                "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_UNAVAILABLE"
            ),
            "return_cogs_profit_application_eligibility_confirmed": False,
            "return_cogs_profit_application_eligible_amount": None,
            "return_cogs_profit_application_eligible_currency": None,
            "return_cogs_profit_application_authorization_records": [],
            "return_cogs_profit_application_blockers": [
                "RETURN_COGS_APPLICATION_EVIDENCE_UNAVAILABLE"
            ],
            "return_cogs_profit_applied": False,
            "return_cogs_profit_application_amount": None,
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
