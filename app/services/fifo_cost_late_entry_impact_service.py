"""Calculate an immutable before/after profit impact for a late FIFO rate."""

from __future__ import annotations

import hashlib
import json
import re
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from services.tax_service import TaxService


class FifoCostLateEntryImpactService:
    """Join a complete FIFO replay with frozen period summaries and tax policy.

    The financial summaries are supplied by the caller so this service stays
    read-only and does not introduce an unbounded Ozon request loop. Their
    sale-identity digests determine finance recognition periods; physical dates
    from the replay are never used as financial-period dates.
    """

    _PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    _DIGEST = re.compile(r"^[0-9a-f]{64}$")
    _MODES = {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}

    def __init__(self, tax_service=None):
        self.tax_service = tax_service or TaxService()

    def preview(self, *, reconstruction, period_summaries, tax_policy_result):
        if not isinstance(reconstruction, dict) or reconstruction.get("error") is not False:
            return self._blocked("FIFO_RECONSTRUCTION_UNAVAILABLE")
        if reconstruction.get("code") not in {
            "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
            "FIFO_TRANSITION_RECONSTRUCTION_READY",
        }:
            return self._blocked("FIFO_RECONSTRUCTION_UNAVAILABLE")
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

        identity_map = self._sale_identity_map(reconstruction)
        candidate_total = self._money(reconstruction.get("candidate_total_cogs_rub"))
        if isinstance(identity_map, str) or candidate_total is None:
            reason = identity_map if isinstance(identity_map, str) else "FIFO_RECONSTRUCTION_RESULT_INVALID"
            return self._blocked(reason)
        summaries = self._normalize_summaries(
            period_summaries, set(identity_map.values()),
            reconstruction_fingerprint=reconstruction.get("preview_fingerprint"),
        )
        if isinstance(summaries, str):
            return self._candidate_only(
                reconstruction, reason=summaries,
                candidate_total=candidate_total, candidate_periods=[],
                outflow_value=outflow_value,
            )
        digest_to_period = {
            digest: period
            for period, summary in summaries.items()
            for digest in summary["sale_identity_digests"]
        }
        mapping_fingerprint = self._fingerprint({
            period: {
                "source_fingerprint": summary["source_fingerprint"],
                "sale_identity_digests": sorted(summary["sale_identity_digests"]),
            }
            for period, summary in sorted(summaries.items())
        })

        if reconstruction.get("before_complete") is not True:
            candidate_periods = self._candidate_period_cogs(
                reconstruction, identity_map, digest_to_period,
            )
            return self._candidate_only(
                reconstruction,
                reason=(
                    reconstruction.get("before_reason_code")
                    or "FIFO_BASELINE_UNAVAILABLE"
                ),
                candidate_total=candidate_total,
                candidate_periods=(
                    candidate_periods if isinstance(candidate_periods, list) else []
                ),
                outflow_value=outflow_value,
                mapping_fingerprint=mapping_fingerprint,
            )

        periods = self._period_cogs(
            reconstruction, identity_map, digest_to_period,
        )
        if isinstance(periods, str):
            return self._candidate_only(
                reconstruction, reason=periods, candidate_total=candidate_total,
                candidate_periods=[], outflow_value=outflow_value,
                mapping_fingerprint=mapping_fingerprint,
            )
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
            return self._candidate_only(
                reconstruction, reason="FIFO_RECONSTRUCTION_TOTAL_MISMATCH",
                candidate_total=candidate_total, candidate_periods=[],
                outflow_value=outflow_value,
                mapping_fingerprint=mapping_fingerprint,
            )
        if set(summaries) != set(periods):
            return self._candidate_only(
                reconstruction, reason="FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE",
                candidate_total=candidate_total, candidate_periods=[],
                outflow_value=outflow_value,
                mapping_fingerprint=mapping_fingerprint,
            )
        policy = self._normalize_policy(tax_policy_result)
        if isinstance(policy, str):
            return self._blocked(policy)
        if any(
            summary["tax_policy_fingerprint"] != policy["fingerprint"]
            for summary in summaries.values()
        ):
            return self._candidate_only(
                reconstruction,
                reason="FIFO_PERIOD_SUMMARY_TAX_POLICY_MISMATCH",
                candidate_total=candidate_total, candidate_periods=[],
                outflow_value=outflow_value,
                mapping_fingerprint=mapping_fingerprint,
            )

        result_periods = []
        for period in sorted(periods):
            summary = summaries[period]
            replay = periods[period]
            before_cost = self._money(summary["current_sku_product_cost"])
            before_replay_cost = replay["before_cogs"]
            after_cost = replay["after_cogs"]
            total_cost = self._money(summary["current_total_product_cost"])
            if before_cost is None or total_cost is None:
                return self._candidate_only(
                    reconstruction, reason="FIFO_PERIOD_SUMMARY_INVALID",
                    candidate_total=candidate_total, candidate_periods=[],
                    outflow_value=outflow_value,
                    mapping_fingerprint=mapping_fingerprint,
                )
            if before_cost != before_replay_cost:
                return self._candidate_only(
                    reconstruction, reason="FIFO_PERIOD_COGS_BASELINE_MISMATCH",
                    candidate_total=candidate_total, candidate_periods=[],
                    outflow_value=outflow_value,
                    mapping_fingerprint=mapping_fingerprint,
                )
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
                "physical_sale_start_date": replay["physical_sale_start_date"],
                "physical_sale_end_date": replay["physical_sale_end_date"],
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
            "financial_period_mapping_fingerprint": mapping_fingerprint,
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

    def _candidate_only(
        self, reconstruction, *, reason, candidate_total, candidate_periods,
        outflow_value, mapping_fingerprint=None,
    ):
        payload = {
            "draft_id": reconstruction.get("draft_id"),
            "stream_revision": reconstruction.get("stream_revision"),
            "allocation_revision": reconstruction.get("allocation_revision"),
            "source_set_fingerprint": reconstruction.get("source_set_fingerprint"),
            "reconstruction_fingerprint": reconstruction.get("preview_fingerprint"),
            "financial_period_mapping_fingerprint": mapping_fingerprint,
            "candidate_total_cogs_rub": format(candidate_total, ".2f"),
            "candidate_periods": candidate_periods,
            "related_return_count": reconstruction["related_return_count"],
            "non_sale_outflow_count": reconstruction["non_sale_outflow_count"],
            "non_sale_outflow_estimated_value_rub": format(outflow_value, ".2f"),
            "return_cogs_authorization_changed": False,
            "non_sale_outflows_included_in_sales_cogs": False,
            "candidate_only": True,
            "complete": False,
            "read_only": True,
            "code": "FIFO_LATE_ENTRY_IMPACT_CANDIDATE_ONLY",
            "reason_code": str(reason or "FIFO_BASELINE_UNAVAILABLE"),
            "error": False,
        }
        payload["preview_fingerprint"] = self._fingerprint(payload)
        return payload

    @classmethod
    def _sale_identity_map(cls, reconstruction):
        mapping = reconstruction.get("sale_identity_digests_by_event")
        dates = reconstruction.get("sale_effective_dates")
        allocations = reconstruction.get("candidate_allocations")
        if not isinstance(mapping, dict) or not isinstance(dates, dict) or not isinstance(allocations, list):
            return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
        event_ids = [
            row.get("event_id") for row in allocations
            if isinstance(row, dict) and isinstance(row.get("event_id"), str)
        ]
        if (
            len(event_ids) != len(allocations)
            or len(event_ids) != len(set(event_ids))
            or set(mapping) != set(event_ids)
            or set(dates) != set(event_ids)
            or any(
                not isinstance(digest, str) or not cls._DIGEST.fullmatch(digest)
                for digest in mapping.values()
            )
            or len(set(mapping.values())) != len(mapping)
            or any(
                not cls._valid_date(dates[event_id])
                for event_id in event_ids
            )
        ):
            return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
        return mapping

    @classmethod
    def _period_cogs(cls, reconstruction, identity_map, digest_to_period):
        dates = reconstruction.get("sale_effective_dates")
        before = reconstruction.get("before_allocations")
        after = reconstruction.get("candidate_allocations")
        if not isinstance(dates, dict) or not isinstance(before, list) or not isinstance(after, list):
            return "FIFO_RECONSTRUCTION_RESULT_INVALID"
        before_result = cls._aggregate_allocations(
            before, dates, identity_map, digest_to_period,
        )
        after_result = cls._aggregate_allocations(
            after, dates, identity_map, digest_to_period,
        )
        if isinstance(before_result, str):
            return before_result
        if isinstance(after_result, str):
            return after_result
        if set(before_result["events"]) != set(after_result["events"]):
            return "FIFO_ALLOCATION_EVENT_COVERAGE_MISMATCH"
        for event_id, before_row in before_result["events"].items():
            after_row = after_result["events"][event_id]
            if (before_row["period"], before_row["quantity"]) != (
                after_row["period"], after_row["quantity"],
            ):
                return "FIFO_ALLOCATION_QUANTITY_MISMATCH"
        if set(before_result["periods"]) != set(after_result["periods"]):
            return "FIFO_ALLOCATION_EVENT_COVERAGE_MISMATCH"
        periods = {}
        for period, after in after_result["periods"].items():
            before = before_result["periods"][period]
            if before["units"] != after["units"]:
                return "FIFO_ALLOCATION_QUANTITY_MISMATCH"
            periods[period] = {
                "units": after["units"],
                "before_cogs": before["cogs"],
                "after_cogs": after["cogs"],
                "before_units_by_basis": before["units_by_basis"],
                "after_units_by_basis": after["units_by_basis"],
                "before_cogs_by_basis": before["cogs_by_basis"],
                "after_cogs_by_basis": after["cogs_by_basis"],
                "physical_sale_start_date": after["physical_sale_start_date"],
                "physical_sale_end_date": after["physical_sale_end_date"],
            }
        return periods if periods else "FIFO_IMPACT_PERIODS_EMPTY"

    @classmethod
    def _candidate_period_cogs(cls, reconstruction, identity_map, digest_to_period):
        result = cls._aggregate_allocations(
            reconstruction.get("candidate_allocations"),
            reconstruction.get("sale_effective_dates"),
            identity_map,
            digest_to_period,
        )
        if isinstance(result, str):
            return result
        return [
            {
                "period": period,
                "units": row["units"],
                "candidate_cogs_rub": format(row["cogs"], ".2f"),
                "candidate_units_by_basis": row["units_by_basis"],
                "candidate_cogs_by_basis_rub": row["cogs_by_basis"],
                "physical_sale_start_date": row["physical_sale_start_date"],
                "physical_sale_end_date": row["physical_sale_end_date"],
                "completeness": "CANDIDATE_ONLY",
            }
            for period, row in sorted(result["periods"].items())
        ]

    @classmethod
    def _aggregate_allocations(cls, rows, dates, identity_map, digest_to_period):
        if not isinstance(rows, list) or not isinstance(dates, dict):
            return "FIFO_RECONSTRUCTION_RESULT_INVALID"
        periods = {}
        events = {}
        for allocation in rows:
            if not isinstance(allocation, dict):
                return "FIFO_RECONSTRUCTION_RESULT_INVALID"
            event_id = allocation.get("event_id")
            date_value = dates.get(event_id)
            digest = identity_map.get(event_id)
            period = digest_to_period.get(digest)
            if (
                not isinstance(event_id, str) or event_id in events
                or not isinstance(date_value, str) or len(date_value) != 10
                or not isinstance(period, str) or not cls._PERIOD.fullmatch(period)
            ):
                return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
            quantity = allocation.get("quantity")
            amount = cls._money(allocation.get("total_cost_rub"))
            lines = allocation.get("lines")
            if type(quantity) is not int or quantity <= 0 or amount is None or not isinstance(lines, list) or not lines:
                return "FIFO_RECONSTRUCTION_RESULT_INVALID"
            state = periods.setdefault(period, {
                "units": 0, "cogs": Decimal("0.00"),
                "units_by_basis": {}, "cogs_by_basis": {}, "physical_dates": [],
            })
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
                state["units_by_basis"][basis_key] = state["units_by_basis"].get(basis_key, 0) + line_quantity
                state["cogs_by_basis"][basis_key] = format(
                    Decimal(state["cogs_by_basis"].get(basis_key, "0.00")) + line_amount,
                    ".2f",
                )
                line_units += line_quantity
                line_total += line_amount
            if line_units != quantity or line_total != amount:
                return "FIFO_RECONSTRUCTION_RESULT_INVALID"
            state["units"] += quantity
            state["cogs"] += amount
            state["physical_dates"].append(date_value)
            events[event_id] = {"period": period, "quantity": quantity}
        for state in periods.values():
            physical_dates = state.pop("physical_dates")
            state["physical_sale_start_date"] = min(physical_dates)
            state["physical_sale_end_date"] = max(physical_dates)
            state["cogs"] = state["cogs"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {"periods": periods, "events": events}

    @classmethod
    def _normalize_summaries(
        cls, values, expected_sale_digests, *, reconstruction_fingerprint,
    ):
        if not isinstance(values, list) or not values or len(values) > 200:
            return "FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE"
        if not isinstance(reconstruction_fingerprint, str) or not cls._DIGEST.fullmatch(
            reconstruction_fingerprint,
        ):
            return "FIFO_PERIOD_SUMMARY_RECONSTRUCTION_MISMATCH"
        result = {}
        all_digests = []
        for row in values:
            if not isinstance(row, dict) or row.get("complete") is not True:
                return "FIFO_PERIOD_SUMMARY_UNAVAILABLE"
            period = row.get("period")
            fingerprint = row.get("source_fingerprint")
            snapshot_reconstruction_fingerprint = row.get("reconstruction_fingerprint")
            tax_policy_fingerprint = row.get("tax_policy_fingerprint")
            sale_digests = row.get("sale_identity_digests")
            if (
                not isinstance(period, str) or not cls._PERIOD.fullmatch(period)
                or period in result
                or not isinstance(fingerprint, str) or not cls._DIGEST.fullmatch(fingerprint)
                or not isinstance(snapshot_reconstruction_fingerprint, str)
                or not cls._DIGEST.fullmatch(snapshot_reconstruction_fingerprint)
                or not isinstance(tax_policy_fingerprint, str)
                or not cls._DIGEST.fullmatch(tax_policy_fingerprint)
                or not isinstance(sale_digests, list) or not sale_digests
                or any(
                    not isinstance(digest, str) or not cls._DIGEST.fullmatch(digest)
                    for digest in sale_digests
                )
                or len(sale_digests) != len(set(sale_digests))
            ):
                return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
            period_start = row.get("period_from")
            period_end = row.get("period_to")
            last_day = monthrange(int(period[:4]), int(period[5:7]))[1]
            if (
                period_start != f"{period}-01"
                or period_end != f"{period}-{last_day:02d}"
            ):
                return "FIFO_PERIOD_SUMMARY_INVALID"
            if snapshot_reconstruction_fingerprint != reconstruction_fingerprint:
                return "FIFO_PERIOD_SUMMARY_RECONSTRUCTION_MISMATCH"
            if len(all_digests) + len(sale_digests) > 100_000:
                return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
            all_digests.extend(sale_digests)
            normalized = {
                "period": period, "complete": True,
                "source_fingerprint": fingerprint,
                "reconstruction_fingerprint": snapshot_reconstruction_fingerprint,
                "tax_policy_fingerprint": tax_policy_fingerprint,
                "sale_identity_digests": list(sale_digests),
            }
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
        if len(all_digests) != len(set(all_digests)) or set(all_digests) != expected_sale_digests:
            return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
        return result

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
    def _valid_date(value):
        if not isinstance(value, str) or len(value) != 10:
            return False
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        return parsed.isoformat() == value

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
