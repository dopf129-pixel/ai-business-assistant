from datetime import date, timedelta

from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    current_period_profit_trace,
)
from services.unit_economics_window_snapshot_service import UnitEconomicsWindowSnapshotService as Service
from services.unit_economics_readiness_view_service import UnitEconomicsReadinessViewService


IDENTITY = {
    "owner_id": "owner-1", "store_id": "store-1", "product_id": "product-1",
    "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
}
BUDGET = {
    "remaining_seconds": 30.0, "requests_reserved": 2, "request_limit": 128,
    "total_requests_reserved": 2, "total_request_limit": 128,
    "stop_reason": "NONE", "http_429_count": 0,
}


def _segment(start, end, amount, units, *, status="COMPLETE", denominator="SOLD_UNITS_WINDOW"):
    return {
        "identity": dict(IDENTITY),
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "components": {"ADS": {"status": "PRESENT", "amount_rub": str(amount)}},
        "quantity": {
            "status": status,
            "units": units if status == "COMPLETE" else None,
            "denominator_kind": denominator if status == "COMPLETE" else None,
        },
        "coverage": {"complete": status == "COMPLETE", "page_count": 1, "stop_reason": "END_OF_DATA"},
        "source_revisions": ["rev-1"],
    }


def _full_reference(as_of="2026-02-26"):
    return Service.reference_window(as_of, "Europe/Moscow")


def test_reference_window_is_exact_56_completed_local_days():
    result = _full_reference()
    assert result["error"] is False
    assert result["window"] == {
        "from_date": "2026-01-01", "to_date": "2026-02-25",
        "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
    }
    assert result["requested_days"] == 56


def test_weighted_rate_uses_total_numerator_over_total_units():
    spec = _full_reference()
    start = date.fromisoformat(spec["window"]["from_date"])
    segments = [
        _segment(start, start + timedelta(days=9), 100, 10),
        _segment(start + timedelta(days=10), date.fromisoformat(spec["window"]["to_date"]), 100, 100),
    ]
    result = Service.build_snapshot(spec, IDENTITY, segments, ["ADS"], BUDGET)
    assert result["error"] is False
    assert result["coverage"]["status"] == "COMPLETE"
    assert result["components"]["ADS"]["observed_numerator_rub"] == "200.00"
    assert result["denominator"] == {"units": 110, "kind": "SOLD_UNITS_WINDOW"}
    assert result["total_unit_expense_rub"] == "1.82"
    assert result["total_unit_expense_rub"] != "5.50"
    assert len(result["source_revision"]) == 64
    assert len(result["coverage"]["segments"][0]["source_revision"]) == 64


def test_zero_units_keeps_complete_money_but_does_not_invent_zero_rate():
    spec = _full_reference()
    start = date.fromisoformat(spec["window"]["from_date"])
    end = date.fromisoformat(spec["window"]["to_date"])
    result = Service.build_snapshot(spec, IDENTITY, [_segment(start, end, 12, 0)], ["ADS"], BUDGET)
    assert result["coverage"]["status"] == "COMPLETE"
    assert result["observed_total_expense_rub"] == "12.00"
    assert result["rate_status"] == "ZERO_DENOMINATOR"
    assert result["total_unit_expense_rub"] is None


def test_reference_and_phase_are_kept_as_separate_windows():
    reference = _full_reference()
    phase = Service.phase_window("2026-02-01", "2026-02-07", "2026-02-26", "Europe/Moscow")
    ref_start = date.fromisoformat(reference["window"]["from_date"])
    ref_end = date.fromisoformat(reference["window"]["to_date"])
    phase_start = date.fromisoformat(phase["window"]["from_date"])
    phase_end = date.fromisoformat(phase["window"]["to_date"])
    pair = Service.build_pair(
        {"window_spec": reference, "identity": IDENTITY,
         "segments": [_segment(ref_start, ref_end, 500, 100)],
         "required_component_keys": ["ADS"], "budget": BUDGET},
        {"window_spec": phase, "identity": IDENTITY,
         "segments": [_segment(phase_start, phase_end, 70, 10)],
         "required_component_keys": ["ADS"], "budget": BUDGET},
    )
    assert pair["error"] is False
    assert pair["status"] == "COMPLETE"
    assert pair["combined"] is False
    assert pair["comparison_eligibility"] == "DENOMINATOR_COMPATIBLE"
    assert pair["reference"]["total_unit_expense_rub"] == "5.00"
    assert pair["phase"]["total_unit_expense_rub"] == "7.00"


