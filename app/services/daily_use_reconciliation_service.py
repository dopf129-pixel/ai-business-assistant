"""Offline comparison of an Ozon accrual workbook and a saved profit snapshot.

This service is deliberately narrow: it normalizes the signed total from one
explicit accrual report profile and compares it with the existing Period Profit
snapshot. It does not calculate profit or make Ozon requests.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re


class DailyUseReconciliationService:
    PROFILE_ID = "ozon_accruals_xlsx_v1"
    SHEET_NAME = "Начисления"
    HEADER_ROW = 2
    MAX_REPORT_ROWS = 100_000
    MAX_REPORT_COLUMNS = 64
    REQUIRED_HEADERS = (
        "Дата начисления",
        "Сумма итого, руб.",
    )
    AMOUNT_METRIC = "net_accrual"
    SCOPE_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
    VALID_COVERAGE_ASSERTIONS = {"USER_CONFIRMED_FULL_PERIOD"}
    SNAPSHOT_METRIC_STATUSES = {"CONFIRMED", "PARTIAL", "UNAVAILABLE", "INVALID"}

    def normalize_accrual_table(
        self,
        *,
        sheet_name,
        header_row,
        headers,
        rows,
        period_from,
        period_to,
        source_period_from,
        source_period_to,
        scope_alias,
        coverage_assertion=None,
        sku_filter_value=None,
        sku_dimension_alias=None,
    ):
        """Return a safe period aggregate from rows read using the exact profile.

        ``source_period_*`` must come from the workbook's visible report period;
        ``period_*`` is the requested comparison period. The caller's coverage
        assertion is explicit because row dates alone cannot prove that a report
        has no missing transactions.
        """
        error = self._validate_table(sheet_name, header_row, headers, rows)
        if error:
            return self._error(error)
        period = self._period(period_from, period_to)
        source_period = self._period(source_period_from, source_period_to)
        if period is None or source_period is None:
            return self._error("DAILY_USE_RECONCILIATION_PERIOD_INVALID")
        alias = self._scope_alias(scope_alias)
        if alias is None:
            return self._error("DAILY_USE_RECONCILIATION_SCOPE_ALIAS_INVALID")

        header_positions = {name: index for index, name in enumerate(headers)}
        date_index = header_positions["Дата начисления"]
        amount_index = header_positions["Сумма итого, руб."]
        sku_index = header_positions.get("SKU")
        if sku_filter_value is not None and (sku_index is None or self._scope_alias(sku_dimension_alias) is None):
            return self._error("DAILY_USE_RECONCILIATION_SKU_FILTER_INVALID")
        if sku_filter_value is None and sku_dimension_alias is not None:
            return self._error("DAILY_USE_RECONCILIATION_SKU_FILTER_INVALID")
        total = Decimal("0")
        selected_rows = 0
        invalid_rows = 0
        for row_number, row in enumerate(rows, start=self.HEADER_ROW + 1):
            if not isinstance(row, (list, tuple)) or len(row) != len(headers):
                return self._error("DAILY_USE_RECONCILIATION_ROW_SCHEMA_INVALID")
            row_date = self._date(row[date_index])
            if row_date is None:
                invalid_rows += 1
                continue
            if row_date < source_period[0] or row_date > source_period[1]:
                return self._error("DAILY_USE_RECONCILIATION_SOURCE_PERIOD_MISMATCH")
            if row_date < period[0] or row_date > period[1]:
                continue
            if sku_filter_value is not None and str(row[sku_index]).strip() != str(sku_filter_value).strip():
                continue
            amount = self._decimal(row[amount_index])
            if amount is None:
                # Expose only the workbook row number; never echo its contents.
                return self._error(
                    "DAILY_USE_RECONCILIATION_AMOUNT_INVALID",
                    row_number=row_number,
                )
            total += amount
            selected_rows += 1

        if invalid_rows:
            coverage_status = "INCOMPLETE"
            reason = "REPORT_ROWS_WITHOUT_VALID_ACCRUAL_DATE"
        elif selected_rows == 0:
            coverage_status = "UNAVAILABLE"
            reason = "NO_ROWS_IN_REQUESTED_PERIOD"
        elif source_period[0] > period[0] or source_period[1] < period[1]:
            coverage_status = "PARTIAL"
            reason = "SOURCE_REPORT_PERIOD_DIFFERS_FROM_REQUESTED_PERIOD"
        elif coverage_assertion not in self.VALID_COVERAGE_ASSERTIONS:
            coverage_status = "UNVERIFIED"
            reason = "FULL_PERIOD_COVERAGE_NOT_CONFIRMED"
        else:
            coverage_status = "COMPLETE"
            reason = None

        return {
            "error": False,
            "status": "DAILY_USE_REFERENCE_READY",
            "reference": {
                "schema": "daily_use_reference",
                "schema_version": 1,
                "profile_id": self.PROFILE_ID,
                "scope_alias": alias,
                "dimension": {
                    "kind": "sku" if sku_filter_value is not None else "store",
                    "alias": self._scope_alias(sku_dimension_alias) if sku_filter_value is not None else alias,
                },
                "period": {"from": period[0].isoformat(), "to": period[1].isoformat()},
                "source_period": {
                    "from": source_period[0].isoformat(),
                    "to": source_period[1].isoformat(),
                },
                "date_basis": "accrual_date",
                "coverage": {
                    "status": coverage_status,
                    "reason": reason,
                    "rows_in_period": selected_rows,
                    "invalid_date_rows": invalid_rows,
                },
                "metrics": {
                    self.AMOUNT_METRIC: {
                        "value": self._money(total) if selected_rows else None,
                        "status": (
                            "CONFIRMED" if coverage_status == "COMPLETE"
                            else "UNAVAILABLE" if selected_rows == 0
                            else "PARTIAL"
                        ),
                        "unit": "RUB",
                        "semantic": "signed_leaf_accrual_amount_sum",
                    },
                },
            },
            "read_only": True,
            "executed": False,
        }

    def compare(self, reference, canonical_snapshot):
        """Compare only period, store alias, coverage, unit, and value semantics."""
        ref_error = self._validate_reference(reference)
        if ref_error:
            return self._error(ref_error)
        snapshot_error = self._validate_snapshot(canonical_snapshot)
        if snapshot_error:
            return self._error(snapshot_error)

        expected = reference["metrics"][self.AMOUNT_METRIC]
        actual = self._snapshot_metric(canonical_snapshot, self.AMOUNT_METRIC)
        if actual is None:
            return self._error("DAILY_USE_CANONICAL_METRIC_UNAVAILABLE")
        ref_period = reference["period"]
        snap_period = canonical_snapshot["period"]
        if reference["scope_alias"] != canonical_snapshot["scope_alias"]:
            status = "NOT_COMPARABLE"
            reason = "STORE_SCOPE_ALIAS_MISMATCH"
        elif reference.get("dimension") != canonical_snapshot.get("dimension"):
            status = "NOT_COMPARABLE"
            reason = (
                "SKU_DIMENSION_MISMATCH"
                if (reference.get("dimension") or {}).get("kind") == "sku"
                or (canonical_snapshot.get("dimension") or {}).get("kind") == "sku"
                else "DIMENSION_MISMATCH"
            )
        elif ref_period != snap_period:
            status = "NOT_COMPARABLE"
            reason = "PERIOD_MISMATCH"
        elif reference["date_basis"] != actual["date_basis"]:
            status = "NOT_COMPARABLE"
            reason = "DATE_BASIS_MISMATCH"
        elif expected["unit"] != actual["unit"] or expected["semantic"] != actual["semantic"]:
            status = "NOT_COMPARABLE"
            reason = "METRIC_SEMANTICS_MISMATCH"
        elif reference["coverage"]["status"] != "COMPLETE":
            status = "EVIDENCE_REQUIRED"
            reason = reference["coverage"]["reason"] or "REFERENCE_COVERAGE_INCOMPLETE"
        elif canonical_snapshot["coverage"]["status"] != "COMPLETE":
            status = "EVIDENCE_REQUIRED"
            reason = "CANONICAL_SNAPSHOT_COVERAGE_INCOMPLETE"
        elif expected["status"] != "CONFIRMED" or actual["status"] != "CONFIRMED":
            status = "EVIDENCE_REQUIRED"
            reason = "METRIC_STATUS_NOT_CONFIRMED"
        else:
            expected_value = self._decimal(expected["value"])
            actual_value = self._decimal(actual["value"])
            if expected_value is None or actual_value is None:
                return self._error("DAILY_USE_CANONICAL_METRIC_VALUE_INVALID")
            difference = actual_value - expected_value
            status = "MATCH" if difference == Decimal("0.00") else "UNRESOLVED"
            reason = None if status == "MATCH" else "SIGNED_AMOUNT_DIFFERENCE"
        expected_value = expected.get("value") if status in {"MATCH", "UNRESOLVED"} else None
        actual_value = actual.get("value") if status in {"MATCH", "UNRESOLVED"} else None
        difference_value = None
        if status in {"MATCH", "UNRESOLVED"}:
            difference_value = self._money(
                self._decimal(actual_value) - self._decimal(expected_value)
            )

        return {
            "error": False,
            "status": "DAILY_USE_COMPARISON_READY",
            "rows": [{
                "metric": self.AMOUNT_METRIC,
                "expected": expected_value,
                "actual": actual_value,
                "difference": difference_value,
                "source_basis": "ozon_accruals_xlsx_v1/accrual_date vs period_profit/net_accrual",
                "coverage": reference["coverage"]["status"] + "/" + canonical_snapshot["coverage"]["status"],
                "status": status,
                "reason": reason,
            }],
            "read_only": True,
            "executed": False,
        }

    def canonical_from_period_profit_export(
        self, document, *, scope_alias, revision="UNAVAILABLE"
    ):
        """Project the existing allowlisted export into the comparator contract."""
        alias = self._scope_alias(scope_alias)
        if alias is None:
            return self._error("DAILY_USE_RECONCILIATION_SCOPE_ALIAS_INVALID")
        if (
            not isinstance(document, dict)
            or document.get("document_kind") != "owner_analytics_export"
            or document.get("export_kind") != "period_profit"
            or document.get("schema_version") != 1
        ):
            return self._error("DAILY_USE_CANONICAL_EXPORT_SCHEMA_UNSUPPORTED")
        metadata = document.get("metadata")
        periods = metadata.get("periods") if isinstance(metadata, dict) else None
        current = periods.get("current") if isinstance(periods, dict) else None
        if not isinstance(current, dict):
            return self._error("DAILY_USE_CANONICAL_PERIOD_MISSING")
        period = self._period(current.get("from"), current.get("to"))
        if period is None:
            return self._error("DAILY_USE_CANONICAL_PERIOD_INVALID")
        rows = document.get("rows")
        matching = [
            row for row in rows if isinstance(row, dict)
            and row.get("section") == "comparison_metric"
            and row.get("name") == self.AMOUNT_METRIC
        ] if isinstance(rows, list) else []
        if len(matching) != 1:
            return self._error("DAILY_USE_CANONICAL_METRIC_UNAVAILABLE")
        metric = matching[0]
        status = metric.get("current_status")
        value = metric.get("current_value")
        if status not in self.SNAPSHOT_METRIC_STATUSES:
            return self._error("DAILY_USE_CANONICAL_METRIC_STATUS_INVALID")
        coverage_status = (
            metadata.get("coverage_status") if isinstance(metadata, dict) else None
        )
        if coverage_status not in {"COMPLETE", "PARTIAL", "UNAVAILABLE", "UNKNOWN"}:
            coverage_status = "UNKNOWN"
        if not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", revision):
            return self._error("DAILY_USE_CANONICAL_REVISION_INVALID")
        return {
            "error": False,
            "status": "DAILY_USE_CANONICAL_SNAPSHOT_READY",
            "snapshot": {
                "schema": "daily_use_canonical_snapshot",
                "schema_version": 1,
                "scope_alias": alias,
                "dimension": {"kind": "store", "alias": alias},
                "application_revision": revision,
                "generated_at": metadata.get("snapshot_generated_at"),
                "period": {"from": period[0].isoformat(), "to": period[1].isoformat()},
                "date_basis": "accrual_date",
                "coverage": {"status": coverage_status},
                "metrics": {
                    self.AMOUNT_METRIC: {
                        "value": value,
                        "status": status,
                        "unit": metric.get("unit"),
                        "semantic": "signed_leaf_accrual_amount_sum",
                        "date_basis": "accrual_date",
                    },
                },
                "read_only": True,
                "executed": False,
            },
        }

    def _validate_table(self, sheet_name, header_row, headers, rows):
        if sheet_name != self.SHEET_NAME:
            return "DAILY_USE_REPORT_PROFILE_SHEET_MISMATCH"
        if header_row != self.HEADER_ROW:
            return "DAILY_USE_REPORT_PROFILE_HEADER_ROW_MISMATCH"
        if not isinstance(headers, (list, tuple)) or not headers or len(headers) > self.MAX_REPORT_COLUMNS:
            return "DAILY_USE_REPORT_PROFILE_COLUMNS_MISSING"
        if any(not isinstance(value, str) for value in headers):
            return "DAILY_USE_REPORT_PROFILE_COLUMNS_INVALID"
        if len(headers) != len(set(headers)):
            return "DAILY_USE_REPORT_PROFILE_DUPLICATE_COLUMN"
        if any(name not in headers for name in self.REQUIRED_HEADERS):
            return "DAILY_USE_REPORT_PROFILE_COLUMNS_UNSUPPORTED"
        if not isinstance(rows, (list, tuple)) or len(rows) > self.MAX_REPORT_ROWS:
            return "DAILY_USE_REPORT_PROFILE_ROWS_INVALID"
        return None

    def _validate_reference(self, reference):
        if not isinstance(reference, dict) or reference.get("schema") != "daily_use_reference" or reference.get("schema_version") != 1 or reference.get("profile_id") != self.PROFILE_ID:
            return "DAILY_USE_REFERENCE_SCHEMA_UNSUPPORTED"
        if self._scope_alias(reference.get("scope_alias")) is None:
            return "DAILY_USE_RECONCILIATION_SCOPE_ALIAS_INVALID"
        dimension = reference.get("dimension")
        if not isinstance(dimension, dict) or dimension.get("kind") not in {"store", "sku"} or self._scope_alias(dimension.get("alias")) is None:
            return "DAILY_USE_REFERENCE_DIMENSION_INVALID"
        period = reference.get("period")
        if not isinstance(period, dict) or self._period(period.get("from"), period.get("to")) is None:
            return "DAILY_USE_REFERENCE_PERIOD_INVALID"
        if reference.get("date_basis") != "accrual_date":
            return "DAILY_USE_REFERENCE_DATE_BASIS_INVALID"
        coverage = reference.get("coverage")
        metrics = reference.get("metrics")
        metric = metrics.get(self.AMOUNT_METRIC) if isinstance(metrics, dict) else None
        if not isinstance(coverage, dict) or not isinstance(metric, dict):
            return "DAILY_USE_REFERENCE_SCHEMA_INVALID"
        if coverage.get("status") not in {"COMPLETE", "PARTIAL", "INCOMPLETE", "UNAVAILABLE", "UNVERIFIED"}:
            return "DAILY_USE_REFERENCE_COVERAGE_INVALID"
        if metric.get("unit") != "RUB" or metric.get("semantic") != "signed_leaf_accrual_amount_sum":
            return "DAILY_USE_REFERENCE_METRIC_SEMANTICS_INVALID"
        if metric.get("value") is not None and self._decimal(metric.get("value")) is None:
            return "DAILY_USE_REFERENCE_METRIC_VALUE_INVALID"
        if metric.get("status") == "CONFIRMED" and metric.get("value") is None:
            return "DAILY_USE_REFERENCE_METRIC_VALUE_INVALID"
        return None

    def _validate_snapshot(self, snapshot):
        if not isinstance(snapshot, dict) or snapshot.get("schema") != "daily_use_canonical_snapshot" or snapshot.get("schema_version") != 1:
            return "DAILY_USE_CANONICAL_SNAPSHOT_SCHEMA_UNSUPPORTED"
        if self._scope_alias(snapshot.get("scope_alias")) is None:
            return "DAILY_USE_RECONCILIATION_SCOPE_ALIAS_INVALID"
        dimension = snapshot.get("dimension")
        if not isinstance(dimension, dict) or dimension.get("kind") not in {"store", "sku"} or self._scope_alias(dimension.get("alias")) is None:
            return "DAILY_USE_CANONICAL_DIMENSION_INVALID"
        period = snapshot.get("period")
        if not isinstance(period, dict) or self._period(period.get("from"), period.get("to")) is None:
            return "DAILY_USE_CANONICAL_PERIOD_INVALID"
        metric = self._snapshot_metric(snapshot, self.AMOUNT_METRIC)
        if metric is None:
            return "DAILY_USE_CANONICAL_METRIC_UNAVAILABLE"
        if metric.get("unit") != "RUB" or metric.get("semantic") != "signed_leaf_accrual_amount_sum":
            return "DAILY_USE_CANONICAL_METRIC_SEMANTICS_INVALID"
        if metric.get("status") not in self.SNAPSHOT_METRIC_STATUSES:
            return "DAILY_USE_CANONICAL_METRIC_STATUS_INVALID"
        if metric.get("value") is not None and self._decimal(metric.get("value")) is None:
            return "DAILY_USE_CANONICAL_METRIC_VALUE_INVALID"
        coverage = snapshot.get("coverage")
        if not isinstance(coverage, dict) or coverage.get("status") not in {"COMPLETE", "PARTIAL", "UNAVAILABLE", "UNKNOWN"}:
            return "DAILY_USE_CANONICAL_COVERAGE_INVALID"
        return None

    @staticmethod
    def _snapshot_metric(snapshot, name):
        metrics = snapshot.get("metrics") if isinstance(snapshot, dict) else None
        value = metrics.get(name) if isinstance(metrics, dict) else None
        return value if isinstance(value, dict) else None

    @classmethod
    def _period(cls, start, end):
        first = cls._date(start)
        last = cls._date(end)
        if first is None or last is None or first > last:
            return None
        return first, last

    @staticmethod
    def _date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
            result = Decimal(str(value))
            if not result.is_finite() or result.adjusted() > 12 or result.adjusted() < -6:
                return None
            return result
        except (InvalidOperation, TypeError, ValueError):
            return None

    @classmethod
    def _money(cls, value):
        return format(value.quantize(Decimal("0.01")), "f")

    @classmethod
    def _scope_alias(cls, value):
        return value if isinstance(value, str) and cls.SCOPE_ALIAS_RE.fullmatch(value) else None

    @staticmethod
    def _error(code, **details):
        result = {"error": True, "status": code, "code": code}
        result.update(details)
        return result
