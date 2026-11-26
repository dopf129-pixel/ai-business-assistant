"""Pure aggregate FIFO range estimate over two reconciled Ozon reports.

This projection is non-authoritative, performs no I/O, and never persists COGS.
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from collections.abc import Mapping
from services.fifo_cost_transition_contracts import EvidenceCompleteness, PeriodProvenance, ReportEvidence, ReportType, ScopeIdentity, source_fingerprint
from services.fifo_cost_provisional_contracts import OPENING_BUCKETS, RECEIPT_COLUMNS, NON_SALE_EXPENSE_COLUMNS, SUPPORTED_RECEIPT_COLUMNS, SUPPORTED_NON_SALE_EXPENSE_COLUMNS, ProvisionalIssueCode, ProvisionalStatus, ProvisionalSummaryRequest, ProvisionalSummaryResult

class FifoCostProvisionalSummaryService:
    POLICY_VERSION = "fifo-provisional-summary-v1"
    MAX_UNITS = 1_000_000
    _CENT = Decimal("0.01")

    def calculate(self, request: ProvisionalSummaryRequest) -> ProvisionalSummaryResult:
        if not isinstance(request, ProvisionalSummaryRequest):
            return self._need(ProvisionalIssueCode.SNAPSHOT_REQUIRED)
        if request.snapshot is None:
            return self._need(ProvisionalIssueCode.SNAPSHOT_REQUIRED)
        if request.movement_report is None:
            return self._need(ProvisionalIssueCode.MOVEMENT_REPORT_REQUIRED)
        if request.assumptions.opening_all_old is not True:
            return self._need(ProvisionalIssueCode.OWNER_OPENING_COMPOSITION_REQUIRED)
        if request.assumptions.all_period_supply_receipts_new is not True:
            return self._need(ProvisionalIssueCode.OWNER_RECEIPT_PARTY_REQUIRED)
        try:
            snapshot = self._read_turnover(request.snapshot, scope=request.scope, timezone=request.store_timezone)
            movement = self._read_turnover(request.movement_report, scope=request.scope, timezone=request.store_timezone)
        except _ReportIssue as issue:
            return self._conflict(issue.code)
        if (snapshot["period_from"] != snapshot["period_to"]
                or movement["period_from"] != snapshot["period_to"] + timedelta(days=1)
                or movement["period_to"] < movement["period_from"]
                or request.snapshot.file_sha256 == request.movement_report.file_sha256):
            return self._conflict(ProvisionalIssueCode.REPORT_WINDOW_MISMATCH)
        if snapshot["closing_buckets"] != movement["opening_buckets"]:
            return self._conflict(ProvisionalIssueCode.BUCKET_BOUNDARY_MISMATCH)
        if any(movement["receipt_components"][key] for key in set(RECEIPT_COLUMNS) - SUPPORTED_RECEIPT_COLUMNS):
            return self._conflict(ProvisionalIssueCode.UNSUPPORTED_RECEIPTS)
        if any(movement["other_expense_components"][key] for key in set(NON_SALE_EXPENSE_COLUMNS) - SUPPORTED_NON_SALE_EXPENSE_COLUMNS):
            return self._conflict(ProvisionalIssueCode.UNSUPPORTED_EXPENSES)

        a = sum(snapshot["closing_buckets"].values())
        l = movement["receipt_components"]["L"]
        r = movement["receipt_components"]["M"]
        sold = movement["redeemed_units"]
        other_expenses = sum(movement["other_expense_components"][key] for key in SUPPORTED_NON_SALE_EXPENSE_COLUMNS)
        b = movement["closing_total"]
        if a + l + r - sold - other_expenses != b:
            return self._conflict(ProvisionalIssueCode.REPORT_CONTROL_INVALID)

        assumptions = request.assumptions
        upper_residual = min(b, a + r)
        if assumptions.closing_old_min is None:
            o_min, o_max = 0, upper_residual
            residual_unknown = True
        else:
            o_min, o_max = assumptions.closing_old_min, assumptions.closing_old_max
            residual_unknown = False
            if o_max > upper_residual:
                return self._conflict(ProvisionalIssueCode.CLOSING_OLD_STOCK_RANGE_INVALID)
        old_min, old_max = self.derive_old_sold_range(
            opening_old=a, buyer_returns=r, redeemed=sold,
            supported_other_expenses=other_expenses,
            closing_old_min=o_min, closing_old_max=o_max,
        )
        if old_min is None or old_max is None:
            return self._conflict(ProvisionalIssueCode.QUANTITY_DISTRIBUTION_EMPTY)
        new_min, new_max = sold - old_max, sold - old_min
        cogs_1 = self._round_money(old_min * request.old_unit_cost_rub + (sold - old_min) * request.new_unit_cost_rub)
        cogs_2 = self._round_money(old_max * request.old_unit_cost_rub + (sold - old_max) * request.new_unit_cost_rub)
        cogs_low, cogs_high = sorted((cogs_1, cogs_2))
        fingerprint = source_fingerprint({
            "policy": self.POLICY_VERSION,
            "scope": {"owner_id": request.scope.owner_id, "store_id": request.scope.store_id,
                      "product_id": request.scope.product_id, "offer_id": request.scope.offer_id, "sku": request.scope.sku},
            "timezone": request.store_timezone,
            "snapshot": request.snapshot.file_sha256,
            "movement": request.movement_report.file_sha256,
            "assumptions": {"opening_all_old": assumptions.opening_all_old,
                            "all_period_supply_receipts_new": assumptions.all_period_supply_receipts_new,
                            "closing_old_min": o_min, "closing_old_max": o_max,
                            "closing_old_was_unknown": residual_unknown},
            "old_cost": str(request.old_unit_cost_rub), "new_cost": str(request.new_unit_cost_rub),
        })
        issues = (ProvisionalIssueCode.END_OLD_STOCK_UNESTABLISHED,) if residual_unknown else ()
        return ProvisionalSummaryResult(
            status=ProvisionalStatus.SUMMARY_RANGE, issue_codes=issues,
            period_from=movement["period_from"].isoformat(), period_to=movement["period_to"].isoformat(),
            opening_total=a, opening_buckets=snapshot["closing_buckets"],
            closing_total=b, closing_buckets=movement["closing_buckets"],
            supply_receipts=l, buyer_return_receipts=r, redeemed_units=sold,
            other_supported_expenses=other_expenses,
            excluded_compensation_receipt=movement["excluded_compensation_receipt"],
            excluded_compensation_expense=movement["excluded_compensation_expense"],
            old_sold_min=old_min, old_sold_max=old_max, new_sold_min=new_min, new_sold_max=new_max,
            gross_cogs_low_rub=cogs_low, gross_cogs_high_rub=cogs_high,
            old_cost_rub=request.old_unit_cost_rub, new_cost_rub=request.new_unit_cost_rub,
            snapshot_fingerprint=request.snapshot.file_sha256,
            movement_fingerprint=request.movement_report.file_sha256,
            result_fingerprint=fingerprint,
        )

    @staticmethod
    def derive_old_sold_range(*, opening_old, buyer_returns, redeemed, supported_other_expenses, closing_old_min, closing_old_max):
        values = (opening_old, buyer_returns, redeemed, supported_other_expenses, closing_old_min, closing_old_max)
        if any(type(value) is not int or value < 0 for value in values) or closing_old_min > closing_old_max:
            return None, None
        lower = max(0, opening_old - supported_other_expenses - closing_old_max)
        upper = min(redeemed, opening_old + buyer_returns - closing_old_min)
        return (lower, upper) if lower <= upper else (None, None)

    @classmethod
    def _read_turnover(cls, report, *, scope, timezone):
        if not isinstance(report, ReportEvidence) or report.report_type is not ReportType.TURNOVER:
            raise _ReportIssue(ProvisionalIssueCode.REPORT_INCOMPLETE)
        if report.metadata.scope != scope or report.metadata.store_timezone != timezone:
            raise _ReportIssue(ProvisionalIssueCode.REPORT_SCOPE_MISMATCH)
        if report.period_provenance is not PeriodProvenance.OWNER_CONFIRMED:
            raise _ReportIssue(ProvisionalIssueCode.REPORT_PERIOD_UNCONFIRMED)
        if report.metadata.completeness is not EvidenceCompleteness.COMPLETE:
            raise _ReportIssue(ProvisionalIssueCode.REPORT_INCOMPLETE)
        if not report.period_from or not report.period_to:
            raise _ReportIssue(ProvisionalIssueCode.REPORT_PERIOD_UNCONFIRMED)
        try:
            period_from, period_to = date.fromisoformat(report.period_from), date.fromisoformat(report.period_to)
            fields = report.normalized_fields
            opening = cls._buckets(fields.get("opening_buckets"))
            closing = cls._buckets(fields.get("closing_buckets"))
            receipts = cls._columns(fields.get("receipt_components_by_column"), RECEIPT_COLUMNS)
            expenses = cls._columns(fields.get("non_sale_expense_components_by_column"), NON_SALE_EXPENSE_COLUMNS)
            redeemed = cls._quantity(fields.get("redeemed_units"))
            opening_total = cls._quantity(fields.get("opening_total"))
            receipts_total = cls._quantity(fields.get("receipts_total"))
            expenses_total = cls._quantity(fields.get("expenses_total"))
            closing_total = cls._quantity(fields.get("closing_total"))
            difference = fields.get("reported_balance_difference")
            if type(difference) is not int or abs(difference) > cls.MAX_UNITS:
                raise ValueError("FIFO_PROVISIONAL_QUANTITY_INVALID")
            computed_difference = opening_total + receipts_total - expenses_total - closing_total
            excluded_receipt = cls._quantity(fields.get("excluded_compensation_receipt"))
            excluded_expense = cls._quantity(fields.get("excluded_compensation_expense"))
        except (TypeError, ValueError, KeyError, OverflowError):
            raise _ReportIssue(ProvisionalIssueCode.REPORT_CONTROL_INVALID)
        if (period_to < period_from
                or sum(opening.values()) != opening_total
                or sum(closing.values()) != closing_total
                or sum(receipts.values()) != receipts_total
                or redeemed + sum(expenses.values()) != expenses_total
                or fields.get("component_controls_match") is not True
                or fields.get("computed_balance_difference") != computed_difference
                or fields.get("balance_status") != "BALANCED"
                or difference != computed_difference
                or computed_difference != 0):
            raise _ReportIssue(ProvisionalIssueCode.REPORT_CONTROL_INVALID)
        return {
            "period_from": period_from, "period_to": period_to,
            "opening_buckets": opening, "closing_buckets": closing,
            "opening_total": opening_total, "receipts_total": receipts_total,
            "expenses_total": expenses_total, "closing_total": closing_total,
            "receipt_components": receipts, "other_expense_components": expenses,
            "redeemed_units": redeemed,
            "excluded_compensation_receipt": excluded_receipt,
            "excluded_compensation_expense": excluded_expense,
        }

    @classmethod
    def _buckets(cls, value):
        if not isinstance(value, Mapping) or set(value) != set(OPENING_BUCKETS):
            raise ValueError("FIFO_PROVISIONAL_BUCKETS_INVALID")
        return {key: cls._quantity(value[key]) for key in OPENING_BUCKETS}

    @classmethod
    def _columns(cls, value, expected):
        if not isinstance(value, Mapping) or set(value) != set(expected):
            raise ValueError("FIFO_PROVISIONAL_COLUMNS_INVALID")
        return {key: cls._quantity(value[key]) for key in expected}

    @classmethod
    def _quantity(cls, value):
        if type(value) is not int or not 0 <= value <= cls.MAX_UNITS:
            raise ValueError("FIFO_PROVISIONAL_QUANTITY_INVALID")
        return value

    @classmethod
    def _round_money(cls, value):
        return value.quantize(cls._CENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _need(code):
        return ProvisionalSummaryResult(status=ProvisionalStatus.NEED_INPUT, issue_codes=(code,))

    @staticmethod
    def _conflict(code):
        return ProvisionalSummaryResult(status=ProvisionalStatus.SOURCE_CONFLICT, issue_codes=(code,))

class _ReportIssue(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code.value)
