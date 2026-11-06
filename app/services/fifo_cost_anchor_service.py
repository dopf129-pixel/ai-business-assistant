"""Owner-confirmed opening FIFO anchor validation and preview."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from services.fifo_cost_repository import FifoCostRepository


class FifoCostAnchorService:
    """Build the first explicit per-SKU FIFO layer set without inferring stock.

    All zone quantities and old costs must be supplied and confirmed by the
    owner. This service never promotes a diagnostic Ozon snapshot to an anchor.
    """

    MAX_LAYERS = 100
    MAX_EVENT_UNITS = FifoCostRepository.MAX_EVENT_QUANTITY
    MAX_STREAM_UNITS = FifoCostRepository.MAX_COMMAND_UNITS
    _ZONES = (
        ("ozon_units", "OZON"),
        ("transit_units", "TRANSIT"),
        ("home_units", "HOME"),
    )
    _LAYER_FIELDS = frozenset({
        "sequence", "unit_cost_rub", "ozon_units", "transit_units", "home_units",
    })

    def __init__(self, repository: FifoCostRepository | None = None, *, now_provider=None):
        self.repository = repository or FifoCostRepository()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def preview_opening_anchor(
        self,
        *,
        store_id,
        product_id,
        offer_id,
        sku,
        inventory_cutoff,
        cost_layers,
        ozon_units_include_reserved_confirmed,
        transit_not_in_ozon_confirmed,
        expected_revision=None,
    ):
        """Return a read-only revision-bound anchor preview or a typed error."""

        identity = self._identity_scope(
            store_id=store_id, product_id=product_id, offer_id=offer_id, sku=sku,
        )
        if identity is None:
            return self._error("FIFO_IDENTITY_INVALID")
        cutoff = self._date(inventory_cutoff)
        if cutoff is None:
            return self._error("FIFO_ANCHOR_CUTOFF_INVALID")
        if type(ozon_units_include_reserved_confirmed) is not bool:
            return self._error("FIFO_ANCHOR_STOCK_CONFIRMATION_REQUIRED")
        if not ozon_units_include_reserved_confirmed:
            return self._error("STOCK_SEMANTICS_UNCONFIRMED")
        if type(transit_not_in_ozon_confirmed) is not bool:
            return self._error("FIFO_ANCHOR_TRANSIT_CONFIRMATION_REQUIRED")
        if not transit_not_in_ozon_confirmed:
            return self._error("TRANSIT_OVERLAP_UNRESOLVED")
        normalized_layers, code = self._layers(cost_layers)
        if code:
            return self._error(code)
        if not normalized_layers:
            return self._error("FIFO_ANCHOR_LAYERS_REQUIRED")

        total_units = sum(
            layer[zone] for layer in normalized_layers
            for zone, _location in self._ZONES
        )
        if total_units <= 0:
            return self._error("FIFO_ANCHOR_ZERO_TOTAL_UNSUPPORTED")
        if total_units > self.MAX_STREAM_UNITS:
            return self._error("FIFO_STREAM_QUANTITY_LIMIT")

        events = []
        zone_totals = {location: 0 for _key, location in self._ZONES}
        zero_confirmation_refs = []
        for layer in normalized_layers:
            for quantity_key, location in self._ZONES:
                quantity = layer[quantity_key]
                zone_totals[location] += quantity
                if quantity == 0:
                    zero_confirmation_refs.append({
                        "kind": "OTHER",
                        "digest": self._zero_confirmation_digest(
                            cutoff, layer["sequence"], location,
                        ),
                    })
                    continue
                events.append({
                    "kind": "OPENING_FIFO_ANCHOR",
                    "quantity": quantity,
                    "unit_cost_rub": layer["unit_cost_rub"],
                    "effective_date": cutoff,
                    "inventory_cutoff": cutoff,
                    "location_to": location,
                    "currency": "RUB",
                })
        if len(events) > FifoCostRepository.MAX_COMMAND_EVENTS:
            return self._error("FIFO_COMMAND_EVENT_LIMIT")
        if len(zero_confirmation_refs) > FifoCostRepository.MAX_REFERENCES_PER_SOURCE:
            return self._error("FIFO_SOURCE_REFERENCE_LIMIT")

        captured_at = self._captured_at()
        if captured_at is None:
            return self._error("FIFO_CLOCK_INVALID")
        canonical_scope = {
            **identity,
            "inventory_cutoff": cutoff,
            "layers": normalized_layers,
            "ozon_units_include_reserved_confirmed": True,
            "transit_not_in_ozon_confirmed": True,
        }
        source_fingerprint = self._fingerprint(canonical_scope)
        source = {
            "kind": "OWNER_CONFIRMATION",
            "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
            "status": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "fingerprint": source_fingerprint,
            "captured_at": captured_at,
            "inventory_cutoff": cutoff,
            "record_count": len(events),
            "references": zero_confirmation_refs,
        }
        preview = self.repository.preview_command(
            **identity,
            events=events,
            source=source,
            expected_revision=expected_revision,
        )
        if preview.get("error") is True:
            return preview

        known_value = sum(
            Decimal(layer["unit_cost_rub"])
            * sum(layer[key] for key, _location in self._ZONES)
            for layer in normalized_layers
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "error": False,
            "code": "FIFO_ANCHOR_PREVIEW_READY",
            "preview_id": preview["preview_id"],
            "expected_revision": preview["expected_revision"],
            "next_revision": preview["next_revision"],
            "event_count": preview["event_count"],
            "total_units": total_units,
            "known_cost_rub": format(known_value, ".2f"),
            "next_unit_cost_rub": normalized_layers[0]["unit_cost_rub"],
            "zone_totals": zone_totals,
            "inventory_cutoff": cutoff,
            "source_fingerprint": source_fingerprint,
            "period_profit_cutoff_status": "INVENTORY_CUTOFF_UNRECONCILED",
        }

    def commit_opening_anchor(self, *, preview_id, active_preview_id, idempotency_key):
        """Confirm the preview through the repository's atomic CAS boundary."""

        return self.repository.commit_command(
            preview_id=preview_id,
            active_preview_id=active_preview_id,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def _layers(cls, value):
        if not isinstance(value, list) or not 1 <= len(value) <= cls.MAX_LAYERS:
            return None, "FIFO_ANCHOR_LAYERS_INVALID"
        result = []
        total_units = 0
        for expected_sequence, row in enumerate(value, start=1):
            if not isinstance(row, dict) or set(row) != cls._LAYER_FIELDS:
                return None, "FIFO_ANCHOR_LAYER_FIELDS_INVALID"
            if type(row["sequence"]) is not int or row["sequence"] != expected_sequence:
                return None, "FIFO_ANCHOR_LAYER_ORDER_INVALID"
            unit_cost = cls._money(row["unit_cost_rub"])
            if unit_cost is None:
                return None, "FIFO_MONEY_INPUT_INVALID"
            normalized = {
                "sequence": expected_sequence,
                "unit_cost_rub": unit_cost,
            }
            layer_units = 0
            for quantity_key, _location in cls._ZONES:
                quantity = row[quantity_key]
                if type(quantity) is not int or not 0 <= quantity <= cls.MAX_EVENT_UNITS:
                    return None, "FIFO_ANCHOR_QUANTITY_INVALID"
                normalized[quantity_key] = quantity
                layer_units += quantity
            if layer_units == 0:
                return None, "FIFO_ANCHOR_EMPTY_LAYER"
            total_units += layer_units
            if total_units > cls.MAX_STREAM_UNITS:
                return None, "FIFO_STREAM_QUANTITY_LIMIT"
            result.append(normalized)
        return result, None

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == value else None

    @staticmethod
    def _identity_scope(*, store_id, product_id, offer_id, sku):
        def part(value, *, required, limit):
            if value is None:
                return None if not required else ""
            if isinstance(value, bool) or type(value) not in {str, int}:
                return ""
            normalized = str(value).strip()
            if not normalized:
                return None if not required else ""
            if len(normalized) > limit or any(ord(char) < 32 for char in normalized):
                return ""
            return normalized

        store = part(store_id, required=True, limit=128)
        product = part(product_id, required=False, limit=128)
        offer = part(offer_id, required=False, limit=128)
        normalized_sku = part(sku, required=True, limit=64)
        if (
            not store or not normalized_sku or product == "" or offer == ""
            or not (product or offer)
        ):
            return None
        return {
            "store_id": store,
            "product_id": product,
            "offer_id": offer,
            "sku": normalized_sku,
        }

    @staticmethod
    def _money(value):
        if isinstance(value, (bool, float)) or value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
            return None
        return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")

    def _captured_at(self):
        value = self.now_provider()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z",
        )

    @staticmethod
    def _fingerprint(value):
        serialized = json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _zero_confirmation_digest(cls, cutoff, sequence, location):
        return cls._fingerprint({
            "evidence": "OWNER_CONFIRMED_ZERO_FIFO_ZONE",
            "version": 1,
            "inventory_cutoff": cutoff,
            "layer_sequence": sequence,
            "location": location,
        })

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
