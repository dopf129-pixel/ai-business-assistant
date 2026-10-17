from app.services.product_business_decision_query_service import (
    ProductBusinessDecisionQueryService,
)
from app.services.product_business_decision_service import (
    ProductBusinessDecisionService,
)
from app.services.product_decision_input_provider import (
    ProductDecisionInputProvider,
)
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    reset_period_profit_trace,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


class _Products:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def load_products(self):
        self.calls += 1
        return list(self.rows)


class _Metrics:
    def __init__(self, fail_product_id=None):
        self.fail_product_id = fail_product_id
        self.sales_calls = []
        self.stock_calls = []

    def sales_for_product(self, sku, product):
        self.sales_calls.append((sku, product["product_id"]))
        if product["product_id"] == self.fail_product_id:
            raise OSError("synthetic source failure")
        return {
            "product_id": product["product_id"],
            "sku": sku,
            "sales_velocity": 4.0,
            "sales_trend": "GROWING",
        }

    def stock_for_product(self, sku, product):
        self.stock_calls.append((sku, product["product_id"]))
        return {
            "product_id": product["product_id"],
            "sku": sku,
            "current_stock": 8,
            "days_of_stock": 2.0,
            "priority": "CRITICAL",
        }


class _Economics:
    def __init__(self):
        self.calls = []

    def query_for_product(self, sku, product):
        self.calls.append((sku, product["product_id"]))
        return {
            "error": False,
            "available": True,
            "product_id": product["product_id"],
            "sku": sku,
            "net_profit_per_unit": 510.0,
            "margin_percent": 34.0,
            "missing_fields": [],
        }


class _LifecycleSpy:
    def __init__(self):
        self.calls = []

    def record(self, *args, **kwargs):
        self.calls.append(("history", args, kwargs))

    def propose(self, *args, **kwargs):
        self.calls.append(("proposal", args, kwargs))

    def reconcile(self, *args, **kwargs):
        self.calls.append(("task_draft", args, kwargs))


def _service(products, metrics=None):
    catalog = _Products(products)
    source = metrics or _Metrics()
    economics = _Economics()
    lifecycle = _LifecycleSpy()
    service = ProductBusinessDecisionQueryService(
        product_service=catalog,
        sales_metrics_source=source,
        stock_metrics_source=source,
        unit_economics_query_service=economics,
        decision_input_provider=ProductDecisionInputProvider(),
        decision_service=ProductBusinessDecisionService(),
        decision_history_service=lifecycle,
        action_proposal_service=lifecycle,
        action_proposal_confirmation_service=lifecycle,
        cache_ttl_seconds=600,
    )
    return service, catalog, source, economics, lifecycle


def test_selected_query_loads_catalog_once_deduplicates_and_avoids_write_lifecycle():
    rows = [
        {"product_id": "p1", "offer_id": "offer-1", "sku": "sku-1"},
        {"product_id": "p2", "offer_id": "offer-2", "sku": "sku-2"},
        {"product_id": "p3", "offer_id": "shared", "sku": "sku-3"},
        {"product_id": "p4", "offer_id": "offer-4", "sku": "shared"},
    ]
    service, catalog, source, economics, lifecycle = _service(rows)
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = service.query_selected_products(
            ["offer-1", "sku-2", "shared", "missing", "offer-1"]
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is False
    assert catalog.calls == 1
    assert [row["status"] for row in result["rows"]] == [
        "READY",
        "READY",
        "IDENTITY_AMBIGUOUS",
        "NOT_FOUND",
    ]
    assert result["coverage"] == {
        "selected_count": 4,
        "processed_count": 2,
        "decision_ready_count": 2,
        "incomplete_count": 0,
        "source_unavailable_count": 0,
        "not_found_count": 1,
        "identity_conflict_count": 1,
        "budget_unprocessed_count": 0,
        "cancelled_count": 0,
    }
    assert source.sales_calls == [("offer-1", "p1"), ("sku-2", "p2")]
    assert source.stock_calls == [("offer-1", "p1"), ("sku-2", "p2")]
    assert economics.calls == [("offer-1", "p1"), ("sku-2", "p2")]
    assert lifecycle.calls == []
    assert service._decision_cache == {}


def test_selected_query_preserves_good_rows_when_one_source_fails():
    rows = [
        {"product_id": "p1", "offer_id": "offer-1", "sku": "sku-1"},
        {"product_id": "p2", "offer_id": "offer-2", "sku": "sku-2"},
    ]
    service, catalog, _source, _economics, _lifecycle = _service(
        rows,
        metrics=_Metrics(fail_product_id="p1"),
    )
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = service.query_selected_products(["offer-1", "offer-2"])
    finally:
        reset_current_tenant_user_id(token)

    assert catalog.calls == 1
    assert result["rows"][0]["status"] == "SOURCE_UNAVAILABLE"
    assert result["rows"][1]["status"] == "READY"
    assert result["coverage"]["source_unavailable_count"] == 1
    assert result["coverage"]["decision_ready_count"] == 1


def test_selected_query_requires_tenant_and_caps_selection_at_twenty():
    service, catalog, _source, _economics, _lifecycle = _service([])
    missing_tenant = service.query_selected_products(["one"])
    assert missing_tenant["code"] == "PRODUCT_DECISION_TENANT_REQUIRED"

    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        too_many = service.query_selected_products(
            [f"sku-{index}" for index in range(21)]
        )
        empty = service.query_selected_products([])
    finally:
        reset_current_tenant_user_id(token)

    assert too_many["code"] == "PRODUCT_DECISION_SELECTION_LIMIT_EXCEEDED"
    assert catalog.calls == 0
    assert empty["error"] is False
    assert empty["coverage"]["selected_count"] == 0


def test_selected_query_marks_rows_unprocessed_after_parent_budget_exhaustion():
    service, catalog, source, _economics, _lifecycle = _service([
        {"product_id": "p1", "offer_id": "offer-1", "sku": "sku-1"},
        {"product_id": "p2", "offer_id": "offer-2", "sku": "sku-2"},
    ])
    tenant = set_current_tenant_user_id("user-1::ozon::store-1")
    trace = PeriodProfitOperationTrace(ozon_request_budget=0)
    trace_token = activate_period_profit_trace(trace)
    try:
        result = service.query_selected_products(["offer-1", "offer-2"])
    finally:
        reset_period_profit_trace(trace_token)
        reset_current_tenant_user_id(tenant)

    assert catalog.calls == 1
    assert all(row["status"] == "BUDGET_EXHAUSTED" for row in result["rows"])
    assert result["coverage"]["budget_unprocessed_count"] == 2
    assert source.sales_calls == []
