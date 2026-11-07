from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from services.fifo_cost_source_collection_service import (
    FifoCostSourceCollectionService,
)
from services.fifo_cost_transition_contracts import (
    SupplyReferenceKind,
    supply_reference_digest,
)
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    current_period_profit_trace,
)


IDENTITY = {"product_id": "101", "offer_id": "hook-2", "sku": "3921245627"}


class _FakeOzonClient:
    def __init__(self):
        self.calls = []
        self.list_pages = []
        self.details_by_id = {}
        self.summary = None
        self.products = None
        self.request_options = []
        self.list_state_filters = []
        self.stock_response = {
            "total_items": 1,
            "items": [{
                "product_id": 101,
                "stocks": [{"type": "fbo", "present": 300, "reserved": 40}],
            }],
        }
        self.on_request = None

    def _request(self, method, observer):
        self.calls.append(method)
        trace = current_period_profit_trace()
        if trace is not None:
            reservation = trace.reserve_ozon_request("/synthetic")
            if reservation.get("error") is True:
                return {"error": True, "code": reservation.get("code")}
        if callable(observer):
            observer("/synthetic")
        if callable(self.on_request):
            self.on_request(method)
        return None

    def get_product_stocks(self, _product_id, **options):
        self.request_options.append(options)
        error = self._request("stocks", options.get("request_attempt_observer"))
        if error:
            return error
        return self.stock_response

    def get_supply_orders_list(self, _states, *, last_id=None, **options):
        self.request_options.append(options)
        self.list_state_filters.append(tuple(_states))
        error = self._request("list", options.get("request_attempt_observer"))
        if error:
            return error
        if not self.list_pages:
            return {"error": True, "code": "OZON_HTTP_ERROR"}
        page = self.list_pages.pop(0)
        return page(last_id) if callable(page) else page

    def get_supply_orders_details(self, order_ids, **options):
        self.request_options.append(options)
        error = self._request("details", options.get("request_attempt_observer"))
        if error:
            return error
        return {"orders": [self.details_by_id[str(value)] for value in order_ids]}

    def get_supply_act_summary(self, _order_id, **options):
        self.request_options.append(options)
        error = self._request("summary", options.get("request_attempt_observer"))
        if error:
            return error
        return self.summary

    def get_supply_act_products(self, _supply_id, **options):
        self.request_options.append(options)
        error = self._request("products", options.get("request_attempt_observer"))
        if error:
            return error
        return self.products


def _service(client=None, **kwargs):
    return FifoCostSourceCollectionService(
        ozon_client=client or _FakeOzonClient(),
        utc_clock=lambda: datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc),
        **kwargs,
    )


def _completed_order(order_id=11, supplies=None):
    return {
        "order_id": order_id,
        "state": "COMPLETED",
        "supplies": supplies or [],
    }


def _accepted_act(
    *, sku=3921245627, quantity=100, declared_quantity=None,
    approved_quantity=None, created_date=None,
):
    product_item = {"sku_info": {"sku": sku}, "fact_quantity": quantity,
                    "unidentified_quantity": 0}
    if declared_quantity is not None:
        product_item["declared_quantity"] = declared_quantity
    if approved_quantity is not None:
        product_item["approved_quantity"] = approved_quantity
    summary_act = {
        "act_id": 3001,
        "type": "ACCEPTANCE",
        "act_state": "ACCEPTED",
        "summary": {"fact_quantity": quantity, "unidentified_quantity": 0},
    }
    if created_date is not None:
        summary_act["created_date"] = created_date
    summary = {"supplies_acts": [{
        "supply_id": 2001,
        "is_agreement_completed": True,
        "supply_acts": [summary_act],
    }]}
    products = {"supply_acts": [{
        "act_id": 3001,
        "type": "ACCEPTANCE",
        "items": [product_item],
    }]}
    return summary, products


def test_stock_collection_is_explicit_bounded_and_fail_closed():
    client = _FakeOzonClient()
    service = _service(client)

    result = service.collect_stock_snapshot(
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        identity_mapping_confirmed=False,
    )

    assert client.calls == ["stocks"]
    assert result.actual_http_attempts == 1
    assert result.http_attempt_cap == 1
    assert result.read_only is True
    assert result.status == "PARTIAL"
    assert result.stock_snapshot.fbo_units == 300
    assert result.stock_snapshot.reserved_units == 40
    assert result.stock_snapshot.available_units is None
    assert result.stock_snapshot.source_as_of is None
    assert result.stock_snapshot.anchor_eligible is False
    assert client.request_options[0]["limit"] == 100
    assert client.request_options[0]["max_attempts"] == 1
    assert client.request_options[0]["timeout"] <= 8
    assert client.request_options[0]["total_timeout"] <= 10


