"""Preview and atomically confirm a narrowly supported late FIFO rate correction."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from services.fifo_cost_late_entry_reconstruction_service import (
    FifoCostLateEntryReconstructionService,
)
from services.fifo_cost_rate_service import FifoCostRateService


class FifoCostLateEntryCorrectionService:
    """Bind a complete impact preview to the existing CAS rate commit.

    The initial release handles one missing rate transition only. Existing rate
    changes or return-basis replay stay explicitly blocked for FC23.
    """

    _LOCK = threading.RLock()
    _TICKETS = {}
    _TTL_SECONDS = 600

    def __init__(
        self, repository, *, rate_service=None, reconstruction_service=None,
        now_provider=None,
    ):
        self.repository = repository
        self.rate_service = rate_service or FifoCostRateService(repository)
        self.reconstruction_service = reconstruction_service or (
            FifoCostLateEntryReconstructionService(repository)
        )
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def preview(
        self, *, store_id, product_id=None, offer_id=None, sku, draft_id,
        period_summaries, tax_policy_result,
    ):
        scope = self.repository._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        identity = self.repository._normalize_identity(
            store_id, product_id, offer_id, sku, 1,
        )
        impact = self.reconstruction_service.preview_impact(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            draft_id=draft_id, period_summaries=period_summaries,
            tax_policy_result=tax_policy_result,
        )
        if not isinstance(impact, dict) or impact.get("code") != "FIFO_LATE_ENTRY_IMPACT_READY":
            return impact
        drafts = self.repository.read_late_entry_drafts(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if drafts.get("error") is not False:
            return drafts
        draft = next((row for row in drafts["drafts"] if row["draft_id"] == draft_id), None)
        if draft is None or draft["expected_revision"] != impact["stream_revision"]:
            return self._blocked("FIFO_LATE_ENTRY_PREVIEW_STALE")
        rate_preview = self.rate_service.preview_new_cost(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            effective_date=draft["owner_effective_date"],
            purchase_cost_rub=draft["purchase_cost_rub"],
            delivery_cost_rub=draft["delivery_cost_rub"],
            packaging_cost_rub=draft["packaging_cost_rub"],
            old_home_units=draft["owner_old_home_units"],
            expected_revision=draft["expected_revision"],
            late_entry_correction_preview=impact,
        )
        if not isinstance(rate_preview, dict) or rate_preview.get("error") is not False:
            return rate_preview
        if rate_preview.get("unit_cost_rub") != draft["unit_cost_rub"]:
            return self._blocked("FIFO_LATE_ENTRY_COST_MISMATCH")
        now = self._now()
        ticket_key = scope["owner_fingerprint"]
        with self._LOCK:
            self._purge_expired(now)
            self._TICKETS[ticket_key] = {
                "preview_id": rate_preview["preview_id"],
                "identity": identity,
                "tenant_fingerprint": scope["tenant_fingerprint"],
                "impact_fingerprint": impact["preview_fingerprint"],
                "draft_id": draft_id,
                "expires_at": now.timestamp() + self._TTL_SECONDS,
            }
        return {
            **impact,
            "code": "FIFO_LATE_ENTRY_CORRECTION_PREVIEW_READY",
            "preview_id": rate_preview["preview_id"],
            "active_preview_id": rate_preview["preview_id"],
            "unit_cost_rub": rate_preview["unit_cost_rub"],
            "expected_revision": rate_preview["expected_revision"],
            "replay_required_after_commit": True,
            "period_profit_changed": False,
            "expires_in_seconds": self._TTL_SECONDS,
        }

    def confirm(
        self, *, preview_id, active_preview_id, idempotency_key,
        store_id, product_id=None, offer_id=None, sku, draft_id,
        period_summaries, tax_policy_result,
    ):
        scope = self.repository._tenant_scope(store_id)
        if scope.get("error"):
            return scope
        identity = self.repository._normalize_identity(
            store_id, product_id, offer_id, sku, 1,
        )
        now = self._now()
        ticket_key = scope["owner_fingerprint"]
        with self._LOCK:
            self._purge_expired(now)
            ticket = self._TICKETS.get(ticket_key)
            if (
                ticket is None or preview_id != active_preview_id
                or ticket["preview_id"] != preview_id
                or ticket["draft_id"] != draft_id
                or ticket["identity"] != identity
                or ticket["tenant_fingerprint"] != scope["tenant_fingerprint"]
            ):
                return self._blocked("FIFO_PREVIEW_STALE")
            if ticket.get("committed_result") is not None:
                if ticket.get("committed_idempotency_key") != idempotency_key:
                    return self._blocked("FIFO_IDEMPOTENCY_CONFLICT")
                return dict(ticket["committed_result"], idempotent=True)

        current_impact = self.reconstruction_service.preview_impact(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
            draft_id=draft_id, period_summaries=period_summaries,
            tax_policy_result=tax_policy_result,
        )
        if (
            not isinstance(current_impact, dict)
            or current_impact.get("code") != "FIFO_LATE_ENTRY_IMPACT_READY"
            or current_impact.get("preview_fingerprint") != ticket["impact_fingerprint"]
        ):
            with self._LOCK:
                self._TICKETS.pop(ticket_key, None)
            return self._blocked("FIFO_LATE_ENTRY_SOURCE_STALE")

        committed = self.rate_service.confirm_new_cost(
            preview_id=preview_id, active_preview_id=active_preview_id,
            idempotency_key=idempotency_key,
            late_entry_correction=current_impact,
        )
        if committed.get("error") is not False:
            with self._LOCK:
                self._TICKETS.pop(ticket_key, None)
            return committed
        response = {
            "error": False,
            "code": "FIFO_LATE_ENTRY_CORRECTION_COMMITTED",
            "correction_id": committed.get("correction_id"),
            "draft_id": draft_id,
            "revision": committed["revision"],
            "rate_sequence": committed["rate_sequence"],
            "unit_cost_rub": committed["unit_cost_rub"],
            "periods": current_impact["periods"],
            "impact_preview_fingerprint": current_impact["preview_fingerprint"],
            "period_profit_changed": False,
            "replay_required": True,
            "projection_complete": False,
            "read_only_external_sources": True,
        }
        with self._LOCK:
            current_ticket = self._TICKETS.get(ticket_key)
            if current_ticket is not None and current_ticket["preview_id"] == preview_id:
                current_ticket["committed_idempotency_key"] = idempotency_key
                current_ticket["committed_result"] = response
        return response

    def _now(self):
        value = self._now_provider()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("FIFO_CLOCK_INVALID")
        return value.astimezone(timezone.utc)

    @classmethod
    def _purge_expired(cls, now):
        cutoff = now.timestamp()
        for key in [key for key, ticket in cls._TICKETS.items() if ticket["expires_at"] <= cutoff]:
            cls._TICKETS.pop(key, None)

    @staticmethod
    def _blocked(reason):
        return {
            "error": False, "code": "FIFO_LATE_ENTRY_CORRECTION_BLOCKED",
            "complete": False, "reason_code": reason, "read_only": True,
        }
