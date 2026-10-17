from datetime import datetime, timezone

from services.product_overview_service import ProductOverviewService
from services.scoped_transient_snapshot_store import ScopedTransientSnapshotStore
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


def _row(
    selector,
    *,
    identity=None,
    status="READY",
    code=None,
    decision=None,
):
    return {
        "selector": selector,
        "identity": identity or {
            "product_id": "101",
            "offer_id": selector,
            "catalog_sku": "9001",
        },
        "status": status,
        "code": code,
        "decision": decision or {
            "error": False,
            "code": None,
            "decision_type": "INVESTIGATE_LOW_PROFIT",
            "priority": "HIGH",
            "confidence": "MEDIUM",
            "reasons": ["LOW_UNIT_PROFIT"],
            "missing_data": ["advertising"],
            "sales_velocity": 2.5,
            "sales_trend": "GROWING",
            "current_stock": 12,
            "days_of_stock": 4.8,
            "decision_profit_per_unit": 52.25,
            "decision_margin_percent": 18.0,
            "sales_observed_at": "2026-10-17T10:00:00Z",
            "sales_source_recorded_at": "2026-10-17T09:59:00Z",
            "sales_period_from": "2026-10-01",
            "sales_period_to": "2026-10-16",
            "stock_observed_at": "2026-10-17T10:00:30Z",
            "unit_economics_observed_at": "2026-10-17T09:58:00Z",
            "internal_payload": {"secret": "must not persist"},
        },
    }


class _DecisionQuery:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query_selected_products(self, selectors):
        self.calls.append(list(selectors))
        return {"error": False, "rows": list(self.rows)}


def _service(rows):
    store = ScopedTransientSnapshotStore()
    query = _DecisionQuery(rows)
    service = ProductOverviewService(
        decision_query=query,
        snapshot_store=store,
        utc_now=lambda: datetime(
            2026, 10, 17, 10, 1, tzinfo=timezone.utc
        ),
    )
    return service, store, query


def _tenant(value="owner-1::ozon::store-1"):
    return set_current_tenant_user_id(value)


def test_snapshot_projects_safe_metrics_provenance_and_exact_coverage():
    service, store, query = _service([
        _row("hook-2"),
        _row("missing", identity=None, status="NOT_FOUND", code="SKU_NOT_FOUND"),
        _row("ambiguous", identity=None, status="IDENTITY_AMBIGUOUS", code="PRODUCT_IDENTITY_AMBIGUOUS"),
        _row("partial", status="INCOMPLETE", code="INSUFFICIENT_DATA", decision={
            "decision_type": "INSUFFICIENT_DATA",
            "priority": "NONE",
            "confidence": "LOW",
            "reasons": ["ECONOMICS_INCOMPLETE"],
            "missing_data": ["profit_per_unit"],
        }),
        _row("down", status="SOURCE_UNAVAILABLE", code="SALES_METRICS_UNAVAILABLE", decision={
            "error": True,
            "decision_type": "INSUFFICIENT_DATA",
            "priority": "NONE",
            "confidence": "LOW",
            "reasons": [],
            "missing_data": ["decision"],
        }),
    ])
    tenant = _tenant()
    try:
        result = service.create_snapshot(
            ["hook-2", "missing", "ambiguous", "partial", "down"],
            page=1,
            page_size=1,
        )
        assert result["error"] is False
        assert result["coverage"] == {
            "selected_count": 5,
            "requested_selector_count": 5,
            "duplicate_identity_count": 0,
            "processed_count": 3,
            "decision_ready_count": 1,
            "incomplete_count": 1,
            "source_unavailable_count": 1,
            "not_found_count": 1,
            "identity_conflict_count": 1,
            "budget_unprocessed_count": 0,
            "cancelled_count": 0,
        }
        first = result["rows"][0]
        assert first["identity"] == {
            "product_id": "101",
            "offer_id": "hook-2",
            "catalog_sku": "9001",
        }
        assert first["decision"] == {
            "decision_type": "INVESTIGATE_LOW_PROFIT",
            "priority": "HIGH",
            "confidence": "MEDIUM",
            "reasons": ["LOW_UNIT_PROFIT"],
        }
        assert first["metrics"]["sales_velocity"] == {
            "value": 2.5,
            "unit": "units_per_day",
        }
        assert first["metrics"]["decision_profit_per_unit"] == {
            "value": 52.25,
            "unit": "RUB_per_unit",
        }
        assert first["source_freshness"]["sales"] == {
            "sales_observed_at": "2026-10-17T10:00:00Z",
            "sales_source_recorded_at": "2026-10-17T09:59:00Z",
            "sales_period_from": "2026-10-01",
            "sales_period_to": "2026-10-16",
            "freshness_status": "OBSERVED",
            "age_seconds": 60,
        }
        assert "internal_payload" not in first
        assert "secret" not in repr(store._snapshots)
        assert query.calls == [["hook-2", "missing", "ambiguous", "partial", "down"]]
    finally:
        reset_current_tenant_user_id(tenant)