def test_short_reference_history_is_labeled_and_not_used_as_full_56_day_rate():
    spec = _full_reference()
    end = date.fromisoformat(spec["window"]["to_date"])
    start = end - timedelta(days=20)
    result = Service.build_snapshot(
        spec, IDENTITY, [_segment(start, end, 100, 50)], ["ADS"], BUDGET,
    )
    assert result["coverage"]["status"] == "SHORT_HISTORY"
    assert result["coverage"]["full_requested_window"] is False
    assert result["observed_days"] == 21
    assert result["observed_window"] == {"from_date": start.isoformat(), "to_date": end.isoformat()}
    assert result["observed_total_unit_expense_rub"] == "2.00"
    assert result["total_unit_expense_rub"] is None

    incomplete = _segment(start, end, 100, 50, status="PARTIAL")
    incomplete["quantity"] = {"status": "PARTIAL", "units": None, "denominator_kind": None}
    incomplete["coverage"] = {"complete": False, "page_count": 1, "stop_reason": "MORE_PAGES"}
    partial = Service.build_snapshot(spec, IDENTITY, [incomplete], ["ADS"], BUDGET)
    assert partial["coverage"]["status"] == "PARTIAL"


def test_mixed_denominators_and_cross_docking_denominator_are_rejected_as_incomparable():
    spec = _full_reference()
    start = date.fromisoformat(spec["window"]["from_date"])
    middle = start + timedelta(days=27)
    end = date.fromisoformat(spec["window"]["to_date"])
    mixed = Service.build_snapshot(
        spec, IDENTITY,
        [_segment(start, middle, 50, 10), _segment(middle + timedelta(days=1), end, 50, 10,
                                                   denominator="ORDERED_UNITS_WINDOW")],
        ["ADS"], BUDGET,
    )
    assert mixed["coverage"]["status"] == "INCOMPARABLE"
    assert mixed["total_unit_expense_rub"] is None
    supplied = _segment(start, end, 100, 50, denominator="SUPPLIED_UNITS_CROSS_DOCKING")
    assert Service.build_snapshot(spec, IDENTITY, [supplied], ["ADS"], BUDGET)["error"] is True


def test_gap_or_incomplete_pages_do_not_become_full_window():
    spec = _full_reference()
    start = date.fromisoformat(spec["window"]["from_date"])
    end = date.fromisoformat(spec["window"]["to_date"])
    gap = start + timedelta(days=10)
    result = Service.build_snapshot(
        spec, IDENTITY,
        [_segment(start, gap - timedelta(days=1), 10, 10),
         _segment(gap + timedelta(days=1), end, 10, 10)],
        ["ADS"], BUDGET,
    )
    assert result["coverage"]["status"] == "PARTIAL"
    assert result["total_unit_expense_rub"] is None
    partial = _segment(start, end, 20, 10, status="PARTIAL")
    partial["quantity"] = {"status": "PARTIAL", "units": None, "denominator_kind": None}
    partial["coverage"] = {"complete": False, "page_count": 1, "stop_reason": "HTTP_429"}
    limited = Service.build_snapshot(spec, IDENTITY, [partial], ["ADS"], {
        **BUDGET, "stop_reason": "HTTP_429", "http_429_count": 1,
    })
    assert limited["coverage"]["status"] == "RATE_LIMITED"
    assert limited["coverage"]["complete"] is False


