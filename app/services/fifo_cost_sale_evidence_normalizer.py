"""Normalize a stable FIFO sale identity without inventing physical timing.

This pure boundary deliberately separates a sale's stable identity, its
financial recognition dates, and the physical inventory effective date. It
never treats an order status or accrual date as proof of a physical sale time.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import re
from typing import Mapping


class FifoCostSaleEvidenceNormalizer:
    MAX_TEXT = 256
    MAX_QUANTITY = 100_000

    def normalize_sale(
        self,
        *,
        store_id: object,
        posting_number: object,
        finance_sku: object,
        identity: Mapping[str, object],
        quantity: object,
        sale_authority: object,
        sale_authority_confirmed: object,
        physical_effective_date: object = None,
        effective_date_semantics_confirmed: object = False,
        inventory_cutoff_bridge_confirmed: object = False,
        financial_accrual_dates: object = (),
    ) -> dict:
        """Return a redacted stable sale key and an explicit allocation gate.

        ``offer_id`` is the preferred stable identity when the seller has
        confirmed its mapping. ``product_id`` is the fallback. Catalog SKU is
        validated as source evidence but is not part of that key, so a catalog
        SKU rewrite for the same confirmed offer does not create another sale.
        """
        if sale_authority != "OZON_REALIZATION_REPORT":
            return self._error("FIFO_SALE_AUTHORITY_UNSUPPORTED")
        if sale_authority_confirmed is not True:
            return self._error("FIFO_SALE_AUTHORITY_UNCONFIRMED")
        if type(quantity) is not int or not 1 <= quantity <= self.MAX_QUANTITY:
            return self._error("FIFO_SALE_QUANTITY_INVALID")

        identity_result = self.build_identity_digest(
            store_id=store_id,
            posting_number=posting_number,
            finance_sku=finance_sku,
            identity=identity,
        )
        if identity_result.get("error") is True:
            return identity_result
        digest = identity_result["source_identity_digest"]

        dates = self._dates(financial_accrual_dates)
        if dates is None:
            return self._error("FIFO_SALE_FINANCE_DATES_INVALID")

        physical_date = self._date(physical_effective_date)
        if physical_effective_date not in (None, "") and physical_date is None:
            return self._error("FIFO_SALE_PHYSICAL_DATE_INVALID")
        for flag in (
            effective_date_semantics_confirmed,
            inventory_cutoff_bridge_confirmed,
        ):
            if type(flag) is not bool:
                return self._error("FIFO_SALE_TIME_CONFIRMATION_INVALID")

        date_is_proven = (
            physical_date is not None
            and effective_date_semantics_confirmed is True
        )
        allocation_eligible = (
            date_is_proven
            and inventory_cutoff_bridge_confirmed is True
        )
        if allocation_eligible:
            status = "READY_FOR_FIFO_EVENT"
        elif physical_date is None:
            status = "IDENTITY_CONFIRMED_TIME_UNAVAILABLE"
        elif not effective_date_semantics_confirmed:
            status = "IDENTITY_CONFIRMED_TIME_SEMANTICS_UNCONFIRMED"
        else:
            status = "IDENTITY_CONFIRMED_CUTOFF_UNRECONCILED"

        return {
            "error": False,
            "status": status,
            "source_identity_digest": digest,
            "quantity": quantity,
            "physical_effective_date": physical_date if date_is_proven else None,
            "financial_accrual_dates": dates,
            "allocation_eligible": allocation_eligible,
        }

    @classmethod
    def build_identity_digest(
        cls, *, store_id: object, posting_number: object,
        finance_sku: object, identity: Mapping[str, object],
    ) -> dict:
        """Create a redacted join key without asserting time/source eligibility."""
        store = cls._text(store_id)
        posting = cls._text(posting_number)
        source_sku = cls._text(finance_sku)
        if store is None or posting is None or source_sku is None:
            return cls._error("FIFO_SALE_IDENTITY_INPUT_INVALID")
        if not isinstance(identity, Mapping):
            return cls._error("FIFO_SALE_PRODUCT_IDENTITY_UNAVAILABLE")
        if identity.get("mapping_confirmed") is not True:
            return cls._error("FIFO_SALE_PRODUCT_IDENTITY_UNCONFIRMED")
        offer_id = cls._text(identity.get("offer_id"))
        product_id = cls._text(identity.get("product_id"))
        if offer_id is not None:
            identity_kind, stable_product_identity = "OFFER", offer_id
        elif product_id is not None:
            identity_kind, stable_product_identity = "PRODUCT", product_id
        else:
            return cls._error("FIFO_SALE_STABLE_PRODUCT_KEY_UNAVAILABLE")
        material = {
            "version": 1,
            "domain": "ozon-fifo-physical-sale",
            "store_id": store,
            "posting_number": posting,
            "identity_kind": identity_kind,
            "stable_product_identity": stable_product_identity,
        }
        digest = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {"error": False, "source_identity_digest": digest}

    @classmethod
    def _text(cls, value):
        if isinstance(value, bool) or value is None:
            return None
        text = str(value).strip()
        if not text or len(text) > cls.MAX_TEXT or any(ord(char) < 32 for char in text):
            return None
        return text

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None

    @classmethod
    def _dates(cls, values):
        if not isinstance(values, (list, tuple, set, frozenset)) or len(values) > 366:
            return None
        normalized = []
        for value in values:
            item = cls._date(value)
            if item is None:
                return None
            normalized.append(item)
        return sorted(set(normalized))

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
