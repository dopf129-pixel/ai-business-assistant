from math import isfinite


class PeriodProfitReturnCogsRecognitionEligibilityService:
    """Bind staged Return COGS money to exact period/accounting evidence."""

    READY = "PERIOD_PROFIT_RETURN_COGS_RECOGNITION_ELIGIBILITY_READY"
    BLOCKED = "PERIOD_PROFIT_RETURN_COGS_RECOGNITION_ELIGIBILITY_BLOCKED"
    ATTRIBUTION_READY = "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY"
    COMPENSATION_STATES = {
        "NO_COMPENSATION_CONFIRMED",
        "COMPENSATION_PRESENT",
    }

    def __init__(self, base_service):
        self.base_service = base_service

    def analyze(self, return_evidence, products):
        analyzer = getattr(self.base_service, "analyze", None)
        if not callable(analyzer):
            return self._unavailable("RETURN_COGS_RECOGNITION_BASE_UNAVAILABLE")
        try:
            base = analyzer(return_evidence, products)
        except Exception:
            return self._unavailable("RETURN_COGS_RECOGNITION_BASE_EXCEPTION")

        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_RECOGNITION_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._unavailable("RETURN_COGS_RECOGNITION_RESULT_INVALID")

        result = dict(base)
        blockers = []

        if base.get("return_cogs_accounting_readiness_confirmed") is not True:
            blockers.append("RETURN_COGS_ACCOUNTING_READINESS_REQUIRED")
        if base.get("return_cogs_recovery_amount_evidence_confirmed") is not True:
            blockers.append("RETURN_COGS_RECOVERY_AMOUNT_EVIDENCE_REQUIRED")

        staged_amount = self._money(
            base.get("return_cogs_recovery_amount_evidence_amount")
        )
        currency = str(
            base.get("return_cogs_recovery_amount_evidence_currency") or ""
        ).strip().upper()
        if staged_amount is None:
            blockers.append("RETURN_COGS_STAGED_AMOUNT_REQUIRED")
        if currency != "RUB":
            blockers.append("RETURN_COGS_STAGED_AMOUNT_CURRENCY_RUB_REQUIRED")

        candidates = base.get("candidate_records")
        amount_records = base.get("return_cogs_recovery_amount_evidence_records")
        attribution_records = base.get("accounting_attribution_evidence_records")
        if not isinstance(candidates, list) or not candidates:
            blockers.append("RETURN_COGS_RECOGNITION_CANDIDATES_REQUIRED")
            candidates = []
        if not isinstance(amount_records, list):
            blockers.append("RETURN_COGS_AMOUNT_RECORDS_REQUIRED")
            amount_records = []
        if not isinstance(attribution_records, list):
            blockers.append("RETURN_COGS_ATTRIBUTION_RECORDS_REQUIRED")
            attribution_records = []

        candidate_index, candidate_issue = self._index_candidates(candidates)
        amount_index, amount_total, amount_issue = self._index_amount_records(
            amount_records
        )
        attribution_index, attribution_issue = self._index_attribution_records(
            attribution_records
        )
        blockers.extend(candidate_issue)
        blockers.extend(amount_issue)
        blockers.extend(attribution_issue)

        candidate_keys = set(candidate_index)
        if set(amount_index) != candidate_keys:
            blockers.append("RETURN_COGS_AMOUNT_IDENTITY_COVERAGE_REQUIRED")
        if set(attribution_index) != candidate_keys:
            blockers.append("RETURN_COGS_ATTRIBUTION_IDENTITY_COVERAGE_REQUIRED")

        if staged_amount is not None and amount_total is not None:
            if abs(staged_amount - amount_total) > 0.01:
                blockers.append("RETURN_COGS_STAGED_AMOUNT_TOTAL_MISMATCH")

        for key in candidate_keys:
            attribution = attribution_index.get(key)
            if attribution is None:
                continue
            if attribution.get("status") != self.ATTRIBUTION_READY:
                blockers.append("RETURN_COGS_ATTRIBUTION_READY_REQUIRED")
            if (
                attribution.get("recovery_accounting_period_matches_request")
                is not True
            ):
                blockers.append("RETURN_COGS_RECOGNITION_PERIOD_MATCH_REQUIRED")
            compensation_state = str(
                attribution.get("compensation_state") or ""
            ).strip().upper()
            if compensation_state not in self.COMPENSATION_STATES:
                blockers.append("RETURN_COGS_COMPENSATION_STATE_REQUIRED")
            if attribution.get("compensation_double_count_clear") is not True:
                blockers.append("RETURN_COGS_COMPENSATION_DOUBLE_COUNT_CLEAR_REQUIRED")

        blockers = self._dedupe(blockers)
        eligible = not blockers and bool(candidate_keys)

        result["return_cogs_recognition_eligibility_status"] = (
            self.READY if eligible else self.BLOCKED
        )
        result["return_cogs_recognition_eligibility_confirmed"] = eligible
        result["return_cogs_recognition_eligible_amount"] = (
            staged_amount if eligible else None
        )
        result["return_cogs_recognition_eligible_currency"] = (
            "RUB" if eligible else None
        )
        result["return_cogs_recognition_candidate_count"] = len(candidate_keys)
        result["return_cogs_recognition_eligibility_blockers"] = blockers
        result["return_cogs_recognition_identity_basis"] = (
            "RETURN_ID_POSTING_NUMBER_SKU"
        )

        # v1341-v1350 proves recognition eligibility only. It does not book the
        # recovery into the selected period and does not change Period Profit.
        result["period_cogs_recovery_confirmed"] = False
        result["accounting_cogs_recovery_confirmed"] = False
        result["confirmed_cogs_recovery_amount"] = 0.0
        result["profit_adjustment_allowed"] = False
        result["automatic_recovery_allowed"] = False
        result["compensation_profit_adjustment_allowed"] = False
        result["read_only"] = True
        result["executed"] = False
        return result

    @classmethod
    def _index_candidates(cls, records):
        result = {}
        blockers = []
        for record in records:
            key = cls._identity(record)
            if key is None:
                blockers.append("RETURN_COGS_RECOGNITION_CANDIDATE_IDENTITY_REQUIRED")
                continue
            if key in result:
                blockers.append("RETURN_COGS_RECOGNITION_CANDIDATE_IDENTITY_DUPLICATE")
                continue
            result[key] = record
        return result, blockers

    @classmethod
    def _index_amount_records(cls, records):
        result = {}
        blockers = []
        total = 0.0
        for record in records:
            key = cls._identity(record)
            if key is None:
                blockers.append("RETURN_COGS_AMOUNT_RECORD_IDENTITY_REQUIRED")
                continue
            if key in result:
                blockers.append("RETURN_COGS_AMOUNT_RECORD_IDENTITY_DUPLICATE")
                continue
            amount = cls._money(record.get("staged_recovery_amount"))
            if record.get("status") != "RETURN_COGS_AMOUNT_CANDIDATE_READY":
                blockers.append("RETURN_COGS_AMOUNT_RECORD_READY_REQUIRED")
            if amount is None:
                blockers.append("RETURN_COGS_AMOUNT_RECORD_VALUE_REQUIRED")
            else:
                total += amount
            result[key] = record
        if not isfinite(total):
            blockers.append("RETURN_COGS_AMOUNT_RECORD_TOTAL_INVALID")
            return result, None, blockers
        return result, round(total, 2), blockers

    @classmethod
    def _index_attribution_records(cls, records):
        result = {}
        blockers = []
        for record in records:
            key = cls._identity(record)
            if key is None:
                blockers.append("RETURN_COGS_ATTRIBUTION_RECORD_IDENTITY_REQUIRED")
                continue
            if key in result:
                blockers.append("RETURN_COGS_ATTRIBUTION_RECORD_IDENTITY_DUPLICATE")
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
            "return_cogs_recognition_eligibility_status": (
                "PERIOD_PROFIT_RETURN_COGS_RECOGNITION_ELIGIBILITY_UNAVAILABLE"
            ),
            "return_cogs_recognition_eligibility_confirmed": False,
            "return_cogs_recognition_eligible_amount": None,
            "return_cogs_recognition_eligible_currency": None,
            "return_cogs_recognition_eligibility_blockers": [
                "RETURN_COGS_RECOGNITION_EVIDENCE_UNAVAILABLE"
            ],
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