def test_partial_segment_covering_tail_dates_does_not_make_window_complete():
    spec = _full_reference()
    start = date.fromisoformat(spec["window"]["from_date"])
    end = date.fromisoformat(spec["window"]["to_date"])
    complete = _segment(start, start + timedelta(days=27), 100, 100)
    partial = _segment(start + timedelta(days=28), end, 900, 100, status="PARTIAL")
    partial["quantity"] = {
        "status": "PARTIAL", "units": None, "denominator_kind": None,
    }
    partial["coverage"] = {
        "complete": False, "page_count": 1, "stop_reason": "MORE_PAGES",
    }

    result = Service.build_snapshot(
        spec, IDENTITY, [complete, partial], ["ADS"], BUDGET,
    )

    assert result["coverage"]["full_requested_window"] is True
    assert result["coverage"]["status"] == "PARTIAL"
    assert result["coverage"]["complete"] is False
    assert result["complete_days"] == 28
    assert result["total_unit_expense_rub"] is None
    component = result["components"]["ADS"]
    assert component["status"] == "PARTIAL"
    assert component["observed_unit_expense_rub"] == "1.00"
    assert component["unit_expense_rub"] is None
    assert component["covered_days"] == 28
    projected = UnitEconomicsReadinessViewService.build(
        result, {"ADS": {"source": "OZON_PERFORMANCE", "applicability": "WINDOW_MODEL_INPUT"}},
    )
    assert projected["error"] is False
    assert projected["status"] == "PARTIAL"
    assert projected["components"][0]["evidence_status"] == "PARTIAL"
    assert projected["components"][0]["status"] == "UNKNOWN"


def test_identity_mismatch_overlap_and_negative_credit_fail_closed():
    spec = _full_reference()
    start = date.fromisoformat(spec["window"]["from_date"])
    end = date.fromisoformat(spec["window"]["to_date"])
    overlap = [_segment(start, end, 100, 10), _segment(start, end, 100, 10)]
    assert Service.build_snapshot(spec, IDENTITY, overlap, ["ADS"], BUDGET)["code"] == (
        "UNIT_ECONOMICS_WINDOW_SEGMENTS_OVERLAP"
    )
    mismatch = _segment(start, end, 100, 10)
    mismatch["identity"]["store_id"] = "other-store"
    assert Service.build_snapshot(spec, IDENTITY, [mismatch], ["ADS"], BUDGET)["error"] is True
    credit = _segment(start, end, -1, 10)
    assert Service.build_snapshot(spec, IDENTITY, [credit], ["ADS"], BUDGET)["coverage"]["status"] == "PARTIAL"
    assert Service.build_snapshot(spec, IDENTITY, [credit], ["ADS"], BUDGET)["total_unit_expense_rub"] is None


def test_phase_requires_completed_local_dates_and_maximum_28_days():
    assert Service.phase_window("2026-02-20", "2026-02-26", "2026-02-26", "Europe/Moscow")["error"]
    assert Service.phase_window("2026-01-01", "2026-01-29", "2026-02-01", "Europe/Moscow")["error"]
    assert Service.phase_window("2026-02-01", "2026-02-07", "2026-02-26", "Not/AZone")["error"]


