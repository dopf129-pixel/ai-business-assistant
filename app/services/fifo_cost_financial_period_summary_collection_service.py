"""Collect canonical Period Profit summaries in bounded owner-triggered steps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re
from math import isfinite
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.fifo_cost_financial_period_summary_service import (
    FifoCostFinancialPeriodSummaryService,
)
from services.fifo_cost_late_entry_impact_service import (
    FifoCostLateEntryImpactService,
)
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.fifo_cost_transition_contracts import source_fingerprint
from services.fifo_cost_transition_contracts import FifoFinancialPeriodSummary
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)


@dataclass(frozen=True)
class _Checkpoint:
    binding: str
    periods: tuple[str, ...]
    digests_by_period: tuple[tuple[str, tuple[str, ...]], ...]
    expected_case_revision: int
    period_index: int
    next_date: str
    totals: tuple[tuple[str, str], ...]
    chunk_fingerprints: tuple[str, ...]
    expires_at: float


class FifoCostFinancialPeriodSummaryCollectionService:
    """Bounded read of Period Profit; persists only complete monthly freezes."""

    MAX_DAYS_PER_CALL = 4
    MAX_HTTP_ATTEMPTS = 10
    MAX_SECONDS = 20.0
    CHECKPOINT_TTL_SECONDS = 600.0
    MAX_CHECKPOINTS = 64
    MAX_PERIODS = 200
    MAX_SALES = 100_000
    AMOUNTS = ("revenue", "discount_points", "net_accrual", "product_cost",
               "current_sku_product_cost")
    _DIGEST = re.compile(r"^[0-9a-f]{64}$")
    _PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

    def __init__(self, *, monotonic_clock=monotonic, snapshot_builder=None,
                 impact_service=None):
        self.monotonic_clock = monotonic_clock
        self.snapshot_builder = snapshot_builder or FifoCostFinancialPeriodSummaryService()
        self.impact_service = impact_service or FifoCostLateEntryImpactService()
        self._checkpoints = {}
        self._lock = RLock()

    def collect(
        self, *, case_id, identity, expected_case_revision, reconstruction,
        finance_batch, products, tax_policy_result, summary_reader,
        finance_service, evidence_service, continuation_token=None,
        days_per_call=MAX_DAYS_PER_CALL, http_attempt_budget=MAX_HTTP_ATTEMPTS,
        time_budget_seconds=MAX_SECONDS, parent_trace=None,
        existing_summaries=(),
    ):
        if (
            not isinstance(case_id, str) or not case_id
            or type(expected_case_revision) is not int or expected_case_revision < 1
            or not isinstance(identity, dict) or not isinstance(reconstruction, dict)
            or not isinstance(products, list) or not products
            or not callable(summary_reader)
            or not callable(getattr(finance_service, "get_cached_daily_accruals", None))
            or not callable(getattr(evidence_service, "record_period_profit_summary", None))
            or not isinstance(existing_summaries, tuple)
            or any(
                not isinstance(item, FifoFinancialPeriodSummary)
                for item in existing_summaries
            )
        ):
            return self._error("FIFO_PERIOD_SUMMARY_COLLECTION_INPUT_INVALID")
        try:
            day_limit = self._int(days_per_call, 1, self.MAX_DAYS_PER_CALL)
            request_limit = self._int(http_attempt_budget, 1, self.MAX_HTTP_ATTEMPTS)
            seconds_limit = self._seconds(time_budget_seconds)
            catalog_fp = self._catalog_fingerprint(products)
            policy = self.impact_service._normalize_policy(tax_policy_result)
            if isinstance(policy, str):
                return self._error(policy)
            digest_map = self._digests_by_period(reconstruction, finance_batch, identity)
            if isinstance(digest_map, str):
                return self._error(digest_map)
            periods = tuple(sorted(digest_map))
            if not periods or len(periods) > self.MAX_PERIODS or catalog_fp is None:
                return self._error("FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE")
            persisted_by_period = {}
            for item in existing_summaries:
                if (
                    item.period not in digest_map
                    or item.period in persisted_by_period
                ):
                    return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_CONFLICT")
                persisted_by_period[item.period] = item
            mapping = tuple((month, tuple(digest_map[month])) for month in periods)
            binding = source_fingerprint({
                "case_id": case_id,
                "identity": identity,
                "reconstruction": reconstruction.get("preview_fingerprint"),
                "finance_identity": getattr(finance_batch, "source_fingerprint", None),
                "tax_policy": policy["fingerprint"],
                "catalog": catalog_fp,
                "digests_by_period": mapping,
            })
        except (TypeError, ValueError, KeyError, OverflowError):
            return self._error("FIFO_PERIOD_SUMMARY_COLLECTION_INPUT_INVALID")

        state, checkpoint_error = self._take_checkpoint(
            continuation_token, binding=binding, periods=periods, mapping=mapping,
            expected_case_revision=expected_case_revision,
        )
        if checkpoint_error:
            return self._error(checkpoint_error)
        if state is None:
            state = self._initial_checkpoint(
                binding, periods, mapping, expected_case_revision,
            )

        trace = PeriodProfitOperationTrace(
            operation="fifo_financial_period_summary_collection",
            time_budget_seconds=seconds_limit,
            ozon_request_budget=request_limit,
            parent=parent_trace or current_period_profit_trace(),
            clock=self.monotonic_clock,
        )
        token = activate_period_profit_trace(trace)
        days_collected = 0
        saved_periods = []
        issue = None
        try:
            while state.period_index < len(periods) and days_collected < day_limit:
                if trace.is_cancelled() or trace.remaining_seconds() <= 0:
                    issue = "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED"
                    break
                if trace.ozon_requests_reserved >= trace.ozon_request_budget:
                    issue = "FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED"
                    break
                period = periods[state.period_index]
                start, end = self._month_bounds(period)
                cursor = date.fromisoformat(state.next_date)
                if not start <= cursor <= end:
                    issue = "FIFO_PERIOD_SUMMARY_CHECKPOINT_INVALID"
                    break
                chunk_end = min(end, cursor + timedelta(days=day_limit - days_collected - 1))
                summary = self._call_reader(summary_reader, cursor, chunk_end, products)
                if not self._valid_chunk(summary, cursor, chunk_end, identity):
                    issue = self._source_code(summary)
                    break
                cached = finance_service.get_cached_daily_accruals(
                    cursor.isoformat(), chunk_end.isoformat(),
                )
                days = (chunk_end - cursor).days + 1
                if not isinstance(cached, dict) or len(cached) != days:
                    issue = "FIFO_PERIOD_SUMMARY_DAILY_SOURCE_INCOMPLETE"
                    break
                source_fp = source_fingerprint({
                    "finance_daily_cache": self._fingerprint_value(cached),
                    "period_profit": self._summary_material(summary),
                })
                totals = dict(state.totals) if state.totals else {
                    key: "0.00" for key in self.AMOUNTS
                }
                for key in self.AMOUNTS:
                    amount = self._money(summary.get(key))
                    if amount is None:
                        issue = "FIFO_PERIOD_SUMMARY_AMOUNT_INVALID"
                        break
                    totals[key] = format(self._money(Decimal(totals[key]) + amount), ".2f")
                if issue:
                    break
                after = chunk_end + timedelta(days=1)
                candidate_state = _Checkpoint(
                    binding, periods, mapping, state.expected_case_revision,
                    state.period_index,
                    after.isoformat() if after <= end else end.isoformat(),
                    tuple(sorted(totals.items())),
                    (*state.chunk_fingerprints, source_fp),
                    self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
                )
                days_collected += days
                if after > end:
                    month_summary = {
                        "error": False,
                        "period": period,
                        "date_from": start.isoformat(),
                        "date_to": end.isoformat(),
                        **totals,
                        "profit_scope": "CANONICAL_PERIOD_PROFIT_SUMMARY",
                        "account_level_ozon_accruals_included": True,
                        "product_revenue_reconciled": True,
                        "sale_quantity_reconciled": True,
                        "effective_cost_reconciled": True,
                        "fifo_cogs_reconciliation_required": False,
                    }
                    built = self.snapshot_builder.build_snapshot(
                        period_profit_summary=month_summary,
                        reconstruction=reconstruction,
                        sale_identity_digests=list(digest_map[period]),
                        daily_source_fingerprint=source_fingerprint(
                            list(candidate_state.chunk_fingerprints),
                        ),
                        tax_policy_fingerprint=policy["fingerprint"],
                    )
                    if built.get("error") is True:
                        issue = built.get("code") or "FIFO_PERIOD_SUMMARY_SOURCE_INVALID"
                        break
                    persisted = persisted_by_period.get(period)
                    if persisted is not None:
                        # A restarted collector re-reads the month and proves
                        # it is byte-for-byte equivalent to the durable freeze.
                        # It must not append the immutable month a second time.
                        if persisted.source_fingerprint != built["summary"].source_fingerprint:
                            issue = "FIFO_PERIOD_SUMMARY_SNAPSHOT_CONFLICT"
                            break
                        next_case_revision = state.expected_case_revision
                    else:
                        stored = evidence_service.record_period_profit_summary(
                            case_id=case_id,
                            identity=identity,
                            summary=built["summary"],
                            expected_case_revision=state.expected_case_revision,
                            idempotency_key="fifo-period-summary-" + built["summary"].source_fingerprint[:40],
                        )
                        if not isinstance(stored, dict) or stored.get("error") is not False:
                            issue = self._source_code(stored)
                            break
                        next_case_revision = stored.get("case_revision")
                        if next_case_revision != state.expected_case_revision + 1:
                            issue = "FIFO_TRANSITION_REVISION_CONFLICT"
                            break
                    saved_periods.append(period)
                    next_index = state.period_index + 1
                    next_date = (
                        self._month_bounds(periods[next_index])[0].isoformat()
                        if next_index < len(periods) else ""
                    )
                    state = _Checkpoint(
                        binding, periods, mapping, next_case_revision,
                        next_index, next_date, (), (),
                        self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
                    )
                else:
                    state = candidate_state
        except Exception:
            issue = "FIFO_PERIOD_SUMMARY_SOURCE_UNAVAILABLE"
        finally:
            reset_period_profit_trace(token)

        complete = state.period_index == len(periods)
        continuation = None if complete else self._save_checkpoint(state)
        if not complete and continuation is None:
            issue = issue or "FIFO_PERIOD_SUMMARY_CONTINUATION_UNAVAILABLE"
        return {
            "error": False,
            "code": "FIFO_PERIOD_SUMMARIES_READY" if complete else "FIFO_PERIOD_SUMMARIES_PARTIAL",
            "status": "COMPLETE" if complete else "PARTIAL",
            "periods_complete_this_call": len(saved_periods),
            "periods_total": len(periods),
            "days_collected_this_call": days_collected,
            "actual_http_attempts": trace.ozon_requests_reserved,
            "http_attempt_cap": trace.ozon_request_budget,
            "elapsed_seconds": round(self.monotonic_clock() - trace.started_at, 3),
            "issue_code": issue,
            "continuation_token": continuation,
            "current_case_revision": state.expected_case_revision,
            "read_only": True,
        }

    @classmethod
    def _digests_by_period(cls, reconstruction, finance_batch, identity):
        if (
            reconstruction.get("error") is not False
            or reconstruction.get("code") not in {
                "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
                "FIFO_TRANSITION_RECONSTRUCTION_READY",
            }
            or reconstruction.get("before_complete") is not True
            or not cls._DIGEST.fullmatch(str(reconstruction.get("preview_fingerprint") or ""))
            or getattr(getattr(finance_batch, "metadata", None), "completeness", None) is None
            or getattr(finance_batch.metadata.completeness, "value", None) != "COMPLETE"
            or not isinstance(getattr(finance_batch, "rows", None), tuple)
        ):
            return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
        scope = getattr(getattr(finance_batch, "metadata", None), "scope", None)
        if scope is None or any(
            getattr(scope, field, None) != identity.get(field)
            for field in ("store_id", "product_id", "offer_id", "sku")
        ):
            return "FIFO_FINANCIAL_PERIOD_MAPPING_SCOPE_MISMATCH"
        identity_map = reconstruction.get("sale_identity_digests_by_event")
        expected = set(identity_map.values()) if isinstance(identity_map, dict) else set()
        if not expected or len(expected) > cls.MAX_SALES or any(
            not isinstance(value, str) or not cls._DIGEST.fullmatch(value)
            for value in expected
        ):
            return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
        grouped, seen = {}, set()
        for row in finance_batch.rows:
            period = getattr(row, "financial_period", None)
            if not isinstance(period, str) or not cls._PERIOD.fullmatch(period):
                return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
            row_offer = getattr(row, "offer_id", None)
            row_product = getattr(row, "product_id", None)
            if (
                row_offer is not None and identity.get("offer_id") is not None
                and row_offer != identity.get("offer_id")
            ) or (
                row_product is not None and identity.get("product_id") is not None
                and row_product != identity.get("product_id")
            ):
                return "FIFO_FINANCIAL_PERIOD_MAPPING_CONFLICT"
            result = FifoCostSaleEvidenceNormalizer.build_identity_digest(
                store_id=identity.get("store_id"),
                posting_number=getattr(row, "posting_number", None),
                finance_sku=getattr(row, "finance_sku", None),
                identity={
                    "mapping_confirmed": bool(identity.get("offer_id") or identity.get("product_id")),
                    "offer_id": identity.get("offer_id"),
                    "product_id": identity.get("product_id"),
                },
            )
            if not isinstance(result, dict) or result.get("error") is not False:
                return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
            digest = result.get("source_identity_digest")
            if not isinstance(digest, str) or not cls._DIGEST.fullmatch(digest) or digest in seen:
                return "FIFO_FINANCIAL_PERIOD_MAPPING_CONFLICT"
            seen.add(digest)
            grouped.setdefault(period, []).append(digest)
        if seen != expected:
            return "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
        return {period: tuple(sorted(values)) for period, values in grouped.items()}

    @classmethod
    def _valid_chunk(cls, summary, start, end, identity):
        if not isinstance(summary, dict) or summary.get("error") is not False:
            return False
        if any((
            summary.get("date_from") != start.isoformat(),
            summary.get("date_to") != end.isoformat(),
            summary.get("account_level_ozon_accruals_included") is not True,
            summary.get("product_revenue_reconciled") is not True,
            summary.get("sale_quantity_reconciled") is not True,
            summary.get("effective_cost_reconciled") is not True,
            summary.get("fifo_cogs_reconciliation_required") is not False,
            summary.get("fee_components_included") is False,
        )):
            return False
        if any(cls._money(summary.get(key)) is None for key in cls.AMOUNTS[:4]):
            return False
        product_cost = cls._sku_cost(summary.get("products"), identity)
        if product_cost is None:
            return False
        summary["current_sku_product_cost"] = float(product_cost)
        return True

    @classmethod
    def _sku_cost(cls, rows, identity):
        if not isinstance(rows, list):
            return None
        matches = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            is_match = (
                (identity.get("product_id") and row.get("product_id") == identity.get("product_id"))
                or (identity.get("offer_id") and row.get("offer_id") == identity.get("offer_id"))
                or (identity.get("sku") and identity.get("sku") in {
                    row.get("sku"), row.get("catalog_sku"),
                })
            )
            if is_match:
                matches.append(row)
        if not matches:
            return None
        total, seen_skus = Decimal("0.00"), set()
        for row in matches:
            sku = row.get("sku")
            cost = cls._money(row.get("product_cost"))
            if not isinstance(sku, str) or not sku or sku in seen_skus or cost is None:
                return None
            seen_skus.add(sku)
            total += cost
        return cls._money(total)

    @classmethod
    def _catalog_fingerprint(cls, products):
        values, seen = [], set()
        for row in products:
            if isinstance(row, dict):
                item = tuple(str(row.get(field) or "").strip() for field in (
                    "product_id", "offer_id", "sku",
                ))
            elif isinstance(row, (tuple, list)) and len(row) >= 3:
                item = tuple(str(value or "").strip() for value in row[:3])
            else:
                return None
            if not any(item) or item in seen:
                return None
            seen.add(item)
            values.append(item)
        return source_fingerprint(sorted(values))

    @staticmethod
    def _call_reader(reader, start, end, products):
        try:
            result = reader(start.isoformat(), end.isoformat(), products)
        except Exception:
            return {"error": True, "code": "FIFO_PERIOD_SUMMARY_SOURCE_UNAVAILABLE"}
        return result if isinstance(result, dict) else {
            "error": True, "code": "FIFO_PERIOD_SUMMARY_SOURCE_INVALID",
        }

    @classmethod
    def _summary_material(cls, summary):
        material = {
            key: summary.get(key)
            for key in (
                "date_from", "date_to", "product_count",
                "account_level_ozon_accruals_included",
                "product_revenue_reconciled", "sale_quantity_reconciled",
                "effective_cost_reconciled", "fee_components_included",
            )
        }
        for key in ("revenue", "discount_points", "net_accrual", "product_cost"):
            amount = cls._money(summary.get(key))
            if amount is None:
                raise ValueError("FIFO_PERIOD_SUMMARY_AMOUNT_INVALID")
            material[key] = format(amount, ".2f")
        return material

    @classmethod
    def _fingerprint_value(cls, value):
        """Normalize JSON-like API values to the strict fingerprint contract."""
        if value is None or type(value) in (bool, int, str):
            return value
        if isinstance(value, float):
            if not isfinite(value):
                raise ValueError("FIFO_PERIOD_SUMMARY_SOURCE_INVALID")
            return Decimal(str(value))
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("FIFO_PERIOD_SUMMARY_SOURCE_INVALID")
            return value
        if isinstance(value, (tuple, list)):
            return tuple(cls._fingerprint_value(item) for item in value)
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("FIFO_PERIOD_SUMMARY_SOURCE_INVALID")
            return {
                key: cls._fingerprint_value(item)
                for key, item in value.items()
            }
        raise ValueError("FIFO_PERIOD_SUMMARY_SOURCE_INVALID")

    @staticmethod
    def _month_bounds(period):
        start = date.fromisoformat(period + "-01")
        next_month = (
            date(start.year + 1, 1, 1) if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return start, next_month - timedelta(days=1)

    def _initial_checkpoint(self, binding, periods, mapping, expected_case_revision):
        return _Checkpoint(
            binding, periods, mapping, expected_case_revision, 0,
            self._month_bounds(periods[0])[0].isoformat(),
            (), (), self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
        )

    def _take_checkpoint(
        self, token, *, binding, periods, mapping, expected_case_revision,
    ):
        if token is None:
            return None, None
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            return None, "FIFO_PERIOD_SUMMARY_CONTINUATION_INVALID"
        with self._lock:
            value = self._checkpoints.get(token)
            if value is None:
                return None, "FIFO_PERIOD_SUMMARY_CONTINUATION_STALE"
            if value.expires_at <= self.monotonic_clock():
                self._checkpoints.pop(token, None)
                return None, "FIFO_PERIOD_SUMMARY_CONTINUATION_EXPIRED"
            if (
                value.binding != binding or value.periods != periods
                or value.digests_by_period != mapping
            ):
                return None, "FIFO_PERIOD_SUMMARY_CONTINUATION_SCOPE_MISMATCH"
            if value.expected_case_revision != expected_case_revision:
                self._checkpoints.pop(token, None)
                return None, "FIFO_TRANSITION_REVISION_CONFLICT"
            self._checkpoints.pop(token, None)
        return value, None

    def _save_checkpoint(self, value):
        token = uuid4().hex
        with self._lock:
            now = self.monotonic_clock()
            for key, current in list(self._checkpoints.items()):
                if current.expires_at <= now:
                    self._checkpoints.pop(key, None)
            while len(self._checkpoints) >= self.MAX_CHECKPOINTS:
                self._checkpoints.pop(next(iter(self._checkpoints)))
            self._checkpoints[token] = value
        return token

    @staticmethod
    def _int(value, minimum, maximum):
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError
        return value

    @classmethod
    def _seconds(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError
        if not 1 <= value <= cls.MAX_SECONDS:
            raise ValueError
        return float(value)

    @staticmethod
    def _money(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not result.is_finite() or abs(result) > Decimal("1000000000"):
            return None
        return result.quantize(Decimal("0.01"))

    @staticmethod
    def _source_code(result):
        code = result.get("code") if isinstance(result, dict) else None
        return code if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{1,96}", code) else "FIFO_PERIOD_SUMMARY_SOURCE_INCOMPLETE"

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": "FIFO_PERIOD_SUMMARY_UNAVAILABLE",
            "read_only": True,
        }
