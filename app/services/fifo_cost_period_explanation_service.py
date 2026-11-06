"""Build a bounded, redacted FIFO layer explanation for a Period Profit read."""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation


class FifoCostPeriodExplanationService:
    """Project validated allocation details without changing canonical COGS."""

    MAX_LAYER_ROWS = 100_000
    MAX_CORRECTIONS = 200
    PROVENANCE = {
        "OWNER_CONFIRMED", "OZON_CONFIRMED_FIELD", "DOCUMENT_RECONCILED",
    }
    SOURCE_METHODS = {
        "OWNER_CONFIRMED_FIFO_CUTOFF",
        "OWNER_CONFIRMED_NEW_COST_RATE",
        "OWNER_CONFIRMED_TEST_RECEIPT",
        "OZON_REALIZATION_REPORT",
    }
    SOURCE_STATUSES = {"COMPLETE", "OWNER_CONFIRMED"}
    BASIS_REF = re.compile(r"^fifo-basis-[0-9a-f]{20}$")
    CORRECTION_PERIOD = re.compile(r"^\d{4}-\d{2}$")

    def build(
        self, *, allocation_result, repository, store_id, product, sku,
        date_from, date_to, units, product_cost,
    ):
        layers, layer_status = self._layers(
            allocation_result, units=units, product_cost=product_cost,
        )
        corrections = self._corrections(
            repository=repository,
            store_id=store_id,
            product=product,
            sku=sku,
            date_from=date_from,
            date_to=date_to,
            stream_revision=allocation_result.get("stream_revision"),
            allocation_revision=allocation_result.get("allocation_revision"),
        )
        return {
            "cost_mode": "FIFO",
            "status": layer_status,
            "reason_code": None if layer_status == "CONFIRMED" else "FIFO_LAYER_EXPLANATION_INCOMPLETE",
            "cutoff_date": self._date_or_none(allocation_result.get("cutoff_date")),
            "stream_revision": self._revision(allocation_result.get("stream_revision"), positive=True),
            "allocation_revision": self._revision(allocation_result.get("allocation_revision")),
            "units_sold": units,
            "product_cost_rub": format(product_cost.quantize(Decimal("0.01")), ".2f"),
            "layers": layers,
            "corrections": corrections,
        }

    def _layers(self, allocation, *, units, product_cost):
        raw = allocation.get("layers")
        if not isinstance(raw, list) or len(raw) > self.MAX_LAYER_ROWS:
            return [], "UNKNOWN"
        layers = []
        total_units = 0
        total_cost = Decimal("0.00")
        complete = allocation.get("layer_breakdown_complete") is True
        for row in raw:
            if not isinstance(row, dict):
                complete = False
                continue
            reference = row.get("basis_ref")
            quantity = row.get("quantity")
            sequence = row.get("sequence")
            kind = row.get("basis_kind")
            effective_date = self._date_or_none(row.get("effective_date"))
            unit_cost = self._money(row.get("unit_cost_rub"))
            amount = self._money(row.get("total_cogs_rub"))
            if (
                not isinstance(reference, str) or not self.BASIS_REF.fullmatch(reference)
                or type(quantity) is not int or quantity < 1
                or type(sequence) is not int or sequence < 1
                or kind not in {"LAYER", "RATE"}
                or effective_date is None
                or unit_cost is None or amount is None
                or (unit_cost * quantity).quantize(Decimal("0.01")) != amount
            ):
                complete = False
                continue
            provenance = row.get("provenance")
            method = row.get("source_method")
            source_status = row.get("source_status")
            coverage = row.get("coverage_status")
            provenance_known = provenance in self.PROVENANCE
            source_known = (
                provenance_known
                and method in self.SOURCE_METHODS
                and source_status in self.SOURCE_STATUSES
                and coverage in {"COMPLETE", "OWNER_CONFIRMED"}
            )
            if not source_known:
                complete = False
            layers.append({
                "basis_ref": reference,
                "basis_kind": "FIFO_LAYER" if kind == "LAYER" else "OPEN_RATE",
                "sequence": sequence,
                "effective_date": effective_date,
                "confirmation": provenance if provenance_known else "UNKNOWN",
                "source_method": method if method in self.SOURCE_METHODS else "UNKNOWN",
                "source_status": source_status if source_status in self.SOURCE_STATUSES else "UNKNOWN",
                "coverage_status": coverage if coverage in {"COMPLETE", "OWNER_CONFIRMED"} else "UNKNOWN",
                "quantity": quantity,
                "unit_cost_rub": format(unit_cost, ".2f"),
                "total_cogs_rub": format(amount, ".2f"),
            })
            total_units += quantity
            total_cost += amount
        total_cost = total_cost.quantize(Decimal("0.01"))
        if total_units != units or total_cost != product_cost.quantize(Decimal("0.01")):
            complete = False
        layers.sort(key=lambda item: (
            item["effective_date"], item["sequence"], item["basis_ref"],
        ))
        return layers, "CONFIRMED" if complete else "PARTIAL"

    def _corrections(
        self, *, repository, store_id, product, sku, date_from, date_to,
        stream_revision, allocation_revision,
    ):
        reader = getattr(repository, "read_late_entry_corrections", None)
        if not callable(reader):
            return self._correction_result("UNAVAILABLE", "FIFO_CORRECTION_HISTORY_UNAVAILABLE")
        try:
            history = reader(
                store_id=store_id,
                product_id=self._text(product.get("product_id")),
                offer_id=self._text(product.get("offer_id")),
                sku=sku,
            )
        except Exception:
            history = None
        if not isinstance(history, dict) or history.get("error") is not False:
            return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_UNAVAILABLE")
        corrections = history.get("corrections")
        if not isinstance(corrections, list) or len(corrections) > self.MAX_CORRECTIONS:
            return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
        start = self._date_or_none(date_from)
        end = self._date_or_none(date_to)
        if start is None or end is None or start > end:
            return self._correction_result("UNKNOWN", "FIFO_CORRECTION_PERIOD_INVALID")

        projected = []
        not_aligned = False
        for correction in corrections:
            if not isinstance(correction, dict):
                return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
            revision = correction.get("stream_revision")
            previous_allocation = correction.get("allocation_revision")
            impact = correction.get("impact")
            correction_ref = self._opaque_ref(correction.get("correction_id"))
            if (
                type(revision) is not int or revision < 1
                or type(previous_allocation) is not int or previous_allocation < 0
                or not isinstance(impact, dict)
                or not isinstance(impact.get("periods"), list)
                or correction_ref is None
            ):
                return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
            if type(stream_revision) is int and revision > stream_revision:
                continue
            for item in impact["periods"]:
                if not isinstance(item, dict):
                    return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
                period = item.get("period")
                if not isinstance(period, str) or not self.CORRECTION_PERIOD.fullmatch(period):
                    return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
                month_start, month_end = self._month_bounds(period)
                if month_start is None:
                    return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
                if month_end < start or month_start > end:
                    continue
                if month_start < start or month_end > end:
                    not_aligned = True
                    continue
                amounts = {
                    key: self._money(
                        item.get(key),
                        nonnegative=key not in {
                            "delta_cogs_rub", "delta_tax_rub", "delta_profit_rub",
                            "before_profit_rub", "after_profit_rub",
                        },
                    )
                    for key in (
                        "before_sku_cogs_rub", "after_sku_cogs_rub", "delta_cogs_rub",
                        "before_total_cogs_rub", "after_total_cogs_rub",
                        "before_tax_rub", "after_tax_rub", "delta_tax_rub",
                        "before_profit_rub", "after_profit_rub", "delta_profit_rub",
                    )
                }
                if any(amount is None for amount in amounts.values()):
                    return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
                if (
                    amounts["after_sku_cogs_rub"] - amounts["before_sku_cogs_rub"] != amounts["delta_cogs_rub"]
                    or amounts["after_total_cogs_rub"] - amounts["before_total_cogs_rub"] != amounts["delta_cogs_rub"]
                    or amounts["after_tax_rub"] - amounts["before_tax_rub"] != amounts["delta_tax_rub"]
                    or amounts["after_profit_rub"] - amounts["before_profit_rub"] != amounts["delta_profit_rub"]
                ):
                    return self._correction_result("UNKNOWN", "FIFO_CORRECTION_HISTORY_INVALID")
                projected.append({
                    "correction_ref": correction_ref,
                    "correction_revision": revision,
                    "previous_allocation_revision": previous_allocation,
                    "period": period,
                    "status": (
                        "CURRENT_RESULT"
                        if revision == stream_revision
                        and allocation_revision == previous_allocation + 1
                        else "HISTORICAL_SNAPSHOT"
                    ),
                    "before_sku_cogs_rub": format(amounts["before_sku_cogs_rub"], ".2f"),
                    "after_sku_cogs_rub": format(amounts["after_sku_cogs_rub"], ".2f"),
                    "delta_cogs_rub": format(amounts["delta_cogs_rub"], ".2f"),
                    "before_total_cogs_rub": format(amounts["before_total_cogs_rub"], ".2f"),
                    "after_total_cogs_rub": format(amounts["after_total_cogs_rub"], ".2f"),
                    "before_tax_rub": format(amounts["before_tax_rub"], ".2f"),
                    "after_tax_rub": format(amounts["after_tax_rub"], ".2f"),
                    "delta_tax_rub": format(amounts["delta_tax_rub"], ".2f"),
                    "before_profit_rub": format(amounts["before_profit_rub"], ".2f"),
                    "after_profit_rub": format(amounts["after_profit_rub"], ".2f"),
                    "delta_profit_rub": format(amounts["delta_profit_rub"], ".2f"),
                })
        projected.sort(key=lambda item: (item["period"], item["correction_revision"]))
        if projected:
            return {"status": "AVAILABLE", "reason_code": None, "revisions": projected}
        if not_aligned:
            return self._correction_result("NOT_ALIGNED", "FIFO_CORRECTION_PERIOD_NOT_ALIGNED")
        return self._correction_result("NO_CORRECTION", None)

    @staticmethod
    def _correction_result(status, reason):
        return {"status": status, "reason_code": reason, "revisions": []}

    @staticmethod
    def _opaque_ref(value):
        if not isinstance(value, str) or not value or len(value) > 160:
            return None
        digest = hashlib.sha256(("fifo-correction-v1:" + value).encode("utf-8")).hexdigest()[:20]
        return "fifo-correction-" + digest

    @staticmethod
    def _revision(value, positive=False):
        return value if type(value) is int and (value > 0 if positive else value >= 0) else None

    @staticmethod
    def _text(value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _date_or_none(value):
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _month_bounds(period):
        try:
            year, month = (int(part) for part in period.split("-"))
            return (
                date(year, month, 1).isoformat(),
                date(year, month, calendar.monthrange(year, month)[1]).isoformat(),
            )
        except (TypeError, ValueError):
            return None, None

    @staticmethod
    def _money(value, *, nonnegative=True):
        if value is None or isinstance(value, bool):
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return None
        if not amount.is_finite() or nonnegative and amount < 0:
            return None
        normalized = amount.quantize(Decimal("0.01"))
        return normalized if normalized == amount else None