def test_reader_collector_shares_parent_trace_and_stops_after_rate_limit():
    parent = PeriodProfitOperationTrace(ozon_request_budget=300)
    parent.reserve_ozon_request("already-used")
    called = []

    def first_reader():
        called.append("first")
        trace = current_period_profit_trace()
        assert trace is not None
        assert trace.reserve_ozon_request("mock-source")["error"] is False
        return {"status": "COMPLETE", "evidence_revision": "rev-1"}

    def limited_reader():
        called.append("limited")
        trace = current_period_profit_trace()
        assert trace.reserve_ozon_request("mock-429")["error"] is False
        return {"status": "RATE_LIMITED"}

    def must_not_run():
        called.append("later")
        return {"status": "COMPLETE"}

    result = Service.collect_sources(
        [("FINANCE", first_reader), ("RETURNS", limited_reader), ("ADS", must_not_run)],
        parent_trace=parent,
    )
    assert result["status"] == "PARTIAL"
    assert result["budget"]["stop_reason"] == "HTTP_429"
    assert result["budget"]["http_429_count"] == 1
    assert result["budget"]["requests_reserved"] == 2
    assert result["budget"]["request_limit"] == 127
    assert result["budget"]["total_requests_reserved"] == 3
    assert result["budget"]["total_request_limit"] == 128
    assert parent.ozon_requests_reserved == 3
    assert called == ["first", "limited"]
    assert result["not_started_source_keys"] == ["ADS"]


def test_reader_collector_respects_already_exhausted_parent_budget():
    parent = PeriodProfitOperationTrace(ozon_request_budget=1)
    parent.reserve_ozon_request("used")
    called = []
    result = Service.collect_sources([("FINANCE", lambda: called.append("called"))], parent_trace=parent)
    assert result["status"] == "PARTIAL"
    assert result["budget"]["stop_reason"] == "REQUEST_BUDGET_EXHAUSTED"
    assert called == []


def test_reader_collection_stops_later_sources_when_shared_time_budget_expires():
    class FakeClock:
        value = 0.0

        def __call__(self):
            return self.value

    clock = FakeClock()
    parent = PeriodProfitOperationTrace(
        clock=clock, time_budget_seconds=600, ozon_request_budget=300,
    )
    called = []

    def slow_reader():
        called.append("finance")
        trace = current_period_profit_trace()
        assert trace.reserve_ozon_request("mock-source")["error"] is False
        clock.value = 121.0
        return {"status": "COMPLETE"}

    def later_reader():
        called.append("returns")
        return {"status": "COMPLETE"}

    result = Service.collect_sources(
        [("FINANCE", slow_reader), ("RETURNS", later_reader)], parent_trace=parent,
    )
    assert result["status"] == "PARTIAL"
    assert result["budget"]["stop_reason"] == "TIME_BUDGET_EXHAUSTED"
    assert result["sources"][-1]["status"] == "TIME_BUDGET_EXHAUSTED"
    assert result["not_started_source_keys"] == ["RETURNS"]
    assert called == ["finance"]


def test_reader_collection_rejects_duplicate_source_keys():
    result = Service.collect_sources([("FINANCE", lambda: {}), ("FINANCE", lambda: {})])
    assert result["error"] is True
    assert result["code"] == "UNIT_ECONOMICS_SOURCE_READER_DUPLICATE"


def test_reader_collection_rejects_raw_response_containers():
    result = Service.collect_sources([("FINANCE", lambda: {"status": "COMPLETE", "rows": []})])
    assert result["status"] == "PARTIAL"
    assert result["sources"] == [{"source_key": "FINANCE", "status": "SOURCE_EVIDENCE_INVALID"}]


def test_reader_collection_enforces_aggregate_evidence_size_cap():
    oversized = {"status": "COMPLETE", "chunks": ["x" * 512 for _ in range(150)]}
    result = Service.collect_sources([("FINANCE", lambda: oversized)])
    assert result["status"] == "PARTIAL"
    assert result["budget"]["stop_reason"] == "SOURCE_EVIDENCE_LIMIT_EXCEEDED"
    assert result["sources"] == [{"source_key": "FINANCE", "status": "SOURCE_EVIDENCE_LIMIT_EXCEEDED"}]


def test_incomplete_source_does_not_mark_collection_complete():
    called = []
    result = Service.collect_sources([
        ("FINANCE", lambda: {"status": "INCOMPLETE"}),
        ("RETURNS", lambda: called.append("returns") or {"status": "COMPLETE"}),
    ])
    assert result["status"] == "PARTIAL"
    assert called == ["returns"]
    assert result["not_started_source_keys"] == []