def test_stock_collection_confirms_zero_only_with_explicit_owner_scope_flags():
    client = _FakeOzonClient()
    client.stock_response = {
        "total_items": 1,
        "items": [{
            "product_id": 101,
            "stocks": [
                {"type": "fbo", "present": 0, "reserved": 0},
                {"type": "fbs", "present": 0, "reserved": 0},
            ],
        }],
    }
    result = _service(client).collect_stock_snapshot(
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        identity_mapping_confirmed=True,
        owner_confirmed_stock_semantics=True,
        owner_confirmed_zero_transit=True,
    )

    assert result.status == "CONFIRMED_ZERO"
    assert result.source_status == "COMPLETE"
    assert result.stock_snapshot.fbo_units == 0
    assert result.stock_snapshot.reserved_units == 0
    assert result.stock_snapshot.transit_units == 0
    assert result.stock_snapshot.transit_status == "DISJOINT_CONFIRMED"
    assert "INVENTORY_CUTOFF_UNRECONCILED" in result.stock_snapshot.issue_codes


def test_stock_collection_does_not_confirm_zero_without_explicit_fbo_row():
    client = _FakeOzonClient()
    client.stock_response = {
        "total_items": 1,
        "items": [{
            "product_id": 101,
            "stocks": [{"type": "fbs", "present": 0, "reserved": 0}],
        }],
    }

    result = _service(client).collect_stock_snapshot(
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        identity_mapping_confirmed=True,
        owner_confirmed_stock_semantics=True,
        owner_confirmed_zero_transit=True,
    )

    assert result.status == "PARTIAL"
    assert result.source_status == "PARTIAL"
    assert result.stock_snapshot.status == "PARTIAL"
    assert result.stock_snapshot.fbo_units is None
    assert result.stock_snapshot.reserved_units is None
    assert result.stock_snapshot.available_units is None
    assert "FBO_STOCK_ROW_MISSING" in result.stock_snapshot.issue_codes


def test_stock_page_gap_is_not_reported_as_complete():
    client = _FakeOzonClient()
    client.stock_response["total_items"] = 2
    service = _service(client)

    result = service.collect_stock_snapshot(
        identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "PARTIAL"
    assert result.stock_snapshot.pagination_complete is False
    assert result.stock_snapshot.fbo_units is None
    assert result.actual_http_attempts == 1


def test_parent_time_budget_blocks_call_without_an_http_attempt():
    client = _FakeOzonClient()
    trace = PeriodProfitOperationTrace(
        operation="test_parent", time_budget_seconds=0, ozon_request_budget=10,
    )
    result = _service(client).collect_stock_snapshot(
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        operation_trace=trace,
    )

    assert result.actual_http_attempts == 0
    assert client.calls == []
    assert result.status == "UNAVAILABLE"


def test_cancelled_parent_stops_before_first_http_attempt():
    client = _FakeOzonClient()
    trace = PeriodProfitOperationTrace(
        operation="test_parent", time_budget_seconds=10, ozon_request_budget=10,
    )
    trace.cancel()
    result = _service(client).find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        operation_trace=trace,
    )

    assert result.actual_http_attempts == 0
    assert client.calls == []
    assert result.status == "UNAVAILABLE"
    assert "FIFO_SOURCE_CANCELLED" in result.issue_codes


def test_cancellation_during_source_call_stops_child_calls():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": "cursor-A"}]
    client.details_by_id["11"] = _completed_order(11)
    parent = PeriodProfitOperationTrace(
        operation="test_parent", time_budget_seconds=10, ozon_request_budget=10,
    )
    client.on_request = lambda method: parent.cancel() if method == "list" else None

    result = _service(client).find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        operation_trace=parent,
    )

    assert result.status == "UNAVAILABLE"
    assert result.actual_http_attempts == 1
    assert parent.ozon_requests_reserved == 1
    assert "FIFO_SOURCE_CANCELLED" in result.issue_codes
    assert client.calls == ["list"]


def test_parent_timeout_after_first_call_stops_next_http_attempt():
    clock_value = [0.0]
    parent = PeriodProfitOperationTrace(
        operation="test_parent",
        time_budget_seconds=1,
        ozon_request_budget=10,
        clock=lambda: clock_value[0],
    )
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": "cursor-A"}]
    client.details_by_id["11"] = _completed_order(11)
    client.on_request = lambda method: clock_value.__setitem__(0, 2.0)

    result = _service(client).find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        operation_trace=parent,
    )

    assert result.status == "PARTIAL"
    assert result.actual_http_attempts == 1
    assert parent.ozon_requests_reserved == 1
    assert result.continuation_token
    assert "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED" in result.issue_codes


def test_supply_lookup_returns_not_found_only_after_complete_search():
    client = _FakeOzonClient()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [], "last_id": None},
    ]
    client.details_by_id["11"] = _completed_order(11)
    service = _service(client)

    first = service.find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
        max_pages_per_call=1,
    )

    assert first.status == "PARTIAL"
    assert first.continuation_token
    assert "cursor-A" not in repr(first)
    assert first.actual_http_attempts == 2

    second = service.find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        checkpoint_token=first.continuation_token,
        max_pages_per_call=1,
    )

    assert second.status == "NOT_FOUND"
    assert second.source_status == "COMPLETE"
    assert second.continuation_token is None
    assert second.actual_http_attempts == 1
    assert "2001" not in repr(second)


def test_replayed_checkpoint_does_not_issue_duplicate_api_calls():
    client = _FakeOzonClient()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [12], "last_id": "cursor-B"},
    ]
    client.details_by_id["11"] = _completed_order(11)
    client.details_by_id["12"] = _completed_order(12)
    service = _service(client)
    first = service.find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
        max_pages_per_call=1,
    )
    second = service.find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        checkpoint_token=first.continuation_token,
        max_pages_per_call=1,
    )
    calls_after_second = list(client.calls)

    replay = service.find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        checkpoint_token=first.continuation_token,
        max_pages_per_call=1,
    )

    assert first.continuation_token
    assert second.continuation_token
    assert replay.status == "CONFLICT"
    assert "FIFO_SUPPLY_CHECKPOINT_STALE" in replay.issue_codes
    assert client.calls == calls_after_second


def test_checkpoint_is_bound_to_owner_store_and_exact_sku():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": "cursor-A"}]
    client.details_by_id["11"] = _completed_order(11)
    service = _service(client)
    first = service.find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
        max_pages_per_call=1,
    )

    mismatch = service.find_supply_by_id(
        2001,
        identity={**IDENTITY, "sku": "3921245628"},
        store_id="store-a",
        tenant_scope="owner:1",
        checkpoint_token=first.continuation_token,
        max_pages_per_call=1,
    )

    assert mismatch.status == "CONFLICT"
    assert "FIFO_SUPPLY_CHECKPOINT_SCOPE_MISMATCH" in mismatch.issue_codes
    assert len(client.calls) == 2


def test_repeated_cursor_fails_closed_with_finite_request_count():
    client = _FakeOzonClient()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [12], "last_id": "cursor-A"},
    ]
    client.details_by_id["11"] = _completed_order(11)
    client.details_by_id["12"] = _completed_order(12)
    result = _service(client).find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "CONFLICT"
    assert "FIFO_SUPPLY_CURSOR_NOT_ADVANCING" in result.issue_codes
    assert result.actual_http_attempts == 3
    assert len(client.calls) == 3


def test_rate_limit_keeps_search_partial_and_continuable():
    client = _FakeOzonClient()
    client.list_pages = [{"error": True, "code": "OZON_RATE_LIMITED"}]
    result = _service(client).find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "PARTIAL"
    assert result.actual_http_attempts == 1
    assert result.http_attempt_cap <= 10
    assert result.continuation_token


def test_found_supply_uses_fact_quantity_and_hides_raw_source_ids():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": None}]
    client.details_by_id["11"] = _completed_order(
        11, [{"supply_id": 2001, "state": "COMPLETED", "is_crossdock": False}],
    )
    client.summary, client.products = _accepted_act()
    result = _service(client).find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "COMPLETE"
    assert result.supply_snapshot.units_by_sku == (("3921245627", 100),)
    assert result.supply_snapshot.effective_at is None
    assert result.supply_snapshot.order_ref
    assert result.supply_snapshot.order_ref != "11"
    assert client.list_state_filters == [("COMPLETED",)]
    assert result.actual_http_attempts == 4
    assert "2001" not in repr(result)
    assert "3001" not in repr(result)
    assert all(options["max_attempts"] == 1 for options in client.request_options)


def test_supply_act_for_another_sku_is_conflict():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": None}]
    client.details_by_id["11"] = _completed_order(
        11, [{"supply_id": 2001, "state": "COMPLETED", "is_crossdock": False}],
    )
    client.summary, client.products = _accepted_act(sku=3921245628)
    result = _service(client).find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "CONFLICT"
    assert "FIFO_SUPPLY_SKU_IDENTITY_MISMATCH" in result.issue_codes
    assert result.actual_http_attempts == 4


def test_stock_request_failure_does_not_retry_around_parent_budget():
    client = _FakeOzonClient()
    client.stock_response = {"error": True, "code": "OZON_RATE_LIMITED"}
    result = _service(client).collect_stock_snapshot(
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        http_attempt_budget=1,
    )

    assert result.status == "UNAVAILABLE"
    assert result.actual_http_attempts == 1
    assert client.calls == ["stocks"]


def test_parent_http_budget_is_shared_with_child_source_calls():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": "cursor-A"}]
    client.details_by_id["11"] = _completed_order(11)
    parent = PeriodProfitOperationTrace(
        operation="test_parent", time_budget_seconds=10, ozon_request_budget=1,
    )

    result = _service(client).find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        operation_trace=parent,
        max_pages_per_call=1,
    )

    assert result.actual_http_attempts == 1
    assert parent.ozon_requests_reserved == 1
    assert client.calls == ["list", "details"]
    assert result.status == "PARTIAL"
    assert result.continuation_token


def test_duplicate_concurrent_stock_collection_is_singleflight():
    client = _FakeOzonClient()
    entered_request = Event()
    release_request = Event()

    def pause_request(method):
        if method == "stocks":
            entered_request.set()
            assert release_request.wait(timeout=2)

    client.on_request = pause_request
    service = _service(client)
    options = {
        "identity": IDENTITY,
        "store_id": "store-a",
        "tenant_scope": "owner:1",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(service.collect_stock_snapshot, **options)
        assert entered_request.wait(timeout=2)
        duplicate = service.collect_stock_snapshot(**options)
        release_request.set()
        first = first_future.result(timeout=2)

    assert first.actual_http_attempts == 1
    assert duplicate.actual_http_attempts == 0
    assert "FIFO_SOURCE_ALREADY_IN_PROGRESS" in duplicate.issue_codes
    assert client.calls == ["stocks"]


@pytest.mark.parametrize(
    ("second_identity", "second_store"),
    [
        (IDENTITY, "store-b"),
        ({**IDENTITY, "offer_id": "other-hook", "sku": "9876543210"}, "store-a"),
    ],
    ids=("different-store", "different-sku"),
)
def test_concurrent_stock_collection_does_not_block_independent_scope(
    second_identity, second_store,
):
    client = _FakeOzonClient()
    first_entered = Event()
    second_entered = Event()
    release_first = Event()
    request_count = [0]

    def pause_first_request(method):
        if method != "stocks":
            return
        request_count[0] += 1
        if request_count[0] == 1:
            first_entered.set()
            assert release_first.wait(timeout=2)
        elif request_count[0] == 2:
            second_entered.set()

    client.on_request = pause_first_request
    service = _service(client)
    first_options = {
        "identity": IDENTITY,
        "store_id": "store-a",
        "tenant_scope": "owner:1",
        "identity_mapping_confirmed": True,
    }
    second_options = {
        "identity": second_identity,
        "store_id": second_store,
        "tenant_scope": "owner:1",
        "identity_mapping_confirmed": True,
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            service.collect_stock_snapshot, **first_options
        )
        assert first_entered.wait(timeout=2)
        second_future = executor.submit(
            service.collect_stock_snapshot, **second_options
        )
        assert second_entered.wait(timeout=2)
        second = second_future.result(timeout=2)
        release_first.set()
        first = first_future.result(timeout=2)

    assert first.actual_http_attempts == 1
    assert second.actual_http_attempts == 1
    assert first.status == second.status == "PARTIAL"
    assert first.stock_snapshot is not None
    assert second.stock_snapshot is not None
    assert request_count[0] == 2


def test_search_page_cap_is_enforced_and_token_expires():
    clock = [0.0]
    client = _FakeOzonClient()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [12], "last_id": "cursor-B"},
    ]
    client.details_by_id["11"] = _completed_order(11)
    client.details_by_id["12"] = _completed_order(12)
    service = _service(client, monotonic_clock=lambda: clock[0])
    first = service.find_supply_by_id(
        2001, identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
        max_pages_per_call=1,
    )
    assert first.continuation_token

    clock[0] += service.CHECKPOINT_TTL_SECONDS + 1
    expired = service.find_supply_by_id(
        2001,
        identity=IDENTITY,
        store_id="store-a",
        tenant_scope="owner:1",
        checkpoint_token=first.continuation_token,
    )

    assert expired.status == "CONFLICT"
    assert "FIFO_SUPPLY_CHECKPOINT_EXPIRED" in expired.issue_codes
    assert len(client.calls) == 2


