"""Pure, read-only FIFO cost projection for an explicitly planned quantity."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class FifoPlanningQuantityAllocationService:
    """Allocate a planned successful-sales quantity across a bounded FIFO basis.

    This projection is model-only. It never consumes a queue, writes a FIFO
    event, or makes the result eligible for factual Period Profit COGS.
    """

    SCHEMA_VERSION = 1
    MAX_QUANTITY = 100_000
    MAX_LAYERS = 20
    MAX_COST = Decimal("1000000000.00")
    MAX_TOTAL_COST = Decimal("1000000000000.00")
    CENT = Decimal("0.01")
    _BASIS_FIELDS = frozenset({
        "schema_version", "status", "method", "as_of_date", "cutoff_date",
        "revision", "remaining_status", "movement_count", "model_only",
        "factual_period_profit_eligible", "layers", "open_rate", "reason_code",
    })

    def allocate(self, *, quantity, basis):
        if type(quantity) is not int or not 0 <= quantity <= self.MAX_QUANTITY:
            return self._result("UNAVAILABLE", "FIFO_PLANNING_QUANTITY_INVALID", quantity)
        if quantity == 0:
            return self._complete(quantity, [], None, None)
        normalized, error = self._normalize_basis(basis)
        if error:
            return self._result("UNAVAILABLE", error, quantity)

        remaining = quantity
        lines = []
        for layer in normalized["layers"]:
            if remaining <= 0:
                break
            taken = min(remaining, layer["quantity"])
            if taken <= 0:
                continue
            total = (layer["unit_cost"] * taken).quantize(self.CENT, rounding=ROUND_HALF_UP)
            lines.append({
                "sequence": layer["sequence"],
                "kind": layer["kind"],
                "effective_date": layer["effective_date"],
                "quantity": taken,
                "unit_cost_rub": self._money(layer["unit_cost"]),
                "total_cost_rub": self._money(total),
            })
            remaining -= taken

        open_rate = normalized["open_rate"]
        if remaining > 0 and open_rate is not None:
            total = (open_rate["unit_cost"] * remaining).quantize(
                self.CENT, rounding=ROUND_HALF_UP,
            )
            lines.append({
                "sequence": "OPEN_RATE",
                "kind": "OPEN_RATE",
                "effective_date": open_rate["effective_date"],
                "quantity": remaining,
                "unit_cost_rub": self._money(open_rate["unit_cost"]),
                "total_cost_rub": self._money(total),
            })
            remaining = 0

        if remaining:
            allocated = quantity - remaining
            known_cost = sum(
                (Decimal(line["total_cost_rub"]) for line in lines), Decimal("0.00"),
            ).quantize(self.CENT, rounding=ROUND_HALF_UP)
            return {
                "status": "PARTIAL",
                "reason_code": "FIFO_PLANNING_CONFIRMED_QUANTITY_EXHAUSTED",
                "quantity": quantity,
                "allocated_quantity": allocated,
                "total_cost_rub": None,
                "known_cost_rub": self._money(known_cost),
                "average_cost_rub": None,
                "lines": lines,
                **self._provenance(normalized),
                "read_only": True,
                "executed": False,
            }
        total_cost = sum(
            (Decimal(line["total_cost_rub"]) for line in lines), Decimal("0.00"),
        )
        if abs(total_cost) > self.MAX_TOTAL_COST:
            return self._result("UNAVAILABLE", "FIFO_PLANNING_AMOUNT_LIMIT_EXCEEDED", quantity)
        return self._complete(quantity, lines, normalized["open_rate"], normalized)

    @classmethod
    def normalize_persisted_basis(cls, value):
        """Validate/project the small allowlisted plan snapshot contract."""
        normalized, error = cls._normalize_basis(value)
        if error:
            return None
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "status": "AVAILABLE",
            "method": "FIFO_CURRENT_SNAPSHOT",
            "as_of_date": normalized["as_of_date"],
            "cutoff_date": normalized["cutoff_date"],
            "revision": normalized["revision"],
            "remaining_status": "AT_CONFIRMED_SNAPSHOT",
            "movement_count": 0,
            "model_only": True,
            "factual_period_profit_eligible": False,
            "layers": [
                {
                    "sequence": row["sequence"],
                    "kind": row["kind"],
                    "quantity": row["quantity"],
                    "unit_cost_rub": cls._money(row["unit_cost"]),
                    "effective_date": row["effective_date"],
                }
                for row in normalized["layers"]
            ],
            "open_rate": (
                {
                    "unit_cost_rub": cls._money(normalized["open_rate"]["unit_cost"]),
                    "effective_date": normalized["open_rate"]["effective_date"],
                }
                if normalized["open_rate"] is not None else None
            ),
        }

    @classmethod
    def _normalize_basis(cls, basis):
        if not isinstance(basis, dict) or set(basis) - cls._BASIS_FIELDS:
            return None, "FIFO_PLANNING_BASIS_INVALID"
        if (type(basis.get("schema_version")) is not int
                or basis.get("schema_version") != cls.SCHEMA_VERSION
                or basis.get("status") != "AVAILABLE"
                or basis.get("method") != "FIFO_CURRENT_SNAPSHOT"
                or basis.get("remaining_status") != "AT_CONFIRMED_SNAPSHOT"
                or type(basis.get("movement_count")) is not int
                or basis.get("movement_count") != 0
                or basis.get("model_only") is not True
                or basis.get("factual_period_profit_eligible") is not False):
            return None, str(basis.get("reason_code") or "FIFO_PLANNING_BASIS_INCOMPLETE")
        as_of = cls._valid_date(basis.get("as_of_date"))
        cutoff = cls._valid_date(basis.get("cutoff_date"))
        revision = basis.get("revision")
        if (as_of is None or cutoff is None or cutoff > as_of
                or not isinstance(revision, str)
                or not revision.strip() or len(revision) > 128):
            return None, "FIFO_PLANNING_BASIS_PROVENANCE_INVALID"
        raw_layers = basis.get("layers")
        if not isinstance(raw_layers, list) or len(raw_layers) > cls.MAX_LAYERS:
            return None, "FIFO_PLANNING_LAYER_LIMIT_EXCEEDED"
        layers = []
        last_sequence = 0
        for raw in raw_layers:
            if not isinstance(raw, dict) or set(raw) != {
                "sequence", "kind", "quantity", "unit_cost_rub", "effective_date",
            }:
                return None, "FIFO_PLANNING_LAYER_INVALID"
            sequence = raw.get("sequence")
            quantity = raw.get("quantity")
            unit_cost = cls._decimal(raw.get("unit_cost_rub"))
            effective_date = cls._valid_date(raw.get("effective_date"))
            kind = raw.get("kind")
            if (type(sequence) is not int or sequence <= last_sequence
                    or type(quantity) is not int or not 1 <= quantity <= cls.MAX_QUANTITY
                    or unit_cost is None or unit_cost < 0 or unit_cost > cls.MAX_COST
                    or effective_date is None
                    or kind not in {"FINITE_LAYER", "RECONCILED_RATE"}):
                return None, "FIFO_PLANNING_LAYER_INVALID"
            if effective_date > as_of:
                return None, "FIFO_PLANNING_FUTURE_LAYER"
            layers.append({
                "sequence": sequence, "kind": kind, "quantity": quantity,
                "unit_cost": unit_cost.quantize(cls.CENT, rounding=ROUND_HALF_UP),
                "effective_date": effective_date,
            })
            last_sequence = sequence

        total_finite = sum(item["quantity"] for item in layers)
        if total_finite > 1_000_000:
            return None, "FIFO_PLANNING_STREAM_QUANTITY_LIMIT_EXCEEDED"

        raw_open = basis.get("open_rate")
        open_rate = None
        if raw_open is not None:
            if not isinstance(raw_open, dict) or set(raw_open) != {"unit_cost_rub", "effective_date"}:
                return None, "FIFO_PLANNING_OPEN_RATE_INVALID"
            unit_cost = cls._decimal(raw_open.get("unit_cost_rub"))
            effective_date = cls._valid_date(raw_open.get("effective_date"))
            if (unit_cost is None or unit_cost < 0 or unit_cost > cls.MAX_COST
                    or effective_date is None
                    or effective_date > as_of):
                return None, "FIFO_PLANNING_OPEN_RATE_INVALID"
            if layers and effective_date <= layers[-1]["effective_date"]:
                return None, "FIFO_PLANNING_OPEN_RATE_ORDER_AMBIGUOUS"
            open_rate = {
                "unit_cost": unit_cost.quantize(cls.CENT, rounding=ROUND_HALF_UP),
                "effective_date": effective_date,
            }
        return {
            "as_of_date": as_of,
            "cutoff_date": cutoff,
            "revision": revision,
            "layers": layers,
            "open_rate": open_rate,
        }, None

    @classmethod
    def _complete(cls, quantity, lines, open_rate, basis):
        total = sum(
            (Decimal(line["total_cost_rub"]) for line in lines), Decimal("0.00"),
        ).quantize(cls.CENT, rounding=ROUND_HALF_UP)
        average = (
            (total / quantity).quantize(cls.CENT, rounding=ROUND_HALF_UP)
            if quantity else None
        )
        normalized = basis if isinstance(basis, dict) and "revision" in basis else None
        return {
            "status": "COMPLETE",
            "reason_code": None,
            "quantity": quantity,
            "allocated_quantity": quantity,
            "total_cost_rub": cls._money(total),
            "known_cost_rub": cls._money(total),
            "average_cost_rub": cls._money(average) if average is not None else None,
            "lines": lines,
            **(cls._provenance(normalized) if normalized is not None else {
                "source_revision": None, "as_of_date": None, "cutoff_date": None,
                "model_only": True, "factual_period_profit_eligible": False,
            }),
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _provenance(basis):
        if not isinstance(basis, dict):
            return {
                "source_revision": None, "as_of_date": None, "cutoff_date": None,
                "model_only": True, "factual_period_profit_eligible": False,
            }
        return {
            "source_revision": basis.get("revision"),
            "as_of_date": basis.get("as_of_date"),
            "cutoff_date": basis.get("cutoff_date"),
            "model_only": True,
            "factual_period_profit_eligible": False,
        }

    @classmethod
    def _result(cls, status, reason, quantity):
        return {
            "status": status,
            "reason_code": reason,
            "quantity": quantity,
            "allocated_quantity": 0,
            "total_cost_rub": None,
            "known_cost_rub": "0.00",
            "average_cost_rub": None,
            "lines": [],
            "source_revision": None,
            "as_of_date": None,
            "cutoff_date": None,
            "model_only": True,
            "factual_period_profit_eligible": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _money(cls, value):
        return format(Decimal(value).quantize(cls.CENT, rounding=ROUND_HALF_UP), ".2f")

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _valid_date(value):
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            from datetime import date
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
