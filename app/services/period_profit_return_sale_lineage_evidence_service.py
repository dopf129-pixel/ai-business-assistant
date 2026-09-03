from datetime import date, datetime, timedelta


class PeriodProfitReturnSaleLineageEvidenceService:
    """Read-only evidence linking returns to positive sale accruals in the period."""

    CUSTOMER_RETURN_TYPES = {
        "clientreturn",
        "fullreturn",
    }

    def __init__(
        self,
        finance_service,
    ):
        self.finance_service = (
            finance_service
        )

    def analyze(
        self,
        return_evidence,
    ):
        source = dict(
            return_evidence
            or {}
        )

        if source.get("error") is True:
            return self._unavailable(
                "RETURN_EVIDENCE_UNAVAILABLE"
            )

        if source.get("status") not in {
            "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
            "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL",
        }:
            return self._unavailable(
                "RETURN_EVIDENCE_REQUIRED"
            )

        records = source.get(
            "records"
        )
        if not isinstance(
            records,
            list,
        ):
            return self._unavailable(
                "RETURN_RECORDS_INVALID"
            )

        period = self._period(
            source.get("date_from"),
            source.get("date_to"),
        )
        if period is None:
            return self._unavailable(
                "RETURN_LINEAGE_PERIOD_INVALID"
            )

        lineage_records = []
        target_pairs = set()

        for record in records:
            if not isinstance(
                record,
                dict,
            ):
                continue

            return_type = str(
                record.get("type")
                or ""
            ).strip().lower()
            if (
                return_type
                not in self.CUSTOMER_RETURN_TYPES
            ):
                continue

            posting_number = str(
                record.get(
                    "posting_number"
                )
                or ""
            ).strip()
            sku = str(
                record.get("sku")
                or ""
            ).strip()

            row = {
                "return_id": (
                    record.get("id")
                    or record.get("return_id")
                ),
                "posting_number": (
                    posting_number
                    or None
                ),
                "sku": (
                    sku
                    or None
                ),
                "offer_id": (
                    record.get("offer_id")
                ),
                "lineage_status": (
                    "UNRESOLVED_IDENTIFIERS"
                    if (
                        not posting_number
                        or not sku
                    )
                    else "PENDING"
                ),
                "matched_sale_accrual_date": None,
                "matched_sale_accrual_dates": [],
            }
            lineage_records.append(
                row
            )

            if (
                posting_number
                and sku
            ):
                target_pairs.add(
                    (
                        posting_number,
                        sku,
                    )
                )

        finance_error_dates = []
        finance_partial_dates = []
        malformed_sale_record_count = 0
        sale_dates_by_pair = {}

        if target_pairs:
            getter = getattr(
                self.finance_service,
                "get_daily_sale_posting_evidence",
                None,
            )
            if not callable(getter):
                return self._unavailable(
                    "SALE_POSTING_EVIDENCE_UNAVAILABLE"
                )

            current, finish = period
            while current <= finish:
                day = current.isoformat()

                try:
                    daily = getter(
                        day
                    )
                except Exception:
                    finance_error_dates.append(
                        day
                    )
                    current += timedelta(
                        days=1
                    )
                    continue

                if (
                    not isinstance(
                        daily,
                        dict,
                    )
                    or daily.get("error")
                    is True
                ):
                    finance_error_dates.append(
                        day
                    )
                    current += timedelta(
                        days=1
                    )
                    continue

                if (
                    daily.get("complete")
                    is not True
                ):
                    finance_partial_dates.append(
                        day
                    )

                malformed = (
                    daily.get(
                        "malformed_sale_record_count"
                    )
                    or 0
                )
                if (
                    isinstance(
                        malformed,
                        bool,
                    )
                    or not isinstance(
                        malformed,
                        int,
                    )
                    or malformed < 0
                ):
                    finance_partial_dates.append(
                        day
                    )
                else:
                    malformed_sale_record_count += (
                        malformed
                    )

                daily_records = daily.get(
                    "records"
                )
                if not isinstance(
                    daily_records,
                    list,
                ):
                    finance_partial_dates.append(
                        day
                    )
                    current += timedelta(
                        days=1
                    )
                    continue

                for sale_record in daily_records:
                    if not isinstance(
                        sale_record,
                        dict,
                    ):
                        finance_partial_dates.append(
                            day
                        )
                        continue

                    posting_number = str(
                        sale_record.get(
                            "posting_number"
                        )
                        or ""
                    ).strip()
                    sku = str(
                        sale_record.get("sku")
                        or ""
                    ).strip()
                    accrual_date = self._date(
                        sale_record.get(
                            "accrual_date"
                        )
                    )

                    if (
                        not posting_number
                        or not sku
                        or accrual_date is None
                    ):
                        finance_partial_dates.append(
                            day
                        )
                        continue

                    pair = (
                        posting_number,
                        sku,
                    )
                    if pair not in target_pairs:
                        continue

                    sale_dates_by_pair.setdefault(
                        pair,
                        set(),
                    ).add(
                        accrual_date.isoformat()
                    )

                current += timedelta(
                    days=1
                )

        finance_error_dates = sorted(
            set(finance_error_dates)
        )
        finance_partial_dates = sorted(
            set(finance_partial_dates)
        )
        finance_period_complete = (
            not finance_error_dates
            and not finance_partial_dates
        )

        matched = 0
        unmatched = 0
        ambiguous = 0
        unresolved = 0

        for row in lineage_records:
            if (
                row["lineage_status"]
                == "UNRESOLVED_IDENTIFIERS"
            ):
                unresolved += 1
                continue

            pair = (
                row["posting_number"],
                row["sku"],
            )
            dates = sorted(
                sale_dates_by_pair.get(
                    pair,
                    set(),
                )
            )
            row[
                "matched_sale_accrual_dates"
            ] = dates

            if len(dates) == 1:
                row["lineage_status"] = (
                    "MATCHED_IN_SELECTED_PERIOD"
                )
                row[
                    "matched_sale_accrual_date"
                ] = dates[0]
                matched += 1
            elif not dates:
                row["lineage_status"] = (
                    "SALE_NOT_FOUND_IN_SELECTED_PERIOD"
                )
                unmatched += 1
            else:
                row["lineage_status"] = (
                    "MULTIPLE_SALE_DATES_AMBIGUOUS"
                )
                ambiguous += 1

        return_sample_complete = (
            source.get("complete")
            is True
            and source.get(
                "return_record_count_exact"
            )
            is True
        )

        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_READY"
                if finance_period_complete
                else "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_PARTIAL"
            ),
            "date_from": (
                period[0].isoformat()
            ),
            "date_to": (
                period[1].isoformat()
            ),
            "eligible_return_record_count": (
                len(lineage_records)
            ),
            "matched_return_record_count": (
                matched
            ),
            "unmatched_return_record_count": (
                unmatched
            ),
            "ambiguous_return_record_count": (
                ambiguous
            ),
            "unresolved_return_record_count": (
                unresolved
            ),
            "finance_period_complete": (
                finance_period_complete
            ),
            "finance_error_dates": (
                finance_error_dates
            ),
            "finance_partial_dates": (
                finance_partial_dates
            ),
            "malformed_sale_record_count": (
                malformed_sale_record_count
            ),
            "return_sample_complete": (
                return_sample_complete
            ),
            "lineage_records": (
                lineage_records
            ),
            "matching_basis": (
                "OZON_POSTING_NUMBER_AND_SKU_POSITIVE_SALE_ACCRUAL"
            ),
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _period(
        cls,
        date_from,
        date_to,
    ):
        start = cls._date(
            date_from
        )
        finish = cls._date(
            date_to
        )
        if (
            start is None
            or finish is None
            or start > finish
        ):
            return None
        return start, finish

    @staticmethod
    def _date(value):
        if isinstance(
            value,
            datetime,
        ):
            return value.date()
        if isinstance(
            value,
            date,
        ):
            return value

        try:
            return datetime.fromisoformat(
                str(value).replace(
                    "Z",
                    "+00:00",
                )
            ).date()
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_UNAVAILABLE"
            ),
            "finance_period_complete": False,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }
