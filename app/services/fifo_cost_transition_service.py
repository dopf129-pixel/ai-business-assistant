"""Application lifecycle for owner-reported FIFO transition cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    CostComponents,
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
    utc_now,
)
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


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

    def __init__(self, repository: FifoCostRepository | None = None, *, now_provider=None):
        self.repository = repository or FifoCostRepository()
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

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
