"""Application lifecycle for owner-reported FIFO transition cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import re

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_cutoff_bridge_service import FifoCostCutoffBridgeService
from services.fifo_cost_source_normalizer import (
    FifoActiveSupplySnapshot,
)
from services.fifo_cost_transition_contracts import (
    CostComponents,
    CostInputMode,
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    SupplyDeclaration,
    SupplyObservation,
    SupplyReferenceKind,
    UnknownValue,
    supply_reference_digest,
    utc_now,
)
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.tenant_cipher_provider import encrypt_tenant_value


class FifoCostTransitionService:
    """Create, revise, cancel, and list durable transition drafts.

    This layer only coordinates typed owner facts and the existing FIFO
    repository. It never chooses a cutoff, creates inventory, or changes
    current cost/profit.
    """

    _EDITABLE_STATES = frozenset({
        TransitionState.DRAFT,
        TransitionState.AWAITING_EVIDENCE,
    })

    def __init__(
        self, repository: FifoCostRepository | None = None, *,
        now_provider=None, cutoff_bridge_service=None,
    ):
        self.repository = repository or FifoCostRepository()
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.cutoff_bridge_service = cutoff_bridge_service or FifoCostCutoffBridgeService()

    def build_cutoff_bridge(self, **evidence) -> dict:
        """Build a read-only bridge through the production transition service."""
        try:
            result = self.cutoff_bridge_service.build(**evidence)
        except (TypeError, ValueError) as exc:
            code = str(exc) or "FIFO_CUTOFF_BRIDGE_INPUT_INVALID"
            return self._error(code)
        return {"error": False, "result": result}

    def create_case(self, *, case: TransitionCase, idempotency_key: str) -> dict:
        if not isinstance(case, TransitionCase):
            return self._error("FIFO_TRANSITION_CASE_INVALID")
        if case.case_revision != 1 or case.state is not TransitionState.DRAFT:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        return self.repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key=idempotency_key,
        )

    def update_case(
        self, *, case: TransitionCase, expected_revision: int,
        idempotency_key: str,
    ) -> dict:
        if not isinstance(case, TransitionCase):
            return self._error("FIFO_TRANSITION_CASE_INVALID")
        if type(expected_revision) is not int or expected_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if (
            case.case_revision != expected_revision + 1
            or case.state not in self._EDITABLE_STATES
        ):
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        scope = case.metadata.scope
        current = self.repository.read_transition_case(
            case_id=case.case_id,
            store_id=scope.store_id,
            product_id=scope.product_id,
            offer_id=scope.offer_id,
            sku=scope.sku,
        )
        if current.get("error"):
            return current
        if current["case_revision"] == expected_revision + 1:
            # Let repository idempotency resolve a retry of the exact committed
            # payload before treating the now-advanced revision as stale.
            return self.repository.save_transition_case(
                case=case, expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        if current["case_revision"] != expected_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        if current["state"] not in {state.value for state in self._EDITABLE_STATES}:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        return self.repository.save_transition_case(
            case=case, expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def cancel_case(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        expected_revision, idempotency_key,
    ) -> dict:
        if type(expected_revision) is not int or expected_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        current_payload = self.repository.read_transition_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current_payload.get("error"):
            return current_payload
        if (
            current_payload["state"] == TransitionState.CANCELLED.value
            and current_payload["case_revision"] == expected_revision + 1
        ):
            try:
                already_cancelled = self._case_from_payload(current_payload["case"])
            except (TypeError, ValueError, KeyError):
                return self._error("FIFO_TRANSITION_CASE_CORRUPT")
            return self.repository.cancel_transition_case(
                case=already_cancelled, expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        if current_payload["case_revision"] != expected_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        if current_payload["state"] not in {state.value for state in self._EDITABLE_STATES}:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        try:
            case = self._case_from_payload(current_payload["case"])
            updated_at = max(utc_now(self._now_provider), case.updated_at)
            cancelled = replace(
                case,
                case_revision=expected_revision + 1,
                state=TransitionState.CANCELLED,
                updated_at=updated_at,
            )
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
        return self.repository.cancel_transition_case(
            case=cancelled, expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def get_case(self, *, case_id, store_id, product_id=None, offer_id=None, sku):
        return self.repository.read_transition_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )

    def list_cases(
        self, *, store_id, sku=None,
        states=("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM"), limit=100,
    ):
        return self.repository.list_transition_cases(
            store_id=store_id, sku=sku, states=states, limit=limit,
        )

    def declare_supply(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        reference_kind, reference_id, declared_shipped_units,
        dispatch_date=None, expected_case_revision, idempotency_key,
    ) -> dict:
        """Append an owner-declared typed ORDER/SUPPLY link to the exact case.

        The raw lookup reference exists only in this call frame: persistence
        receives a scoped digest and, when the configured tenant cipher is
        available, a Fernet token. A missing cipher does not discard the
        declaration; it explicitly disables future refresh-by-ID.
        """
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        try:
            case = self._case_from_payload(current["case"])
            if case.state not in self._EDITABLE_STATES:
                return self._error("FIFO_TRANSITION_CASE_NOT_READY")
            kind = (
                reference_kind if isinstance(reference_kind, SupplyReferenceKind)
                else SupplyReferenceKind(str(reference_kind).strip().upper())
            )
            normalized_reference = self._normalize_reference_id(reference_id)
            reference_digest = supply_reference_digest(
                owner_id=case.metadata.scope.owner_id,
                store_id=case.metadata.scope.store_id,
                reference_kind=kind,
                reference_id=normalized_reference,
            )
            if reference_digest is None:
                return self._error("FIFO_TRANSITION_REFERENCE_INVALID")
            encrypted_lookup = encrypt_tenant_value(normalized_reference)
            unknown_values = {}
            if declared_shipped_units is None:
                unknown_values["declared_shipped_units"] = UnknownValue(
                    TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                    EvidenceSourceKind.OWNER_INPUT,
                )
            if encrypted_lookup is None:
                unknown_values["lookup_reference"] = UnknownValue(
                    TransitionReasonCode.LOOKUP_REFERENCE_UNAVAILABLE,
                    EvidenceSourceKind.OWNER_INPUT,
                )
            source_fingerprint = hashlib.sha256(
                ("fifo-transition-declaration:v1:" + ":".join((
                    reference_digest,
                    "UNKNOWN" if declared_shipped_units is None
                    else str(declared_shipped_units),
                    str(dispatch_date or ""),
                ))).encode("utf-8")
            ).hexdigest()
            metadata = TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
                completeness=(
                    EvidenceCompleteness.PARTIAL if unknown_values
                    else EvidenceCompleteness.COMPLETE
                ),
                source_fingerprint=source_fingerprint,
                store_timezone=case.metadata.store_timezone,
            )
            declaration_id = "decl_" + hashlib.sha256(
                f"fifo-transition-declaration-id:v1:{case.case_id}:{idempotency_key}".encode()
            ).hexdigest()[:32]
            declaration = SupplyDeclaration(
                metadata=metadata,
                case_id=case.case_id,
                declaration_id=declaration_id,
                revision=1,
                reference_kind=kind,
                reference_digest=reference_digest,
                encrypted_lookup_reference=encrypted_lookup,
                declared_shipped_units=declared_shipped_units,
                dispatch_date=dispatch_date,
                provenance=EvidenceSourceKind.OWNER_INPUT,
                unknown_values=unknown_values,
            )
        except (TypeError, ValueError, KeyError) as exc:
            reason = getattr(exc, "reason_code", None)
            if reason is not None:
                return self._error(reason.value)
            if isinstance(exc, ValueError) and str(exc) == "FIFO_TRANSITION_REFERENCE_INVALID":
                return self._error(str(exc))
            return self._error("FIFO_TRANSITION_DECLARATION_INVALID")
        return self.repository.append_supply_declaration(
            declaration=declaration,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def get_supply_manifest(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
    ) -> dict:
        """Return safe supply quantities and owner-total remainder, never IDs."""
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        evidence = self.repository.read_transition_evidence(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, kind="SUPPLY_DECLARATION", limit=100,
        )
        if evidence.get("error"):
            return evidence
        latest = {}
        for item in evidence["items"]:
            key = item["declaration_id"]
            if key not in latest or item["evidence_revision"] > latest[key]["evidence_revision"]:
                latest[key] = item
        declarations = sorted(
            latest.values(), key=lambda item: (item.get("recorded_at") or "", item["declaration_id"]),
        )
        known_units = sum(
            item["declared_shipped_units"]
            for item in declarations
            if item["declared_shipped_units"] is not None
        )
        quantities_complete = all(
            item["declared_shipped_units"] is not None for item in declarations
        )
        owner_total = current["case"].get("declared_shipped_units")
        if owner_total is not None and known_units > owner_total:
            return self._error("FIFO_TRANSITION_SUPPLY_TOTAL_CONFLICT")
        undistributed = (
            owner_total - known_units
            if owner_total is not None and quantities_complete else None
        )
        return {
            "error": False,
            "code": "FIFO_TRANSITION_SUPPLY_MANIFEST_FOUND",
            "case_id": current["case_id"],
            "case_revision": current["case_revision"],
            "owner_declared_total": owner_total,
            "known_assigned_units": known_units,
            "assignment_complete": quantities_complete,
            "undistributed_units": undistributed,
            "undistributed_status": "KNOWN" if undistributed is not None else "UNKNOWN",
            "declarations": [
                {
                    "declaration_id": item["declaration_id"],
                    "reference_kind": item["reference_kind"],
                    "declared_shipped_units": item["declared_shipped_units"],
                    "dispatch_date": item["dispatch_date"],
                    "lookup_status": (
                        "AVAILABLE" if item.get("lookup_reference_available")
                        else "LOOKUP_REFERENCE_UNAVAILABLE"
                    ),
                }
                for item in declarations
            ],
        }

    def supply_declaration_matches_reference(
        self, *, case_id, declaration_id, owner_id, store_id,
        product_id=None, offer_id=None, sku, reference_id,
    ) -> bool:
        """Validate a supplied ID against one scoped encrypted declaration.

        The scoped digest is compared internally and never returned in a
        manifest or diagnostic result.
        """
        evidence = self.repository.read_transition_evidence(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, kind="SUPPLY_DECLARATION", limit=100,
        )
        if evidence.get("error"):
            return False
        latest = {}
        for item in evidence["items"]:
            key = item["declaration_id"]
            if key not in latest or item["evidence_revision"] > latest[key]["evidence_revision"]:
                latest[key] = item
        persisted = latest.get(declaration_id)
        expected_digest = self.reference_digest_for_supply(
            owner_id=owner_id, store_id=store_id, reference_id=reference_id,
        )
        return bool(
            persisted is not None
            and persisted.get("reference_kind") == "SUPPLY"
            and persisted.get("lookup_reference_available")
            and expected_digest is not None
            and persisted.get("reference_digest") == expected_digest
        )

    def record_supply_observation(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        declaration_id, reference_id, snapshot, expected_case_revision,
        idempotency_key,
    ) -> dict:
        """Append a redacted status observation for its exact supply declaration.

        ``reference_id`` is used only in memory to bind the API result back to
        the encrypted owner declaration; neither the ID nor its plaintext
        digest is returned from this method.
        """
        if not isinstance(snapshot, FifoActiveSupplySnapshot):
            return self._error("FIFO_TRANSITION_OBSERVATION_INVALID")
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if (
            snapshot.status not in {"PRESENT", "MISSING"}
            or snapshot.presence != snapshot.status
            or snapshot.source_status not in {"COMPLETE", "PARTIAL"}
            or snapshot.store_id != store_id
            or snapshot.source_fingerprint is None
            or (snapshot.presence == "PRESENT" and snapshot.order_ref is None)
            or (
                snapshot.presence == "MISSING"
                and (snapshot.raw_status is not None or snapshot.normalized_status != "UNKNOWN")
            )
            or type(snapshot.scope_complete) is not bool
            or type(snapshot.pagination_complete) is not bool
        ):
            return self._error("FIFO_TRANSITION_OBSERVATION_INVALID")
        if snapshot.presence == "MISSING" and not (
            snapshot.source_status == "COMPLETE"
            and snapshot.scope_complete
            and snapshot.pagination_complete
        ):
            return self._error("FIFO_TRANSITION_OBSERVATION_NOT_COMPLETE")
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        if current["case_revision"] != expected_case_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        try:
            case = self._case_from_payload(current["case"])
            if case.state not in self._EDITABLE_STATES:
                return self._error("FIFO_TRANSITION_CASE_NOT_READY")
            normalized_reference = self._normalize_reference_id(reference_id)
            expected_supply_digest = supply_reference_digest(
                owner_id=case.metadata.scope.owner_id,
                store_id=case.metadata.scope.store_id,
                reference_kind=SupplyReferenceKind.SUPPLY,
                reference_id=normalized_reference,
            )
            if expected_supply_digest is None:
                return self._error("FIFO_TRANSITION_REFERENCE_INVALID")
            if snapshot.supply_reference_digest != expected_supply_digest:
                return self._error("FIFO_TRANSITION_SUPPLY_REFERENCE_MISMATCH")
            declarations = self.repository.read_transition_evidence(
                case_id=case_id, store_id=store_id, product_id=product_id,
                offer_id=offer_id, sku=sku,
                kind="SUPPLY_DECLARATION", limit=100,
            )
            if declarations.get("error"):
                return declarations
            matching = [
                item for item in declarations["items"]
                if item.get("declaration_id") == declaration_id
            ]
            if not matching or any(
                item.get("reference_kind") != SupplyReferenceKind.SUPPLY.value
                or item.get("reference_digest") != expected_supply_digest
                for item in matching
            ):
                return self._error("FIFO_TRANSITION_SUPPLY_REFERENCE_MISMATCH")
            if any(item.get("lookup_reference_available") is not True for item in matching):
                return self._error("FIFO_TRANSITION_LOOKUP_REFERENCE_UNAVAILABLE")

            normalized_status = NormalizedSupplyStatus(snapshot.normalized_status)
            presence = EvidencePresence(snapshot.presence)
            completeness = (
                EvidenceCompleteness.COMPLETE
                if snapshot.source_status == "COMPLETE"
                else EvidenceCompleteness.PARTIAL
            )
            metadata = TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OZON_API,
                completeness=completeness,
                source_fingerprint=snapshot.source_fingerprint,
                store_timezone=case.metadata.store_timezone,
            )
            unknown_reason = (
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING
                if presence is EvidencePresence.MISSING
                else TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE
            )
            unknown_values = {
                "declared_quantity": UnknownValue(
                    unknown_reason, EvidenceSourceKind.OZON_API,
                ),
                "accepted_quantity": UnknownValue(
                    unknown_reason, EvidenceSourceKind.OZON_API,
                ),
            }
            observation = SupplyObservation(
                metadata=metadata,
                declaration_id=declaration_id,
                captured_at=snapshot.captured_at,
                source_as_of=None,
                raw_status=snapshot.raw_status,
                normalized_status=normalized_status,
                declared_quantity=None,
                accepted_quantity=None,
                accepted_quantity_kind=None,
                act_reference_digest=None,
                act_version_digest=None,
                scope_complete=snapshot.scope_complete,
                pagination_complete=snapshot.pagination_complete,
                presence=presence,
                unknown_values=unknown_values,
            )
        except (TypeError, ValueError, KeyError) as exc:
            reason = getattr(exc, "reason_code", None)
            if reason is not None:
                return self._error(reason.value)
            return self._error("FIFO_TRANSITION_OBSERVATION_INVALID")
        return self.repository.append_supply_observation(
            case_id=case_id, observation=observation,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _normalize_reference_id(value) -> str:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("FIFO_TRANSITION_REFERENCE_INVALID")
        raw = str(value).strip()
        if not re.fullmatch(r"[0-9]{1,40}", raw):
            raise ValueError("FIFO_TRANSITION_REFERENCE_INVALID")
        return str(int(raw))

    @classmethod
    def reference_digest_for_supply(cls, *, owner_id, store_id, reference_id):
        try:
            normalized_reference = cls._normalize_reference_id(reference_id)
        except (TypeError, ValueError):
            return None
        return supply_reference_digest(
            owner_id=owner_id,
            store_id=store_id,
            reference_kind=SupplyReferenceKind.SUPPLY,
            reference_id=normalized_reference,
        )

    @staticmethod
    def _case_from_payload(payload: dict) -> TransitionCase:
        metadata_payload = payload["metadata"]
        scope_payload = metadata_payload["scope"]
        owner_id, scoped_store = split_store_tenant_scope(
            str(get_current_tenant_user_id() or "").strip(),
        )
        if scoped_store != scope_payload["store_id"]:
            raise ValueError("FIFO_TRANSITION_SCOPE_MISMATCH")
        metadata = TransitionMetadata(
            scope=ScopeIdentity(
                owner_id=owner_id,
                store_id=scope_payload["store_id"],
                product_id=scope_payload.get("product_id"),
                offer_id=scope_payload.get("offer_id"),
                sku=scope_payload["sku"],
            ),
            source_kind=EvidenceSourceKind(metadata_payload["source_kind"]),
            completeness=EvidenceCompleteness(metadata_payload["completeness"]),
            source_fingerprint=metadata_payload["source_fingerprint"],
            schema_version=metadata_payload["schema_version"],
            store_timezone=metadata_payload["store_timezone"],
        )
        component_payload = payload.get("cost_components")
        components = (
            CostComponents(
                purchase_cost_rub=Decimal(component_payload["purchase_cost_rub"]),
                delivery_cost_rub=Decimal(component_payload["delivery_cost_rub"]),
                packaging_cost_rub=Decimal(component_payload["packaging_cost_rub"]),
            )
            if isinstance(component_payload, dict) else None
        )
        unknown_values = {
            name: UnknownValue(
                reason_code=TransitionReasonCode(value["reason_code"]),
                source_kind=EvidenceSourceKind(value["source_kind"]),
            )
            for name, value in payload.get("unknown_values", {}).items()
        }
        return TransitionCase(
            metadata=metadata,
            case_id=payload["case_id"],
            case_revision=payload["case_revision"],
            state=TransitionState(payload["state"]),
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            dispatch_date=payload.get("dispatch_date"),
            old_unit_cost_rub=(
                None if payload.get("old_unit_cost_rub") is None
                else Decimal(payload["old_unit_cost_rub"])
            ),
            new_unit_cost_rub=(
                None if payload.get("new_unit_cost_rub") is None
                else Decimal(payload["new_unit_cost_rub"])
            ),
            cost_input_mode=CostInputMode(payload["cost_input_mode"]),
            cost_components=components,
            owner_old_home_units=payload.get("owner_old_home_units"),
            owner_old_transit_units=payload.get("owner_old_transit_units"),
            new_home_quantity=payload.get("new_home_quantity"),
            declared_shipped_units=payload.get("declared_shipped_units"),
            opening_evidence_ref=payload.get("opening_evidence_ref"),
            source_watermark=payload.get("source_watermark"),
            reason_codes=tuple(
                TransitionReasonCode(value)
                for value in payload.get("reason_codes", ())
            ),
            supersedes_case_id=payload.get("supersedes_case_id"),
            unknown_values=unknown_values,
        )

    @staticmethod
    def _error(code: str) -> dict:
        return {"error": True, "code": code}
