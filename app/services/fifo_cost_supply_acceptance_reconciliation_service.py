"""Pure reconciliation of cumulative accepted quantities for one FIFO supply.

The service interprets already-normalized, redacted act snapshots. It does not
call Ozon, persist evidence, create inventory movements, or change FIFO state.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.fifo_cost_source_normalizer import (
    FifoSupplyActEvidence,
    FifoSupplyActSnapshot,
)


@dataclass(frozen=True, slots=True)
class FifoSupplyAcceptanceReconciliation:
    status: str
    declared_quantity: int | None
    accepted_quantity: int | None
    candidate_quantity: int | None
    unaccepted_quantity: int | None
    act_count: int
    act_reference_digests: tuple[str, ...]
    store_id: str | None
    supply_reference: str | None
    source_fingerprint: str | None
    issue_codes: tuple[str, ...]
    required_action: str


class FifoCostSupplyAcceptanceReconciliationService:
    """Resolve duplicate/cumulative act snapshots without inventing movements."""

    MAX_UNITS = 1_000_000
    MAX_SNAPSHOTS = 100

    def reconcile(
        self, *, snapshots, target_sku, declared_quantity,
        final_state_confirmed=False,
    ) -> FifoSupplyAcceptanceReconciliation:
        if (
            not isinstance(snapshots, (list, tuple))
            or len(snapshots) > self.MAX_SNAPSHOTS
            or not isinstance(target_sku, str)
            or not target_sku.isascii()
            or not target_sku.isdigit()
            or type(final_state_confirmed) is not bool
            or (
                declared_quantity is not None
                and (
                    type(declared_quantity) is not int
                    or not 0 <= declared_quantity <= self.MAX_UNITS
                )
            )
        ):
            return self._result(
                "INVALID", declared_quantity, None, None, None, (), None,
                None, None, ("SUPPLY_RECONCILIATION_INPUT_INVALID",),
                "CORRECT_INPUT",
            )
        if not snapshots or any(
            not isinstance(snapshot, FifoSupplyActSnapshot) for snapshot in snapshots
        ):
            return self._result(
                "UNAVAILABLE", declared_quantity, None, None, None, (), None,
                None, None, ("SUPPLY_ACT_EVIDENCE_UNAVAILABLE",),
                "REFRESH_SOURCE",
            )

        stores = {snapshot.store_id for snapshot in snapshots}
        supplies = {snapshot.supply_ref for snapshot in snapshots}
        if len(stores) != 1 or None in stores or len(supplies) != 1 or None in supplies:
            return self._result(
                "CONFLICT", declared_quantity, None, None, None, (), None,
                None, None, ("SUPPLY_IDENTITY_CONFLICT",), "REVIEW_IDENTITY",
            )

        ordered = sorted(snapshots, key=lambda item: (item.captured_at or "", item.source_fingerprint or ""))
        by_capture: dict[str, str] = {}
        unique: list[FifoSupplyActSnapshot] = []
        seen_evidence: set[str] = set()
        for snapshot in ordered:
            if not snapshot.captured_at or not snapshot.source_fingerprint:
                return self._result(
                    "CONFLICT", declared_quantity, None, None, None, (),
                    next(iter(stores)), next(iter(supplies)), None,
                    ("SUPPLY_SOURCE_PROVENANCE_INVALID",), "REFRESH_SOURCE",
                )
            previous_fingerprint = by_capture.get(snapshot.captured_at)
            if previous_fingerprint and previous_fingerprint != snapshot.source_fingerprint:
                return self._result(
                    "CONFLICT", declared_quantity, None, None, None, (),
                    next(iter(stores)), next(iter(supplies)), None,
                    ("SUPPLY_OBSERVATION_ORDER_AMBIGUOUS",), "REVIEW_SOURCE_ORDER",
                )
            by_capture[snapshot.captured_at] = snapshot.source_fingerprint
            evidence_fingerprint = snapshot.evidence_fingerprint
            if evidence_fingerprint and evidence_fingerprint in seen_evidence:
                continue
            if evidence_fingerprint:
                seen_evidence.add(evidence_fingerprint)
            unique.append(snapshot)

        latest: FifoSupplyActSnapshot | None = None
        latest_incomplete: FifoSupplyActSnapshot | None = None
        previous_accepted: int | None = None
        for snapshot in unique:
            if snapshot.status in {"PARTIAL", "UNAVAILABLE", "EMPTY"}:
                latest_incomplete = snapshot
                continue
            if snapshot.status in {"INVALID", "CONFLICT"}:
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    (), next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    tuple(snapshot.issue_codes) or ("SUPPLY_SOURCE_CONFLICT",),
                    "REVIEW_SOURCE",
                )
            if snapshot.status not in {"COMPLETE", "CONFIRMED_ZERO"}:
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    (), next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("SUPPLY_SNAPSHOT_STATUS_UNSUPPORTED",), "REVIEW_SOURCE",
                )
            rows = snapshot.units_by_sku
            if not isinstance(rows, tuple) or len(rows) != 1:
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    (), next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS",), "REVIEW_SKU_SPLIT",
                )
            sku, quantity = rows[0]
            if (
                sku != target_sku
                or type(quantity) is not int
                or not 0 <= quantity <= self.MAX_UNITS
            ):
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    (), next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("SUPPLY_PRODUCT_IDENTITY_CONFLICT",), "REVIEW_SKU_SPLIT",
                )
            if (
                not isinstance(snapshot.act_refs, tuple)
                or any(
                    not isinstance(reference, str)
                    or len(reference) != 64
                    or any(character not in "0123456789abcdef" for character in reference)
                    for reference in snapshot.act_refs
                )
                or not isinstance(snapshot.act_evidence, tuple)
                or any(
                    not isinstance(item, FifoSupplyActEvidence)
                    for item in snapshot.act_evidence
                )
            ):
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    (), next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("SUPPLY_ACT_IDENTITY_INVALID",), "REFRESH_ACT_DETAILS",
                )
            act_refs = tuple(sorted(set(snapshot.act_refs)))
            if not act_refs or len(snapshot.act_evidence) != len(act_refs):
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    (), next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("SUPPLY_ACT_IDENTITY_INCOMPLETE",), "REFRESH_ACT_DETAILS",
                )
            evidence_refs = {item.act_ref for item in snapshot.act_evidence}
            if evidence_refs != set(act_refs) or sum(
                item.fact_quantity for item in snapshot.act_evidence
            ) != quantity:
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    act_refs, next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("SUPPLY_ACT_QUANTITY_MISMATCH",), "REFRESH_ACT_DETAILS",
                )
            if quantity > self.MAX_UNITS:
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, None, None,
                    act_refs, next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("SUPPLY_QUANTITY_LIMIT",), "REVIEW_SOURCE",
                )
            if previous_accepted is not None and quantity < previous_accepted:
                return self._result(
                    "CORRECTION_REVIEW_REQUIRED", declared_quantity,
                    previous_accepted, quantity, None, act_refs,
                    next(iter(stores)), next(iter(supplies)), snapshot.source_fingerprint,
                    ("ACCEPTED_QUANTITY_DECREASE_REQUIRES_REVIEW",),
                    "CONFIRM_DOCUMENTED_CORRECTION",
                )
            if declared_quantity is not None and quantity > declared_quantity:
                return self._result(
                    "CONFLICT", declared_quantity, previous_accepted, quantity,
                    None, act_refs, next(iter(stores)), next(iter(supplies)),
                    snapshot.source_fingerprint,
                    ("ACCEPTED_EXCEEDS_DECLARED",), "REVIEW_QUANTITIES",
                )
            previous_accepted = quantity
            latest = snapshot

        if latest_incomplete is not None and (
            latest is None or latest_incomplete.captured_at > latest.captured_at
        ):
            return self._result(
                "PARTIAL", declared_quantity, previous_accepted, None, None,
                tuple(sorted(set(latest.act_refs))) if latest is not None else (),
                next(iter(stores)), next(iter(supplies)),
                latest_incomplete.source_fingerprint,
                tuple(latest_incomplete.issue_codes) or ("SUPPLY_SOURCE_INCOMPLETE",),
                "REFRESH_SOURCE",
            )
        if latest is None or previous_accepted is None:
            return self._result(
                "PARTIAL", declared_quantity, None, None, None, (),
                next(iter(stores)), next(iter(supplies)), None,
                ("SUPPLY_ACCEPTED_QUANTITY_UNCONFIRMED",), "WAIT_FOR_COMPLETE_ACTS",
            )
        refs = tuple(sorted(set(latest.act_refs)))
        short = (
            declared_quantity - previous_accepted
            if declared_quantity is not None and previous_accepted < declared_quantity
            else None
        )
        if final_state_confirmed and short is not None:
            return self._result(
                "DISCREPANCY", declared_quantity, previous_accepted,
                previous_accepted, short, refs, next(iter(stores)),
                next(iter(supplies)), latest.source_fingerprint,
                ("FINAL_ACCEPTED_BELOW_DECLARED",), "CONFIRM_SHORTAGE_MOVEMENT",
            )
        return self._result(
            "COMPLETE" if short is None else "PARTIALLY_ACCEPTED",
            declared_quantity, previous_accepted, previous_accepted, short,
            refs, next(iter(stores)), next(iter(supplies)),
            latest.source_fingerprint, (),
            "NONE" if short is None else "WAIT_FOR_FINAL_ACCEPTANCE",
        )

    @staticmethod
    def _result(
        status, declared_quantity, accepted_quantity, candidate_quantity,
        unaccepted_quantity, act_refs, store_id, supply_ref, source_fingerprint,
        issue_codes, required_action,
    ):
        return FifoSupplyAcceptanceReconciliation(
            status=status,
            declared_quantity=declared_quantity,
            accepted_quantity=accepted_quantity,
            candidate_quantity=candidate_quantity,
            unaccepted_quantity=unaccepted_quantity,
            act_count=len(act_refs),
            act_reference_digests=tuple(act_refs),
            store_id=store_id,
            supply_reference=supply_ref,
            source_fingerprint=source_fingerprint,
            issue_codes=tuple(issue_codes),
            required_action=required_action,
        )