def test_active_supply_observer_finds_receiving_without_requesting_receipt_units():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": None}]
    client.details_by_id["11"] = {
        "order_id": 11,
        "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "supplies": [{
            "supply_id": 2001,
            "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
            "is_crossdock": True,
        }],
    }

    result = _service(client).observe_active_supply_by_id(
        2001, owner_id="owner-a",
        identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "PRESENT"
    assert result.source_status == "COMPLETE"
    assert result.actual_http_attempts == 2
    assert result.supply_snapshot.presence == "PRESENT"
    assert result.supply_snapshot.raw_status == "ACCEPTANCE_AT_STORAGE_WAREHOUSE"
    assert result.supply_snapshot.normalized_status == "RECEIVING"
    assert result.supply_snapshot.supply_reference_digest == supply_reference_digest(
        owner_id="owner-a", store_id="store-a",
        reference_kind=SupplyReferenceKind.SUPPLY, reference_id="2001",
    )
    assert result.supply_snapshot.order_ref != "11"
    assert "2001" not in repr(result.supply_snapshot)
    assert set(client.list_state_filters[0]) == set(
        _service(client).ACTIVE_SUPPLY_STATES
    )
    assert "COMPLETED" in client.list_state_filters[0]
    assert "IN_TRANSIT" in client.list_state_filters[0]
    assert client.calls == ["list", "details"]


def test_active_supply_missing_is_emitted_only_after_complete_lookup():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": None}]
    client.details_by_id["11"] = _completed_order(
        11, [{"supply_id": 3002, "state": "COMPLETED"}],
    )

    result = _service(client).observe_active_supply_by_id(
        2001, owner_id="owner-a",
        identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "MISSING"
    assert result.source_status == "COMPLETE"
    assert result.supply_snapshot.presence == "MISSING"
    assert result.supply_snapshot.scope_complete is True
    assert result.supply_snapshot.pagination_complete is True
    assert result.supply_snapshot.normalized_status == "UNKNOWN"
    assert result.supply_snapshot.raw_status is None
    assert "2001" not in repr(result.supply_snapshot)


def test_active_supply_partial_page_is_not_reported_missing_and_can_resume():
    client = _FakeOzonClient()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [], "last_id": None},
    ]
    client.details_by_id["11"] = _completed_order(
        11, [{"supply_id": 3002, "state": "COMPLETED"}],
    )
    service = _service(client)

    partial = service.observe_active_supply_by_id(
        2001, owner_id="owner-a",
        identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
        max_pages_per_call=1,
    )
    assert partial.status == "PARTIAL"
    assert partial.supply_snapshot is None
    assert partial.continuation_token

    missing = service.observe_active_supply_by_id(
        2001, owner_id="owner-a",
        identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
        checkpoint_token=partial.continuation_token,
    )
    assert missing.status == "MISSING"
    assert missing.supply_snapshot.presence == "MISSING"
    assert missing.supply_snapshot.pagination_complete is True
    assert client.calls == ["list", "details", "list"]


def test_active_supply_unknown_state_is_visible_not_filtered():
    client = _FakeOzonClient()
    client.list_pages = [{"order_ids": [11], "last_id": None}]
    client.details_by_id["11"] = {
        "order_id": 11,
        "state": "COMPLETED",
        "supplies": [{"supply_id": 2001, "state": "NEW_VENDOR_STATUS"}],
    }

    result = _service(client).observe_active_supply_by_id(
        2001, owner_id="owner-a",
        identity=IDENTITY, store_id="store-a", tenant_scope="owner:1",
    )

    assert result.status == "PRESENT"
    assert result.supply_snapshot.raw_status == "NEW_VENDOR_STATUS"
    assert result.supply_snapshot.normalized_status == "UNKNOWN"
    assert "SUPPLY_STATUS_UNKNOWN" in result.issue_codes
