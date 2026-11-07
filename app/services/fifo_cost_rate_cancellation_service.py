"""Owner-confirmed cancellation of an unused future FIFO rate change."""

from __future__ import annotations

from services.fifo_cost_repository import FifoCostRepository


class FifoCostRateCancellationService:
    """Append a cancellation audit row without editing the original rate."""

    def __init__(self, repository: FifoCostRepository | None = None):
        self.repository = repository or FifoCostRepository()

    def preview(
        self, *, store_id, product_id=None, offer_id=None, sku,
        rate_sequence, expected_revision,
    ):
        return self.repository.preview_cancel_future_rate(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
            rate_sequence=rate_sequence,
            expected_revision=expected_revision,
        )

    def confirm(
        self, *, preview_id, active_preview_id, idempotency_key,
        store_id, product_id=None, offer_id=None, sku,
    ):
        return self.repository.commit_cancel_future_rate(
            preview_id=preview_id,
            active_preview_id=active_preview_id,
            idempotency_key=idempotency_key,
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
        )
