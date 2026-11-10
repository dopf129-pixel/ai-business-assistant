"""Create a review-only opening inventory proposal for a late FIFO transition.

The proposal preserves evidence buckets and time provenance.  It deliberately
does not convert report totals into FIFO opening units or mutate the live queue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType
from typing import Mapping

from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    TransitionCase,
    TransitionState,
    normalize_date_only,
    normalize_quantity,
)
from services.fifo_cost_transition_supply_reconciliation_service import (
    FifoCostTransitionSupplyReconciliation,
    FifoSupplyDeclarationView,
)


@dataclass(frozen=True, slots=True)
class FifoOpeningStockEvidenceView:
    report_fingerprint: str
    captured_at: str
    period_from: str | None
    period_to: str | None
    period_provenance: PeriodProvenance
    completeness: EvidenceCompleteness
    stock_buckets: Mapping[str, int | None]
    fbs_return_available_units: int | None
    fbs_return_is_subset_of_available: bool | None
    warehouse_control_status: str | None
    eligible_as_cutoff_snapshot: bool
    owner_confirmed_reserved_units: int | None = None
    owner_confirmed_total_ozon_units: int | None = None
    opening_composition_fingerprint: str | None = None
    opening_composition_report_fingerprint: str | None = None
    opening_composition_date: str | None = None


@dataclass(frozen=True, slots=True)
class FifoTurnoverControlView:
    report_fingerprint: str
    captured_at: str
    period_from: str | None
    period_to: str | None
    period_provenance: PeriodProvenance
    completeness: EvidenceCompleteness
    opening_total: int | None
    receipts_total: int | None
    expenses_total: int | None
    redeemed_units: int | None
    non_sale_expense_units: int | None
    withdrawal_units: int | None
    closing_total: int | None
    closing_buyer_delivery_units: int | None
    closing_buyer_return_transit_units: int | None
    reported_control_difference: int | None
    computed_control_difference: int | None
    balance_status: str


@dataclass(frozen=True, slots=True)
class FifoCostTransitionOpeningProposal:
    status: str
    scope: ScopeIdentity
    case_id: str
    case_revision: int
    confirmed_cutoff_date: str | None
    old_home_units: int | None
    old_transit_units: int | None
    new_home_units: int | None
    owner_declared_shipped_total: int | None
    owner_unassigned_shipped_units: int | None
    supply_declarations: tuple[FifoSupplyDeclarationView, ...]
    stock_snapshots: tuple[FifoOpeningStockEvidenceView, ...]
    turnover_controls: tuple[FifoTurnoverControlView, ...]
    turnover_coverage_gap: tuple[str, str] | None
    turnover_candidate_gap: tuple[str, str] | None
    fifo_opening_units: int | None
    is_atomic_snapshot: bool
    preview_only: bool
    ready_to_apply: bool
    requirements: tuple[str, ...]
    issue_codes: tuple[str, ...]


class FifoCostTransitionOpeningProposalService:
    """Assemble the existing evidence into a non-mutating owner-review draft."""

    MAX_REPORTS = 100
    _BLOCKING_ISSUES = frozenset({
        "FIFO_ALREADY_INITIALIZED",
        "OWNER_CUTOFF_DATE_INVALID",
        "STOCK_REPORT_SCOPE_MISMATCH",
        "TURNOVER_REPORT_SCOPE_MISMATCH",
        "SUPPLY_RECONCILIATION_SCOPE_MISMATCH",
        "SUPPLY_RECONCILIATION_CONFLICT",
    })
    _TURNOVER_FIELDS = (
        "opening_total", "receipts_total", "expenses_total", "redeemed_units",
        "non_sale_expense_units", "withdrawal_units", "closing_total",
        "reported_balance_difference", "computed_balance_difference",
    )

    def propose(
        self,
        *,
        case: TransitionCase,
        fifo_initialized: bool,
        owner_confirmed_cutoff_date: str | None,
        confirmed_opening_composition: Mapping | None = None,
        stock_reports: tuple[ReportEvidence, ...],
        turnover_reports: tuple[ReportEvidence, ...],
        supply_reconciliation: FifoCostTransitionSupplyReconciliation | None,
    ) -> FifoCostTransitionOpeningProposal:
        if (
            not isinstance(case, TransitionCase)
            or type(fifo_initialized) is not bool
            or case.state not in {
                TransitionState.DRAFT, TransitionState.AWAITING_EVIDENCE,
                TransitionState.READY_TO_CONFIRM,
            }
        ):
            raise ValueError("FIFO_OPENING_PROPOSAL_INPUT_INVALID")
        stock_reports = self._bounded_reports(stock_reports)
        turnover_reports = self._bounded_reports(turnover_reports)
        cutoff_date = None
        issues: set[str] = set()
        blocked = fifo_initialized
        if owner_confirmed_cutoff_date is not None:
            try:
                cutoff_date = normalize_date_only(owner_confirmed_cutoff_date)
            except (TypeError, ValueError):
                issues.add("OWNER_CUTOFF_DATE_INVALID")
                blocked = True
        else:
            issues.add("OWNER_CUTOFF_DATE_REQUIRED")

        scope = case.metadata.scope
        if fifo_initialized:
            issues.add("FIFO_ALREADY_INITIALIZED")

        opening_composition = self._verified_opening_composition(
            confirmed_opening_composition,
            case=case,
            cutoff_date=cutoff_date,
        )

        supply_owner_total = None
        supply_unassigned = None
        supply_declarations = ()
        if supply_reconciliation is None:
            issues.add("SUPPLY_RECONCILIATION_UNAVAILABLE")
        elif not isinstance(supply_reconciliation, FifoCostTransitionSupplyReconciliation):
            raise ValueError("FIFO_OPENING_PROPOSAL_INPUT_INVALID")
        elif (
            supply_reconciliation.scope != scope
            or supply_reconciliation.case_id != case.case_id
        ):
            issues.add("SUPPLY_RECONCILIATION_SCOPE_MISMATCH")
            blocked = True
        else:
            supply_owner_total = supply_reconciliation.owner_declared_total
            supply_unassigned = supply_reconciliation.owner_undistributed_units
            supply_declarations = supply_reconciliation.declarations
            if supply_reconciliation.status == "CONFLICT":
                issues.add("SUPPLY_RECONCILIATION_CONFLICT")
                blocked = True
            elif supply_reconciliation.status != "COMPLETE":
                issues.add("SUPPLY_RECONCILIATION_PARTIAL")

        stock_views = []
        accepted_stock_fingerprints = set()
        for report in stock_reports:
            if not isinstance(report, ReportEvidence):
                raise ValueError("FIFO_OPENING_PROPOSAL_INPUT_INVALID")
            if report.report_type is not ReportType.STOCK_MANAGEMENT:
                issues.add("STOCK_REPORT_TYPE_INVALID")
                continue
            if report.metadata.scope != scope:
                issues.add("STOCK_REPORT_SCOPE_MISMATCH")
                blocked = True
                continue
            fields = report.normalized_fields
            raw_buckets = fields.get("stock_buckets")
            if not isinstance(raw_buckets, Mapping):
                issues.add("STOCK_REPORT_BUCKETS_UNAVAILABLE")
                continue
            buckets = self._normalized_buckets(raw_buckets)
            eligible = bool(
                cutoff_date is not None
                and report.metadata.completeness is EvidenceCompleteness.COMPLETE
                and report.period_provenance is PeriodProvenance.OWNER_CONFIRMED
                and report.period_from == cutoff_date
                and report.period_to == cutoff_date
            )
            if eligible:
                accepted_stock_fingerprints.add(report.file_sha256)
            if report.metadata.completeness is not EvidenceCompleteness.COMPLETE:
                issues.add("STOCK_REPORT_PARTIAL")
            owner_reserved = None
            owner_ozon_total = None
            composition_fingerprint = None
            if (
                eligible
                and opening_composition is not None
                and opening_composition["stock_report_fingerprint"] == report.file_sha256
            ):
                available = buckets.get("available")
                owner_ozon_total = opening_composition["total_ozon_units"]
                owner_reserved = owner_ozon_total - available if type(available) is int else None
                reported_reserved = buckets.get("reserved")
                if (
                    owner_reserved is not None
                    and owner_reserved >= 0
                    and owner_reserved == opening_composition["reserved_units"]
                    and (reported_reserved is None or reported_reserved == owner_reserved)
                ):
                    buckets["reserved"] = owner_reserved
                    composition_fingerprint = opening_composition["composition_fingerprint"]
                else:
                    owner_reserved = None
                    owner_ozon_total = None
            if buckets.get("reserved") is None:
                issues.add("RESERVED_BUCKET_UNKNOWN")
            if fields.get("fbs_return_is_subset_of_available") is not True:
                issues.add("FBS_RETURN_RELATION_UNCONFIRMED")
            stock_views.append(FifoOpeningStockEvidenceView(
                report_fingerprint=report.file_sha256,
                captured_at=report.captured_at,
                period_from=report.period_from,
                period_to=report.period_to,
                period_provenance=report.period_provenance,
                completeness=report.metadata.completeness,
                stock_buckets=MappingProxyType(dict(sorted(buckets.items()))),
                fbs_return_available_units=self._optional_quantity(
                    fields.get("fbs_return_available_units"),
                ),
                fbs_return_is_subset_of_available=(
                    fields.get("fbs_return_is_subset_of_available")
                    if type(fields.get("fbs_return_is_subset_of_available")) is bool
                    else None
                ),
                warehouse_control_status=(
                    fields.get("warehouse_control", {}).get("status")
                    if isinstance(fields.get("warehouse_control"), Mapping)
                    else None
                ),
                eligible_as_cutoff_snapshot=eligible,
                owner_confirmed_reserved_units=owner_reserved,
                owner_confirmed_total_ozon_units=owner_ozon_total,
                opening_composition_fingerprint=composition_fingerprint,
                opening_composition_report_fingerprint=(
                    report.file_sha256 if composition_fingerprint is not None else None
                ),
                opening_composition_date=(
                    cutoff_date if composition_fingerprint is not None else None
                ),
            ))
        if not stock_views:
            issues.add("STOCK_REPORT_REQUIRED")
        if cutoff_date is not None and not accepted_stock_fingerprints:
            issues.add("OWNER_CONFIRMED_STOCK_SNAPSHOT_FOR_CUTOFF_REQUIRED")

        turnover_views = []
        latest_confirmed_turnover_end = None
        latest_candidate_turnover_end = None
        for report in turnover_reports:
            if not isinstance(report, ReportEvidence):
                raise ValueError("FIFO_OPENING_PROPOSAL_INPUT_INVALID")
            if report.report_type is not ReportType.TURNOVER:
                issues.add("TURNOVER_REPORT_TYPE_INVALID")
                continue
            if report.metadata.scope != scope:
                issues.add("TURNOVER_REPORT_SCOPE_MISMATCH")
                blocked = True
                continue
            fields = report.normalized_fields
            quantities = {
                name: (
                    self._optional_signed_quantity(fields.get(name))
                    if name in {"reported_balance_difference", "computed_balance_difference"}
                    else self._optional_quantity(fields.get(name))
                )
                for name in self._TURNOVER_FIELDS
            }
            reported_difference = quantities["reported_balance_difference"]
            computed_difference = quantities["computed_balance_difference"]
            if (
                fields.get("balance_status") != "BALANCED"
                or reported_difference not in (None, 0)
                or computed_difference not in (None, 0)
                or (
                    reported_difference is not None
                    and computed_difference is not None
                    and reported_difference != computed_difference
                )
            ):
                issues.add("TURNOVER_BALANCE_CONTROL_FAILED")
            if (
                quantities["opening_total"] is not None
                and quantities["receipts_total"] is not None
                and quantities["expenses_total"] is not None
                and quantities["closing_total"] is not None
                and quantities["reported_balance_difference"] is not None
                and quantities["computed_balance_difference"] is not None
            ):
                calculated = (
                    quantities["opening_total"] + quantities["receipts_total"]
                    - quantities["expenses_total"] - quantities["closing_total"]
                )
                if (
                    calculated != quantities["reported_balance_difference"]
                    or calculated != quantities["computed_balance_difference"]
                ):
                    issues.add("TURNOVER_BALANCE_CONTROL_FAILED")
            closing_buckets = fields.get("closing_buckets")
            if not isinstance(closing_buckets, Mapping):
                issues.add("TURNOVER_CLOSING_BUCKETS_UNAVAILABLE")
                closing_buckets = {}
            if report.metadata.completeness is not EvidenceCompleteness.COMPLETE:
                issues.add("TURNOVER_REPORT_PARTIAL")
            if report.period_provenance is not PeriodProvenance.OWNER_CONFIRMED:
                issues.add("TURNOVER_PERIOD_CONFIRMATION_REQUIRED")
            if report.period_to is not None:
                if report.period_provenance is PeriodProvenance.OWNER_CONFIRMED:
                    latest_confirmed_turnover_end = max(
                        latest_confirmed_turnover_end or report.period_to, report.period_to,
                    )
                elif report.period_provenance is PeriodProvenance.FILENAME_CANDIDATE:
                    latest_candidate_turnover_end = max(
                        latest_candidate_turnover_end or report.period_to, report.period_to,
                    )
            turnover_views.append(FifoTurnoverControlView(
                report_fingerprint=report.file_sha256,
                captured_at=report.captured_at,
                period_from=report.period_from,
                period_to=report.period_to,
                period_provenance=report.period_provenance,
                completeness=report.metadata.completeness,
                opening_total=quantities["opening_total"],
                receipts_total=quantities["receipts_total"],
                expenses_total=quantities["expenses_total"],
                redeemed_units=quantities["redeemed_units"],
                non_sale_expense_units=quantities["non_sale_expense_units"],
                withdrawal_units=quantities["withdrawal_units"],
                closing_total=quantities["closing_total"],
                closing_buyer_delivery_units=self._optional_quantity(
                    closing_buckets.get("buyer_delivery"),
                ),
                closing_buyer_return_transit_units=self._optional_quantity(
                    closing_buckets.get("buyer_return_transit"),
                ),
                reported_control_difference=quantities["reported_balance_difference"],
                computed_control_difference=quantities["computed_balance_difference"],
                balance_status=str(fields.get("balance_status", "UNKNOWN")),
            ))

        coverage_gap = None
        candidate_gap = None
        if cutoff_date is not None and latest_confirmed_turnover_end is not None:
            cutoff = date.fromisoformat(cutoff_date)
            report_end = date.fromisoformat(latest_confirmed_turnover_end)
            if report_end < cutoff:
                coverage_gap = ((report_end + timedelta(days=1)).isoformat(), cutoff_date)
                issues.add("TURNOVER_COVERAGE_GAP")
        if cutoff_date is not None and latest_candidate_turnover_end is not None:
            cutoff = date.fromisoformat(cutoff_date)
            candidate_end = date.fromisoformat(latest_candidate_turnover_end)
            if candidate_end < cutoff:
                candidate_gap = ((candidate_end + timedelta(days=1)).isoformat(), cutoff_date)
        elif cutoff_date is not None and not turnover_views:
            issues.add("TURNOVER_REPORT_REQUIRED")

        if turnover_views and any(
            view.closing_buyer_delivery_units not in (None, 0)
            or view.closing_buyer_return_transit_units not in (None, 0)
            for view in turnover_views
        ):
            issues.add("CUSTOMER_DELIVERY_OR_RETURN_NOT_FIFO_OPENING")
        if turnover_views and any(
            view.non_sale_expense_units is not None and view.non_sale_expense_units > 0
            for view in turnover_views
        ):
            issues.add("NON_SALE_MOVEMENT_REQUIRES_SEPARATE_REVIEW")
        if case.owner_old_home_units is None:
            issues.add("OLD_HOME_QUANTITY_UNKNOWN")
        if case.owner_old_transit_units is None:
            issues.add("OLD_TRANSIT_QUANTITY_UNKNOWN")
        if case.new_home_quantity is None:
            issues.add("NEW_HOME_QUANTITY_UNKNOWN")
        if not turnover_views or not stock_views:
            issues.add("OPENING_EVIDENCE_INCOMPLETE")
        issues.add("SALE_CUTOFF_BRIDGE_REQUIRED")
        issues.add("PHYSICAL_FIFO_OPENING_NOT_PROVEN")

        return FifoCostTransitionOpeningProposal(
            status="BLOCKED" if blocked else "REVIEW_ONLY",
            scope=scope,
            case_id=case.case_id,
            case_revision=case.case_revision,
            confirmed_cutoff_date=cutoff_date,
            old_home_units=case.owner_old_home_units,
            old_transit_units=case.owner_old_transit_units,
            new_home_units=case.new_home_quantity,
            owner_declared_shipped_total=supply_owner_total,
            owner_unassigned_shipped_units=supply_unassigned,
            supply_declarations=supply_declarations,
            stock_snapshots=tuple(sorted(
                stock_views, key=lambda view: (view.captured_at, view.report_fingerprint),
            )),
            turnover_controls=tuple(sorted(
                turnover_views, key=lambda view: (view.period_from or "", view.report_fingerprint),
            )),
            turnover_coverage_gap=coverage_gap,
            turnover_candidate_gap=candidate_gap,
            fifo_opening_units=None,
            is_atomic_snapshot=False,
            preview_only=True,
            ready_to_apply=False,
            requirements=tuple(sorted(issues)),
            issue_codes=tuple(sorted(issues & self._BLOCKING_ISSUES)),
        )

    @classmethod
    def _bounded_reports(cls, reports):
        if not isinstance(reports, tuple) or len(reports) > cls.MAX_REPORTS:
            raise ValueError("FIFO_OPENING_PROPOSAL_INPUT_INVALID")
        return reports

    @staticmethod
    def _required_quantity(value):
        if value is None:
            raise ValueError("FIFO_OPENING_PROPOSAL_EVIDENCE_INVALID")
        return normalize_quantity(value)

    @classmethod
    def _optional_quantity(cls, value):
        return None if value is None else cls._required_quantity(value)

    @staticmethod
    def _optional_signed_quantity(value):
        if value is None:
            return None
        if type(value) is not int or not -1_000_000 <= value <= 1_000_000:
            raise ValueError("FIFO_OPENING_PROPOSAL_EVIDENCE_INVALID")
        return value

    @classmethod
    def _normalized_buckets(cls, values):
        normalized = {}
        for key, value in values.items():
            if not isinstance(key, str):
                continue
            normalized[key] = cls._optional_quantity(value)
        return normalized

    @staticmethod
    def _verified_opening_composition(value, *, case, cutoff_date):
        """Accept only a durable, separately confirmed composition from the review path."""
        if not isinstance(value, Mapping) or value.get("confirmed") is not True:
            return None
        if (
            value.get("case_id") != case.case_id
            or value.get("opening_date") != cutoff_date
            or value.get("scope") != {
                "owner_id": case.metadata.scope.owner_id,
                "store_id": case.metadata.scope.store_id,
                "product_id": case.metadata.scope.product_id,
                "offer_id": case.metadata.scope.offer_id,
                "sku": case.metadata.scope.sku,
            }
            or value.get("stock_report_fingerprint") is None
            or not isinstance(value.get("composition_fingerprint"), str)
            or len(value["composition_fingerprint"]) != 64
            or any(char not in "0123456789abcdef" for char in value["composition_fingerprint"].lower())
            or type(value.get("owner_confirmed_total_ozon_units")) is not int
            or value["owner_confirmed_total_ozon_units"] < 0
            or type(value.get("owner_confirmed_reserved_units")) is not int
            or value["owner_confirmed_reserved_units"] < 0
            or not isinstance(value.get("layers"), (list, tuple))
            or not value.get("layers")
            or any(not isinstance(layer, Mapping) for layer in value["layers"])
        ):
            return None
        try:
            total = sum(
                normalize_quantity(layer["ozon_units"])
                for layer in value["layers"]
            )
        except (KeyError, TypeError, ValueError):
            return None
        if (
            total != value["owner_confirmed_total_ozon_units"]
            or not isinstance(value.get("case_id"), str)
            or not isinstance(value.get("stock_report_fingerprint"), str)
        ):
            return None
        return MappingProxyType({
            "case_id": value["case_id"],
            "opening_date": value["opening_date"],
            "stock_report_fingerprint": value["stock_report_fingerprint"],
            "composition_fingerprint": value["composition_fingerprint"].lower(),
            "total_ozon_units": total,
            "reserved_units": value["owner_confirmed_reserved_units"],
        })