def test_pages_read_the_same_snapshot_without_repeating_sources_and_ids_stay_stable():
    rows = [_row(f"offer-{i}", identity={
        "product_id": str(i),
        "offer_id": f"offer-{i}",
        "catalog_sku": str(1000 + i),
    }) for i in range(1, 8)]
    service, _store, query = _service(rows)
    tenant = _tenant()
    try:
        first = service.create_snapshot(
            [row["selector"] for row in rows], page=1, page_size=3
        )
        page_two = service.get_page(
            snapshot_id=first["snapshot"]["snapshot_id"],
            generation=first["snapshot"]["generation"],
            version=first["snapshot"]["version"],
            page=2,
            page_size=3,
        )
        assert first["pagination"] == {
            "page": 1,
            "page_size": 3,
            "total_rows": 7,
            "total_pages": 3,
            "has_previous": False,
            "has_next": True,
        }
        assert [row["identity"]["offer_id"] for row in page_two["rows"]] == [
            "offer-4", "offer-5", "offer-6"
        ]
        assert query.calls == [[row["selector"] for row in rows]]
        assert [row["row_id"] for row in first["rows"]] == [
            row["row_id"] for row in service.create_snapshot(
                [row["selector"] for row in rows], page=1, page_size=3
            )["rows"]
        ]
    finally:
        reset_current_tenant_user_id(tenant)


def test_duplicate_catalog_identity_is_shown_once_and_coverage_reconciles():
    identity = {
        "product_id": "101",
        "offer_id": "offer-1",
        "catalog_sku": "sku-1",
    }
    service, _store, _query = _service([
        _row("offer-1", identity=identity),
        _row("sku-1", identity=identity),
    ])
    tenant = _tenant()
    try:
        result = service.create_snapshot(["offer-1", "sku-1"])
    finally:
        reset_current_tenant_user_id(tenant)

    assert len(result["rows"]) == 1
    assert result["coverage"]["selected_count"] == 1
    assert result["coverage"]["requested_selector_count"] == 2
    assert result["coverage"]["duplicate_identity_count"] == 1
    assert result["coverage"]["decision_ready_count"] == 1


def test_ready_row_with_invalid_identity_is_downgraded_and_never_advertised():
    service, _store, _query = _service([
        _row("hook-2", identity={
            "product_id": "101",
            "offer_id": "offer-1",
            "catalog_sku": "x" * 129,
        }),
    ])
    tenant = _tenant()
    try:
        result = service.create_snapshot(["hook-2"])
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["rows"][0]["status"] == "SOURCE_UNAVAILABLE"
    assert result["rows"][0]["error"] == "PRODUCT_OVERVIEW_ROW_INVALID"
    assert result["rows"][0]["decision"] is None
    assert result["rows"][0]["missing_data"] == ["identity"]
    assert result["coverage"]["decision_ready_count"] == 0
    assert result["coverage"]["source_unavailable_count"] == 1


def test_pagination_and_snapshot_scope_fail_closed_without_extra_queries():
    service, _store, query = _service([_row("hook-2")])
    missing_tenant = service.create_snapshot(["hook-2"])
    assert missing_tenant["code"] == "PRODUCT_OVERVIEW_TENANT_REQUIRED"

    tenant = _tenant()
    try:
        created = service.create_snapshot(["hook-2"])
        out_of_range = service.get_page(
            created["snapshot"]["snapshot_id"],
            created["snapshot"]["generation"],
            created["snapshot"]["version"],
            page=2,
        )
    finally:
        reset_current_tenant_user_id(tenant)

    other_tenant = _tenant("owner-1::ozon::store-2")
    try:
        foreign = service.get_page(
            created["snapshot"]["snapshot_id"],
            created["snapshot"]["generation"],
            created["snapshot"]["version"],
        )
    finally:
        reset_current_tenant_user_id(other_tenant)

    assert out_of_range["code"] == "PRODUCT_OVERVIEW_PAGE_OUT_OF_RANGE"
    assert foreign["code"] == "TRANSIENT_SNAPSHOT_STALE"
    assert query.calls == [["hook-2"]]


def test_budget_unprocessed_rows_remain_visible_in_group_coverage():
    service, _store, _query = _service([
        _row("first", status="BUDGET_EXHAUSTED", code="BUDGET_EXHAUSTED", decision=None),
        _row("second", status="CANCELLED", code="CANCELLED", decision=None),
    ])
    tenant = _tenant()
    try:
        result = service.create_snapshot(["first", "second"])
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["coverage"]["selected_count"] == 2
    assert result["coverage"]["processed_count"] == 0
    assert result["coverage"]["budget_unprocessed_count"] == 1
    assert result["coverage"]["cancelled_count"] == 1
