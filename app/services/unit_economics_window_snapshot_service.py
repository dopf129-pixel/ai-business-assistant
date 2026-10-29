"""Build bounded, weighted unit-economics snapshots from normalized evidence."""

import math
import re
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    reset_period_profit_trace,
)


class UnitEconomicsWindowSnapshotService:
    """Keep a frozen 56-day reference separate from one observed phase window."""

    SCHEMA_VERSION = 1
    REFERENCE_DAYS = 56
    MAX_PHASE_DAYS = 28
    MAX_SEGMENTS = 64
    MAX_COMPONENTS = 64
    MAX_COLLECTION_NODES = 20_000
    MAX_COLLECTION_BYTES = 64 * 1024
    MAX_HTTP_ATTEMPTS = 128
    MAX_SECONDS = 120
    MAX_UNITS = 1_000_000_000
    MAX_AMOUNT = Decimal("999999999999.99")
    QUANTUM = Decimal("0.01")
    DENOMINATORS = frozenset({"ORDERED_UNITS_WINDOW", "SOLD_UNITS_WINDOW"})
    _KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    _REVISION_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

    @classmethod
    def reference_window(cls, as_of_local_date, timezone_name):
        """Return the exact 56 completed local calendar days before as-of date."""
        as_of = cls._date(as_of_local_date)
        zone = cls._timezone(timezone_name)
        if as_of is None or zone is None:
            return cls._error("UNIT_ECONOMICS_REFERENCE_WINDOW_INVALID")
        end = as_of - timedelta(days=1)
        start = end - timedelta(days=cls.REFERENCE_DAYS - 1)
        return {
            "error": False,
            "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
            "window": cls._window(start, end, zone),
            "as_of_local_date": as_of.isoformat(),
            "requested_days": cls.REFERENCE_DAYS,
        }

    @classmethod
    def phase_window(cls, start_date, end_date, as_of_local_date, timezone_name):
        """Validate one completed, bounded experimental phase window."""
        start = cls._date(start_date)
        end = cls._date(end_date)
        as_of = cls._date(as_of_local_date)
        zone = cls._timezone(timezone_name)
        if (
            start is None or end is None or as_of is None or zone is None
            or start > end or end >= as_of
            or (end - start).days + 1 > cls.MAX_PHASE_DAYS
        ):
            return cls._error("UNIT_ECONOMICS_PHASE_WINDOW_INVALID")
        return {
            "error": False,
            "scope_kind": "EXPERIMENT_PHASE_WINDOW",
            "window": cls._window(start, end, zone),
            "as_of_local_date": as_of.isoformat(),
            "requested_days": (end - start).days + 1,
        }

    @classmethod
    def new_operation_trace(cls, parent_trace=None, clock=None):
        """Create a child trace with strict caps; its parent budget still applies."""
        request_limit = cls.MAX_HTTP_ATTEMPTS
        if parent_trace is not None:
            chain = []
            current = parent_trace
            while current is not None:
                chain.append(current)
                current = current.parent
            already_reserved = max(item.ozon_requests_reserved for item in chain)
            request_limit = min(
                cls.MAX_HTTP_ATTEMPTS - already_reserved,
                *(item.ozon_request_budget - item.ozon_requests_reserved for item in chain),
            )
            request_limit = max(0, request_limit)
        return PeriodProfitOperationTrace(
            operation="unit_economics_snapshot",
            time_budget_seconds=cls.MAX_SECONDS,
            ozon_request_budget=request_limit,
            clock=clock,
            parent=parent_trace,
        )

    @classmethod
    def collect_sources(cls, readers, parent_trace=None):
        """Run explicit normalized-evidence readers sequentially under one trace.

        Readers must return already-normalized, bounded evidence. Ozon clients use
        the active trace and reserve every HTTP attempt. This method never retries.
        """
        if not isinstance(readers, list) or not readers or len(readers) > cls.MAX_COMPONENTS:
            return cls._error("UNIT_ECONOMICS_SOURCE_READER_LIMIT_EXCEEDED")
        if parent_trace is not None and not isinstance(parent_trace, PeriodProfitOperationTrace):
            return cls._error("UNIT_ECONOMICS_PARENT_TRACE_INVALID")
        normalized_readers = []
        source_keys = set()
        for item in readers:
            if (
                not isinstance(item, tuple) or len(item) != 2
                or not isinstance(item[0], str) or cls._KEY_RE.fullmatch(item[0]) is None
                or not callable(item[1])
            ):
                return cls._error("UNIT_ECONOMICS_SOURCE_READER_INVALID")
            if item[0] in source_keys:
                return cls._error("UNIT_ECONOMICS_SOURCE_READER_DUPLICATE")
            source_keys.add(item[0])
            normalized_readers.append(item)

        trace = cls.new_operation_trace(parent_trace=parent_trace)
        token = activate_period_profit_trace(trace)
        source_results = []
        stop_reason = "NONE"
        stopped_index = len(normalized_readers)
        collection_nodes = 0
        collection_bytes = 0
        try:
            for index, (source_key, reader) in enumerate(normalized_readers):
                if trace.is_budget_exhausted():
                    stop_reason = cls._budget_stop_reason(trace)
                    stopped_index = index
                    break
                try:
                    value = reader()
                except Exception:
                    source_results.append({"source_key": source_key, "status": "SOURCE_READ_FAILED"})
                    stop_reason = "SOURCE_READ_FAILED"
                    stopped_index = index + 1
                    break
                bounded_value, node_count = cls._bounded_evidence(
                    value, cls.MAX_COLLECTION_NODES - collection_nodes,
                )
                if bounded_value is None:
                    source_results.append({"source_key": source_key, "status": "SOURCE_EVIDENCE_INVALID"})
                    stop_reason = "SOURCE_EVIDENCE_INVALID"
                    stopped_index = index + 1
                    break
                try:
                    evidence_size = len(json.dumps(
                        bounded_value, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False,
                    ).encode("utf-8"))
                except (TypeError, ValueError):
                    evidence_size = cls.MAX_COLLECTION_BYTES + 1
                if evidence_size > cls.MAX_COLLECTION_BYTES - collection_bytes:
                    source_results.append({"source_key": source_key, "status": "SOURCE_EVIDENCE_LIMIT_EXCEEDED"})
                    stop_reason = "SOURCE_EVIDENCE_LIMIT_EXCEEDED"
                    stopped_index = index + 1
                    break
                collection_nodes += node_count
                collection_bytes += evidence_size
                if bounded_value.get("status") == "RATE_LIMITED":
                    source_results.append({"source_key": source_key, "status": "RATE_LIMITED"})
                    stop_reason = "HTTP_429"
                    stopped_index = index + 1
                    break
                if bounded_value.get("error") is True:
                    source_results.append({"source_key": source_key, "status": "SOURCE_UNAVAILABLE"})
                    continue
                if trace.is_budget_exhausted():
                    stop_reason = cls._budget_stop_reason(trace)
                    source_results.append({"source_key": source_key, "status": stop_reason})
                    stopped_index = index + 1
                    break
                source_results.append({"source_key": source_key, "evidence": bounded_value})
        finally:
            reset_period_profit_trace(token)

        budget = cls._trace_budget(trace, stop_reason)
        return {
            "error": False,
            "status": "COMPLETE" if (
                stop_reason == "NONE" and len(source_results) == len(normalized_readers)
                and all(
                    item.get("evidence", {}).get("status") in {"COMPLETE", "CONFIRMED_ZERO"}
                    for item in source_results
                )
            )
            else "PARTIAL",
            "sources": source_results,
            "not_started_source_keys": [key for key, _ in normalized_readers[stopped_index:]],
            "budget": budget,
            "read_only": True,
            "executed": True,
        }

    @classmethod
    def build_snapshot(cls, window_spec, identity, segments, required_component_keys, budget):
        """Aggregate disjoint window slices with weighted, compatible denominators."""
        validated = cls._validate_request(
            window_spec, identity, segments, required_component_keys, budget,
        )
        if validated is None:
            return cls._error("UNIT_ECONOMICS_WINDOW_SNAPSHOT_INVALID")
        spec, identity, segments, keys, budget = validated
        day_segments = {}
        for segment in segments:
            for offset in range((segment["end"] - segment["start"]).days + 1):
                day = segment["start"] + timedelta(days=offset)
                if day in day_segments:
                    return cls._error("UNIT_ECONOMICS_WINDOW_SEGMENTS_OVERLAP")
                day_segments[day] = segment

        requested_days = (spec["end"] - spec["start"]).days + 1
        covered_days = sorted(day_segments)
        full_dates = (
            len(covered_days) == requested_days
            and covered_days[0] == spec["start"] and covered_days[-1] == spec["end"]
            and all((right - left).days == 1 for left, right in zip(covered_days, covered_days[1:]))
        ) if covered_days else False
        observed_days = len(covered_days)
        complete_segments = [segment for segment in segments if segment["complete"]]
        complete_days = sorted({
            segment["start"] + timedelta(days=offset)
            for segment in complete_segments
            for offset in range(segment["days"])
        })
        short_history = (
            len(complete_segments) == len(segments)
            and 0 < len(complete_days) < requested_days
            and complete_days[-1] == spec["end"]
            and all((right - left).days == 1 for left, right in zip(complete_days, complete_days[1:]))
        )
        denominator_kinds = {segment["denominator_kind"] for segment in complete_segments}
        mixed_denominators = len(denominator_kinds) > 1
        eligible_segments = [] if mixed_denominators else complete_segments
        component_rows = {}
        for key in keys:
            known_amount = Decimal("0.00")
            eligible_days = 0
            missing_segments = 0
            for segment in eligible_segments:
                component = segment["components"].get(key)
                if component is None or component["status"] not in {"PRESENT", "CONFIRMED_ZERO"}:
                    missing_segments += 1
                    continue
                known_amount += component["amount"]
                eligible_days += segment["days"]
            units = sum(segment["units"] for segment in eligible_segments)
            all_component_days = eligible_days == sum(segment["days"] for segment in eligible_segments)
            observed_rate = cls._rate(known_amount, units) if all_component_days else None
            full_coverage = full_dates and not mixed_denominators and all_component_days
            status = cls._snapshot_status(
                spec, full_coverage, observed_days, requested_days, budget,
                mixed_denominators, short_history,
            )
            rate_status = "AVAILABLE" if observed_rate is not None else (
                "ZERO_DENOMINATOR" if all_component_days and units == 0 else "UNAVAILABLE"
            )
            component_rows[key] = {
                "status": status if full_coverage else (
                    "INCOMPARABLE" if mixed_denominators else "PARTIAL"
                ),
                "observed_numerator_rub": cls._money(known_amount),
                "observed_denominator_units": units,
                "denominator_kind": next(iter(denominator_kinds)) if len(denominator_kinds) == 1 else None,
                "observed_unit_expense_rub": observed_rate,
                "unit_expense_rub": observed_rate if full_coverage and status == "COMPLETE" else None,
                "rate_status": rate_status,
                "covered_days": eligible_days,
                "missing_segments": missing_segments,
            }

        total_amount = Decimal("0.00")
        observed_components_complete = bool(keys) and bool(eligible_segments) and not mixed_denominators
        eligible_days = sum(segment["days"] for segment in eligible_segments)
        for key in keys:
            if component_rows[key]["covered_days"] != eligible_days:
                observed_components_complete = False
                break
            total_amount += Decimal(component_rows[key]["observed_numerator_rub"])
        total_units = sum(segment["units"] for segment in eligible_segments)
        total_rate = (
            cls._rate(total_amount, total_units)
            if observed_components_complete and total_units > 0 else None
        )
        snapshot_status = cls._snapshot_status(
            spec, full_dates and observed_components_complete, observed_days, requested_days,
            budget, mixed_denominators, short_history,
        )
        result = {
            "error": False,
            "schema_version": cls.SCHEMA_VERSION,
            "identity": identity,
            "scope_kind": spec["scope_kind"],
            "model_scope": "WINDOW_COST_ALLOCATION",
            "window": cls._window(spec["start"], spec["end"], spec["timezone"]),
            "as_of_local_date": spec["as_of"].isoformat(),
            "requested_days": requested_days,
            "observed_days": observed_days,
            "complete_days": len(complete_days),
            "observed_window": {
                "from_date": covered_days[0].isoformat() if covered_days else None,
                "to_date": covered_days[-1].isoformat() if covered_days else None,
            },
            "coverage": {
                "status": snapshot_status,
                "complete": snapshot_status == "COMPLETE",
                "full_requested_window": full_dates,
                "eligible_segment_count": len(eligible_segments),
                "segment_count": len(segments),
                "segments": [
                    {
                        "from_date": segment["start"].isoformat(),
                        "to_date": segment["end"].isoformat(),
                        "source_complete": segment["coverage"]["complete"],
                        "evidence_complete": segment["complete"],
                        "page_count": segment["coverage"]["page_count"],
                        "stop_reason": segment["coverage"]["stop_reason"],
                        "quantity_status": segment["quantity_status"],
                        "denominator_units": segment["units"] if segment["complete"] else None,
                        "denominator_kind": segment["denominator_kind"],
                        "source_revision": segment["source_revision"],
                    }
                    for segment in segments
                ],
            },
            "denominator": {
                "units": total_units,
                "kind": next(iter(denominator_kinds)) if len(denominator_kinds) == 1 else None,
            },
            "components": component_rows,
            "observed_total_expense_rub": (
                cls._money(total_amount) if observed_components_complete else None
            ),
            "observed_total_unit_expense_rub": total_rate,
            "total_unit_expense_rub": total_rate if snapshot_status == "COMPLETE" else None,
            "rate_status": "AVAILABLE" if total_rate is not None else (
                "ZERO_DENOMINATOR" if observed_components_complete and total_units == 0 else "UNAVAILABLE"
            ),
            "budget": budget,
            "read_only": True,
            "executed": False,
        }
        result["source_revision"] = cls._fingerprint({
            "identity": identity,
            "scope_kind": spec["scope_kind"],
            "window": result["window"],
            "segments": [segment["source_revision"] for segment in segments],
            "components": component_rows,
            "denominator": result["denominator"],
        })
        return result

    @classmethod
    def build_pair(cls, reference_input, phase_input):
        """Build reference and observed snapshots independently; never pool them."""
        expected = {"window_spec", "identity", "segments", "required_component_keys", "budget"}
        if (
            not isinstance(reference_input, dict) or set(reference_input) != expected
            or not isinstance(phase_input, dict) or set(phase_input) != expected
        ):
            return cls._error("UNIT_ECONOMICS_SNAPSHOT_PAIR_INVALID")
        try:
            reference = cls.build_snapshot(**reference_input)
            phase = cls.build_snapshot(**phase_input)
        except (TypeError, ValueError):
            return cls._error("UNIT_ECONOMICS_SNAPSHOT_PAIR_INVALID")
        if reference.get("error") or phase.get("error"):
            return cls._error("UNIT_ECONOMICS_SNAPSHOT_PAIR_INVALID")
        if reference["identity"] != phase["identity"]:
            return cls._error("UNIT_ECONOMICS_SNAPSHOT_PAIR_IDENTITY_MISMATCH")
        if (
            reference["scope_kind"] != "REFERENCE_56_COMPLETED_LOCAL_DAYS"
            or phase["scope_kind"] != "EXPERIMENT_PHASE_WINDOW"
        ):
            return cls._error("UNIT_ECONOMICS_SNAPSHOT_PAIR_SCOPE_INVALID")
        reference_denominator = reference["denominator"]
        phase_denominator = phase["denominator"]
        denominator_compatible = (
            reference_denominator["kind"] is not None
            and reference_denominator["kind"] == phase_denominator["kind"]
            and reference_denominator["units"] > 0 and phase_denominator["units"] > 0
        )
        return {
            "error": False,
            "status": "COMPLETE" if reference["coverage"]["complete"] and phase["coverage"]["complete"]
            else "INCOMPLETE",
            "reference": reference,
            "phase": phase,
            "combined": False,
            "comparison_eligibility": "DENOMINATOR_COMPATIBLE" if denominator_compatible else "INCOMPARABLE",
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _validate_request(cls, window_spec, identity, segments, required_keys, budget):
        identity_keys = {"owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema"}
        if (
            not isinstance(identity, dict) or set(identity) != identity_keys
            or any(not isinstance(value, str) or not value or len(value) > 128 for value in identity.values())
            or identity.get("sale_schema") not in {"FBO", "FBS"}
            or not isinstance(window_spec, dict)
            or set(window_spec) - {"error"} != {
                "scope_kind", "window", "as_of_local_date", "requested_days",
            }
            or "error" in window_spec and window_spec["error"] is not False
            or not isinstance(window_spec.get("window"), dict)
            or set(window_spec["window"]) != {"from_date", "to_date", "date_basis", "timezone"}
            or window_spec.get("scope_kind") not in {
                "REFERENCE_56_COMPLETED_LOCAL_DAYS", "EXPERIMENT_PHASE_WINDOW",
            }
            or not isinstance(segments, list) or not segments or len(segments) > cls.MAX_SEGMENTS
            or not isinstance(required_keys, list) or not required_keys
            or len(required_keys) > cls.MAX_COMPONENTS
        ):
            return None
        start = cls._date(window_spec["window"].get("from_date"))
        end = cls._date(window_spec["window"].get("to_date"))
        as_of = cls._date(window_spec.get("as_of_local_date"))
        zone = cls._timezone(window_spec["window"].get("timezone"))
        if (
            start is None or end is None or as_of is None or zone is None or start > end
            or window_spec["window"].get("date_basis") != "LOCAL_CALENDAR_DAY"
            or (end - start).days + 1 > cls.REFERENCE_DAYS
        ):
            return None
        days = (end - start).days + 1
        if type(window_spec.get("requested_days")) is not int or window_spec["requested_days"] != days:
            return None
        scope = window_spec["scope_kind"]
        if scope == "REFERENCE_56_COMPLETED_LOCAL_DAYS" and (
            days != cls.REFERENCE_DAYS or end != as_of - timedelta(days=1)
        ):
            return None
        if scope == "EXPERIMENT_PHASE_WINDOW" and (
            days > cls.MAX_PHASE_DAYS or end >= as_of
        ):
            return None
        keys = []
        for key in required_keys:
            if not isinstance(key, str) or cls._KEY_RE.fullmatch(key) is None or key in keys:
                return None
            keys.append(key)
        budget = cls._validate_budget(budget)
        if budget is None:
            return None
        normalized = []
        for value in segments:
            segment = cls._validate_segment(value, identity, start, end, keys)
            if segment is None:
                return None
            normalized.append(segment)
        normalized.sort(key=lambda item: item["start"])
        return ({"scope_kind": scope, "start": start, "end": end, "as_of": as_of,
                 "timezone": zone}, dict(identity), normalized, keys, budget)

    @classmethod
    def _validate_segment(cls, value, identity, start, end, required_keys):
        fields = {"identity", "from_date", "to_date", "components", "quantity", "coverage", "source_revisions"}
        if not isinstance(value, dict) or set(value) != fields or value.get("identity") != identity:
            return None
        seg_start = cls._date(value.get("from_date"))
        seg_end = cls._date(value.get("to_date"))
        components = value.get("components")
        quantity = value.get("quantity")
        coverage = value.get("coverage")
        revisions = value.get("source_revisions")
        if (
            seg_start is None or seg_end is None or seg_start > seg_end or seg_start < start or seg_end > end
            or (seg_end - seg_start).days + 1 > cls.REFERENCE_DAYS
            or not isinstance(components, dict) or len(components) != len(required_keys)
            or set(components) != set(required_keys)
            or not isinstance(quantity, dict) or set(quantity) != {"status", "units", "denominator_kind"}
            or quantity.get("status") not in {"COMPLETE", "PARTIAL", "UNAVAILABLE", "CONFLICT"}
            or not isinstance(coverage, dict) or set(coverage) != {"complete", "page_count", "stop_reason"}
            or type(coverage.get("complete")) is not bool
            or type(coverage.get("page_count")) is not int or not 0 <= coverage["page_count"] <= 10_000
            or not isinstance(coverage.get("stop_reason"), str)
            or cls._KEY_RE.fullmatch(coverage["stop_reason"]) is None
            or not isinstance(revisions, list) or not revisions or len(revisions) > cls.MAX_COMPONENTS
            or any(not isinstance(item, str) or cls._REVISION_RE.fullmatch(item) is None for item in revisions)
        ):
            return None
        units = quantity.get("units")
        kind = quantity.get("denominator_kind")
        if quantity["status"] == "COMPLETE":
            if type(units) is not int or not 0 <= units <= cls.MAX_UNITS or kind not in cls.DENOMINATORS:
                return None
        elif units is not None or kind not in {None, "UNKNOWN"}:
            return None
        normalized_components = {}
        component_statuses = {
            "PRESENT", "CONFIRMED_ZERO", "MISSING", "UNAVAILABLE", "PARTIAL",
            "CONFLICT", "REVIEW_REQUIRED",
        }
        for key, component in components.items():
            if (
                not isinstance(component, dict) or set(component) != {"status", "amount_rub"}
                or component.get("status") not in component_statuses
            ):
                return None
            amount = cls._amount(component.get("amount_rub"))
            status = component["status"]
            if status in {"PRESENT", "CONFIRMED_ZERO", "REVIEW_REQUIRED"}:
                if amount is None or status == "CONFIRMED_ZERO" and amount != 0:
                    return None
            elif component.get("amount_rub") is not None:
                return None
            if status == "PRESENT" and amount < 0:
                status = "REVIEW_REQUIRED"
            normalized_components[key] = {"status": status, "amount": amount}
        complete = (
            coverage["complete"] and coverage["page_count"] > 0 and quantity["status"] == "COMPLETE"
            and all(item["status"] in {"PRESENT", "CONFIRMED_ZERO"} for item in normalized_components.values())
        )
        return {
            "start": seg_start, "end": seg_end, "days": (seg_end - seg_start).days + 1,
            "components": normalized_components, "units": units if complete else 0,
            "denominator_kind": kind if complete else None, "complete": complete,
            "source_revision": cls._fingerprint(sorted(revisions)),
            "coverage": dict(coverage),
            "quantity_status": quantity["status"],
        }

    @classmethod
    def _validate_budget(cls, value):
        fields = {
            "remaining_seconds", "requests_reserved", "request_limit",
            "total_requests_reserved", "total_request_limit", "stop_reason", "http_429_count",
        }
        if not isinstance(value, dict) or set(value) != fields:
            return None
        remaining = value.get("remaining_seconds")
        requests = value.get("requests_reserved")
        limit = value.get("request_limit")
        total_requests = value.get("total_requests_reserved")
        total_limit = value.get("total_request_limit")
        stop = value.get("stop_reason")
        retries = value.get("http_429_count")
        if (
            type(remaining) not in {float, int} or not 0 <= remaining <= cls.MAX_SECONDS
            or type(requests) is not int or not 0 <= requests <= cls.MAX_HTTP_ATTEMPTS
            or type(limit) is not int or not 0 <= limit <= cls.MAX_HTTP_ATTEMPTS
            or requests > limit or not isinstance(stop, str)
            or type(total_requests) is not int or not 0 <= total_requests <= cls.MAX_HTTP_ATTEMPTS
            or type(total_limit) is not int or not 0 <= total_limit <= cls.MAX_HTTP_ATTEMPTS
            or total_requests > total_limit
            or stop not in {
                "NONE", "HTTP_429", "TIME_BUDGET_EXHAUSTED", "REQUEST_BUDGET_EXHAUSTED",
                "SOURCE_READ_FAILED", "SOURCE_EVIDENCE_LIMIT_EXCEEDED",
            }
            or type(retries) is not int or not 0 <= retries <= cls.MAX_HTTP_ATTEMPTS
        ):
            return None
        if retries and stop != "HTTP_429":
            return None
        return {
            "remaining_seconds": round(float(remaining), 3), "requests_reserved": requests,
            "request_limit": limit, "total_requests_reserved": total_requests,
            "total_request_limit": total_limit, "stop_reason": stop, "http_429_count": retries,
        }

    @classmethod
    def _snapshot_status(cls, spec, complete, observed_days, requested_days, budget, mixed, short_history):
        if mixed:
            return "INCOMPARABLE"
        if budget["stop_reason"] == "HTTP_429" or budget["http_429_count"]:
            return "RATE_LIMITED"
        if budget["stop_reason"] == "TIME_BUDGET_EXHAUSTED":
            return "TIME_BUDGET_EXHAUSTED"
        if budget["stop_reason"] == "REQUEST_BUDGET_EXHAUSTED":
            return "REQUEST_BUDGET_EXHAUSTED"
        if budget["stop_reason"] != "NONE":
            return "PARTIAL"
        if complete:
            return "COMPLETE"
        if (
            spec["scope_kind"] == "REFERENCE_56_COMPLETED_LOCAL_DAYS"
            and short_history
        ):
            return "SHORT_HISTORY"
        return "PARTIAL" if observed_days else "UNAVAILABLE"

    @classmethod
    def _trace_budget(cls, trace, stop_reason):
        chain = []
        current = trace
        while current is not None:
            chain.append(current)
            current = current.parent
        limit = min(item.ozon_request_budget for item in chain)
        parent_limits = [item.ozon_request_budget for item in chain[1:]]
        total_limit = min([cls.MAX_HTTP_ATTEMPTS, *parent_limits])
        used = max(item.ozon_requests_reserved for item in chain)
        remaining = trace.remaining_seconds()
        code = trace.budget_reason_code
        if stop_reason == "NONE" and code in {"TIME_BUDGET_EXHAUSTED", "HTTP_ATTEMPT_BUDGET_EXHAUSTED"}:
            stop_reason = "TIME_BUDGET_EXHAUSTED" if code == "TIME_BUDGET_EXHAUSTED" else "REQUEST_BUDGET_EXHAUSTED"
        return {
            "remaining_seconds": min(cls.MAX_SECONDS, max(0.0, remaining)),
            "requests_reserved": min(cls.MAX_HTTP_ATTEMPTS, trace.ozon_requests_reserved),
            "request_limit": min(cls.MAX_HTTP_ATTEMPTS, trace.ozon_request_budget),
            "total_requests_reserved": min(cls.MAX_HTTP_ATTEMPTS, used),
            "total_request_limit": total_limit,
            "stop_reason": stop_reason,
            "http_429_count": 1 if stop_reason == "HTTP_429" else 0,
        }

    @classmethod
    def _bounded_evidence(cls, value, max_nodes):
        forbidden = {
            "api_key", "client_id", "credentials", "raw", "raw_response", "response",
            "data", "items", "rows", "result", "posting", "posting_id", "posting_number",
            "return", "return_id", "order_id", "shipment_id", "barcode", "name",
            "product_name", "token", "authorization",
        }
        node_count = 0

        def visit(item, depth):
            nonlocal node_count
            node_count += 1
            if node_count > max_nodes or depth > 8:
                return None
            if item is None or type(item) in {bool, int}:
                return item
            if isinstance(item, float):
                return item if math.isfinite(item) else None
            if isinstance(item, str):
                return item if len(item) <= 512 else None
            if isinstance(item, list):
                if len(item) > 10_000:
                    return None
                values = [visit(child, depth + 1) for child in item]
                has_rejected_child = any(
                    child is None and original is not None
                    for child, original in zip(values, item)
                )
                return None if has_rejected_child else values
            if isinstance(item, dict):
                has_forbidden_key = any(
                    not isinstance(key, str)
                    or not key
                    or len(key) > 128
                    or key.lower() in forbidden
                    for key in item
                )
                if len(item) > 128 or has_forbidden_key:
                    return None
                values = {key: visit(child, depth + 1) for key, child in item.items()}
                if any(values[key] is None and item[key] is not None for key in item):
                    return None
                return values
            return None

        if not isinstance(value, dict):
            return None, node_count
        return visit(value, 0), node_count

    @classmethod
    def _budget_stop_reason(cls, trace):
        return "TIME_BUDGET_EXHAUSTED" if trace.remaining_seconds() <= 0 else "REQUEST_BUDGET_EXHAUSTED"

    @classmethod
    def _window(cls, start, end, zone):
        return {
            "from_date": start.isoformat(), "to_date": end.isoformat(),
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": zone,
        }

    @classmethod
    def _timezone(cls, value):
        if not isinstance(value, str) or not value or len(value) > 64:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            return None
        return value

    @staticmethod
    def _date(value):
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.isoformat() == value else None

    @classmethod
    def _amount(cls, value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if not amount.is_finite() or abs(amount) > cls.MAX_AMOUNT:
            return None
        return amount.quantize(cls.QUANTUM, rounding=ROUND_HALF_UP)

    @classmethod
    def _rate(cls, numerator, denominator):
        if type(denominator) is not int or denominator <= 0:
            return None
        return cls._money(numerator / Decimal(denominator))

    @classmethod
    def _money(cls, value):
        return format(value.quantize(cls.QUANTUM, rounding=ROUND_HALF_UP), ".2f")

    @staticmethod
    def _fingerprint(value):
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
