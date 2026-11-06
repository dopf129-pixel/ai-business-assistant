"""Persist owner-selected, read-only supply evidence without inventory writes."""

from __future__ import annotations

from services.fifo_cost_repository import FifoCostRepository


class FifoCostSupplyEvidenceService:
    """Link one confirmed supply/act snapshot to an exact FIFO SKU stream.

    This service records source evidence only. It never creates a cost layer,
    FIFO event, movement date, or accepted inventory quantity.
    """

    def __init__(self, repository: FifoCostRepository | None = None):
        self.repository = repository or FifoCostRepository()

    def record_collected_supply(
        self, *, collection_result, store_id, product_id=None, offer_id=None, sku,
    ):
        """Persist only a complete result from the explicit read-only collector."""
        if (
            getattr(collection_result, "read_only", None) is not True
            or getattr(collection_result, "status", None) not in {"COMPLETE", "CONFIRMED_ZERO"}
        ):
            return {"error": True, "code": "FIFO_SUPPLY_SOURCE_NOT_COMPLETE"}
        snapshot = getattr(collection_result, "supply_snapshot", None)
        if snapshot is None:
            return {"error": True, "code": "FIFO_SUPPLY_SNAPSHOT_INVALID"}
        return self.repository.record_supply_evidence(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
            snapshot=snapshot,
        )

    def read_history(self, *, store_id, product_id=None, offer_id=None, sku):
        return self.repository.read_supply_evidence_history(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
        )
