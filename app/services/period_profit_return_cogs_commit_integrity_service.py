from math import isfinite


class PeriodProfitReturnCogsCommitIntegrityService:
    """Fail closed when commit-readiness evidence is internally inconsistent."""

    ELIGIBILITY_READY = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY"
    COMMIT_BLOCKED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_BLOCKED"
    RECOGNITION_RECORD_READY = "RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    AUTHORIZATION_RECORD_READY = "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY"
    RECOGNIZED = "COGS_RECOVERY_RECOGNIZED"
    AUTHORIZED = "PROFIT_APPLICATION_AUTHORIZED"
    MONETARY_AUTHORITY_EXCLUDED = "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL"

    def __init__(self, base_service):
        self.base_service = base_service

    def analyze(self, return_evidence, products):
        analyzer = getattr(self.base_service, "analyze", None)
        if not callable(analyzer):
            return self._unavailable("RETURN_COGS_COMMIT_INTEGRITY_BASE_UNAVAILABLE")
        try:
            base = analyzer(return_evidence, products)
        except Exception:
            return self._unavailable("RETURN_COGS_COMMIT_INTEGRITY_BASE_EXCEPTION")
        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_COMMIT_INTEGRITY_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._unavailable("RETURN_COGS_COMMIT_INTEGRITY_RESULT_INVALID")

        result = dict(base)
        blockers = list(base.get("return_cogs_profit_application_commit_blockers") or [])

        eligibility_confirmed = base.get("return_cogs_profit_application_eligibility_confirmed") is True
        eligibility_status = self._text(base.get("return_cogs_profit_application_eligibility_status")).upper()
        if eligibility_confirmed and eligibility_status != self.ELIGIBILITY_READY:
            blockers.append("RETURN_COGS_COMMIT_CANONICAL_ELIGIBILITY_STATUS_REQUIRED")

        candidates = base.get("candidate_records")
        recognition_records = base.get("return_cogs_accounting_recognition_evidence_records")
        authorization_records = base.get("return_cogs_profit_application_authorization_records")

        candidate_index, candidate_issues = self._identity_index(candidates, "CANDIDATE")
        recognition_index, recognition_issues = self._recognition_index(recognition_records)
        authorization_index, authorization_issues = self._authorization_index(authorization_records)
        blockers.extend(candidate_issues)
        blockers.extend(recognition_issues)
        blockers.extend(authorization_issues)

        candidate_keys = set(candidate_index)
        recognition_keys = {self._identity(record) for record in recognition_index.values() if self._identity(record)}
        authorization_keys = {self._identity(record) for record in authorization_index.values() if self._identity(record)}
        if candidate_keys and recognition_keys != candidate_keys:
            blockers.append("RETURN_COGS_COMMIT_RECOGNITION_CANDIDATE_COVERAGE_REQUIRED")
        if candidate_keys and authorization_keys != candidate_keys:
            blockers.append("RETURN_COGS_COMMIT_AUTHORIZATION_CANDIDATE_COVERAGE_REQUIRED")

        for recognition_id, recognition in recognition_index.items():
            authorization = authorization_index.get(recognition_id)
            if authorization is None:
                blockers.append("RETURN_COGS_COMMIT_AUTHORIZATION_VERSION_COVERAGE_REQUIRED")
                continue
            if self._identity(recognition) != self._identity(authorization):
                blockers.append("RETURN_COGS_COMMIT_AUTHORIZATION_IDENTITY_MISMATCH")
            if self._text(recognition.get("recovery_accounting_date")) != self._text(authorization.get("recovery_accounting_date")):
                blockers.append("RETURN_COGS_COMMIT_AUTHORIZATION_DATE_MISMATCH")
            recognized_amount = self._money(recognition.get("recognized_amount"))
            authorized_amount = self._money(authorization.get("authorized_amount"))
            if recognized_amount is None or authorized_amount is None or abs(recognized_amount - authorized_amount) > 0.01:
                blockers.append("RETURN_COGS_COMMIT_AUTHORIZATION_AMOUNT_MISMATCH")

        blockers.extend(self._commit_record_issues(base, recognition_index, authorization_index))
        blockers = self._dedupe(blockers)
        if blockers:
            result["return_cogs_profit_application_commit_status"] = self.COMMIT_BLOCKED
            result["return_cogs_profit_application_commit_ready"] = False
            result["return_cogs_profit_application_commit_confirmed"] = False
            result["return_cogs_profit_application_commit_blockers"] = blockers
            result["return_cogs_profit_applied"] = False
            result["return_cogs_profit_application_amount"] = None
            result["profit_adjustment_allowed"] = False
        result["return_cogs_profit_application_integrity_confirmed"] = not blockers
        result["automatic_recovery_allowed"] = False
        result["compensation_profit_adjustment_allowed"] = False
        result["read_only"] = True
        result["executed"] = False
        return result

    def _recognition_index(self, records):
        issues = []
        result = {}
        if not isinstance(records, list) or not records:
            return result, ["RETURN_COGS_COMMIT_RECOGNITION_RECORDS_REQUIRED"]
        for record in records:
            if not isinstance(record, dict):
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_RECORD_INVALID")
                continue
            history_id = self._positive_int(record.get("history_id"))
            if history_id is None or history_id in result:
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_VERSION_INVALID")
                continue
            if record.get("error") is not False:
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_RECORD_INVALID")
            if self._text(record.get("status")).upper() != self.RECOGNITION_RECORD_READY:
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_STATUS_REQUIRED")
            if record.get("accounting_recognition_confirmed") is not True:
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_CONFIRMATION_REQUIRED")
            if self._text(record.get("recognition_state")).upper() != self.RECOGNIZED:
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_STATE_REQUIRED")
            if self._identity(record) is None:
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_IDENTITY_REQUIRED")
            if self._money(record.get("recognized_amount")) is None:
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_AMOUNT_REQUIRED")
            if self._text(record.get("currency")).upper() != "RUB":
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_CURRENCY_RUB_REQUIRED")
            if not self._text(record.get("recovery_accounting_date")):
                issues.append("RETURN_COGS_COMMIT_RECOGNITION_DATE_REQUIRED")
            result[history_id] = record
        return result, issues

    def _authorization_index(self, records):
        issues = []
        result = {}
        if not isinstance(records, list) or not records:
            return result, ["RETURN_COGS_COMMIT_AUTHORIZATION_RECORDS_REQUIRED"]
        for record in records:
            if not isinstance(record, dict):
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_RECORD_INVALID")
                continue
            recognition_id = self._positive_int(record.get("recognition_history_id"))
            history_id = self._positive_int(record.get("history_id"))
            if recognition_id is None or history_id is None or recognition_id in result:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_VERSION_INVALID")
                continue
            if record.get("error") is not False:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_RECORD_INVALID")
            if self._text(record.get("status")).upper() != self.AUTHORIZATION_RECORD_READY:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_STATUS_REQUIRED")
            if record.get("application_authorization_confirmed") is not True:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_CONFIRMATION_REQUIRED")
            if self._text(record.get("application_state")).upper() != self.AUTHORIZED:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_STATE_REQUIRED")
            if record.get("application_already_applied") is not False:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_ALREADY_APPLIED_INVALID")
            if self._identity(record) is None:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_IDENTITY_REQUIRED")
            if self._money(record.get("authorized_amount")) is None:
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_AMOUNT_REQUIRED")
            if self._text(record.get("currency")).upper() != "RUB":
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_CURRENCY_RUB_REQUIRED")
            if not self._text(record.get("recovery_accounting_date")):
                issues.append("RETURN_COGS_COMMIT_AUTHORIZATION_DATE_REQUIRED")
            if self._text(record.get("monetary_authority_treatment")).upper() != self.MONETARY_AUTHORITY_EXCLUDED:
                issues.append("RETURN_COGS_COMMIT_MONETARY_AUTHORITY_EXCLUSION_REQUIRED")
            if record.get("monetary_authority_non_overlap_confirmed") is not True:
                issues.append("RETURN_COGS_COMMIT_MONETARY_AUTHORITY_NON_OVERLAP_REQUIRED")
            if record.get("compensation_non_overlap_confirmed") is not True:
                issues.append("RETURN_COGS_COMMIT_COMPENSATION_NON_OVERLAP_REQUIRED")
            result[recognition_id] = record
        return result, issues

    def _commit_record_issues(self, base, recognition_index, authorization_index):
        if base.get("return_cogs_profit_application_commit_confirmed") is not True:
            return []
        records = base.get("return_cogs_profit_application_commit_records")
        if not isinstance(records, list) or not records:
            return ["RETURN_COGS_COMMIT_DURABLE_RECORDS_REQUIRED"]
        issues = []
        seen = set()
        for record in records:
            if not isinstance(record, dict) or record.get("error") is not False or record.get("application_commit_confirmed") is not True:
                issues.append("RETURN_COGS_COMMIT_DURABLE_RECORD_INVALID")
                continue
            recognition_id = self._positive_int(record.get("recognition_history_id"))
            if recognition_id is None or recognition_id in seen:
                issues.append("RETURN_COGS_COMMIT_DURABLE_RECOGNITION_VERSION_INVALID")
                continue
            seen.add(recognition_id)
            recognition = recognition_index.get(recognition_id)
            authorization = authorization_index.get(recognition_id)
            if recognition is None or authorization is None:
                issues.append("RETURN_COGS_COMMIT_DURABLE_UPSTREAM_BINDING_REQUIRED")
                continue
            if self._positive_int(record.get("authorization_history_id")) != self._positive_int(authorization.get("history_id")):
                issues.append("RETURN_COGS_COMMIT_DURABLE_AUTHORIZATION_VERSION_MISMATCH")
            if self._identity(record) != self._identity(recognition) or self._identity(record) != self._identity(authorization):
                issues.append("RETURN_COGS_COMMIT_DURABLE_IDENTITY_MISMATCH")
            amount = self._money(record.get("committed_amount"))
            if amount is None:
                issues.append("RETURN_COGS_COMMIT_DURABLE_AMOUNT_INVALID")
            if self._text(record.get("currency")).upper() != "RUB":
                issues.append("RETURN_COGS_COMMIT_DURABLE_CURRENCY_RUB_REQUIRED")
            if self._text(record.get("recovery_accounting_date")) != self._text(recognition.get("recovery_accounting_date")):
                issues.append("RETURN_COGS_COMMIT_DURABLE_DATE_MISMATCH")
        if seen != set(recognition_index):
            issues.append("RETURN_COGS_COMMIT_DURABLE_COVERAGE_REQUIRED")
        return issues

    @classmethod
    def _identity_index(cls, records, prefix):
        if not isinstance(records, list) or not records:
            return {}, [f"RETURN_COGS_COMMIT_{prefix}_RECORDS_REQUIRED"]
        result = {}
        issues = []
        for record in records:
            key = cls._identity(record)
            if key is None:
                issues.append(f"RETURN_COGS_COMMIT_{prefix}_IDENTITY_REQUIRED")
                continue
            if key in result:
                issues.append(f"RETURN_COGS_COMMIT_{prefix}_IDENTITY_DUPLICATE")
                continue
            result[key] = record
        return result, issues

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
        return "" if value is None else str(value).strip()

    @classmethod
    def _identity(cls, record):
        if not isinstance(record, dict):
            return None
        values = tuple(cls._text(record.get(key)) for key in ("return_id", "posting_number", "sku"))
        return values if all(values) else None

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
            "return_cogs_profit_application_commit_status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_UNAVAILABLE",
            "return_cogs_profit_application_commit_ready": False,
            "return_cogs_profit_application_commit_confirmed": False,
            "return_cogs_profit_application_commit_blockers": ["RETURN_COGS_COMMIT_INTEGRITY_UNAVAILABLE"],
            "return_cogs_profit_application_integrity_confirmed": False,
            "return_cogs_profit_application_amount": None,
            "return_cogs_profit_applied": False,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
