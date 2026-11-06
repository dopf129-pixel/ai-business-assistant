"""Revision-bound recording of an owner-reported FIFO unit-cost rate."""

from __future__ import annotations

from services.fifo_cost_repository import FifoCostRepository


class FifoCostRateService:
    """Record a new cost basis without inventing the purchased quantity.

    A rate is not a finite inventory layer. The owner-reported old-at-home
    remainder is retained as reconciliation evidence and is never added to
    the anchored quantity by this service.
    """

    def __init__(self, repository: FifoCostRepository | None = None):
        self.repository = repository or FifoCostRepository()

    def preview_new_cost(
        self,
        *,
        store_id,
        product_id=None,
        offer_id=None,
        sku,
        effective_date,
        purchase_cost_rub,
        delivery_cost_rub,
        packaging_cost_rub,
        old_home_units,
        expected_revision,
        zero_stock_snapshot=None,
    ):
        """Build a no-write preview for the next open FIFO rate."""
        zero_stock_evidence = None
        if zero_stock_snapshot is not None:
            fields = (
                "status", "source_status", "store_id", "product_id", "offer_id",
                "sku", "captured_at", "pagination_complete", "fbo_units",
                "reserved_units", "transit_units", "transit_status",
                "source_fingerprint",
            )
            try:
                zero_stock_evidence = {
                    field: getattr(zero_stock_snapshot, field) for field in fields
                }
            except (AttributeError, TypeError):
                return {"error": True, "code": "FIFO_ZERO_ANCHOR_SOURCE_INVALID"}
        return self.repository.preview_cost_rate_change(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
            effective_date=effective_date,
            purchase_cost_rub=purchase_cost_rub,
            delivery_cost_rub=delivery_cost_rub,
            packaging_cost_rub=packaging_cost_rub,
            owner_old_home_units=old_home_units,
            expected_revision=expected_revision,
            zero_stock_evidence=zero_stock_evidence,
        )

    def confirm_new_cost(self, *, preview_id, active_preview_id, idempotency_key):
        """Commit the selected preview once through the repository CAS boundary."""

        return self.repository.commit_cost_rate_change(
            preview_id=preview_id,
            active_preview_id=active_preview_id,
            idempotency_key=idempotency_key,
        )
