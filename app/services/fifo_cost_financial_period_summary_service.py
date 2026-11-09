"""Freeze canonical Period Profit totals for exact FIFO sale identities."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from services.fifo_cost_transition_contracts import (
    FifoFinancialPeriodSummary,
    source_fingerprint,
)


class FifoCostFinancialPeriodSummaryService:
    """Build immutable before-cost bindings from existing Period Profit output.

    This class contains no Ozon, Telegram, or repository calls. Its input must
    come from a complete canonical Period Profit read and the exact daily
    finance sale identities collected by that same read session. Baseline COGS
    comes only from the FR19 before-reconstruction allocations.
    """

    MAX_SALE_IDENTITIES = 100_000

    def build_snapshot(
        self, *, period_profit_summary, reconstruction,
        sale_identity_digests, daily_source_fingerprint,
        tax_policy_fingerprint,
    ):
        if not isinstance(period_profit_summary, dict):
            return self._error("FIFO_PERIOD_SUMMARY_SOURCE_INVALID")
        if period_profit_summary.get("error") is not False:
            return self._error("FIFO_PERIOD_SUMMARY_SOURCE_INCOMPLETE")
        if (
            period_profit_summary.get("account_level_ozon_accruals_included") is not True
            or period_profit_summary.get("product_revenue_reconciled") is not True
            or period_profit_summary.get("sale_quantity_reconciled") is not True
            or period_profit_summary.get("effective_cost_reconciled") is not True
            or period_profit_summary.get("fifo_cogs_reconciliation_required") is True
        ):
            return self._error("FIFO_PERIOD_SUMMARY_SOURCE_INCOMPLETE")
        if (
            not isinstance(reconstruction, dict)
            or reconstruction.get("error") is not False
            or reconstruction.get("code") != "FIFO_LATE_ENTRY_RECONSTRUCTION_READY"
            or reconstruction.get("before_complete") is not True
            or not isinstance(reconstruction.get("preview_fingerprint"), str)
        ):
            return self._error("FIFO_BASELINE_UNAVAILABLE")

        try:
            start = self._date(period_profit_summary.get("date_from"))
            end = self._date(period_profit_summary.get("date_to"))
            if start > end or start[:7] != end[:7]:
                raise ValueError
            if (
                not isinstance(sale_identity_digests, (tuple, list))
                or not sale_identity_digests
                or len(sale_identity_digests) > self.MAX_SALE_IDENTITIES
                or any(not self._digest(value) for value in sale_identity_digests)
                or len(sale_identity_digests) != len(set(sale_identity_digests))
                or not self._digest(daily_source_fingerprint)
                or not self._digest(tax_policy_fingerprint)
            ):
                raise ValueError
            source_period = period_profit_summary.get("period")
            if source_period is not None and source_period != start[:7]:
                raise ValueError
            if not self._all_target_sales_have_before_cost(
                reconstruction, set(sale_identity_digests),
            ):
                return self._error("FIFO_BASELINE_UNAVAILABLE")
            sku_cost = self._baseline_cogs_for_digests(
                reconstruction, set(sale_identity_digests),
            )
            total_cost = self._money(period_profit_summary.get("product_cost"))
            summarized_sku_cost = self._money(
                period_profit_summary.get("current_sku_product_cost"),
            )
            if sku_cost is None or summarized_sku_cost != sku_cost:
                return self._error("FIFO_PERIOD_COGS_BASELINE_MISMATCH")
            if total_cost is None or sku_cost is None or sku_cost > total_cost:
                return self._error("FIFO_PERIOD_COST_RECONCILIATION_CONFLICT")
            amounts = {
                "revenue": self._money(period_profit_summary.get("revenue")),
                "discount_points": self._money(
                    period_profit_summary.get("discount_points"),
                ),
                "net_accrual": self._money(
                    period_profit_summary.get("net_accrual"), allow_negative=True,
                ),
            }
            if any(value is None for value in amounts.values()):
                raise ValueError

            source_material = {
                "schema_version": 1,
                "period_from": start,
                "period_to": end,
                "period_profit_summary_fingerprint": source_fingerprint(
                    self._summary_fingerprint_material(period_profit_summary),
                ),
                "daily_source_fingerprint": daily_source_fingerprint,
                "reconstruction_fingerprint": reconstruction["preview_fingerprint"],
                "tax_policy_fingerprint": tax_policy_fingerprint,
                "sale_identity_digests": sorted(sale_identity_digests),
                "revenue": format(amounts["revenue"], ".2f"),
                "discount_points": format(amounts["discount_points"], ".2f"),
                "net_accrual": format(amounts["net_accrual"], ".2f"),
                "current_total_product_cost": format(total_cost, ".2f"),
                "current_sku_product_cost": format(sku_cost, ".2f"),
            }
            snapshot_fingerprint = source_fingerprint(source_material)
            snapshot = FifoFinancialPeriodSummary(
                period_from=start,
                period_to=end,
                source_fingerprint=snapshot_fingerprint,
                reconstruction_fingerprint=reconstruction["preview_fingerprint"],
                tax_policy_fingerprint=tax_policy_fingerprint,
                sale_identity_digests=tuple(sorted(sale_identity_digests)),
                revenue_rub=amounts["revenue"],
                discount_points_rub=amounts["discount_points"],
                net_accrual_rub=amounts["net_accrual"],
                current_total_product_cost_rub=total_cost,
                current_sku_product_cost_rub=sku_cost,
            )
        except (TypeError, ValueError, KeyError, InvalidOperation, OverflowError):
            return self._error("FIFO_PERIOD_SUMMARY_SOURCE_INVALID")
        return {
            "error": False,
            "code": "FIFO_PERIOD_SUMMARY_READY",
            "summary": snapshot,
            "read_only": True,
        }

    @classmethod
    def _all_target_sales_have_before_cost(cls, reconstruction, target_digests):
        identity_map = reconstruction.get("sale_identity_digests_by_event")
        before = reconstruction.get("before_allocations")
        if not isinstance(identity_map, dict) or not isinstance(before, list):
            return False
        if not target_digests or not target_digests.issubset(set(identity_map.values())):
            return False
        event_by_digest = {}
        for event_id, digest in identity_map.items():
            if digest in event_by_digest:
                return False
            event_by_digest[digest] = event_id
        allocation_by_event = {}
        for row in before:
            if not isinstance(row, dict):
                return False
            event_id = row.get("event_id")
            if not isinstance(event_id, str) or event_id in allocation_by_event:
                return False
            allocation_by_event[event_id] = row
        return all(
            event_by_digest[digest] in allocation_by_event
            for digest in target_digests
        )

    @classmethod
    def _baseline_cogs_for_digests(cls, reconstruction, target_digests):
        identity_map = reconstruction.get("sale_identity_digests_by_event")
        before = reconstruction.get("before_allocations")
        if not isinstance(identity_map, dict) or not isinstance(before, list):
            return None
        event_by_digest = {digest: event_id for event_id, digest in identity_map.items()}
        by_event = {row.get("event_id"): row for row in before if isinstance(row, dict)}
        if len(by_event) != len(before):
            return None
        total = Decimal("0.00")
        for digest in target_digests:
            row = by_event.get(event_by_digest.get(digest))
            if row is None:
                return None
            amount = cls._money(row.get("total_cost_rub"))
            if amount is None:
                return None
            total += amount
        return total.quantize(Decimal("0.01"))

    @classmethod
    def _summary_fingerprint_material(cls, summary):
        # Keep identifiers inside the digest; the encrypted snapshot retains no
        # raw external IDs beyond the one sale-identity digest per affected sale.
        amount_fields = {
            "revenue": cls._money(summary.get("revenue")),
            "discount_points": cls._money(summary.get("discount_points")),
            "net_accrual": cls._money(
                summary.get("net_accrual"), allow_negative=True,
            ),
            "product_cost": cls._money(summary.get("product_cost")),
            "current_sku_product_cost": cls._money(
                summary.get("current_sku_product_cost"),
            ),
        }
        if any(value is None for value in amount_fields.values()):
            raise ValueError("FIFO_PERIOD_SUMMARY_SOURCE_INVALID")
        return {
            "date_from": summary.get("date_from"),
            "date_to": summary.get("date_to"),
            **{
                key: format(value, ".2f")
                for key, value in amount_fields.items()
            },
            "profit_scope": summary.get("profit_scope"),
            "account_level_ozon_accruals_included": summary.get(
                "account_level_ozon_accruals_included",
            ),
            "product_revenue_reconciled": summary.get("product_revenue_reconciled"),
            "sale_quantity_reconciled": summary.get("sale_quantity_reconciled"),
            "effective_cost_reconciled": summary.get("effective_cost_reconciled"),
            "fifo_allocation_revision_count": summary.get(
                "fifo_allocation_revision_count",
            ),
        }

    @classmethod
    def _money(cls, value, *, allow_negative=False):
        if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (
            not amount.is_finite()
            or abs(amount) > Decimal("1000000000")
            or (not allow_negative and amount < 0)
            or amount.quantize(Decimal("0.01")) != amount
        ):
            return None
        return amount.quantize(Decimal("0.01"))

    @staticmethod
    def _date(value):
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        from datetime import date
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed.isoformat()

    @staticmethod
    def _digest(value):
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
        )

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": "FIFO_PERIOD_SUMMARY_UNAVAILABLE",
            "read_only": True,
        }
