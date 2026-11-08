"""Read-only reconciliation of FIFO transition supply and stock evidence.

This module keeps owner declarations, API observations, acceptance results, and
stock-report snapshots separate.  It never infers a physical receipt or an
atomic inventory snapshot from sources captured at different times.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping

from services.fifo_cost_supply_acceptance_reconciliation_service import (
    FifoSupplyAcceptanceReconciliation,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    StockBucket,
    SupplyDeclaration,
    SupplyObservation,
    SupplyReferenceKind,
    TransitionMetadata,
    normalize_quantity,
    normalize_utc_timestamp,
)


@dataclass(frozen=True, slots=True)
class FifoSupplyAcceptanceSnapshot:
    """Acceptance reconciliation tied to its declaration and source times."""

    metadata: TransitionMetadata
    declaration_id: str
    declaration_reference_digest: str
    captured_at: str
    source_as_of: str | None
    reconciliation: FifoSupplyAcceptanceReconciliation

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, TransitionMetadata):
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        if self.metadata.source_kind is not EvidenceSourceKind.OZON_API:
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        if (
            not isinstance(self.declaration_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", self.declaration_id)
        ):
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        if (
            not isinstance(self.declaration_reference_digest, str)
            or len(self.declaration_reference_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.declaration_reference_digest)
        ):
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        object.__setattr__(self, "captured_at", normalize_utc_timestamp(self.captured_at))
        if self.source_as_of is not None:
            object.__setattr__(self, "source_as_of", normalize_utc_timestamp(self.source_as_of))
        if not isinstance(self.reconciliation, FifoSupplyAcceptanceReconciliation):
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        result = self.reconciliation
        allowed_statuses = {
            "COMPLETE", "PARTIALLY_ACCEPTED", "DISCREPANCY",
            "CORRECTION_REVIEW_REQUIRED", "PARTIAL", "CONFLICT",
            "INVALID", "UNAVAILABLE",
        }
        if result.status not in allowed_statuses:
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        for name in (
            "declared_quantity", "accepted_quantity", "candidate_quantity",
            "unaccepted_quantity",
        ):
            value = getattr(result, name)
            if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000):
                raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")


@dataclass(frozen=True, slots=True)
class FifoSupplyDeclarationView:
    declaration_id: str
    revision: int
    reference_kind: SupplyReferenceKind
    declared_quantity: int | None
    dispatch_date: str | None
    observed_status: NormalizedSupplyStatus | None
    observed_at: str | None
    observed_source_as_of: str | None
    observed_source_fingerprint: str | None
    observed_presence: EvidencePresence | None
    observation_freshness: str
    observed_declared_quantity: int | None
    declaration_quantity_difference: int | None
    accepted_quantity: int | None
    accepted_at: str | None
    accepted_source_as_of: str | None
    accepted_source_fingerprint: str | None
    acceptance_declared_quantity: int | None
    acceptance_declared_quantity_difference: int | None
    acceptance_status: str
    acceptance_is_current: bool
    pending_quantity: int | None
    discrepancy_quantity: int | None


@dataclass(frozen=True, slots=True)
class FifoStockReportSnapshotView:
    report_fingerprint: str
    captured_at: str
    source_as_of: str | None
    period_from: str | None
    period_to: str | None
    period_provenance: str
    completeness: EvidenceCompleteness
    quantities: Mapping[str, int | None]


@dataclass(frozen=True, slots=True)
class FifoCostTransitionSupplyReconciliation:
    status: str
    scope: ScopeIdentity
    owner_declared_total: int | None
    known_declared_total: int
    owner_undistributed_units: int | None
    declarations_with_unknown_quantity: int
    declarations: tuple[FifoSupplyDeclarationView, ...]
    stock_report_snapshots: tuple[FifoStockReportSnapshotView, ...]
    source_as_of_coherence: str
    is_atomic_snapshot: bool
    issue_codes: tuple[str, ...]


class FifoCostTransitionSupplyReconciliationService:
    """Build a deterministic, non-mutating view of late-entry evidence."""

    MAX_DECLARATIONS = 500
    MAX_OBSERVATIONS = 5_000
    MAX_ACCEPTANCE_SNAPSHOTS = 1_000
    MAX_STOCK_REPORTS = 100

    def reconcile(
        self,
        *,
        scope: ScopeIdentity,
        case_id: str,
        owner_declared_total: int | None,
        declarations: tuple[SupplyDeclaration, ...],
        observations: tuple[SupplyObservation, ...] = (),
        acceptance_snapshots: tuple[FifoSupplyAcceptanceSnapshot, ...] = (),
        stock_reports: tuple[ReportEvidence, ...] = (),
    ) -> FifoCostTransitionSupplyReconciliation:
        if not isinstance(scope, ScopeIdentity) or not isinstance(case_id, str):
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        if len(case_id) < 8 or len(case_id) > 96:
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        if owner_declared_total is not None:
            owner_declared_total = normalize_quantity(owner_declared_total)
        declarations = self._bounded_tuple(declarations, self.MAX_DECLARATIONS)
        observations = self._bounded_tuple(observations, self.MAX_OBSERVATIONS)
        acceptance_snapshots = self._bounded_tuple(
            acceptance_snapshots, self.MAX_ACCEPTANCE_SNAPSHOTS,
        )
        stock_reports = self._bounded_tuple(stock_reports, self.MAX_STOCK_REPORTS)

        current_declarations, issues = self._current_declarations(
            declarations, scope=scope, case_id=case_id,
        )
        if not current_declarations and declarations:
            issues.add("SUPPLY_DECLARATION_CONFLICT")
        known_total = sum(
            declaration.declared_shipped_units
            for declaration in current_declarations.values()
            if declaration.declared_shipped_units is not None
        )
        unknown_declaration_count = sum(
            declaration.declared_shipped_units is None
            for declaration in current_declarations.values()
        )
        if known_total > 1_000_000:
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        undistributed = None
        if owner_declared_total is not None and not unknown_declaration_count:
            if known_total > owner_declared_total:
                issues.add("DECLARATIONS_EXCEED_OWNER_TOTAL")
            else:
                undistributed = owner_declared_total - known_total
        elif owner_declared_total is not None:
            # Do not call the arithmetic difference an undistributed remainder
            # while one or more declared quantities are themselves unknown.
            issues.add("DECLARATION_QUANTITY_UNKNOWN")
        elif current_declarations:
            issues.add("OWNER_TOTAL_UNKNOWN")

        observations_by_id = self._observations_by_declaration(
            observations, scope=scope, declaration_ids=set(current_declarations), issues=issues,
        )
        acceptances_by_id = self._acceptances_by_declaration(
            acceptance_snapshots, scope=scope, declarations=current_declarations,
            issues=issues,
        )
        views = tuple(
            self._declaration_view(
                declaration,
                observations_by_id.get(declaration_id, ()),
                acceptances_by_id.get(declaration_id, ()),
            )
            for declaration_id, declaration in sorted(current_declarations.items())
        )
        if any(view.declaration_quantity_difference not in (None, 0) for view in views):
            issues.add("OWNER_API_DECLARATION_MISMATCH")
        if any(
            view.acceptance_declared_quantity_difference not in (None, 0)
            for view in views
        ):
            issues.add("OWNER_ACCEPTANCE_DECLARATION_MISMATCH")
        if any(view.observed_status is NormalizedSupplyStatus.UNKNOWN for view in views):
            issues.add("SUPPLY_STATUS_UNKNOWN")
        if any(view.acceptance_status in {"CONFLICT", "INVALID"} for view in views):
            issues.add("ACCEPTANCE_RECONCILIATION_CONFLICT")
        report_views = self._stock_report_views(stock_reports, scope=scope, issues=issues)

        if owner_declared_total is None:
            issues.add("OWNER_DECLARED_TOTAL_UNKNOWN")
        coherence = self._as_of_coherence(views, report_views)
        if coherence != "SAME":
            issues.add("SOURCE_AS_OF_NOT_ATOMIC")
        if any(
            view.observation_freshness != "CURRENT"
            for view in views if view.observed_presence is not None
        ):
            issues.add("SUPPLY_OBSERVATION_NOT_CURRENT")
        if any(not view.acceptance_is_current and view.acceptance_status != "UNAVAILABLE" for view in views):
            issues.add("ACCEPTANCE_EVIDENCE_NOT_CURRENT")
        if any(report.completeness is not EvidenceCompleteness.COMPLETE for report in report_views):
            issues.add("STOCK_REPORT_PARTIAL")

        status = "CONFLICT" if any(
            code in issues for code in (
                "SUPPLY_DECLARATION_CONFLICT", "DECLARATIONS_EXCEED_OWNER_TOTAL",
                "SUPPLY_OBSERVATION_CONFLICT", "ACCEPTANCE_BINDING_CONFLICT",
                "STOCK_REPORT_SCOPE_CONFLICT", "ACCEPTANCE_RECONCILIATION_CONFLICT",
            )
        ) else ("COMPLETE" if not issues else "PARTIAL")
        return FifoCostTransitionSupplyReconciliation(
            status=status,
            scope=scope,
            owner_declared_total=owner_declared_total,
            known_declared_total=known_total,
            owner_undistributed_units=undistributed,
            declarations_with_unknown_quantity=unknown_declaration_count,
            declarations=views,
            stock_report_snapshots=report_views,
            source_as_of_coherence=coherence,
            is_atomic_snapshot=False,
            issue_codes=tuple(sorted(issues)),
        )

    @classmethod
    def _bounded_tuple(cls, value, maximum):
        if not isinstance(value, tuple) or len(value) > maximum:
            raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
        return value

    @staticmethod
    def _current_declarations(declarations, *, scope, case_id):
        by_id = {}
        issues = set()
        for item in declarations:
            if not isinstance(item, SupplyDeclaration):
                raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
            if item.metadata.scope != scope or item.case_id != case_id:
                issues.add("SUPPLY_DECLARATION_CONFLICT")
                continue
            previous = by_id.get(item.declaration_id)
            if previous is None or item.revision > previous.revision:
                by_id[item.declaration_id] = item
            elif item.revision == previous.revision and item != previous:
                issues.add("SUPPLY_DECLARATION_CONFLICT")
        return by_id, issues

    @staticmethod
    def _observations_by_declaration(observations, *, scope, declaration_ids, issues):
        grouped = {}
        for item in observations:
            if not isinstance(item, SupplyObservation):
                raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
            if item.metadata.scope != scope or item.declaration_id not in declaration_ids:
                issues.add("SUPPLY_OBSERVATION_CONFLICT")
                continue
            grouped.setdefault(item.declaration_id, []).append(item)
        for declaration_id, rows in grouped.items():
            by_capture = {}
            for item in rows:
                previous = by_capture.get(item.captured_at)
                if previous is not None and previous != item:
                    issues.add("SUPPLY_OBSERVATION_CONFLICT")
                by_capture[item.captured_at] = item
            grouped[declaration_id] = sorted(
                by_capture.values(), key=lambda item: item.captured_at,
            )
        return grouped

    @staticmethod
    def _acceptances_by_declaration(snapshots, *, scope, declarations, issues):
        grouped = {}
        for item in snapshots:
            if not isinstance(item, FifoSupplyAcceptanceSnapshot):
                raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
            declaration = declarations.get(item.declaration_id)
            result = item.reconciliation
            if (
                item.metadata.scope != scope
                or declaration is None
                or item.declaration_reference_digest != declaration.reference_digest
                or result.store_id != scope.store_id
            ):
                issues.add("ACCEPTANCE_BINDING_CONFLICT")
                continue
            grouped.setdefault(item.declaration_id, []).append(item)
        for declaration_id, rows in grouped.items():
            by_capture = {}
            for item in rows:
                previous = by_capture.get(item.captured_at)
                if previous is not None and previous != item:
                    issues.add("ACCEPTANCE_BINDING_CONFLICT")
                by_capture[item.captured_at] = item
            grouped[declaration_id] = sorted(
                by_capture.values(), key=lambda item: item.captured_at,
            )
        return grouped

    @staticmethod
    def _declaration_view(declaration, observations, acceptances):
        latest_observation = observations[-1] if observations else None
        previous_present = next(
            (
                item for item in reversed(observations)
                if item.presence is EvidencePresence.PRESENT
            ),
            None,
        )
        chosen_observation = (
            previous_present if latest_observation is not None
            and latest_observation.presence is EvidencePresence.MISSING
            else latest_observation
        )
        if (
            latest_observation is not None
            and latest_observation.presence is EvidencePresence.MISSING
            and previous_present is None
        ):
            chosen_observation = None
        freshness = "UNAVAILABLE"
        if latest_observation is not None:
            if latest_observation.presence is EvidencePresence.MISSING:
                freshness = "MISSING_LATEST"
            elif chosen_observation is not None:
                freshness = (
                    "CURRENT" if (
                        chosen_observation.scope_complete
                        and chosen_observation.pagination_complete
                        and chosen_observation.metadata.completeness is EvidenceCompleteness.COMPLETE
                    ) else "PARTIAL"
                )

        latest_acceptance = acceptances[-1] if acceptances else None
        result = latest_acceptance.reconciliation if latest_acceptance else None
        acceptance_status = result.status if result else "UNAVAILABLE"
        is_current = bool(
            latest_acceptance is not None
            and latest_acceptance.metadata.completeness is EvidenceCompleteness.COMPLETE
            and result.status in {"COMPLETE", "PARTIALLY_ACCEPTED", "DISCREPANCY"}
            and result.accepted_quantity is not None
        )
        accepted = result.accepted_quantity if result else None
        pending = discrepancy = None
        if is_current and result is not None:
            if result.status == "DISCREPANCY":
                discrepancy = result.unaccepted_quantity
            elif result.status == "PARTIALLY_ACCEPTED":
                pending = result.unaccepted_quantity
        elif result is not None and result.status == "CORRECTION_REVIEW_REQUIRED":
            accepted = None

        return FifoSupplyDeclarationView(
            declaration_id=declaration.declaration_id,
            revision=declaration.revision,
            reference_kind=declaration.reference_kind,
            declared_quantity=declaration.declared_shipped_units,
            dispatch_date=declaration.dispatch_date,
            observed_status=chosen_observation.normalized_status if chosen_observation else None,
            observed_at=chosen_observation.captured_at if chosen_observation else None,
            observed_source_as_of=chosen_observation.source_as_of if chosen_observation else None,
            observed_source_fingerprint=(
                chosen_observation.metadata.source_fingerprint if chosen_observation else None
            ),
            observed_presence=latest_observation.presence if latest_observation else None,
            observation_freshness=freshness,
            observed_declared_quantity=(
                chosen_observation.declared_quantity if chosen_observation else None
            ),
            declaration_quantity_difference=(
                chosen_observation.declared_quantity - declaration.declared_shipped_units
                if chosen_observation is not None
                and chosen_observation.declared_quantity is not None
                and declaration.declared_shipped_units is not None
                else None
            ),
            accepted_quantity=accepted,
            accepted_at=latest_acceptance.captured_at if latest_acceptance else None,
            accepted_source_as_of=latest_acceptance.source_as_of if latest_acceptance else None,
            accepted_source_fingerprint=(
                latest_acceptance.metadata.source_fingerprint if latest_acceptance else None
            ),
            acceptance_declared_quantity=(
                result.declared_quantity if result is not None else None
            ),
            acceptance_declared_quantity_difference=(
                result.declared_quantity - declaration.declared_shipped_units
                if result is not None
                and result.declared_quantity is not None
                and declaration.declared_shipped_units is not None
                else None
            ),
            acceptance_status=acceptance_status,
            acceptance_is_current=is_current,
            pending_quantity=pending,
            discrepancy_quantity=discrepancy,
        )

    @staticmethod
    def _stock_report_views(reports, *, scope, issues):
        views = []
        for report in reports:
            if not isinstance(report, ReportEvidence):
                raise ValueError("SUPPLY_RECONCILIATION_INPUT_INVALID")
            if report.report_type is not ReportType.STOCK_MANAGEMENT or report.metadata.scope != scope:
                issues.add("STOCK_REPORT_SCOPE_CONFLICT")
                continue
            raw_buckets = report.normalized_fields.get("stock_buckets")
            if not isinstance(raw_buckets, Mapping):
                issues.add("STOCK_REPORT_BUCKETS_UNAVAILABLE")
                continue
            quantities = {}
            valid_buckets = {bucket.value for bucket in StockBucket}
            for key, value in raw_buckets.items():
                if key not in valid_buckets:
                    continue
                quantities[key] = None if value is None else normalize_quantity(value)
            views.append(FifoStockReportSnapshotView(
                report_fingerprint=report.file_sha256,
                captured_at=report.captured_at,
                source_as_of=None,
                period_from=report.period_from,
                period_to=report.period_to,
                period_provenance=report.period_provenance.value,
                completeness=report.metadata.completeness,
                quantities=MappingProxyType(dict(sorted(quantities.items()))),
            ))
        return tuple(sorted(views, key=lambda item: (item.captured_at, item.report_fingerprint)))

    @staticmethod
    def _as_of_coherence(declarations, reports):
        values = []
        for item in declarations:
            if item.observed_at is not None:
                values.append(item.observed_source_as_of)
            if item.accepted_at is not None:
                values.append(item.accepted_source_as_of)
        values.extend(item.source_as_of for item in reports)
        if not values or all(value is None for value in values):
            return "UNKNOWN"
        normalized = set(values)
        if None in normalized or len(normalized) != 1:
            return "DIFFERENT"
        return "SAME"
