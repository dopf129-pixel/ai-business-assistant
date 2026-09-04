from math import isfinite


class PeriodProfitReturnCogsRecoveryAmountEvidenceService:
    """Stage a Return COGS amount from accounting-ready historical-cost evidence."""

    READY = "PERIOD_PROFIT_RETURN_COGS_RECOVERY_AMOUNT_EVIDENCE_READY"
    BLOCKED = "PERIOD_PROFIT_RETURN_COGS_RECOVERY_AMOUNT_EVIDENCE_BLOCKED"

    def __init__(self, base_service):
        self.base_service = base_service

    def analyze(self, return_evidence, products):
        analyzer = getattr(self.base_service, "analyze", None)
        if not callable(analyzer):
            return self._unavailable("RETURN_COGS_AMOUNT_BASE_UNAVAILABLE")

        try:
            base = analyzer(return_evidence, products)
        except Exception:
            return self._unavailable("RETURN_COGS_AMOUNT_BASE_EXCEPTION")

        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_AMOUNT_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._unavailable("RETURN_COGS_AMOUNT_RESULT_INVALID")

        result = dict(base)
        candidates = base.get("candidate_records")
        if not isinstance(candidates, list):
            return self._unavailable("RETURN_COGS_AMOUNT_CANDIDATES_INVALID")

        blockers = []
        if base.get("return_cogs_accounting_readiness_confirmed") is not True:
            blockers.append("RETURN_COGS_ACCOUNTING_READINESS_REQUIRED")
        if not candidates:
            blockers.append("RETURN_COGS_AMOUNT_CANDIDATES_REQUIRED")

        amount_records = []
        total = 0.0
        valid_count = 0

        for candidate in candidates:
            row, blocker = self._amount_record(candidate)
            if blocker is not None:
                blockers.append(blocker)
                amount_records.append(row)
                continue
            amount_records.append(row)
            total += row["staged_recovery_amount"]
            valid_count += 1

        if not isfinite(total):
            blockers.append("RETURN_COGS_AMOUNT_TOTAL_INVALID")

        evidence_confirmed = (
            not blockers
            and bool(candidates)
            and valid_count == len(candidates)
        )
        staged_amount = round(total, 2) if evidence_confirmed else None

        result["return_cogs_recovery_amount_evidence_status"] = (
            self.READY if evidence_confirmed else self.BLOCKED
        )
        result["return_cogs_recovery_amount_evidence_confirmed"] = evidence_confirmed
        result["return_cogs_recovery_amount_evidence_amount"] = staged_amount
        result["return_cogs_recovery_amount_evidence_currency"] = (
            "RUB" if evidence_confirmed else None
        )
        result["return_cogs_recovery_amount_evidence_records"] = amount_records
        result["return_cogs_recovery_amount_evidence_candidate_record_count"] = len(
            candidates
        )
        result["return_cogs_recovery_amount_evidence_valid_record_count"] = valid_count
        result["return_cogs_recovery_amount_evidence_blockers"] = self._dedupe(blockers)
        result["return_cogs_recovery_amount_basis"] = (
            "HISTORICAL_COST_PER_UNIT_X_RETURN_QUANTITY"
        )

        # v1331-v1340 stages a monetary evidence amount only. Recognition and
        # Period Profit adjustment remain separate accounting contracts.
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
    def _amount_record(cls, candidate):
        if not isinstance(candidate, dict):
            return (
                {
                    "return_id": None,
                    "posting_number": None,
                    "sku": None,
                    "quantity": None,
                    "historical_cost_per_unit": None,
                    "staged_recovery_amount": None,
                    "status": "RETURN_COGS_AMOUNT_CANDIDATE_INVALID",
                },
                "RETURN_COGS_AMOUNT_CANDIDATE_INVALID",
            )

        return_id = cls._text(candidate.get("return_id"))
        posting_number = cls._text(candidate.get("posting_number"))
        sku = cls._text(candidate.get("sku"))
        quantity = cls._positive_int(candidate.get("quantity"))
        cost = cls._money(candidate.get("historical_cost_per_unit"))
        supplied_value = cls._money(candidate.get("candidate_value_at_historical_cost"))

        row = {
            "return_id": return_id or None,
            "posting_number": posting_number or None,
            "sku": sku or None,
            "quantity": quantity,
            "historical_cost_per_unit": cost,
            "source_candidate_value_at_historical_cost": supplied_value,
            "staged_recovery_amount": None,
            "status": "RETURN_COGS_AMOUNT_CANDIDATE_INVALID",
        }

        if not return_id or not posting_number or not sku:
            return row, "RETURN_COGS_AMOUNT_CANDIDATE_IDENTITY_REQUIRED"
        if quantity is None:
            return row, "RETURN_COGS_AMOUNT_QUANTITY_REQUIRED"
        if cost is None:
            return row, "RETURN_COGS_AMOUNT_HISTORICAL_COST_REQUIRED"
        if supplied_value is None:
            return row, "RETURN_COGS_AMOUNT_HISTORICAL_VALUE_REQUIRED"

        calculated = cost * quantity
        if not isfinite(calculated) or calculated < 0.0:
            return row, "RETURN_COGS_AMOUNT_CALCULATION_INVALID"
        calculated = round(calculated, 2)
        if abs(calculated - supplied_value) > 0.01:
            return row, "RETURN_COGS_AMOUNT_HISTORICAL_VALUE_MISMATCH"

        row["staged_recovery_amount"] = calculated
        row["status"] = "RETURN_COGS_AMOUNT_CANDIDATE_READY"
        return row, None

    @staticmethod
    def _positive_int(value):
        if isinstance(value, bool):
            return None
        if not isinstance(value, int) or value <= 0:
            return None
        return value

    @staticmethod
    def _money(value):
        if isinstance(value, bool) or value is None:
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
            "return_cogs_recovery_amount_evidence_status": (
                "PERIOD_PROFIT_RETURN_COGS_RECOVERY_AMOUNT_EVIDENCE_UNAVAILABLE"
            ),
            "return_cogs_recovery_amount_evidence_confirmed": False,
            "return_cogs_recovery_amount_evidence_amount": None,
            "return_cogs_recovery_amount_evidence_currency": None,
            "return_cogs_recovery_amount_evidence_records": [],
            "return_cogs_recovery_amount_evidence_blockers": [
                "RETURN_COGS_AMOUNT_EVIDENCE_UNAVAILABLE"
            ],
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
