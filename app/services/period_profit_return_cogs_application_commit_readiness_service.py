class PeriodProfitReturnCogsApplicationCommitReadinessService:
    """Expose exact-once commit readiness after eligibility, without applying profit."""

    READY = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_READY"
    BLOCKED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_BLOCKED"
    COMMITTED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED"

    def __init__(self, base_service, application_commit_repository):
        self.base_service = base_service
        self.application_commit_repository = application_commit_repository

    def analyze(self, return_evidence, products):
        analyzer = getattr(self.base_service, "analyze", None)
        if not callable(analyzer):
            return self._unavailable("RETURN_COGS_APPLICATION_COMMIT_BASE_UNAVAILABLE")
        try:
            base = analyzer(return_evidence, products)
        except Exception:
            return self._unavailable("RETURN_COGS_APPLICATION_COMMIT_BASE_EXCEPTION")
        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_APPLICATION_COMMIT_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._unavailable("RETURN_COGS_APPLICATION_COMMIT_RESULT_INVALID")

        result = dict(base)
        blockers = []
        commit_records = []
        eligible = base.get("return_cogs_profit_application_eligibility_confirmed") is True
        if not eligible:
            blockers.append("RETURN_COGS_APPLICATION_ELIGIBILITY_REQUIRED")

        recognition_records = base.get("return_cogs_accounting_recognition_evidence_records")
        authorization_records = base.get("return_cogs_profit_application_authorization_records")
        if not isinstance(recognition_records, list) or not recognition_records:
            blockers.append("RETURN_COGS_APPLICATION_COMMIT_RECOGNITION_RECORDS_REQUIRED")
            recognition_records = []
        if not isinstance(authorization_records, list) or not authorization_records:
            blockers.append("RETURN_COGS_APPLICATION_COMMIT_AUTHORIZATION_RECORDS_REQUIRED")
            authorization_records = []

        recognition_index = {}
        for record in recognition_records:
            history_id = self._positive_int(record.get("history_id")) if isinstance(record, dict) else None
            if history_id is None or history_id in recognition_index:
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_RECOGNITION_VERSION_REQUIRED")
                continue
            recognition_index[history_id] = record

        authorization_index = {}
        for record in authorization_records:
            history_id = self._positive_int(record.get("recognition_history_id")) if isinstance(record, dict) else None
            authorization_history_id = self._positive_int(record.get("history_id")) if isinstance(record, dict) else None
            if history_id is None or authorization_history_id is None or history_id in authorization_index:
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_AUTHORIZATION_VERSION_REQUIRED")
                continue
            authorization_index[history_id] = record

        if set(recognition_index) != set(authorization_index):
            blockers.append("RETURN_COGS_APPLICATION_COMMIT_VERSION_COVERAGE_REQUIRED")

        getter = getattr(self.application_commit_repository, "get_application_commit", None)
        if not callable(getter):
            blockers.append("RETURN_COGS_APPLICATION_COMMIT_REPOSITORY_REQUIRED")

        already_committed = False
        for history_id in sorted(recognition_index):
            recognition = recognition_index[history_id]
            authorization = authorization_index.get(history_id)
            if authorization is None or not callable(getter):
                continue
            try:
                record = getter(history_id)
            except Exception:
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_REPOSITORY_EXCEPTION")
                continue
            if not isinstance(record, dict):
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_RECORD_INVALID")
                continue
            commit_records.append(dict(record))
            if record.get("error") is True:
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_UNAVAILABLE")
                continue
            if record.get("error") is not False:
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_RECORD_INVALID")
                continue
            if record.get("application_commit_confirmed") is not True:
                continue

            already_committed = True
            if self._positive_int(record.get("recognition_history_id")) != history_id:
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_RECOGNITION_VERSION_MISMATCH")
            if self._identity(record) != self._identity(recognition):
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_IDENTITY_MISMATCH")
            if self._text(record.get("recovery_accounting_date")) != self._text(recognition.get("recovery_accounting_date")):
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_ACCOUNTING_DATE_MISMATCH")
            if self._money(record.get("committed_amount")) != self._money(recognition.get("recognized_amount")):
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_AMOUNT_MISMATCH")
            if self._text(record.get("currency")).upper() != "RUB":
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_CURRENCY_RUB_REQUIRED")
            if self._positive_int(record.get("authorization_history_id")) != self._positive_int(authorization.get("history_id")):
                blockers.append("RETURN_COGS_APPLICATION_COMMIT_AUTHORIZATION_VERSION_MISMATCH")

        blockers = self._dedupe(blockers)
        ready = eligible and not blockers and not already_committed
        committed = eligible and not blockers and already_committed and len(commit_records) == len(recognition_index)

        result["return_cogs_profit_application_commit_status"] = (
            self.COMMITTED if committed else self.READY if ready else self.BLOCKED
        )
        result["return_cogs_profit_application_commit_ready"] = ready
        result["return_cogs_profit_application_commit_confirmed"] = committed
        result["return_cogs_profit_application_commit_records"] = commit_records
        result["return_cogs_profit_application_commit_blockers"] = blockers
        result["return_cogs_profit_application_exact_once_basis"] = "UNIQUE_RECOGNITION_HISTORY_ID_APPEND_ONLY_COMMIT_LEDGER"
        result["return_cogs_profit_application_amount"] = None
        result["return_cogs_profit_applied"] = False
        result["profit_adjustment_allowed"] = False
        result["automatic_recovery_allowed"] = False
        result["compensation_profit_adjustment_allowed"] = False
        result["read_only"] = True
        result["executed"] = False
        return result

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
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

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
            "return_cogs_profit_application_commit_records": [],
            "return_cogs_profit_application_commit_blockers": ["RETURN_COGS_APPLICATION_COMMIT_EVIDENCE_UNAVAILABLE"],
            "return_cogs_profit_application_amount": None,
            "return_cogs_profit_applied": False,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
