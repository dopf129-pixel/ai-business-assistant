"""Bridge exact owner-confirmed saleable returns into immutable FIFO history.

This service only restores FIFO availability. The existing Return COGS
calculation and every monetary authorization gate remain separate and unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_return_evidence_normalizer import (
    FifoCostReturnEvidenceNormalizer,
)


class FifoCostReturnRestockService:
    def __init__(self, repository=None, *, now_provider=None):
        self.repository = repository or FifoCostRepository()
        self._now = now_provider or (lambda: datetime.now(timezone.utc))

    def preview_return(
        self, *, store_id, product_id=None, offer_id=None, sku, finance_sku,
        identity, return_record, recovery_evidence, return_sample_complete,
        cutoff_bridge_confirmed,
    ):
        """Prepare a one-time return command without writing FIFO history."""
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

        history = self.repository.read_cost_history_snapshot(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if history.get("error") is True:
            return history
        allocation = history.get("latest_allocation")
        if (
            not isinstance(allocation, dict)
            or allocation.get("status") != "COMPLETE"
            or allocation.get("cutoff_status") != "RECONCILED"
            or allocation.get("stale") is not False
            or allocation.get("stream_revision") != guard.get("stream_revision")
        ):
            return self._blocked("FIFO_RETURN_ORIGIN_ALLOCATION_UNAVAILABLE")

        candidate = FifoCostReturnEvidenceNormalizer.normalize(
            store_id=store_id,
            finance_sku=finance_sku,
            identity=identity,
            return_record=return_record,
            recovery_evidence=recovery_evidence,
            return_sample_complete=return_sample_complete,
            inventory_cutoff=guard.get("anchor_cutoff_date"),
            cutoff_bridge_confirmed=cutoff_bridge_confirmed,
        )
        if candidate.get("eligible") is not True:
            return candidate
        origin = self.repository.read_physical_sale_event_reference(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            source_identity_digest=candidate["origin_sale_identity_digest"],
        )
        if origin.get("error") is True:
            return self._blocked(origin.get("code"))
        if (
            origin.get("inventory_cutoff") != candidate["inventory_cutoff"]
            or origin.get("effective_date") is None
            or candidate["effective_date"] <= origin["effective_date"]
        ):
            return self._blocked("FIFO_RETURN_EFFECTIVE_DATE_UNAVAILABLE")
        if candidate["quantity"] > origin["quantity"]:
            return self._blocked("FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN")

        event = FifoCostReturnEvidenceNormalizer.build_event(
            candidate, origin_sale_event_id=origin["event_id"],
        )
        source = FifoCostReturnEvidenceNormalizer.build_command_source(
            candidate, captured_at=self._now().astimezone(timezone.utc).isoformat(),
        )
        if event.get("eligible") is False or source.get("eligible") is False:
            return event if event.get("eligible") is False else source
        preview = self.repository.preview_command(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            events=[event], source=source,
            expected_revision=guard["stream_revision"],
        )
        if preview.get("error") is True:
            return preview
        return {
            "error": False,
            "code": "FIFO_RETURN_RESTOCK_PREVIEW_READY",
            "preview_id": preview["preview_id"],
            "expected_revision": preview["expected_revision"],
            "quantity": candidate["quantity"],
            "effective_date": candidate["effective_date"],
            "expires_in_seconds": preview["expires_in_seconds"],
            "read_only": True,
        }

    def commit_return(self, *, preview_id, active_preview_id, idempotency_key,
                      store_id, product_id=None, offer_id=None, sku):
        """Append an eligible restock and publish a fresh complete replay."""
        command = self.repository.commit_command(
            preview_id=preview_id,
            active_preview_id=active_preview_id,
            idempotency_key=idempotency_key,
        )
        if command.get("error") is True:
            return command
        history = self.repository.read_cost_history_snapshot(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        allocation = history.get("latest_allocation") if history.get("error") is False else None
        if not (
            isinstance(allocation, dict)
            and allocation.get("status") == "COMPLETE"
            and allocation.get("cutoff_status") == "RECONCILED"
            and allocation.get("stale") is False
            and allocation.get("stream_revision") == command.get("revision")
        ):
            preview = self.repository.preview_current_allocation(
                store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            )
            if preview.get("error") is True:
                return {
                    "error": False,
                    "code": "FIFO_RETURN_COMMITTED_ALLOCATION_STALE",
                    "allocation_reason": preview.get("code"),
                    "command_revision": command.get("revision"),
                    "read_only": False,
                }
            allocation_result = self.repository.append_allocation_revision(
                store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
                preview=preview,
                idempotency_key="return-replay-" + command["command_id"][4:],
            )
            if allocation_result.get("error") is True:
                return {
                    "error": False,
                    "code": "FIFO_RETURN_COMMITTED_ALLOCATION_STALE",
                    "allocation_reason": allocation_result.get("code"),
                    "command_revision": command.get("revision"),
                    "read_only": False,
                }
            allocation = {
                "revision": allocation_result.get("allocation_revision"),
                "stream_revision": allocation_result.get("stream_revision"),
                "status": "COMPLETE",
                "cutoff_status": "RECONCILED",
                "stale": False,
            }
        return {
            "error": False,
            "code": "FIFO_RETURN_RESTOCK_COMMITTED",
            "command_revision": command.get("revision"),
            "allocation_revision": allocation.get("revision"),
            "allocation_stream_revision": allocation.get("stream_revision"),
            "idempotent": command.get("idempotent") is True,
            "read_only": False,
        }

    @staticmethod
    def _blocked(code):
        return {
            "error": False,
            "code": "FIFO_RETURN_RESTOCK_BLOCKED",
            "reason_code": code or "FIFO_RETURN_EVIDENCE_INVALID",
            "eligible": False,
            "read_only": True,
        }
