"""Build a review-only first-activation proposal for a late FIFO transition."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from services.fifo_cost_cutoff_bridge_service import FifoCutoffBridgeResult
from services.fifo_cost_transition_contracts import (
    CostComponents,
    CostInputMode,
    ScopeIdentity,
    TransitionCase,
    TransitionState,
    source_fingerprint,
)
from services.fifo_cost_transition_opening_proposal_service import (
    FifoCostTransitionOpeningProposal,
)


@dataclass(frozen=True, slots=True)
class FifoCostTransitionActivationProposal:
    """A scoped candidate rate and source-separated opening evidence.

    This proposal deliberately has no scalar FIFO opening quantity.  FL20
    replay and FL23's atomic commit are required before any inventory change.
    """

    status: str
    scope: ScopeIdentity
    case_id: str
    case_revision: int
    cutoff_date: str | None
    complete_through: str | None
    old_unit_cost_rub: Decimal | None
    new_unit_cost_rub: Decimal | None
    cost_input_mode: CostInputMode
    cost_components: CostComponents | None
    old_home_units: int | None
    old_transit_units: int | None
    new_home_units: int | None
    owner_declared_shipped_units: int | None
    supply_declaration_count: int
    confirmed_stock_buckets: Mapping[str, int | None]
    accepted_supply_units_added_to_snapshot: int
    fifo_opening_units: int | None
    source_set_fingerprint: str
    requirements: tuple[str, ...]
    preview_only: bool = True
    fifo_initialized: bool = False
    ready_to_apply: bool = False

    def __post_init__(self):
        object.__setattr__(
            self, "confirmed_stock_buckets",
            MappingProxyType(dict(self.confirmed_stock_buckets)),
        )
        object.__setattr__(self, "requirements", tuple(sorted(set(self.requirements))))
        if (
            self.status not in {"REVIEW_ONLY", "SOURCE_BLOCKED"}
            or self.accepted_supply_units_added_to_snapshot != 0
            or self.fifo_opening_units is not None
            or not self.preview_only
            or self.ready_to_apply
        ):
            raise ValueError("FIFO_ACTIVATION_PROPOSAL_INVALID")


class FifoCostTransitionActivationProposalService:
    """Combine a verified cutoff bridge with the editable case, without writes."""

    _BRIDGE_SATISFIED = frozenset({"SALE_CUTOFF_BRIDGE_REQUIRED"})
    _REPLAY_PENDING = "FIFO_OPENING_QUANTITY_REQUIRES_REPLAY"

    def propose(
        self,
        *,
        case: TransitionCase,
        fifo_initialized: bool,
        opening_proposal: FifoCostTransitionOpeningProposal,
        cutoff_bridge: FifoCutoffBridgeResult,
    ) -> FifoCostTransitionActivationProposal:
        if (
            not isinstance(case, TransitionCase)
            or type(fifo_initialized) is not bool
            or case.state not in {
                TransitionState.DRAFT, TransitionState.AWAITING_EVIDENCE,
            }
            or not isinstance(opening_proposal, FifoCostTransitionOpeningProposal)
            or not isinstance(cutoff_bridge, FifoCutoffBridgeResult)
        ):
            raise ValueError("FIFO_ACTIVATION_PROPOSAL_INPUT_INVALID")

        issues: set[str] = set()
        scope = case.metadata.scope
        if fifo_initialized:
            issues.add("FIFO_ALREADY_INITIALIZED")
        if case.new_unit_cost_rub is None:
            issues.add("NEW_UNIT_COST_REQUIRED")
        if (
            opening_proposal.scope != scope
            or opening_proposal.case_id != case.case_id
            or opening_proposal.case_revision != case.case_revision
        ):
            issues.add("OPENING_PROPOSAL_CASE_SCOPE_MISMATCH")
        if (
            cutoff_bridge.scope != scope
            or cutoff_bridge.case_id != case.case_id
            or cutoff_bridge.case_revision != case.case_revision
            or not cutoff_bridge.preview_only
        ):
            issues.add("CUTOFF_BRIDGE_CASE_SCOPE_MISMATCH")
        if (
            not cutoff_bridge.ready_for_fifo_event
            or cutoff_bridge.status != "READY"
            or cutoff_bridge.complete_through is None
            or cutoff_bridge.unresolved_issues
        ):
            issues.add("CUTOFF_BRIDGE_NOT_READY")
        if (
            opening_proposal.confirmed_cutoff_date != cutoff_bridge.cutoff_date
            or cutoff_bridge.cutoff_date is None
        ):
            issues.add("OPENING_CUTOFF_MISMATCH")
        bound_stock_fingerprints = set(
            cutoff_bridge.provenance_by_basis.get("stock_scope", ()),
        )
        if not any(
            snapshot.eligible_as_cutoff_snapshot
            and snapshot.report_fingerprint in bound_stock_fingerprints
            for snapshot in opening_proposal.stock_snapshots
        ):
            issues.add("CUTOFF_STOCK_NOT_BOUND_TO_OPENING_PROPOSAL")
        if opening_proposal.is_atomic_snapshot:
            issues.add("OPENING_PROPOSAL_MUST_REMAIN_NON_ATOMIC")
        if (
            not opening_proposal.preview_only
            or opening_proposal.ready_to_apply
            or opening_proposal.fifo_opening_units is not None
        ):
            issues.add("OPENING_PROPOSAL_NOT_PREVIEW_ONLY")

        requirements = set(opening_proposal.requirements)
        requirements.difference_update(self._BRIDGE_SATISFIED)
        if "PHYSICAL_FIFO_OPENING_NOT_PROVEN" in requirements:
            requirements.remove("PHYSICAL_FIFO_OPENING_NOT_PROVEN")
            requirements.add(self._REPLAY_PENDING)
        if opening_proposal.new_home_units is None:
            requirements.add("NEW_HOME_QUANTITY_UNKNOWN")
        if case.new_unit_cost_rub is None:
            requirements.add("NEW_UNIT_COST_REQUIRED")
        requirements.update(issues)

        # Unknown home quantity is allowed for recording the rate.  Opening
        # quantity stays unknown, and every other missing proof remains visible.
        # Existing opening-proposal requirements remain visible.  This stage
        # only offers a review candidate; the proposal's status/issues and the
        # bridge's independent proof determine whether that candidate can be
        # assembled.  It never means physical opening or apply readiness.
        if opening_proposal.status != "REVIEW_ONLY" or opening_proposal.issue_codes:
            issues.add("OPENING_PROPOSAL_SOURCE_BLOCKED")
            requirements.add("OPENING_PROPOSAL_SOURCE_BLOCKED")
        status = "REVIEW_ONLY" if not issues else "SOURCE_BLOCKED"
        evidence_is_bound = bool(
            opening_proposal.scope == scope
            and opening_proposal.case_id == case.case_id
            and opening_proposal.case_revision == case.case_revision
            and cutoff_bridge.scope == scope
            and cutoff_bridge.case_id == case.case_id
            and cutoff_bridge.case_revision == case.case_revision
            and opening_proposal.confirmed_cutoff_date == cutoff_bridge.cutoff_date
            and cutoff_bridge.ready_for_fifo_event
            and any(
                snapshot.eligible_as_cutoff_snapshot
                and snapshot.report_fingerprint in bound_stock_fingerprints
                for snapshot in opening_proposal.stock_snapshots
            )
        )
        stock_buckets = (
            cutoff_bridge.confirmed_stock_buckets
            if evidence_is_bound
            else {}
        )
        fingerprint = source_fingerprint({
            "case_id": case.case_id,
            "case_revision": case.case_revision,
            "scope": {
                "owner_id": scope.owner_id,
                "store_id": scope.store_id,
                "sku": scope.sku,
                "product_id": scope.product_id,
                "offer_id": scope.offer_id,
            },
            "cutoff_bridge": cutoff_bridge.source_set_fingerprint,
            "cutoff": cutoff_bridge.cutoff_date,
            "complete_through": cutoff_bridge.complete_through,
            "new_unit_cost_rub": (
                str(case.new_unit_cost_rub) if case.new_unit_cost_rub is not None else None
            ),
            "old_unit_cost_rub": (
                str(case.old_unit_cost_rub) if case.old_unit_cost_rub is not None else None
            ),
            "cost_input_mode": case.cost_input_mode.value,
            "stock_buckets": dict(stock_buckets),
            "owner_quantities": {
                "old_home": case.owner_old_home_units,
                "old_transit": case.owner_old_transit_units,
                "new_home": opening_proposal.new_home_units,
                "declared_shipped": case.declared_shipped_units,
            },
        })
        return FifoCostTransitionActivationProposal(
            status=status,
            scope=scope,
            case_id=case.case_id,
            case_revision=case.case_revision,
            cutoff_date=(cutoff_bridge.cutoff_date if evidence_is_bound else None),
            complete_through=(
                cutoff_bridge.complete_through
                if evidence_is_bound else None
            ),
            old_unit_cost_rub=case.old_unit_cost_rub,
            new_unit_cost_rub=case.new_unit_cost_rub,
            cost_input_mode=case.cost_input_mode,
            cost_components=case.cost_components,
            old_home_units=case.owner_old_home_units,
            old_transit_units=case.owner_old_transit_units,
            new_home_units=opening_proposal.new_home_units,
            owner_declared_shipped_units=case.declared_shipped_units,
            supply_declaration_count=len(opening_proposal.supply_declarations),
            confirmed_stock_buckets=stock_buckets,
            # Supply observations are reconciliation evidence, never an
            # additive quantity over the authoritative cutoff snapshot.
            accepted_supply_units_added_to_snapshot=0,
            fifo_opening_units=None,
            source_set_fingerprint=fingerprint,
            requirements=tuple(requirements),
            fifo_initialized=fifo_initialized,
        )
