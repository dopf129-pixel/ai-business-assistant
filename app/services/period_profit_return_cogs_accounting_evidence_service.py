from datetime import date, datetime


class PeriodProfitReturnCogsAccountingEvidenceService:
    """Add explicit accounting-date and compensation evidence to Return COGS."""

    READY_STATUS = "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY"
    MISSING_STATUS = "RETURN_COGS_ACCOUNTING_ATTRIBUTION_MISSING"
    CONFLICT_STATUS = "RETURN_COGS_ACCOUNTING_ATTRIBUTION_IDENTITY_CONFLICT"
    COMPENSATION_STATES = {
        "NO_COMPENSATION_CONFIRMED",
        "COMPENSATION_PRESENT",
    }

    def __init__(self, base_service, accounting_attribution_repository):
        self.base_service = base_service
        self.accounting_attribution_repository = accounting_attribution_repository

    def analyze(self, return_evidence, products):
        base = self.base_service.analyze(return_evidence, products)
        if not isinstance(base, dict):
            return self._unavailable("RETURN_COGS_BASE_EVIDENCE_INVALID")
        if base.get("error") is True:
            return dict(base)

        candidates = base.get("candidate_records")
        if not isinstance(candidates, list):
            return self._unavailable("RETURN_COGS_CANDIDATES_INVALID")

        source = dict(return_evidence or {})
        date_from = self._date(source.get("date_from"))
        date_to = self._date(source.get("date_to"))
        period_valid = (
            date_from is not None
            and date_to is not None
            and date_from <= date_to
        )

        records = []
        ready_count = 0
        in_period_count = 0
        outside_period_count = 0
        compensation_treatment_count = 0
        double_count_clear_count = 0
        missing_count = 0
        conflict_count = 0
        unavailable_count = 0

        for candidate in candidates:
            row = self._candidate_record(candidate)
            if row is None:
                unavailable_count += 1
                records.append({
                    "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_CANDIDATE_INVALID",
                    "return_id": None,
                    "posting_number": None,
                    "sku": None,
                    "recovery_accounting_date": None,
                    "recovery_accounting_period_matches_request": False,
                    "compensation_state": None,
                    "compensation_double_count_clear": None,
                })
                continue

            evidence = self._lookup(row)
            status = str(evidence.get("status") or "")
            result_row = {
                "return_id": row["return_id"],
                "posting_number": row["posting_number"],
                "sku": row["sku"],
                "status": status,
                "recovery_accounting_date": evidence.get(
                    "recovery_accounting_date"
                ),
                "recovery_accounting_period_matches_request": False,
                "compensation_state": evidence.get("compensation_state"),
                "compensation_double_count_clear": evidence.get(
                    "compensation_double_count_clear"
                ),
                "confirmed_on": evidence.get("confirmed_on"),
                "source": evidence.get("source"),
            }

            if (
                evidence.get("error") is False
                and status == self.READY_STATUS
                and evidence.get("accounting_attribution_confirmed") is True
            ):
                accounting_date = self._date(
                    evidence.get("recovery_accounting_date")
                )
                compensation_state = str(
                    evidence.get("compensation_state") or ""
                ).upper()
                clear = evidence.get("compensation_double_count_clear")
                if (
                    accounting_date is None
                    or compensation_state not in self.COMPENSATION_STATES
                    or not isinstance(clear, bool)
                ):
                    result_row["status"] = (
                        "RETURN_COGS_ACCOUNTING_ATTRIBUTION_ROW_INVALID"
                    )
                    result_row["recovery_accounting_date"] = None
                    result_row["compensation_state"] = None
                    result_row["compensation_double_count_clear"] = None
                    unavailable_count += 1
                    records.append(result_row)
                    continue

                ready_count += 1
                compensation_treatment_count += 1
                if clear is True:
                    double_count_clear_count += 1

                matches = (
                    period_valid
                    and date_from <= accounting_date <= date_to
                )
                result_row[
                    "recovery_accounting_period_matches_request"
                ] = matches
                if matches:
                    in_period_count += 1
                else:
                    outside_period_count += 1
                records.append(result_row)
                continue

            if status == self.MISSING_STATUS and evidence.get("error") is False:
                missing_count += 1
            elif status == self.CONFLICT_STATUS and evidence.get("error") is False:
                conflict_count += 1
            else:
                unavailable_count += 1
            records.append(result_row)

        candidate_count = len(candidates)
        has_candidates = candidate_count > 0
        attribution_complete = (
            period_valid
            and has_candidates
            and ready_count == candidate_count
        )
        attribution_in_period = (
            attribution_complete
            and in_period_count == candidate_count
        )
        compensation_treatment_confirmed = (
            has_candidates
            and compensation_treatment_count == candidate_count
        )
        compensation_double_count_clear = (
            compensation_treatment_confirmed
            and double_count_clear_count == candidate_count
        )
        accounting_evidence_confirmed = (
            attribution_in_period
            and compensation_treatment_confirmed
            and compensation_double_count_clear
        )

        result = dict(base)
        result[
            "accounting_attribution_evidence_available"
        ] = self.accounting_attribution_repository is not None
        result[
            "accounting_attribution_evidence_status"
        ] = (
            "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY"
            if (
                period_valid
                and unavailable_count == 0
                and conflict_count == 0
                and missing_count == 0
            )
            else "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_PARTIAL"
        )
        result["accounting_attribution_evidence_records"] = records
        result["accounting_attribution_candidate_record_count"] = candidate_count
        result["accounting_attribution_ready_candidate_record_count"] = ready_count
        result["accounting_attribution_in_period_candidate_record_count"] = (
            in_period_count
        )
        result["accounting_attribution_outside_period_candidate_record_count"] = (
            outside_period_count
        )
        result["accounting_attribution_missing_candidate_record_count"] = (
            missing_count
        )
        result["accounting_attribution_conflict_candidate_record_count"] = (
            conflict_count
        )
        result["accounting_attribution_unavailable_candidate_record_count"] = (
            unavailable_count
        )
        result["recovery_period_attribution_evidence_complete"] = (
            attribution_complete
        )
        result["recovery_period_attribution_evidence_confirmed"] = (
            attribution_in_period
        )
        result["compensation_accounting_treatment_evidence_confirmed"] = (
            compensation_treatment_confirmed
        )
        result["compensation_double_count_clear"] = compensation_double_count_clear
        result["accounting_attribution_evidence_confirmed"] = (
            accounting_evidence_confirmed
        )

        # v1311-v1320 stages explicit accounting evidence only. None of the
        # established recovery gates are promoted in this package.
        result["originating_sale_quantity_confirmed"] = False
        result["originating_sale_quantity_gate_promoted"] = False
        result["recovery_period_attribution_confirmed"] = False
        result["compensation_accounting_treatment_confirmed"] = False
        result["period_cogs_recovery_confirmed"] = False
        result["accounting_cogs_recovery_confirmed"] = False
        result["confirmed_cogs_recovery_amount"] = 0.0
        result["profit_adjustment_allowed"] = False
        result["automatic_recovery_allowed"] = False
        result["compensation_profit_adjustment_allowed"] = False
        result["read_only"] = True
        result["executed"] = False
        return result

    def _lookup(self, row):
        repository = self.accounting_attribution_repository
        getter = getattr(repository, "get_latest_attribution", None)
        if not callable(getter):
            return self._evidence_unavailable(
                "RETURN_COGS_ACCOUNTING_ATTRIBUTION_REPOSITORY_UNAVAILABLE"
            )
        try:
            evidence = getter(
                return_id=row["return_id"],
                posting_number=row["posting_number"],
                sku=row["sku"],
            )
        except Exception:
            return self._evidence_unavailable(
                "RETURN_COGS_ACCOUNTING_ATTRIBUTION_REPOSITORY_EXCEPTION"
            )
        if not isinstance(evidence, dict):
            return self._evidence_unavailable(
                "RETURN_COGS_ACCOUNTING_ATTRIBUTION_RESULT_INVALID"
            )
        return dict(evidence)

    @classmethod
    def _candidate_record(cls, candidate):
        if not isinstance(candidate, dict):
            return None
        return_id = cls._text(candidate.get("return_id"))
        posting_number = cls._text(candidate.get("posting_number"))
        sku = cls._text(candidate.get("sku"))
        if not return_id or not posting_number or not sku:
            return None
        return {
            "return_id": return_id,
            "posting_number": posting_number,
            "sku": sku,
        }

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _evidence_unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_UNAVAILABLE",
            "accounting_attribution_confirmed": False,
            "recovery_accounting_date": None,
            "compensation_state": None,
            "compensation_double_count_clear": None,
            "confirmed_on": None,
            "source": None,
        }

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_UNAVAILABLE",
            "originating_sale_quantity_confirmed": False,
            "recovery_period_attribution_confirmed": False,
            "compensation_accounting_treatment_confirmed": False,
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
