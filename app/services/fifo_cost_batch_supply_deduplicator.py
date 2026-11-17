"""Pure reconciliation of manual supply declarations and API observations.

Manual declarations and API observations remain distinct evidence with their
original provenance. This module only links them by the exact scoped
SUPPLY+SKU or ORDER digest and prevents a parent ORDER control from being
counted again beside its child supplies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from services.fifo_cost_batch_rule_contracts import SupplySkuObservation
from services.fifo_cost_transition_contracts import (
    EvidenceSourceKind,
    ScopeIdentity,
    SupplyDeclaration,
    SupplyReferenceKind,
)


MAX_OBSERVATIONS = 10_000
MAX_DECLARATIONS = 2_000


class SupplyLinkStatus(str, Enum):
    API_ONLY = "API_ONLY"
    OWNER_ONLY = "OWNER_ONLY"
    RECONCILED = "RECONCILED"
    INCOMPLETE = "INCOMPLETE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class OwnerOrderControlStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    UNVERIFIABLE = "UNVERIFIABLE"
    RECONCILED = "RECONCILED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class CanonicalSupplySkuRecord:
    """One supply for one exact SKU, retaining all independent evidence."""

    scope: ScopeIdentity
    record_key: str
    supply_ref_digest: str
    order_ref_digest: str | None
    observations: tuple[SupplySkuObservation, ...]
    current_observation: SupplySkuObservation | None
    effective_accepted_quantity: int | None
    owner_declaration_refs: tuple[tuple[str, int], ...]
    owner_declared_units: int | None
    owner_dispatch_dates: tuple[str, ...]
    status: SupplyLinkStatus
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OwnerOrderControl:
    """A manual ORDER declaration kept separate from its child supplies."""

    order_ref_digest: str
    declaration_refs: tuple[tuple[str, int], ...]
    declared_units: int | None
    child_record_keys: tuple[str, ...]
    api_shipped_units: int | None
    status: OwnerOrderControlStatus
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FifoCostBatchDeduplicationResult:
    status: str
    code: str
    records: tuple[CanonicalSupplySkuRecord, ...] = ()
    order_controls: tuple[OwnerOrderControl, ...] = ()
    issue_codes: tuple[str, ...] = ()


class FifoCostBatchSupplyDeduplicator:
    """Link exact manual/API evidence without adding parent ORDER totals."""

    @classmethod
    def canonical_record_key(cls, scope: ScopeIdentity, supply_ref_digest: str) -> str:
        if not isinstance(scope, ScopeIdentity) or not cls._is_digest(supply_ref_digest):
            raise ValueError("FIFO_BATCH_SUPPLY_IDENTITY_INVALID")
        material = {
            "version": 1,
            "owner_id": scope.owner_id,
            "store_id": scope.store_id,
            "product_id": scope.product_id,
            "offer_id": scope.offer_id,
            "sku": scope.sku,
            "supply_ref_digest": supply_ref_digest,
        }
        return cls._digest(material)

    @classmethod
    def reconcile(
        cls, *, scope: ScopeIdentity, case_id: str,
        observations: tuple[SupplySkuObservation, ...],
        declarations: tuple[SupplyDeclaration, ...],
    ) -> FifoCostBatchDeduplicationResult:
        """Return a deterministic Supply+SKU set and separately linked controls."""
        if not isinstance(scope, ScopeIdentity):
            return cls._error("FIFO_BATCH_SCOPE_INVALID")
        if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 96:
            return cls._error("FIFO_BATCH_CASE_ID_INVALID")
        if not isinstance(observations, tuple) or len(observations) > MAX_OBSERVATIONS:
            return cls._error("FIFO_BATCH_OBSERVATION_LIMIT_REACHED")
        if not isinstance(declarations, tuple) or len(declarations) > MAX_DECLARATIONS:
            return cls._error("FIFO_BATCH_DECLARATION_LIMIT_REACHED")

        api_groups: dict[str, dict] = {}
        for observation in observations:
            if not isinstance(observation, SupplySkuObservation):
                return cls._error("FIFO_BATCH_OBSERVATION_INVALID")
            if observation.scope != scope:
                return cls._error("FIFO_BATCH_SCOPE_MISMATCH")
            if observation.quantity_source_kind is not EvidenceSourceKind.OZON_API:
                return cls._error("FIFO_BATCH_API_OBSERVATION_PROVENANCE_INVALID")
            expected_key = cls.canonical_record_key(scope, observation.supply_ref_digest)
            if observation.record_key != expected_key:
                return cls._error("FIFO_BATCH_SUPPLY_RECORD_KEY_MISMATCH")
            group = api_groups.setdefault(observation.supply_ref_digest, {
                "record_key": expected_key,
                "order_ref_digest": observation.order_ref_digest,
                "versions": {},
                "capture_history": [],
                "conflict": False,
            })
            if group["order_ref_digest"] != observation.order_ref_digest:
                return cls._error("FIFO_BATCH_SUPPLY_ORDER_MAPPING_CONFLICT")
            content = cls._observation_content_fingerprint(observation)
            group["capture_history"].append(observation)
            prior = group["versions"].get(observation.source_fingerprint)
            if prior is not None:
                if prior["content"] != content:
                    group["conflict"] = True
                elif observation.captured_at > prior["observation"].captured_at:
                    group["versions"][observation.source_fingerprint] = {
                        "observation": observation, "content": content,
                    }
            else:
                group["versions"][observation.source_fingerprint] = {
                    "observation": observation, "content": content,
                }

        manual_supply: dict[str, dict] = {}
        manual_order: dict[str, dict] = {}
        latest_declarations, declaration_error = cls._latest_declarations(
            declarations, scope=scope, case_id=case_id,
        )
        if declaration_error is not None:
            return cls._error(declaration_error)
        for declaration in latest_declarations:
            target = (
                manual_supply if declaration.reference_kind is SupplyReferenceKind.SUPPLY
                else manual_order
            )
            group = target.setdefault(declaration.reference_digest, {
                "units": declaration.declared_shipped_units,
                "dates": set(() if declaration.dispatch_date is None else (declaration.dispatch_date,)),
                "refs": [],
                "conflict": False,
            })
            if group["units"] != declaration.declared_shipped_units:
                group["conflict"] = True
            if declaration.dispatch_date is not None:
                group["dates"].add(declaration.dispatch_date)
            if len(group["dates"]) > 1:
                group["conflict"] = True
            group["refs"].append((declaration.declaration_id, declaration.revision))

        supply_refs = sorted(set(api_groups) | set(manual_supply))
        records = []
        for supply_ref in supply_refs:
            api = api_groups.get(supply_ref)
            owner = manual_supply.get(supply_ref)
            observations_for_supply = ()
            current = None
            effective_accepted = None
            issues = []
            order_ref = None
            record_key = cls.canonical_record_key(scope, supply_ref)
            if api is not None:
                order_ref = api["order_ref_digest"]
                observations_for_supply = tuple(sorted(
                    (entry["observation"] for entry in api["versions"].values()),
                    key=lambda item: (item.captured_at, item.source_fingerprint),
                ))
                if api["conflict"]:
                    issues.append("FIFO_BATCH_DUPLICATE_SOURCE_FINGERPRINT_CONFLICT")
                elif observations_for_supply:
                    latest_time = max(item.captured_at for item in observations_for_supply)
                    latest_rows = tuple(
                        item for item in observations_for_supply if item.captured_at == latest_time
                    )
                    if len(latest_rows) == 1:
                        current = latest_rows[0]
                    elif len({cls._observation_content_fingerprint(item) for item in latest_rows}) == 1:
                        current = max(latest_rows, key=lambda item: item.source_fingerprint)
                    else:
                        issues.append("FIFO_BATCH_OBSERVATION_ORDER_AMBIGUOUS")
                if current is None and not issues:
                    issues.append("FIFO_BATCH_OBSERVATION_CURRENT_UNKNOWN")
                if not api["conflict"]:
                    effective_accepted, acceptance_conflict = cls._reconcile_cumulative_acceptance(
                        api["capture_history"],
                    )
                    if acceptance_conflict:
                        issues.append("FIFO_BATCH_ACCEPTANCE_DECREASE_REQUIRES_REVIEW")
            elif owner is not None:
                effective_accepted = None

            if owner is not None and owner["conflict"]:
                issues.append("FIFO_BATCH_OWNER_SUPPLY_DECLARATION_CONFLICT")
            owner_units = None if owner is None else owner["units"]
            if (
                owner is not None and api is not None and current is not None
                and owner_units is not None
                and current.shipped_composition_quantity is not None
                and current.quantity_coverage.value == "COMPLETE"
                and owner_units != current.shipped_composition_quantity
            ):
                issues.append("FIFO_BATCH_OWNER_API_QUANTITY_CONFLICT")
            if (
                owner is not None and current is not None
                and current.dispatch_time_status.value == "CONFIRMED"
                and current.dispatch_local_date is not None
                and owner["dates"]
                and current.dispatch_local_date not in owner["dates"]
            ):
                issues.append("FIFO_BATCH_OWNER_API_DISPATCH_DATE_CONFLICT")

            if issues:
                status = SupplyLinkStatus.REVIEW_REQUIRED
            elif owner is None:
                status = SupplyLinkStatus.API_ONLY
            elif api is None:
                status = SupplyLinkStatus.OWNER_ONLY
            elif (
                owner_units is not None and current is not None
                and current.shipped_composition_quantity is not None
                and current.quantity_coverage.value == "COMPLETE"
            ):
                status = SupplyLinkStatus.RECONCILED
            else:
                status = SupplyLinkStatus.INCOMPLETE
            records.append(CanonicalSupplySkuRecord(
                scope=scope, record_key=record_key, supply_ref_digest=supply_ref,
                order_ref_digest=order_ref, observations=observations_for_supply,
                current_observation=current,
                effective_accepted_quantity=effective_accepted,
                owner_declaration_refs=() if owner is None else tuple(sorted(owner["refs"])),
                owner_declared_units=owner_units,
                owner_dispatch_dates=() if owner is None else tuple(sorted(owner["dates"])),
                status=status, issues=tuple(issues),
            ))

        order_controls = []
        for order_ref, owner in sorted(manual_order.items()):
            children = tuple(sorted(
                [record for record in records if record.order_ref_digest == order_ref],
                key=lambda item: item.record_key,
            ))
            child_keys = tuple(record.record_key for record in children)
            dispatch_conflict = any(
                record.current_observation is not None
                and record.current_observation.dispatch_time_status.value == "CONFIRMED"
                and record.current_observation.dispatch_local_date is not None
                and owner["dates"]
                and record.current_observation.dispatch_local_date not in owner["dates"]
                for record in children
            )
            if owner["conflict"]:
                status = OwnerOrderControlStatus.REVIEW_REQUIRED
                api_units = None
                issues = ("FIFO_BATCH_OWNER_ORDER_DECLARATION_CONFLICT",)
            elif not children:
                status = OwnerOrderControlStatus.UNRESOLVED
                api_units = None
                issues = ("FIFO_BATCH_OWNER_ORDER_UNRESOLVED",)
            elif dispatch_conflict:
                complete_children = all(
                    record.current_observation is not None
                    and record.current_observation.shipped_composition_quantity is not None
                    and record.current_observation.quantity_coverage.value == "COMPLETE"
                    for record in children
                )
                api_units = (
                    sum(record.current_observation.shipped_composition_quantity for record in children)
                    if complete_children else None
                )
                status = OwnerOrderControlStatus.REVIEW_REQUIRED
                issues = ("FIFO_BATCH_OWNER_API_DISPATCH_DATE_CONFLICT",)
            elif any(
                record.status is SupplyLinkStatus.REVIEW_REQUIRED
                or record.current_observation is None
                or record.current_observation.shipped_composition_quantity is None
                or record.current_observation.quantity_coverage.value != "COMPLETE"
                for record in children
            ):
                status = OwnerOrderControlStatus.UNVERIFIABLE
                api_units = None
                issues = ("FIFO_BATCH_OWNER_ORDER_CHILDREN_INCOMPLETE",)
            else:
                api_units = sum(
                    record.current_observation.shipped_composition_quantity
                    for record in children
                )
                if owner["units"] is None:
                    status = OwnerOrderControlStatus.UNVERIFIABLE
                    issues = ("FIFO_BATCH_OWNER_ORDER_QUANTITY_UNKNOWN",)
                elif owner["units"] == api_units:
                    status = OwnerOrderControlStatus.RECONCILED
                    issues = ()
                else:
                    status = OwnerOrderControlStatus.REVIEW_REQUIRED
                    issues = ("FIFO_BATCH_OWNER_ORDER_QUANTITY_CONFLICT",)
            order_controls.append(OwnerOrderControl(
                order_ref_digest=order_ref,
                declaration_refs=tuple(sorted(owner["refs"])),
                declared_units=owner["units"], child_record_keys=child_keys,
                api_shipped_units=api_units, status=status, issues=issues,
            ))

        if not records and not order_controls:
            return FifoCostBatchDeduplicationResult(
                status="UNKNOWN", code="FIFO_BATCH_DEDUP_SOURCE_EMPTY",
            )
        all_issues = tuple(sorted({
            issue for record in records for issue in record.issues
        } | {
            issue for control in order_controls for issue in control.issues
        }))
        has_review = any(
            record.status is SupplyLinkStatus.REVIEW_REQUIRED for record in records
        ) or any(
            control.status is OwnerOrderControlStatus.REVIEW_REQUIRED
            for control in order_controls
        )
        return FifoCostBatchDeduplicationResult(
            status="REVIEW_REQUIRED" if has_review else "NORMALIZED",
            code="FIFO_BATCH_DEDUP_REVIEW_REQUIRED" if has_review else "FIFO_BATCH_DEDUP_COMPLETE",
            records=tuple(records), order_controls=tuple(order_controls),
            issue_codes=all_issues,
        )

    @classmethod
    def _latest_declarations(cls, declarations, *, scope, case_id):
        latest: dict[str, SupplyDeclaration] = {}
        for declaration in declarations:
            if not isinstance(declaration, SupplyDeclaration):
                return (), "FIFO_BATCH_OWNER_DECLARATION_INVALID"
            if (
                declaration.case_id != case_id
                or declaration.metadata.scope != scope
                or declaration.metadata.source_kind is not EvidenceSourceKind.OWNER_INPUT
                or declaration.provenance is not EvidenceSourceKind.OWNER_INPUT
            ):
                return (), "FIFO_BATCH_OWNER_DECLARATION_SCOPE_MISMATCH"
            current = latest.get(declaration.declaration_id)
            if current is None or declaration.revision > current.revision:
                latest[declaration.declaration_id] = declaration
            elif declaration.revision == current.revision and cls._declaration_payload(
                declaration
            ) != cls._declaration_payload(current):
                return (), "FIFO_BATCH_OWNER_DECLARATION_REVISION_CONFLICT"
        return tuple(latest[key] for key in sorted(latest)), None

    @staticmethod
    def _declaration_payload(declaration):
        return (
            declaration.reference_kind.value, declaration.reference_digest,
            declaration.declared_shipped_units, declaration.dispatch_date,
            declaration.provenance.value,
        )

    @classmethod
    def _observation_content_fingerprint(cls, observation):
        return cls._digest({
            "scope": {
                "owner_id": observation.scope.owner_id,
                "store_id": observation.scope.store_id,
                "product_id": observation.scope.product_id,
                "offer_id": observation.scope.offer_id,
                "sku": observation.scope.sku,
            },
            "record_key": observation.record_key,
            "order_ref_digest": observation.order_ref_digest,
            "supply_ref_digest": observation.supply_ref_digest,
            "source_profile_version": observation.source_profile_version,
            "source_as_of": observation.source_as_of,
            "source_status": observation.source_status,
            "normalized_status": observation.normalized_status.value,
            "is_crossdock": observation.is_crossdock,
            "dispatch_local_date": observation.dispatch_local_date,
            "dispatch_local_time": observation.dispatch_local_time,
            "dispatch_time_status": observation.dispatch_time_status.value,
            "planned_declared_quantity": observation.planned_declared_quantity,
            "shipped_composition_quantity": observation.shipped_composition_quantity,
            "accepted_quantity": observation.accepted_quantity,
            "quantity_source_kind": observation.quantity_source_kind.value,
            "quantity_coverage": observation.quantity_coverage.value,
            "acceptance_fingerprint": observation.acceptance_fingerprint,
            "acceptance_version": observation.acceptance_version,
            "explicit_zero_fields": observation.explicit_zero_fields,
            "membership": observation.membership.value,
            "issues": observation.issues,
        })

    @staticmethod
    def _reconcile_cumulative_acceptance(observations):
        """Retain cumulative maximum on duplicate replays; review novel decreases."""
        ordered = sorted(observations, key=lambda item: (item.captured_at, item.source_fingerprint))
        seen_fingerprints = set()
        maximum = None
        conflict = False
        for observation in ordered:
            quantity = observation.accepted_quantity
            if quantity is None:
                seen_fingerprints.add(observation.source_fingerprint)
                continue
            if maximum is None or quantity >= maximum:
                maximum = quantity
            elif observation.source_fingerprint not in seen_fingerprints:
                conflict = True
            seen_fingerprints.add(observation.source_fingerprint)
        return maximum, conflict

    @staticmethod
    def _digest(value):
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _is_digest(value):
        return (
            isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
        )

    @classmethod
    def _error(cls, code):
        return FifoCostBatchDeduplicationResult(
            status="CONFLICT", code=code, issue_codes=(code,),
        )
