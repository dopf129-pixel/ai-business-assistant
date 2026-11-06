"""Identify when saved planning results use the same frozen FIFO cost basis."""

from hashlib import sha256
import json

from services.fifo_planning_quantity_allocation_service import (
    FifoPlanningQuantityAllocationService,
)


class FifoPlanningBasisCompatibilityService:
    """Create a stable, non-identifying signature for a saved plan cost basis."""

    MANUAL_PROVENANCE = frozenset({
        "manual", "manual_seller_assumption", "manual_unit_economics_input",
    })

    def __init__(self, allocator=None):
        self.allocator = allocator or FifoPlanningQuantityAllocationService()

    def describe_item(self, item):
        if not isinstance(item, dict):
            return {"status": "UNKNOWN", "signature": None}
        provenance = item.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        if str(provenance.get("cost") or "").strip().lower() in self.MANUAL_PROVENANCE:
            return {"status": "MANUAL", "signature": None}

        sources = item.get("sources")
        sources = sources if isinstance(sources, dict) else {}
        completeness = sources.get("completeness")
        completeness = completeness if isinstance(completeness, dict) else {}
        cost = completeness.get("cost")
        cost = cost if isinstance(cost, dict) else {}
        basis = cost.get("quantity_allocation_basis")
        method = str(cost.get("method") or "").strip().upper()
        if basis is None:
            return {
                "status": "UNKNOWN" if method.startswith("FIFO_") else "LEGACY",
                "signature": None,
            }
        normalized = self.allocator.normalize_persisted_basis(basis)
        if normalized is None:
            return {"status": "UNKNOWN", "signature": None}
        signature = self._signature(normalized)
        if signature is None:
            return {"status": "UNKNOWN", "signature": None}
        return {"status": "FIFO_AVAILABLE", "signature": signature}

    def basis_reference(self, item):
        """Return a redacted stable reference for a valid FIFO basis, if present."""
        cost = self._cost_source(item)
        basis = cost.get("quantity_allocation_basis")
        if not isinstance(basis, dict):
            return None
        normalized = self.allocator.normalize_persisted_basis(basis)
        return self._signature(normalized) if normalized is not None else None

    @staticmethod
    def _cost_source(item):
        if not isinstance(item, dict):
            return {}
        sources = item.get("sources")
        sources = sources if isinstance(sources, dict) else {}
        completeness = sources.get("completeness")
        completeness = completeness if isinstance(completeness, dict) else {}
        cost = completeness.get("cost")
        return cost if isinstance(cost, dict) else {}

    @staticmethod
    def _signature(normalized):
        if not isinstance(normalized, dict):
            return None
        try:
            encoded = json.dumps(
                normalized, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            return None
        return sha256(encoded).hexdigest()

    def export_snapshot(self, item):
        """Return only validated, allowlisted cost-source fields for a plan export."""
        if not isinstance(item, dict):
            return None
        sources = item.get("sources")
        sources = sources if isinstance(sources, dict) else {}
        completeness = sources.get("completeness")
        completeness = completeness if isinstance(completeness, dict) else {}
        cost = completeness.get("cost")
        if not isinstance(cost, dict):
            return None
        description = self.describe_item(item)
        if description["status"] == "LEGACY":
            return None
        provenance = item.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        mode = str(provenance.get("cost") or "").strip().lower()
        manual = mode in self.MANUAL_PROVENANCE
        raw_basis = cost.get("quantity_allocation_basis")
        normalized_basis = (
            self.allocator.normalize_persisted_basis(raw_basis)
            if isinstance(raw_basis, dict) and raw_basis.get("status") == "AVAILABLE"
            else None
        )
        output = {
            "status": description["status"],
            "method": self._safe_text(cost.get("method"), 80),
            "amount": self._safe_decimal(cost.get("amount")),
            "as_of_date": self._safe_date(cost.get("as_of_date")),
            "cutoff_date": self._safe_date(cost.get("cutoff_date")),
            "revision": self._safe_text(cost.get("revision"), 128),
            "model_only": cost.get("model_only") is True,
            "factual_period_profit_eligible": cost.get("factual_period_profit_eligible") is True,
            "scenario_override": manual,
        }
        if normalized_basis is not None:
            output["quantity_allocation_basis"] = normalized_basis
            output["basis_ref"] = self._signature(normalized_basis)
        elif description["status"] == "UNKNOWN":
            output["reason_code"] = "FIFO_BASIS_UNAVAILABLE_OR_INVALID"
        return output

    @staticmethod
    def _safe_text(value, limit):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            return None
        return value.strip()

    @staticmethod
    def _safe_decimal(value):
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            return None
        try:
            from decimal import Decimal, InvalidOperation
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not result.is_finite() or abs(result) > Decimal("999999999999.99"):
            return None
        return format(result.quantize(Decimal("0.01")), ".2f")

    @staticmethod
    def _safe_date(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            from datetime import date, datetime
            if "T" in value:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                date.fromisoformat(value)
        except (TypeError, ValueError):
            return None
        return value

    def compare_items(self, first, second):
        left = self.describe_item(first)
        right = self.describe_item(second)
        if "UNKNOWN" in {left["status"], right["status"]}:
            return False, "COST_BASIS_UNKNOWN"
        if left["status"] != right["status"]:
            return False, "COST_BASIS_MISMATCH"
        if (left["status"] == "FIFO_AVAILABLE"
                and left["signature"] != right["signature"]):
            return False, "COST_BASIS_MISMATCH"
        # Legacy and explicit manual scenario assumptions retain their existing
        # compare behavior. Their scalar values/provenance are already visible
        # in saved-plan input changes; FIFO snapshots require an exact match.
        return True, None
