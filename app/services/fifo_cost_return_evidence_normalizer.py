"""Normalize owner-confirmed, saleable return evidence for FIFO replay.

This boundary never infers physical return time from Ozon status timestamps.
The effective date is the seller's explicit date that the exact quantity was
confirmed saleable again. Return COGS accounting remains owned by its existing
independent authorization pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re

from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)


class FifoCostReturnEvidenceNormalizer:
    MAX_TEXT = 256
    MAX_QUANTITY = 100_000
    CUSTOMER_RETURN_TYPES = frozenset({"clientreturn", "fullreturn"})
    SALEABLE_STATUS = "ArrivedAtReturnPlace"
    COMPENSATED_STATUS = "Received"
    SELLER_SOURCE = "SELLER_CONFIRMED_BOT"

    @classmethod
    def build_event(cls, candidate, *, origin_sale_event_id):
        """Build the only repository event shape permitted for a ready candidate."""
        reason = cls._candidate_error(candidate)
        if reason is not None:
            return cls._blocked(reason)
        if (
            not isinstance(origin_sale_event_id, str)
            or not re.fullmatch(r"evt_[0-9a-f]{32}", origin_sale_event_id)
        ):
            return cls._blocked("FIFO_RETURN_ORIGIN_SALE_MISSING")
        return {
            "kind": "SALEABLE_RETURN_RESTOCK",
            "quantity": candidate["quantity"],
            "effective_date": candidate["effective_date"],
            "inventory_cutoff": candidate["inventory_cutoff"],
            "source_identity_digest": candidate["source_identity_digest"],
            "supersedes_event_id": origin_sale_event_id,
        }

    @classmethod
    def build_command_source(cls, candidate, *, captured_at):
        """Create owner-confirmation source metadata without raw seller IDs."""
        reason = cls._candidate_error(candidate)
        if reason is not None:
            return cls._blocked(reason)
        return {
            "kind": "OWNER_CONFIRMATION",
            "method": "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY",
            "status": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "captured_at": captured_at,
            "inventory_cutoff": candidate["inventory_cutoff"],
            "record_count": 1,
            "page_count": 1,
            "references": [
                {"kind": "OTHER", "digest": candidate["source_identity_digest"]},
                {"kind": "OTHER", "digest": candidate["origin_sale_identity_digest"]},
            ],
        }

    @classmethod
    def _candidate_error(cls, candidate):
        if not isinstance(candidate, dict) or candidate.get("eligible") is not True:
            return "FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED"
        if (
            type(candidate.get("quantity")) is not int
            or not 1 <= candidate["quantity"] <= cls.MAX_QUANTITY
            or cls._date(candidate.get("effective_date")) is None
            or cls._date(candidate.get("inventory_cutoff")) is None
            or candidate["effective_date"] <= candidate["inventory_cutoff"]
            or not cls._valid_digest(candidate.get("source_identity_digest"))
            or not cls._valid_digest(candidate.get("origin_sale_identity_digest"))
            or candidate.get("source_method") != "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY"
            or candidate.get("source_status") != "OWNER_CONFIRMED"
            or candidate.get("provenance") != "OWNER_CONFIRMED"
            or candidate.get("completeness") != "OWNER_CONFIRMED"
            or candidate.get("coverage_status") != "OWNER_CONFIRMED"
        ):
            return "FIFO_RETURN_EVIDENCE_INVALID"
        return None

    @classmethod
    def _valid_digest(cls, value):
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
        )

    @classmethod
    def normalize(
        cls, *, store_id, finance_sku, identity, return_record,
        recovery_evidence, return_sample_complete,
        inventory_cutoff, cutoff_bridge_confirmed,
    ):
        """Return a redacted FIFO candidate only for a complete exact match."""
        if return_sample_complete is not True:
            return cls._blocked("FIFO_RETURN_SOURCE_INCOMPLETE")
        if cutoff_bridge_confirmed is not True:
            return cls._blocked("INVENTORY_CUTOFF_UNRECONCILED")
        cutoff = cls._date(inventory_cutoff)
        if cutoff is None:
            return cls._blocked("INVENTORY_CUTOFF_UNRECONCILED")
        if not isinstance(return_record, dict) or not isinstance(recovery_evidence, dict):
            return cls._blocked("FIFO_RETURN_EVIDENCE_INVALID")

        return_id = cls._text(return_record.get("id") or return_record.get("return_id"))
        posting = cls._text(return_record.get("posting_number"))
        record_sku = cls._text(return_record.get("sku"))
        quantity = cls._quantity(return_record.get("quantity"))
        return_type = cls._text(return_record.get("type"))
        if (
            return_id is None or posting is None or record_sku is None
            or record_sku != cls._text(finance_sku)
            or quantity is None
            or return_type is None
            or return_type.lower() not in cls.CUSTOMER_RETURN_TYPES
        ):
            return cls._blocked("FIFO_RETURN_IDENTITY_OR_TYPE_INVALID")
        if return_record.get("visual_status_sys_name") != cls.SALEABLE_STATUS:
            return cls._blocked("FIFO_RETURN_PLACE_STATUS_UNCONFIRMED")
        if return_record.get("compensation_status_sys_name") == cls.COMPENSATED_STATUS:
            return cls._blocked("FIFO_RETURN_COMPENSATION_UNRESOLVED")

        recovery = {
            "return_id": cls._text(recovery_evidence.get("return_id")),
            "posting_number": cls._text(recovery_evidence.get("posting_number")),
            "sku": cls._text(recovery_evidence.get("sku")),
        }
        if (
            recovery_evidence.get("error") is not False
            or recovery_evidence.get("inventory_recovery_confirmed") is not True
            or recovery_evidence.get("recovery_state") != "SALEABLE_RESTORED"
            or recovery_evidence.get("source") != cls.SELLER_SOURCE
            or recovery != {
                "return_id": return_id,
                "posting_number": posting,
                "sku": record_sku,
            }
            or cls._quantity(recovery_evidence.get("quantity")) != quantity
        ):
            return cls._blocked("FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED")
        effective_date = cls._date(recovery_evidence.get("confirmed_on"))
        if effective_date is None or effective_date <= cutoff:
            return cls._blocked("FIFO_RETURN_EFFECTIVE_DATE_UNAVAILABLE")

        stable_identity = {
            "mapping_confirmed": (
                identity.get("mapping_confirmed") is True
                if isinstance(identity, dict) else False
            ),
            "offer_id": identity.get("offer_id") if isinstance(identity, dict) else None,
            "product_id": identity.get("product_id") if isinstance(identity, dict) else None,
        }
        sale_key = FifoCostSaleEvidenceNormalizer.build_identity_digest(
            store_id=store_id,
            posting_number=posting,
            finance_sku=record_sku,
            identity=stable_identity,
        )
        if sale_key.get("error") is True:
            return cls._blocked(sale_key.get("code"))
        return {
            "error": False,
            "status": "FIFO_RETURN_RESTOCK_CANDIDATE_READY",
            "eligible": True,
            "source_identity_digest": cls._return_digest(
                store_id, return_id, posting, record_sku,
            ),
            "origin_sale_identity_digest": sale_key["source_identity_digest"],
            "quantity": quantity,
            "effective_date": effective_date,
            "inventory_cutoff": cutoff,
            "source_method": "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY",
            "source_status": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
        }

    @classmethod
    def _return_digest(cls, store_id, return_id, posting, sku):
        material = {
            "version": 1,
            "domain": "ozon-fifo-saleable-return",
            "store_id": cls._text(store_id),
            "return_id": return_id,
            "posting_number": posting,
            "finance_sku": sku,
        }
        return hashlib.sha256(json.dumps(
            material, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()

    @classmethod
    def _text(cls, value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        if (
            not text or len(text) > cls.MAX_TEXT
            or any(ord(char) < 32 for char in text)
        ):
            return None
        return text

    @classmethod
    def _quantity(cls, value):
        return value if type(value) is int and 1 <= value <= cls.MAX_QUANTITY else None

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return None
        try:
            from datetime import date
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == value else None

    @staticmethod
    def _blocked(reason):
        return {
            "error": False,
            "status": "FIFO_RETURN_RESTOCK_SOURCE_BLOCKED",
            "eligible": False,
            "reason_code": str(reason or "FIFO_RETURN_EVIDENCE_INVALID"),
            "source_identity_digest": None,
            "origin_sale_identity_digest": None,
            "quantity": None,
            "effective_date": None,
        }
