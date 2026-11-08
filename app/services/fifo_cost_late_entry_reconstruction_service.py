"""Read-only reconstruction of an owner-confirmed late FIFO rate transition."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from services.fifo_cost_late_entry_impact_service import (
    FifoCostLateEntryImpactService,
)


class FifoCostLateEntryReconstructionService:
    """Replay an exact-SKU stream with one hypothetical historical open rate."""

    _DIGEST = re.compile(r"^[0-9a-f]{64}$")

    def __init__(self, repository, impact_service=None):
        self.repository = repository
        self.impact_service = impact_service or FifoCostLateEntryImpactService()

    def preview(self, *, store_id, product_id=None, offer_id=None, sku, draft_id):
        result = self.repository.preview_late_entry_reconstruction(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
            draft_id=draft_id,
        )
        if not isinstance(result, dict):
            return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
        if result.get("error") is True:
            return result
        if result.get("code") == "FIFO_LATE_ENTRY_RECONSTRUCTION_BLOCKED":
            if (
                result.get("current_stock_used_as_historical") is not False
                or result.get("period_profit_changed") is not False
            ):
                return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
            return result
        allocations = result.get("candidate_allocations")
        outflows = result.get("candidate_outflows")
        outflow_count = result.get("non_sale_outflow_count")
        outflow_value = result.get("candidate_non_sale_outflow_value_rub")
        restored_units = result.get("candidate_restored_units")
        if (
            result.get("code") != "FIFO_LATE_ENTRY_RECONSTRUCTION_READY"
            or result.get("complete") is not True
            or result.get("read_only") is not True
            or result.get("period_profit_changed") is not False
            or result.get("accepted_units_added_to_stock") != 0
            or not isinstance(result.get("preview_fingerprint"), str)
            or not self._DIGEST.fullmatch(result["preview_fingerprint"])
            or not isinstance(allocations, list)
            or not isinstance(outflows, list)
            or type(outflow_count) is not int
            or outflow_count != len(outflows)
            or type(restored_units) is not int
            or restored_units < 0
            or result.get("return_cogs_authorization_changed") is not False
        ):
            return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
        try:
            normalized_outflow_value = Decimal(str(outflow_value))
            outflow_total = Decimal("0.00")
            for row in outflows:
                if not isinstance(row, dict):
                    return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
                amount = Decimal(str(row.get("estimated_value_rub")))
                if (
                    not isinstance(row.get("event_id"), str)
                    or not row["event_id"]
                    or type(row.get("quantity")) is not int
                    or row["quantity"] <= 0
                    or not amount.is_finite()
                    or amount < 0
                    or amount.quantize(Decimal("0.01")) != amount
                ):
                    return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
                outflow_total += amount
        except (InvalidOperation, TypeError, ValueError):
            return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
        if (
            not normalized_outflow_value.is_finite()
            or normalized_outflow_value < 0
            or normalized_outflow_value.quantize(Decimal("0.01")) != normalized_outflow_value
            or outflow_total != normalized_outflow_value
        ):
            return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
        return result

    def preview_impact(
        self, *, store_id, product_id=None, offer_id=None, sku, draft_id,
        period_summaries, tax_policy_result,
    ):
        reconstruction = self.preview(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
            draft_id=draft_id,
        )
        if not isinstance(reconstruction, dict) or reconstruction.get("error") is True:
            return self._error("FIFO_RECONSTRUCTION_RESULT_INVALID")
        if reconstruction.get("code") != "FIFO_LATE_ENTRY_RECONSTRUCTION_READY":
            return reconstruction
        try:
            impact = self.impact_service.preview(
                reconstruction=reconstruction,
                period_summaries=period_summaries,
                tax_policy_result=tax_policy_result,
            )
        except Exception:
            return self._error("FIFO_LATE_ENTRY_IMPACT_UNAVAILABLE")
        if not isinstance(impact, dict) or impact.get("read_only") is not True:
            return self._error("FIFO_LATE_ENTRY_IMPACT_INVALID")
        return impact

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True}
