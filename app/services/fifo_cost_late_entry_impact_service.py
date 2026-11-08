"""Calculate an immutable before/after profit impact for a late FIFO rate."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from services.tax_service import TaxService


class FifoCostLateEntryImpactService:
    """Join a complete FIFO replay with frozen period summaries and tax policy.

    The financial summaries are supplied by the caller so this service stays
    read-only and does not introduce an unbounded Ozon request loop.
    """

    _PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    _DIGEST = re.compile(r"^[0-9a-f]{64}$")
    _MODES = {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}

    def __init__(self, tax_service=None):
        self.tax_service = tax_service or TaxService()

    def preview(self, *, reconstruction, period_summaries, tax_policy_result):
        if not isinstance(reconstruction, dict) or reconstruction.get("error") is not False:
            return self._blocked("FIFO_RECONSTRUCTION_UNAVAILABLE")
        if reconstruction.get("code") != "FIFO_LATE_ENTRY_RECONSTRUCTION_READY":
            return self._blocked("FIFO_RECONSTRUCTION_UNAVAILABLE")
        if reconstruction.get("before_complete") is not True:
            return self._blocked(
                reconstruction.get("before_reason_code") or "FIFO_BASELINE_UNAVAILABLE",
            )
        if type(reconstruction.get("related_return_count")) is not int:
            return self._blocked("FIFO_RETURN_EVIDENCE_INVALID")
        if not 0 <= reconstruction["related_return_count"] <= 100_000:
            return self._blocked("FIFO_RETURN_EVIDENCE_INVALID")
        if type(reconstruction.get("non_sale_outflow_count")) is not int:
            return self._blocked("FIFO_RECONSTRUCTION_RESULT_INVALID")
        if not 0 <= reconstruction["non_sale_outflow_count"] <= 100_000:
            return self._blocked("FIFO_RECONSTRUCTION_RESULT_INVALID")
        if reconstruction.get("return_cogs_authorization_changed") is not False:
            return self._blocked("FIFO_RETURN_COGS_AUTHORIZATION_CONFLICT")
        outflows = reconstruction.get("candidate_outflows")
        outflow_value = self._money(
            reconstruction.get("candidate_non_sale_outflow_value_rub"),
        )
        if not isinstance(outflows, list) or len(outflows) != reconstruction["non_sale_outflow_count"]:
            return self._blocked("FIFO_NON_SALE_MOVEMENT_EVIDENCE_INVALID")
        if outflow_value is None:
            return self._blocked("FIFO_NON_SALE_MOVEMENT_EVIDENCE_INVALID")
        try:
            outflow_sum = sum(
                (self._money(row.get("estimated_value_rub")) for row in outflows),
                Decimal("0.00"),
            )
        except (TypeError, AttributeError):
            return self._blocked("FIFO_NON_SALE_MOVEMENT_EVIDENCE_INVALID")
        if any(
            not isinstance(row, dict)
            or self._money(row.get("estimated_value_rub")) is None
            or type(row.get("quantity")) is not int
            or row["quantity"] <= 0
            for row in outflows
        ) or outflow_sum != outflow_value:
            return self._blocked("FIFO_NON_SALE_MOVEMENT_EVIDENCE_INVALID")

        periods = self._period_cogs(reconstruction)
        if isinstance(periods, str):
            return self._blocked(periods)
        before_total = sum(
            (row["before_cogs"] for row in periods.values()), Decimal("0.00"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        after_total = sum(
            (row["after_cogs"] for row in periods.values()), Decimal("0.00"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if (
            self._money(reconstruction.get("before_total_cogs_rub")) != before_total
            or self._money(reconstruction.get("candidate_total_cogs_rub")) != after_total
        ):
            return self._blocked("FIFO_RECONSTRUCTION_TOTAL_MISMATCH")
        summaries = self._normalize_summaries(period_summaries, set(periods))
        if isinstance(summaries, str):
            return self._blocked(summaries)
        policy = self._normalize_policy(tax_policy_result)
        if isinstance(policy, str):
            return self._blocked(policy)

        result_periods = []
        for period in sorted(periods):
            summary = summaries[period]
            replay = periods[period]
            before_cost = self._money(summary["current_sku_product_cost"])
            before_replay_cost = replay["before_cogs"]
            after_cost = replay["after_cogs"]
            total_cost = self._money(summary["current_total_product_cost"])
            if before_cost is None or total_cost is None:
                return self._blocked("FIFO_PERIOD_SUMMARY_INVALID")
            if before_cost != before_replay_cost:
                return self._blocked("FIFO_PERIOD_COGS_BASELINE_MISMATCH")
            other_cost = total_cost - before_cost
            if other_cost < Decimal("-0.01"):
                return self._blocked("FIFO_PERIOD_COST_RECONCILIATION_CONFLICT")
            other_cost = max(Decimal("0.00"), other_cost)
            before = self._profit(summary, total_cost, policy)
            after_total_cost = (other_cost + after_cost).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )
            after = self._profit(summary, after_total_cost, policy)
            if before is None or after is None:
                return self._blocked("FIFO_TAX_IMPACT_UNAVAILABLE")
            result_periods.append({
                "period": period,
                "start_date": replay["start_date"],
                "end_date": replay["end_date"],
                "units": replay["units"],
                "before_units_by_basis": replay["before_units_by_basis"],
                "after_units_by_basis": replay["after_units_by_basis"],
                "before_cogs_by_basis_rub": replay["before_cogs_by_basis"],
                "after_cogs_by_basis_rub": replay["after_cogs_by_basis"],
                "completeness": "COMPLETE",
                "before_sku_cogs_rub": format(before_cost, ".2f"),
                "after_sku_cogs_rub": format(after_cost, ".2f"),
                "delta_cogs_rub": format(after_cost - before_cost, ".2f"),
                "before_total_cogs_rub": format(total_cost, ".2f"),
                "after_total_cogs_rub": format(after_total_cost, ".2f"),
                "before_tax_rub": before["tax"],
                "after_tax_rub": after["tax"],
                "delta_tax_rub": format(
                    Decimal(after["tax"]) - Decimal(before["tax"]), ".2f",
                ),
                "before_profit_rub": before["profit"],
                "after_profit_rub": after["profit"],
                "delta_profit_rub": format(
                    Decimal(after["profit"]) - Decimal(before["profit"]), ".2f",
                ),
                "source_fingerprint": summary["source_fingerprint"],
            })

        payload = {
            "draft_id": reconstruction.get("draft_id"),
            "stream_revision": reconstruction.get("stream_revision"),
            "allocation_revision": reconstruction.get("allocation_revision"),
            "source_set_fingerprint": reconstruction.get("source_set_fingerprint"),
            "reconstruction_fingerprint": reconstruction.get("preview_fingerprint"),
            "tax_policy_fingerprint": policy["fingerprint"],
            "periods": result_periods,
            "related_return_count": reconstruction["related_return_count"],
            "non_sale_outflow_count": reconstruction["non_sale_outflow_count"],
            "non_sale_outflow_estimated_value_rub": format(outflow_value, ".2f"),
            "return_cogs_authorization_changed": False,
            "non_sale_outflows_included_in_sales_cogs": False,
            "complete": True,
            "read_only": True,
        }
        payload["preview_fingerprint"] = self._fingerprint(payload)
        payload["code"] = "FIFO_LATE_ENTRY_IMPACT_READY"
        payload["error"] = False
        return payload

    @classmethod
    def _period_cogs(cls, reconstruction):
        dates = reconstruction.get("sale_effective_dates")
        before = reconstruction.get("before_allocations")
        after = reconstruction.get("candidate_allocations")
        if not isinstance(dates, dict) or not isinstance(before, list) or not isinstance(after, list):
            return "FIFO_RECONSTRUCTION_RESULT_INVALID"
        periods = {}
        event_rows = {"before": {}, "after": {}}
        for name, rows in (("before_cogs", before), ("after_cogs", after)):
            seen = set()
            for allocation in rows:
                if not isinstance(allocation, dict):
                    return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                event_id = allocation.get("event_id")
                date_value = dates.get(event_id)
                if not isinstance(event_id, str) or event_id in seen or not isinstance(date_value, str):
                    return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                seen.add(event_id)
                if len(date_value) < 7 or not cls._PERIOD.fullmatch(date_value[:7]):
                    return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                quantity = allocation.get("quantity")
                if type(quantity) is not int or quantity <= 0:
                    return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                amount = cls._money(allocation.get("total_cost_rub"))
                lines = allocation.get("lines")
                if amount is None or not isinstance(lines, list) or not lines:
                    return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                period = date_value[:7]
                state = periods.setdefault(period, {
                    "before_units": 0, "after_units": 0,
                    "before_cogs": Decimal("0.00"), "after_cogs": Decimal("0.00"),
                    "dates": [], "before_units_by_basis": {},
                    "after_units_by_basis": {},
                    "before_cogs_by_basis": {}, "after_cogs_by_basis": {},
                })
                side = "before" if name == "before_cogs" else "after"
                units_by_basis = state[f"{side}_units_by_basis"]
                cogs_by_basis = state[f"{side}_cogs_by_basis"]
                line_units = 0
                line_total = Decimal("0.00")
                for line in lines:
                    if not isinstance(line, dict):
                        return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                    layer_id = line.get("layer_id")
                    rate_id = line.get("rate_change_id")
                    line_quantity = line.get("quantity")
                    unit_cost = cls._money(line.get("unit_cost_rub"))
                    line_amount = cls._money(line.get("total_cost_rub"))
                    if (
                        (layer_id is None) == (rate_id is None)
                        or type(line_quantity) is not int or line_quantity <= 0
                        or unit_cost is None or line_amount is None
                        or (unit_cost * line_quantity).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP,
                        ) != line_amount
                    ):
                        return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                    basis_kind, basis_id = (
                        ("layer", layer_id) if isinstance(layer_id, str)
                        else ("rate", rate_id)
                    )
                    if not isinstance(basis_id, str) or not basis_id or len(basis_id) > 160:
                        return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                    basis_key = f"{basis_kind}:{basis_id}"
                    units_by_basis[basis_key] = units_by_basis.get(basis_key, 0) + line_quantity
                    prior_basis_cogs = Decimal(cogs_by_basis.get(basis_key, "0.00"))
                    cogs_by_basis[basis_key] = format(
                        prior_basis_cogs + line_amount, ".2f",
                    )
                    line_units += line_quantity
                    line_total += line_amount
                if line_units != quantity or line_total != amount:
                    return "FIFO_RECONSTRUCTION_RESULT_INVALID"
                state["before_units" if side == "before" else "after_units"] += quantity
                state[name] += amount
                state["dates"].append(date_value[:10])
                event_rows[side][event_id] = {
                    "period": period, "quantity": quantity, "total_cost": amount,
                }
        if set(event_rows["before"]) != set(event_rows["after"]):
            return "FIFO_ALLOCATION_EVENT_COVERAGE_MISMATCH"
        for event_id, before_row in event_rows["before"].items():
            after_row = event_rows["after"][event_id]
            if (before_row["period"], before_row["quantity"]) != (
                after_row["period"], after_row["quantity"],
            ):
                return "FIFO_ALLOCATION_QUANTITY_MISMATCH"
        for state in periods.values():
            if state["before_units"] != state["after_units"]:
                return "FIFO_ALLOCATION_QUANTITY_MISMATCH"
            state["units"] = state.pop("after_units")
            state.pop("before_units")
            dates = state.pop("dates")
            state["start_date"] = min(dates)
            state["end_date"] = max(dates)
        if not periods:
            return "FIFO_IMPACT_PERIODS_EMPTY"
        return periods

    @classmethod
    def _normalize_summaries(cls, values, expected_periods):
        if not isinstance(values, list) or len(values) != len(expected_periods):
            return "FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE"
        result = {}
        for row in values:
            if not isinstance(row, dict) or row.get("complete") is not True:
                return "FIFO_PERIOD_SUMMARY_UNAVAILABLE"
            period = row.get("period")
            fingerprint = row.get("source_fingerprint")
            if (
                not isinstance(period, str) or not cls._PERIOD.fullmatch(period)
                or period not in expected_periods or period in result
                or not isinstance(fingerprint, str) or not cls._DIGEST.fullmatch(fingerprint)
            ):
                return "FIFO_PERIOD_SUMMARY_INVALID"
            normalized = {"period": period, "complete": True, "source_fingerprint": fingerprint}
            for key in (
                "revenue", "discount_points", "net_accrual",
                "current_total_product_cost", "current_sku_product_cost",
            ):
                amount = cls._money(
                    row.get(key), nonnegative=key != "net_accrual",
                )
                if amount is None:
                    return "FIFO_PERIOD_SUMMARY_INVALID"
                normalized[key] = amount
            result[period] = normalized
        return result if set(result) == expected_periods else "FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE"

    @classmethod
    def _normalize_policy(cls, result):
        if not isinstance(result, dict) or result.get("error") is not False or result.get("configured") is not True:
            return "FIFO_TAX_POLICY_UNAVAILABLE"
        policy = result.get("policy")
        if not isinstance(policy, dict):
            return "FIFO_TAX_POLICY_UNAVAILABLE"
        mode = str(policy.get("mode") or "").upper()
        if mode not in cls._MODES:
            return "FIFO_TAX_MODE_UNSUPPORTED"
        rate = policy.get("tax_rate")
        minimum = policy.get("minimum_tax_rate", 1.0)
        if mode == "NONE":
            rate = 0
            minimum = 1
        rate_value = cls._number(rate)
        minimum_value = cls._number(minimum)
        if rate_value is None or minimum_value is None or not 0 <= rate_value <= 100 or not 0 <= minimum_value <= 100:
            return "FIFO_TAX_POLICY_INVALID"
        normalized = {"mode": mode, "tax_rate": rate_value, "minimum_tax_rate": minimum_value}
        normalized["fingerprint"] = cls._fingerprint(normalized)
        return normalized

    def _profit(self, summary, product_cost, policy):
        revenue = summary["revenue"]
        discount_points = summary["discount_points"]
        net_accrual = summary["net_accrual"]
        gross_profit = net_accrual - product_cost
        try:
            result = self.tax_service.calculate(
                policy["mode"], float(revenue), float(gross_profit),
                tax_rate=policy["tax_rate"],
                minimum_tax_rate=policy["minimum_tax_rate"],
                discount_points=float(discount_points),
            )
        except Exception:
            return None
        if not isinstance(result, dict) or result.get("error") is not False or result.get("configured") is not True:
            return None
        tax = self._money(result.get("tax_amount"))
        if tax is None:
            return None
        return {"tax": format(tax, ".2f"), "profit": format(gross_profit - tax, ".2f")}

    @staticmethod
    def _number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if number == number and abs(number) != float("inf") else None

    @staticmethod
    def _money(value, *, nonnegative=True):
        if value is None or isinstance(value, bool):
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not amount.is_finite() or (nonnegative and amount < 0):
            return None
        quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if quantized != amount:
            return None
        return quantized

    @staticmethod
    def _fingerprint(value):
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()

    @staticmethod
    def _blocked(reason):
        return {
            "error": False,
            "code": "FIFO_LATE_ENTRY_IMPACT_BLOCKED",
            "complete": False,
            "reason_code": str(reason or "FIFO_IMPACT_UNAVAILABLE"),
            "read_only": True,
        }
