"""Normalize explicit non-sale movement evidence for the FIFO cost pool."""

from __future__ import annotations

import hashlib
import json
import re


class FifoCostMovementEvidenceNormalizer:
    MAX_TEXT = 256
    MAX_QUANTITY = 100_000
    OUTFLOW_REASONS = frozenset({
        "HOME_SHORTAGE", "OZON_DISPOSAL", "SUPPLIER_RETURN", "INVENTORY_WRITE_OFF",
    })
    POOL_LOCATIONS = frozenset({"HOME", "TRANSIT", "OZON"})

    @classmethod
    def normalize(
        cls, *, store_id, sku, movement_id, reason_code, quantity=None,
        effective_date=None, inventory_cutoff=None, cutoff_bridge_confirmed,
        declared_quantity=None, accepted_quantity=None,
        location_from=None, location_to=None,
    ):
        """Return an outflow candidate or a non-mutating discrepancy/neutral result."""
        reason = cls._text(reason_code)
        cutoff = cls._date(inventory_cutoff)
        if reason is None:
            return cls._blocked("FIFO_MOVEMENT_REASON_INVALID")
        if reason == "ACCEPTANCE_SHORTFALL":
            if (
                type(declared_quantity) is not int
                or type(accepted_quantity) is not int
                or not 0 <= accepted_quantity <= declared_quantity <= cls.MAX_QUANTITY
            ):
                return cls._blocked("FIFO_ACCEPTANCE_COMPARISON_INVALID")
            return {
                "error": False, "status": "FIFO_MOVEMENT_DISCREPANCY_ONLY",
                "eligible": False, "reason_code": reason,
                "declared_quantity": declared_quantity,
                "accepted_quantity": accepted_quantity,
                "unreceived_quantity": declared_quantity - accepted_quantity,
                "inventory_change": False, "cost_impact_rub": None,
            }
        if reason == "INVENTORY_TRANSFER":
            if (
                location_from not in cls.POOL_LOCATIONS
                or location_to not in cls.POOL_LOCATIONS
                or location_from == location_to
                or type(quantity) is not int or not 1 <= quantity <= cls.MAX_QUANTITY
            ):
                return cls._blocked("FIFO_TRANSFER_EVIDENCE_INVALID")
            return {
                "error": False, "status": "FIFO_MOVEMENT_POOL_NEUTRAL",
                "eligible": False, "reason_code": reason,
                "quantity": quantity, "location_from": location_from,
                "location_to": location_to, "inventory_change": False,
                "cost_impact_rub": None,
            }
        if reason not in cls.OUTFLOW_REASONS:
            return cls._blocked("FIFO_MOVEMENT_REASON_UNSUPPORTED")
        event_id = cls._text(movement_id)
        normalized_sku = cls._text(sku)
        normalized_store = cls._text(store_id)
        normalized_quantity = quantity if type(quantity) is int and 1 <= quantity <= cls.MAX_QUANTITY else None
        effective = cls._date(effective_date)
        if cutoff is None or cutoff_bridge_confirmed is not True:
            return cls._blocked("INVENTORY_CUTOFF_UNRECONCILED")
        if (
            event_id is None or normalized_sku is None or normalized_store is None
            or normalized_quantity is None
        ):
            return cls._blocked("FIFO_MOVEMENT_EVIDENCE_INVALID")
        if effective is None or effective <= cutoff:
            return cls._blocked("FIFO_MOVEMENT_EFFECTIVE_DATE_UNAVAILABLE")
        digest = cls._digest(normalized_store, normalized_sku, event_id, reason)
        return {
            "error": False, "status": "FIFO_NON_SALE_MOVEMENT_READY",
            "eligible": True, "reason_code": reason,
            "source_identity_digest": digest,
            "quantity": normalized_quantity,
            "effective_date": effective,
            "inventory_cutoff": cutoff,
            "source_method": "OWNER_CONFIRMED_FIFO_NON_SALE_MOVEMENT",
            "provenance": "OWNER_CONFIRMED",
        }

    @classmethod
    def build_event(cls, candidate):
        if not isinstance(candidate, dict) or candidate.get("eligible") is not True:
            return cls._blocked("FIFO_MOVEMENT_EVIDENCE_INVALID")
        if (
            candidate.get("reason_code") not in cls.OUTFLOW_REASONS
            or type(candidate.get("quantity")) is not int
            or not 1 <= candidate["quantity"] <= cls.MAX_QUANTITY
            or cls._date(candidate.get("effective_date")) is None
            or cls._date(candidate.get("inventory_cutoff")) is None
            or candidate["effective_date"] <= candidate["inventory_cutoff"]
            or not cls._valid_digest(candidate.get("source_identity_digest"))
            or candidate.get("source_method") != "OWNER_CONFIRMED_FIFO_NON_SALE_MOVEMENT"
        ):
            return cls._blocked("FIFO_MOVEMENT_EVIDENCE_INVALID")
        return {
            "kind": "NON_SALE_OUTFLOW",
            "quantity": candidate["quantity"],
            "effective_date": candidate["effective_date"],
            "inventory_cutoff": candidate["inventory_cutoff"],
            "source_identity_digest": candidate["source_identity_digest"],
            "reason_code": candidate["reason_code"],
        }

    @classmethod
    def build_source(cls, candidate, *, captured_at):
        event = cls.build_event(candidate)
        if not isinstance(event, dict) or event.get("kind") != "NON_SALE_OUTFLOW":
            return event
        return {
            "kind": "OWNER_CONFIRMATION",
            "method": candidate["source_method"],
            "status": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "captured_at": captured_at,
            "inventory_cutoff": candidate["inventory_cutoff"],
            "record_count": 1,
            "page_count": 1,
            "references": [{
                "kind": "OTHER", "digest": candidate["source_identity_digest"],
            }],
        }

    @classmethod
    def _digest(cls, store_id, sku, movement_id, reason):
        material = {
            "version": 1, "domain": "fifo-non-sale-movement",
            "store_id": store_id, "sku": sku,
            "movement_id": movement_id, "reason_code": reason,
        }
        return hashlib.sha256(json.dumps(
            material, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()

    @classmethod
    def _text(cls, value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        if not text or len(text) > cls.MAX_TEXT or any(ord(ch) < 32 for ch in text):
            return None
        return text

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return None
        from datetime import date
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == value else None

    @staticmethod
    def _valid_digest(value):
        return isinstance(value, str) and len(value) == 64 and all(
            char in "0123456789abcdef" for char in value
        )

    @staticmethod
    def _blocked(reason):
        return {
            "error": False, "status": "FIFO_MOVEMENT_BLOCKED",
            "eligible": False, "reason_code": reason,
            "quantity": None, "cost_impact_rub": None,
        }
