from math import isfinite


class PeriodProfitReturnCogsAccountingRecognitionService:
    """Confirm booked Return COGS only from exact explicit accounting evidence."""

    READY = "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    BLOCKED = "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_BLOCKED"
    RECORD_READY = "RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    RECOGNIZED = "COGS_RECOVERY_RECOGNIZED"

    def __init__(self, base_service, accounting_recognition_repository):
        self.base_service = base_service
        self.accounting_recognition_repository = accounting_recognition_repository

    def analyze(self, return_evidence, products):
        analyzer = getattr(self.base_service, "analyze", None)
        if not callable(analyzer):
            return self._unavailable("RETURN_COGS_ACCOUNTING_RECOGNITION_BASE_UNAVAILABLE")
        try:
            base = analyzer(return_evidence, products)
        except Exception:
            return self._unavailable("RETURN_COGS_ACCOUNTING_RECOGNITION_BASE_EXCEPTION")

        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_ACCOUNTING_RECOGNITION_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._unavailable("RETURN_COGS_ACCOUNTING_RECOGNITION_RESULT_INVALID")

        result = dict(base)
        blockers = []

        if base.get("return_cogs_recognition_eligibility_confirmed") is not True:
            blockers.append("RETURN_COGS_RECOGNITION_ELIGIBILITY_REQUIRED")

        eligible_amount = self._money(base.get("return_cogs_recognition_eligible_amount"))
        eligible_currency = self._text(
            base.get("return_cogs_recognition_eligible_currency")
        ).upper()
        if eligible_amount is None:
            blockers.append("RETURN_COGS_RECOGNITION_ELIGIBLE_AMOUNT_REQUIRED")
        if eligible_currency != "RUB":
            blockers.append("RETURN_COGS_RECOGNITION_ELIGIBLE_CURRENCY_RUB_REQUIRED")

        candidates = base.get("candidate_records")
        amount_records = base.get("return_cogs_recovery_amount_evidence_records")
        attribution_records = base.get("accounting_attribution_evidence_records")
        if not isinstance(candidates, list) or not candidates:
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_CANDIDATES_REQUIRED")
            candidates = []
        if not isinstance(amount_records, list):
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_AMOUNT_RECORDS_REQUIRED")
            amount_records = []
        if not isinstance(attribution_records, list):
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_ATTRIBUTION_RECORDS_REQUIRED")
            attribution_records = []

        candidate_index, issues = self._index(candidates, "CANDIDATE")
        blockers.extend(issues)
        amount_index, issues = self._index(amount_records, "AMOUNT")
        blockers.extend(issues)
        attribution_index, issues = self._index(attribution_records, "ATTRIBUTION")
        blockers.extend(issues)

        candidate_keys = set(candidate_index)
        if set(amount_index) != candidate_keys:
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_AMOUNT_COVERAGE_REQUIRED")
        if set(attribution_index) != candidate_keys:
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_ATTRIBUTION_COVERAGE_REQUIRED")

        getter = getattr(
            self.accounting_recognition_repository,
            "get_latest_recognition",
            None,
        )
        if not callable(getter):
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_REPOSITORY_REQUIRED")

        recognition_records = []
        recognition_total = 0.0
        for key in sorted(candidate_keys):
            amount_record = amount_index.get(key)
            attribution_record = attribution_index.get(key)
            if amount_record is None or attribution_record is None or not callable(getter):
                continue

            expected_amount = self._money(amount_record.get("staged_recovery_amount"))
            expected_date = self._text(
                attribution_record.get("recovery_accounting_date")
            )
            if expected_amount is None:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_EXPECTED_AMOUNT_REQUIRED")
                continue
            if not expected_date:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_EXPECTED_DATE_REQUIRED")
                continue

            try:
                record = getter(*key)
            except Exception:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_REPOSITORY_EXCEPTION")
                continue

            if not isinstance(record, dict):
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_RECORD_INVALID")
                continue

            normalized = dict(record)
            recognition_records.append(normalized)

            if record.get("error") is True:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_RECORD_UNAVAILABLE")
                continue
            if record.get("error") is not False:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_RECORD_INVALID")
                continue
            if record.get("status") != self.RECORD_READY:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_RECORD_READY_REQUIRED")
            if record.get("accounting_recognition_confirmed") is not True:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_EXPLICIT_CONFIRMATION_REQUIRED")
            if self._text(record.get("recognition_state")).upper() != self.RECOGNIZED:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_STATE_REQUIRED")

            if self._identity(record) != key:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_IDENTITY_MATCH_REQUIRED")

            recognized_amount = self._money(record.get("recognized_amount"))
            currency = self._text(record.get("currency")).upper()
            recognition_date = self._text(record.get("recovery_accounting_date"))
            if recognized_amount is None:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_AMOUNT_REQUIRED")
            elif abs(recognized_amount - expected_amount) > 0.01:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_AMOUNT_MISMATCH")
            else:
                recognition_total += recognized_amount
            if currency != "RUB":
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_CURRENCY_RUB_REQUIRED")
            if recognition_date != expected_date:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_DATE_MATCH_REQUIRED")

        if len(recognition_records) != len(candidate_keys):
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_EVIDENCE_COVERAGE_REQUIRED")

        if eligible_amount is not None and isfinite(recognition_total):
            recognition_total = round(recognition_total, 2)
            if abs(recognition_total - eligible_amount) > 0.01:
                blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_TOTAL_MISMATCH")
        else:
            blockers.append("RETURN_COGS_ACCOUNTING_RECOGNITION_TOTAL_INVALID")

        blockers = self._dedupe(blockers)
        confirmed = not blockers and bool(candidate_keys)

        result["return_cogs_accounting_recognition_status"] = (
            self.READY if confirmed else self.BLOCKED
        )
        result["return_cogs_accounting_recognition_evidence_confirmed"] = confirmed
        result["return_cogs_accounting_recognition_evidence_records"] = recognition_records
        result["return_cogs_accounting_recognition_blockers"] = blockers
        result["return_cogs_accounting_recognition_identity_basis"] = (
            "RETURN_ID_POSTING_NUMBER_SKU"
        )
        result["period_cogs_recovery_confirmed"] = confirmed
        result["accounting_cogs_recovery_confirmed"] = confirmed
        result["confirmed_cogs_recovery_amount"] = (
            eligible_amount if confirmed else 0.0
        )

        # v1351-v1360 recognizes the accounting fact only. Profit arithmetic
        # remains unchanged until a separate explicit application package.
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
                blockers.append(
                    f"RETURN_COGS_ACCOUNTING_RECOGNITION_{prefix}_IDENTITY_REQUIRED"
                )
                continue
            if key in result:
                blockers.append(
                    f"RETURN_COGS_ACCOUNTING_RECOGNITION_{prefix}_IDENTITY_DUPLICATE"
                )
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
            "return_cogs_accounting_recognition_status": (
                "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_UNAVAILABLE"
            ),
            "return_cogs_accounting_recognition_evidence_confirmed": False,
            "return_cogs_accounting_recognition_evidence_records": [],
            "return_cogs_accounting_recognition_blockers": [
                "RETURN_COGS_ACCOUNTING_RECOGNITION_EVIDENCE_UNAVAILABLE"
            ],
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
