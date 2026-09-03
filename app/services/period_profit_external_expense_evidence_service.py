from datetime import datetime, timedelta
from math import isfinite


class PeriodProfitExternalExpenseEvidenceService:
    """Read-only evidence for seller expenses outside the Ozon accrual stream."""

    def __init__(self, repository):
        self.repository = repository

    def load(
        self,
        date_from,
        date_to,
    ):
        start = self._date(date_from)
        end = self._date(date_to)

        if (
            start is None
            or end is None
            or start > end
        ):
            return self._error(
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_PERIOD_INVALID"
            )

        try:
            expenses = (
                self.repository
                .get_expenses_by_period(
                    start.isoformat(),
                    end.isoformat(),
                )
            )
            coverage_rows = (
                self.repository
                .get_coverage_by_period(
                    start.isoformat(),
                    end.isoformat(),
                )
            )
        except Exception:
            return self._error(
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_SOURCE_UNAVAILABLE"
            )

        if not isinstance(expenses, list):
            return self._error(
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_ROWS_INVALID"
            )

        if not isinstance(
            coverage_rows,
            list,
        ):
            return self._error(
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_COVERAGE_INVALID"
            )

        normalized_expenses = []
        category_totals = {}
        total = 0.0

        for row in expenses:
            normalized = self._expense_row(
                row,
                start,
                end,
            )
            if normalized is None:
                return self._error(
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ROW_INVALID"
                )

            next_total = (
                total
                + normalized["amount"]
            )
            if not isfinite(next_total):
                return self._error(
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_TOTAL_INVALID"
                )

            category = normalized[
                "category"
            ]
            category_total = (
                category_totals.get(
                    category,
                    0.0,
                )
                + normalized["amount"]
            )
            if not isfinite(category_total):
                return self._error(
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_TOTAL_INVALID"
                )

            total = next_total
            category_totals[
                category
            ] = category_total
            normalized_expenses.append(
                normalized
            )

        normalized_coverage = []

        for row in coverage_rows:
            normalized = (
                self._coverage_row(
                    row
                )
            )
            if normalized is None:
                return self._error(
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_COVERAGE_INVALID"
                )

            normalized_coverage.append(
                normalized
            )

        gaps = self._coverage_gaps(
            start,
            end,
            normalized_coverage,
        )
        coverage_complete = (
            len(gaps) == 0
        )
        coverage_configured = bool(
            normalized_coverage
        )

        rounded_total = round(
            total,
            2,
        )
        rounded_categories = {
            key: round(value, 2)
            for key, value
            in sorted(
                category_totals.items()
            )
        }

        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY"
                if coverage_complete
                else "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL"
            ),
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "coverage_configured": (
                coverage_configured
            ),
            "coverage_complete": (
                coverage_complete
            ),
            "coverage_intervals": (
                normalized_coverage
            ),
            "coverage_gaps": gaps,
            "expense_count": len(
                normalized_expenses
            ),
            "expenses": normalized_expenses,
            "category_breakdown": (
                rounded_categories
            ),
            "observed_expense_total": (
                rounded_total
            ),
            "complete_expense_total": (
                rounded_total
                if coverage_complete
                else None
            ),
            "observed_expense_adjustment_supported": True,
            "complete_profit_adjustment_allowed": (
                coverage_complete
            ),
            "missing_expense_configuration_is_zero": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _expense_row(
        cls,
        row,
        start,
        end,
    ):
        if not isinstance(row, dict):
            return None

        expense_id = row.get("id")
        if (
            isinstance(expense_id, bool)
            or not isinstance(
                expense_id,
                int,
            )
            or expense_id <= 0
        ):
            return None

        expense_date = cls._date(
            row.get("expense_date")
        )
        if (
            expense_date is None
            or expense_date < start
            or expense_date > end
        ):
            return None

        category = str(
            row.get("category") or ""
        ).strip()
        if not category:
            return None

        amount = cls._amount(
            row.get("amount")
        )
        if amount is None:
            return None

        description = row.get(
            "description"
        )
        if description is None:
            description = ""
        if not isinstance(
            description,
            str,
        ):
            return None

        return {
            "id": expense_id,
            "expense_date": (
                expense_date.isoformat()
            ),
            "category": category,
            "amount": round(
                amount,
                2,
            ),
            "description": description,
            "source": (
                "LOCAL_EXPENSE_REPOSITORY"
            ),
        }

    @classmethod
    def _coverage_row(
        cls,
        row,
    ):
        if not isinstance(row, dict):
            return None

        coverage_id = row.get("id")
        if (
            isinstance(coverage_id, bool)
            or not isinstance(
                coverage_id,
                int,
            )
            or coverage_id <= 0
        ):
            return None

        start = cls._date(
            row.get("date_from")
        )
        end = cls._date(
            row.get("date_to")
        )
        if (
            start is None
            or end is None
            or start > end
        ):
            return None

        note = row.get("note")
        if note is None:
            note = ""
        if not isinstance(note, str):
            return None

        return {
            "id": coverage_id,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "note": note,
            "source": (
                "LOCAL_EXPENSE_COVERAGE"
            ),
        }

    @classmethod
    def _coverage_gaps(
        cls,
        start,
        end,
        intervals,
    ):
        normalized = []

        for row in intervals:
            row_start = cls._date(
                row.get("date_from")
            )
            row_end = cls._date(
                row.get("date_to")
            )
            if (
                row_start is None
                or row_end is None
            ):
                continue

            clipped_start = max(
                start,
                row_start,
            )
            clipped_end = min(
                end,
                row_end,
            )
            if (
                clipped_start
                <= clipped_end
            ):
                normalized.append(
                    (
                        clipped_start,
                        clipped_end,
                    )
                )

        normalized.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        current = start
        gaps = []

        for row_start, row_end in normalized:
            if row_end < current:
                continue

            if row_start > current:
                gap_end = min(
                    end,
                    row_start
                    - timedelta(days=1),
                )
                if current <= gap_end:
                    gaps.append({
                        "date_from": (
                            current.isoformat()
                        ),
                        "date_to": (
                            gap_end.isoformat()
                        ),
                    })

            candidate = (
                row_end
                + timedelta(days=1)
            )
            if candidate > current:
                current = candidate

            if current > end:
                break

        if current <= end:
            gaps.append({
                "date_from": (
                    current.isoformat()
                ),
                "date_to": (
                    end.isoformat()
                ),
            })

        return gaps

    @staticmethod
    def _amount(value):
        if isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if (
            not isfinite(number)
            or number < 0
        ):
            return None

        return number

    @staticmethod
    def _date(value):
        text = str(
            value or ""
        ).strip()

        try:
            return datetime.strptime(
                text,
                "%Y-%m-%d",
            ).date()
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_UNAVAILABLE"
            ),
            "read_only": True,
            "executed": False,
        }
