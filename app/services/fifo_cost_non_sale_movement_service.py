"""Preview and record owner-confirmed non-sale outflows without changing sale COGS."""

from datetime import datetime, timezone

from services.fifo_cost_movement_evidence_normalizer import (
    FifoCostMovementEvidenceNormalizer,
)
from services.fifo_cost_repository import FifoCostRepository


class FifoCostNonSaleMovementService:
    def __init__(self, repository=None, *, now_provider=None):
        self.repository = repository or FifoCostRepository()
        self._now = now_provider or (lambda: datetime.now(timezone.utc))

    def preview_movement(
        self, *, store_id, product_id=None, offer_id=None, sku,
        movement_id, reason_code, quantity, effective_date,
        cutoff_bridge_confirmed,
    ):
        guard = self.repository.read_allocation_guard(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if guard.get("error") is True:
            return guard
        if guard.get("cutoff_status") != "RECONCILED":
            return self._blocked("INVENTORY_CUTOFF_UNRECONCILED")
        if guard.get("eligible_for_publication") is not True:
            return self._blocked(
                guard.get("replay_reason_code") or "FIFO_ALLOCATION_REPLAY_UNAVAILABLE",
            )
        candidate = FifoCostMovementEvidenceNormalizer.normalize(
            store_id=store_id, sku=sku, movement_id=movement_id,
            reason_code=reason_code, quantity=quantity,
            effective_date=effective_date,
            inventory_cutoff=guard.get("anchor_cutoff_date"),
            cutoff_bridge_confirmed=cutoff_bridge_confirmed,
        )
        if candidate.get("eligible") is not True:
            return candidate
        event = FifoCostMovementEvidenceNormalizer.build_event(candidate)
        captured_at = self._now()
        if (
            not isinstance(captured_at, datetime)
            or captured_at.tzinfo is None
            or captured_at.utcoffset() is None
        ):
            return self._blocked("FIFO_MOVEMENT_CAPTURE_TIME_INVALID")
        source = FifoCostMovementEvidenceNormalizer.build_source(
            candidate, captured_at=captured_at.astimezone(timezone.utc).isoformat(),
        )
        if (
            event.get("kind") != "NON_SALE_OUTFLOW"
            or source.get("method") != "OWNER_CONFIRMED_FIFO_NON_SALE_MOVEMENT"
        ):
            return self._blocked("FIFO_MOVEMENT_EVIDENCE_INVALID")
        impact = self.repository.preview_current_allocation(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            hypothetical_outflow={
                "quantity": candidate["quantity"],
                "reason_code": candidate["reason_code"],
                "effective_date": candidate["effective_date"],
                "inventory_cutoff": candidate["inventory_cutoff"],
                "source_identity_digest": candidate["source_identity_digest"],
            },
        )
        if impact.get("error") is True:
            return self._blocked(impact.get("code"))
        outflow = next((row for row in impact.get("outflows", [])
                        if row.get("event_id") == "evt_" + candidate["source_identity_digest"][:32]), None)
        if not isinstance(outflow, dict):
            return self._blocked("FIFO_MOVEMENT_IMPACT_UNAVAILABLE")
        ticket = self.repository.preview_command(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            events=[event], source=source,
            expected_revision=guard["stream_revision"],
        )
        if ticket.get("error") is True:
            return ticket
        return {
            "error": False, "code": "FIFO_NON_SALE_MOVEMENT_PREVIEW_READY",
            "preview_id": ticket["preview_id"],
            "expected_revision": ticket["expected_revision"],
            "quantity": candidate["quantity"],
            "reason_code": candidate["reason_code"],
            "effective_date": candidate["effective_date"],
            "estimated_fifo_value_rub": outflow["estimated_value_rub"],
            "valuation_method": "FIFO_FINITE_LAYER_ESTIMATE",
            "included_in_sales_cogs": False,
            "read_only": True,
        }

    def commit_movement(self, *, preview_id, active_preview_id, idempotency_key,
                        store_id, product_id=None, offer_id=None, sku):
        command = self.repository.commit_command(
            preview_id=preview_id, active_preview_id=active_preview_id,
            idempotency_key=idempotency_key,
        )
        if command.get("error") is True:
            return command
        preview = self.repository.preview_current_allocation(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if preview.get("error") is True:
            return {
                "error": False, "code": "FIFO_MOVEMENT_COMMITTED_ALLOCATION_STALE",
                "reason_code": preview.get("code"),
                "command_revision": command.get("revision"), "read_only": False,
            }
        allocation = self.repository.append_allocation_revision(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            preview=preview,
            idempotency_key="movement-replay-" + command["command_id"][4:],
        )
        if allocation.get("error") is True:
            return {
                "error": False, "code": "FIFO_MOVEMENT_COMMITTED_ALLOCATION_STALE",
                "reason_code": allocation.get("code"),
                "command_revision": command.get("revision"), "read_only": False,
            }
        return {
            "error": False, "code": "FIFO_NON_SALE_MOVEMENT_COMMITTED",
            "command_revision": command.get("revision"),
            "allocation_revision": allocation.get("allocation_revision"),
            "estimated_outflow_value_rub": preview["non_sale_outflow_value_rub"],
            "included_in_sales_cogs": False,
            "read_only": False,
        }

    @staticmethod
    def _blocked(reason):
        return {
            "error": False, "code": "FIFO_NON_SALE_MOVEMENT_BLOCKED",
            "reason_code": reason or "FIFO_MOVEMENT_EVIDENCE_INVALID",
            "eligible": False, "read_only": True,
        }
