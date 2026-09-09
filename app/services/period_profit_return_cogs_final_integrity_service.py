from math import isfinite


class PeriodProfitReturnCogsFinalIntegrityService:
    """Validate complete candidate-to-commit coverage before final read-only application."""

    MONETARY_AUTHORITY_EXCLUDED = "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL"

    def __init__(self, base_service):
        self.base_service = base_service

    def apply(self, summary, evidence):
        apply = getattr(self.base_service, "apply", None)
        if not callable(apply):
            return self._unavailable("RETURN_COGS_FINAL_INTEGRITY_BASE_UNAVAILABLE")
        if not isinstance(evidence, dict):
            try:
                return apply(summary, evidence)
            except Exception:
                return self._unavailable("RETURN_COGS_FINAL_INTEGRITY_BASE_EXCEPTION")
        if evidence.get("return_cogs_profit_application_commit_confirmed") is not True:
            try:
                return apply(summary, evidence)
            except Exception:
                return self._unavailable("RETURN_COGS_FINAL_INTEGRITY_BASE_EXCEPTION")

        code = self._validate(evidence)
        if code is not None:
            return self._unavailable(code)
        try:
            result = apply(summary, evidence)
        except Exception:
            return self._unavailable("RETURN_COGS_FINAL_INTEGRITY_BASE_EXCEPTION")
        if not isinstance(result, dict):
            return self._unavailable("RETURN_COGS_FINAL_INTEGRITY_RESULT_INVALID")
        if result.get("error") is True:
            return result
        if result.get("error") is not False:
            return self._unavailable("RETURN_COGS_FINAL_INTEGRITY_RESULT_INVALID")
        if result.get("return_cogs_profit_applied") is True:
            result = dict(result)
            result["return_cogs_final_candidate_coverage_confirmed"] = True
            result["return_cogs_final_monetary_authority_reconfirmed"] = True
            nested = result.get("evidence")
            if isinstance(nested, dict):
                nested = dict(nested)
                nested["return_cogs_final_candidate_coverage_confirmed"] = True
                nested["return_cogs_final_monetary_authority_reconfirmed"] = True
                result["evidence"] = nested
        result["read_only"] = True
        result["executed"] = False
        return result

    def _validate(self, evidence):
        candidates = evidence.get("candidate_records")
        recognition_records = evidence.get("return_cogs_accounting_recognition_evidence_records")
        authorization_records = evidence.get("return_cogs_profit_application_authorization_records")
        commit_records = evidence.get("return_cogs_profit_application_commit_records")

        candidate_index, code = self._identity_index(candidates, "RETURN_COGS_FINAL_CANDIDATE")
        if code:
            return code
        recognition_index, code = self._identity_index(recognition_records, "RETURN_COGS_FINAL_RECOGNITION")
        if code:
            return code
        authorization_index, code = self._identity_index(authorization_records, "RETURN_COGS_FINAL_AUTHORIZATION")
        if code:
            return code
        commit_index, code = self._identity_index(commit_records, "RETURN_COGS_FINAL_COMMIT")
        if code:
            return code

        candidate_keys = set(candidate_index)
        if set(recognition_index) != candidate_keys:
            return "RETURN_COGS_FINAL_CANDIDATE_RECOGNITION_COVERAGE_MISMATCH"
        if set(authorization_index) != candidate_keys:
            return "RETURN_COGS_FINAL_CANDIDATE_AUTHORIZATION_COVERAGE_MISMATCH"
        if set(commit_index) != candidate_keys:
            return "RETURN_COGS_FINAL_CANDIDATE_COMMIT_COVERAGE_MISMATCH"

        for key in sorted(candidate_keys):
            recognition = recognition_index[key]
            authorization = authorization_index[key]
            commit = commit_index[key]
            if authorization.get("error") is not False:
                return "RETURN_COGS_FINAL_AUTHORIZATION_RECORD_INVALID"
            if self._text(authorization.get("monetary_authority_treatment")).upper() != self.MONETARY_AUTHORITY_EXCLUDED:
                return "RETURN_COGS_FINAL_MONETARY_AUTHORITY_EXCLUSION_REQUIRED"
            if authorization.get("monetary_authority_non_overlap_confirmed") is not True:
                return "RETURN_COGS_FINAL_MONETARY_AUTHORITY_NON_OVERLAP_REQUIRED"
            if authorization.get("compensation_non_overlap_confirmed") is not True:
                return "RETURN_COGS_FINAL_COMPENSATION_NON_OVERLAP_REQUIRED"
            if commit.get("error") is not False or commit.get("application_commit_confirmed") is not True:
                return "RETURN_COGS_FINAL_COMMIT_RECORD_INVALID"

            recognized_amount = self._money(recognition.get("recognized_amount"))
            authorized_amount = self._money(authorization.get("authorized_amount"))
            committed_amount = self._money(commit.get("committed_amount"))
            if None in (recognized_amount, authorized_amount, committed_amount):
                return "RETURN_COGS_FINAL_CHAIN_AMOUNT_INVALID"
            if abs(recognized_amount - authorized_amount) > 0.01 or abs(recognized_amount - committed_amount) > 0.01:
                return "RETURN_COGS_FINAL_CHAIN_AMOUNT_MISMATCH"
            if self._text(recognition.get("currency")).upper() != "RUB":
                return "RETURN_COGS_FINAL_RECOGNITION_CURRENCY_RUB_REQUIRED"
            if self._text(authorization.get("currency")).upper() != "RUB":
                return "RETURN_COGS_FINAL_AUTHORIZATION_CURRENCY_RUB_REQUIRED"
            if self._text(commit.get("currency")).upper() != "RUB":
                return "RETURN_COGS_FINAL_COMMIT_CURRENCY_RUB_REQUIRED"
            date = self._text(recognition.get("recovery_accounting_date"))
            if not date or self._text(authorization.get("recovery_accounting_date")) != date or self._text(commit.get("recovery_accounting_date")) != date:
                return "RETURN_COGS_FINAL_CHAIN_DATE_MISMATCH"
        return None

    @classmethod
    def _identity_index(cls, records, prefix):
        if not isinstance(records, list) or not records:
            return {}, f"{prefix}_RECORDS_REQUIRED"
        result = {}
        for record in records:
            key = cls._identity(record)
            if key is None:
                return {}, f"{prefix}_IDENTITY_REQUIRED"
            if key in result:
                return {}, f"{prefix}_IDENTITY_DUPLICATE"
            result[key] = record
        return result, None

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
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_UNAVAILABLE",
            "return_cogs_profit_applied": False,
            "return_cogs_profit_application_amount": None,
            "return_cogs_final_candidate_coverage_confirmed": False,
            "return_cogs_final_monetary_authority_reconfirmed": False,
            "read_only": True,
            "executed": False,
        }
