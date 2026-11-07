"""Version and validate exact model-only cost allocations saved with sales mixes."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from services.fifo_planning_basis_compatibility_service import (
    FifoPlanningBasisCompatibilityService,
)


class PlanningSalesMixCostSnapshotAdapter:
    SCHEMA_VERSION = 1
    MAX_ROWS = 10
    MAX_LINES = 20
    _CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    _CENT = Decimal("0.01")
    _MAX_MONEY = Decimal("999999999999.99")
    _STATUSES = frozenset({"COMPLETE", "PARTIAL", "UNAVAILABLE"})
    _ROW_STATUSES = frozenset({
        "COMPLETE", "PARTIAL", "UNAVAILABLE", "MANUAL_SCENARIO_OVERRIDE",
    })
    _METHODS = frozenset({
        "FIFO_CURRENT_SNAPSHOT", "MANUAL_SCENARIO_COST",
        "LEGACY_EFFECTIVE_DATED", "UNKNOWN",
    })

    def __init__(self, fifo_basis=None):
        self.fifo_basis = fifo_basis or FifoPlanningBasisCompatibilityService()

    def build(self, items, sales_mix, projection):
        if (not isinstance(items, list) or not isinstance(sales_mix, dict)
                or not isinstance(projection, dict) or projection.get("error") is not False
                or len(items) > self.MAX_ROWS):
            return None
        results = {}
        for key in ("rows", "excluded_rows"):
            values = projection.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                row_id = item.get("row_id")
                if isinstance(row_id, str) and row_id and row_id not in results:
                    results[row_id] = item
        quantities = sales_mix.get("quantities")
        if not isinstance(quantities, dict):
            return None
        rows = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return None
            row_id = str(item.get("row_id") or item["identity"].get("sku") or "")
            raw = results.get(row_id, {})
            quantity = quantities.get(row_id)
            allocation = raw.get("cost_allocation")
            allocation = allocation if isinstance(allocation, dict) else None
            classified = self.fifo_basis.describe_item(item)
            if allocation and allocation.get("status") == "MANUAL_SCENARIO_OVERRIDE":
                method = "MANUAL_SCENARIO_COST"
            elif classified["status"] in {"FIFO_AVAILABLE", "UNKNOWN"}:
                method = "FIFO_CURRENT_SNAPSHOT"
            elif classified["status"] == "MANUAL":
                method = "MANUAL_SCENARIO_COST"
            else:
                method = "LEGACY_EFFECTIVE_DATED"

            source_cost = self._cost_source(item)
            basis = source_cost.get("quantity_allocation_basis")
            source_revision = None
            if isinstance(allocation, dict):
                source_revision = allocation.get("source_revision") or allocation.get(
                    "reference_fifo_revision",
                )
            if source_revision is None and isinstance(basis, dict):
                source_revision = basis.get("revision")
            if source_revision is None:
                source_revision = source_cost.get("revision")

            components = raw.get("components")
            components = components if isinstance(components, dict) else {}
            if quantity == 0:
                row_status = (
                    "MANUAL_SCENARIO_OVERRIDE"
                    if method == "MANUAL_SCENARIO_COST" else "COMPLETE"
                )
                total_cost = known_cost = "0.00"
                allocated = 0
                lines = []
                reason_code = None
            else:
                if allocation is not None:
                    status = allocation.get("status")
                    if status == "COMPLETE":
                        row_status = "COMPLETE"
                    elif status == "PARTIAL":
                        row_status = "PARTIAL"
                    elif status == "MANUAL_SCENARIO_OVERRIDE":
                        row_status = "MANUAL_SCENARIO_OVERRIDE"
                    else:
                        row_status = "UNAVAILABLE"
                elif (quantity is not None and method == "LEGACY_EFFECTIVE_DATED"
                      and components.get("cost_of_goods") is not None):
                    row_status = "COMPLETE"
                else:
                    row_status = "UNAVAILABLE"
                total_cost = (
                    allocation.get("total_cost_rub") if allocation is not None
                    else components.get("cost_of_goods")
                )
                known_cost = (
                    allocation.get("known_cost_rub") if allocation is not None
                    else total_cost
                )
                if row_status in {"PARTIAL", "UNAVAILABLE"}:
                    total_cost = None
                if row_status == "UNAVAILABLE":
                    known_cost = None
                allocated = (
                    allocation.get("allocated_quantity") if allocation is not None
                    else quantity if row_status in {"COMPLETE", "MANUAL_SCENARIO_OVERRIDE"}
                    else 0
                )
                if type(allocated) is not int:
                    allocated = 0
                if method == "FIFO_CURRENT_SNAPSHOT":
                    lines = allocation.get("lines", []) if allocation else []
                else:
                    lines = []
                reason_code = (
                    allocation.get("reason_code") if allocation else
                    raw.get("cost_reason") or (
                        "ROW_EXCLUDED_FROM_SALES_MIX" if row_status == "UNAVAILABLE" else None
                    )
                )
            rows.append({
                "row_id": row_id, "quantity": quantity, "status": row_status,
                "method": method,
                "basis_ref": self.fifo_basis.basis_reference(item),
                "source_revision": source_revision,
                "total_cost_rub": total_cost, "known_cost_rub": known_cost,
                "allocated_quantity": allocated,
                "average_cost_rub": allocation.get("average_cost_rub") if allocation else None,
                "reason_code": reason_code,
                "as_of_date": allocation.get("as_of_date") if allocation else (
                    basis.get("as_of_date") if isinstance(basis, dict) else source_cost.get("as_of_date")
                ),
                "cutoff_date": allocation.get("cutoff_date") if allocation else (
                    basis.get("cutoff_date") if isinstance(basis, dict) else source_cost.get("cutoff_date")
                ),
                "lines": lines,
            })
        rows.sort(key=lambda row: row["row_id"])
        complete_rows = all(row["status"] in {"COMPLETE", "MANUAL_SCENARIO_OVERRIDE"}
                            for row in rows)
        status = (
            "COMPLETE" if complete_rows else
            "UNAVAILABLE" if rows and all(row["status"] == "UNAVAILABLE" for row in rows)
            else "PARTIAL"
        )
        candidate = {
            "schema_version": self.SCHEMA_VERSION,
            "period_label": sales_mix.get("period_label"),
            "quantities": dict(quantities), "status": status,
            "model_only": True, "factual_period_profit_eligible": False,
            "rows": rows,
        }
        return self.normalize(candidate, items, sales_mix)

    def normalize(self, value, items, sales_mix):
        if (not isinstance(value, dict) or set(value) != {
                "schema_version", "period_label", "quantities", "status",
                "model_only", "factual_period_profit_eligible", "rows",
        } or type(value.get("schema_version")) is not int
                or value["schema_version"] != self.SCHEMA_VERSION
                or value.get("status") not in self._STATUSES
                or value.get("model_only") is not True
                or value.get("factual_period_profit_eligible") is not False
                or not isinstance(sales_mix, dict)
                or value.get("period_label") != sales_mix.get("period_label")
                or value.get("quantities") != sales_mix.get("quantities")
                or not isinstance(value.get("rows"), list)
                or not isinstance(items, list) or not 1 <= len(items) <= self.MAX_ROWS
                or len(value["rows"]) != len(items)):
            return None
        item_by_id = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return None
            row_id = str(item.get("row_id") or item["identity"].get("sku") or "")
            if not row_id or row_id in item_by_id:
                return None
            item_by_id[row_id] = item
        normalized = []
        seen = set()
        for row in value["rows"]:
            required = {
                "row_id", "quantity", "status", "method", "basis_ref",
                "source_revision",
                "total_cost_rub", "known_cost_rub", "allocated_quantity",
                "average_cost_rub", "reason_code", "as_of_date", "cutoff_date", "lines",
            }
            if not isinstance(row, dict) or set(row) != required:
                return None
            row_id = row.get("row_id")
            if not isinstance(row_id, str) or row_id not in item_by_id or row_id in seen:
                return None
            seen.add(row_id)
            expected_quantity = sales_mix["quantities"].get(row_id)
            if row.get("quantity") != expected_quantity:
                return None
            if (row.get("status") not in self._ROW_STATUSES
                    or row.get("method") not in self._METHODS
                    or type(row.get("allocated_quantity")) is not int
                    or row["allocated_quantity"] < 0
                    or not isinstance(row.get("lines"), list)
                    or len(row["lines"]) > self.MAX_LINES):
                return None
            q = row["quantity"]
            allocated = row["allocated_quantity"]
            if q is not None and (type(q) is not int or not 0 <= q <= 100_000):
                return None
            if allocated > (q if q is not None else 0):
                return None
            total = self._money(row.get("total_cost_rub"), nullable=True)
            known = self._money(row.get("known_cost_rub"), nullable=True)
            average = self._money(row.get("average_cost_rub"), nullable=True)
            if any(result is False for result in (total, known, average)):
                return None
            reason = row.get("reason_code")
            if reason is not None and (not isinstance(reason, str) or self._CODE.fullmatch(reason) is None):
                return None
            source_revision = row.get("source_revision")
            if source_revision is not None and (
                not isinstance(source_revision, str) or not source_revision.strip()
                or len(source_revision) > 128
            ):
                return None
            basis_ref = row.get("basis_ref")
            item = item_by_id[row_id]
            expected_basis_ref = self.fifo_basis.basis_reference(item)
            if basis_ref != expected_basis_ref:
                return None
            if basis_ref is not None and (
                not isinstance(basis_ref, str) or re.fullmatch(r"[0-9a-f]{64}", basis_ref) is None
            ):
                return None
            dates = {}
            for key in ("as_of_date", "cutoff_date"):
                raw = row.get(key)
                if raw is not None:
                    if not isinstance(raw, str) or len(raw) > 40:
                        return None
                    try:
                        if "T" in raw:
                            from datetime import datetime
                            datetime.fromisoformat(raw.replace("Z", "+00:00"))
                        else:
                            date.fromisoformat(raw)
                    except (TypeError, ValueError):
                        return None
                dates[key] = raw
            method = row["method"]
            status = row["status"]
            source_cost = self._cost_source(item)
            source_basis = source_cost.get("quantity_allocation_basis")
            expected_revision = (
                source_basis.get("revision") if isinstance(source_basis, dict)
                else source_cost.get("revision")
            )
            if expected_revision is not None and source_revision != expected_revision:
                return None
            lines = []
            line_quantity = 0
            line_total = Decimal("0.00")
            for line in row["lines"]:
                clean = self._line(line)
                if clean is None:
                    return None
                line_quantity += clean["quantity"]
                line_total += Decimal(clean["total_cost_rub"])
                lines.append(clean)
            if method == "FIFO_CURRENT_SNAPSHOT":
                basis = source_basis
                if expected_revision is None:
                    return None
                if status in {"COMPLETE", "PARTIAL"}:
                    expected_allocation = self.fifo_basis.allocator.allocate(
                        quantity=q, basis=basis,
                    )
                    if (expected_allocation.get("status") != status
                            or expected_allocation.get("allocated_quantity") != allocated
                            or expected_allocation.get("total_cost_rub") != total
                            or expected_allocation.get("known_cost_rub") != known
                            or expected_allocation.get("average_cost_rub") != average
                            or expected_allocation.get("reason_code") != reason
                            or expected_allocation.get("lines") != lines):
                        return None
            elif lines:
                return None
            if status in {"COMPLETE", "MANUAL_SCENARIO_OVERRIDE"}:
                if (q is None or allocated != q or total is None or known != total
                        or reason is not None):
                    return None
                if method == "FIFO_CURRENT_SNAPSHOT" and (
                    line_quantity != allocated or line_total.quantize(self._CENT) != Decimal(total)
                ):
                    return None
                if status == "MANUAL_SCENARIO_OVERRIDE" and method != "MANUAL_SCENARIO_COST":
                    return None
            elif status == "PARTIAL":
                if (method != "FIFO_CURRENT_SNAPSHOT" or q is None or not 0 < allocated < q
                        or total is not None or known is None or reason is None
                        or line_quantity != allocated or line_total.quantize(self._CENT) != Decimal(known)):
                    return None
            else:
                if (total is not None or known is not None or allocated != 0 or lines
                        or reason is None):
                    return None
            normalized.append({
                "row_id": row_id, "quantity": q, "status": status,
                "method": method, "basis_ref": basis_ref,
                "source_revision": source_revision,
                "total_cost_rub": total, "known_cost_rub": known,
                "allocated_quantity": allocated, "average_cost_rub": average,
                "reason_code": reason, "as_of_date": dates["as_of_date"],
                "cutoff_date": dates["cutoff_date"], "lines": lines,
            })
        if seen != set(item_by_id) or normalized != sorted(normalized, key=lambda row: row["row_id"]):
            return None
        all_complete = all(row["status"] in {"COMPLETE", "MANUAL_SCENARIO_OVERRIDE"}
                           for row in normalized)
        expected_status = (
            "COMPLETE" if all_complete else
            "UNAVAILABLE" if normalized and all(row["status"] == "UNAVAILABLE" for row in normalized)
            else "PARTIAL"
        )
        if value["status"] != expected_status:
            return None
        return {
            "schema_version": self.SCHEMA_VERSION,
            "period_label": value["period_label"],
            "quantities": dict(value["quantities"]), "status": expected_status,
            "model_only": True, "factual_period_profit_eligible": False,
            "rows": normalized,
        }

    def has_fifo_basis(self, items):
        return any(
            self.fifo_basis.describe_item(item)["status"] in {"FIFO_AVAILABLE", "UNKNOWN"}
            for item in items if isinstance(item, dict)
        )

    @staticmethod
    def _cost_source(item):
        sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
        completeness = sources.get("completeness")
        completeness = completeness if isinstance(completeness, dict) else {}
        cost = completeness.get("cost")
        return cost if isinstance(cost, dict) else {}

    @classmethod
    def _money(cls, value, *, nullable=False):
        if value is None and nullable:
            return None
        if not isinstance(value, str) or len(value) > 32:
            return False
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            return False
        if (not amount.is_finite() or abs(amount) > cls._MAX_MONEY
                or amount.quantize(cls._CENT, rounding=ROUND_HALF_UP) != amount):
            return False
        return format(amount, ".2f")

    @classmethod
    def _line(cls, line):
        if not isinstance(line, dict) or set(line) != {
                "sequence", "kind", "effective_date", "quantity",
                "unit_cost_rub", "total_cost_rub",
        }:
            return None
        sequence = line.get("sequence")
        kind = line.get("kind")
        if (type(line.get("quantity")) is not int or line["quantity"] < 1
                or kind not in {"FINITE_LAYER", "RECONCILED_RATE", "OPEN_RATE"}
                or (kind == "OPEN_RATE" and sequence != "OPEN_RATE")
                or (kind != "OPEN_RATE" and (type(sequence) is not int or sequence < 1))):
            return None
        effective_date = line.get("effective_date")
        if not isinstance(effective_date, str):
            return None
        try:
            date.fromisoformat(effective_date)
        except ValueError:
            return None
        unit = cls._money(line.get("unit_cost_rub"))
        total = cls._money(line.get("total_cost_rub"))
        if unit is False or total is False:
            return None
        expected = (Decimal(unit) * line["quantity"]).quantize(cls._CENT, rounding=ROUND_HALF_UP)
        if expected != Decimal(total):
            return None
        return {
            "sequence": sequence, "kind": kind, "effective_date": effective_date,
            "quantity": line["quantity"], "unit_cost_rub": unit,
            "total_cost_rub": total,
        }
