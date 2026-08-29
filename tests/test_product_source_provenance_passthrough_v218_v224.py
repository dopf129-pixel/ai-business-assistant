from datetime import datetime, timezone

from app.services.product_action_task_draft_service import (
    ProductActionTaskDraftService,
)
from app.services.product_decision_input_provider import (
    ProductDecisionInputProvider,
)
from app.services.product_decision_metrics_source import (
    ProductDecisionMetricsSource,
)
from app.services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)
from app.services.product_unit_economics_provider import (
    ProductUnitEconomicsProvider,
)


class _ProductService:
    def load_products(self):
        return [{
            "product_id": "p1",
            "offer_id": "sku-1",
            "sku": "sku-1",
        }]


class _FinanceAnalytics:
    def get_period_finance(self, date_from, date_to, sku=None):
        return {"error": False, "sales_count": 5}


class _Analytics:
    def __init__(self, current):
        self.current = current
        self.finance_analytics = _FinanceAnalytics()
        self.comparison_service = None

    def get_period(self):
        return {
            "date_from": "2026-08-20",
            "date_to": "2026-08-28",
            "days": 9,
        }

    def get_previous_period(self):
        return {
            "date_from": "2026-08-11",
            "date_to": "2026-08-19",
            "days": 9,
        }

    def analyze_finance(self, sku=None):
        return dict(self.current)


class _Metrics:
    def __init__(self, payload):
        self.payload = payload

    def get_product_metrics(self, product_id):
        return dict(self.payload)


class _StockIntelligence:
    def analyze(self, stock_data, sales_data, period_days):
        return {
            "error": False,
            "sales_velocity": 1.0,
            "days_of_stock": 18.0,
            "priority": "LOW",
        }


def _metrics_source(finance=None, stock=None):
    return ProductDecisionMetricsSource(
        product_service=_ProductService(),
        analytics_service=_Analytics(
            finance or {"error": False, "sales_count": 9}
        ),
        metrics_service=_Metrics(
            stock or {
                "error": False,
                "metrics": {"fbo_available": 18},
            }
        ),
        stock_intelligence_service=_StockIntelligence(),
        observation_clock=lambda: datetime(
            2026, 8, 29, 10, 0, tzinfo=timezone.utc
        ),
    )


def test_v218_sales_exact_source_timestamp_is_preserved():
    source = _metrics_source(finance={
        "error": False,
        "sales_count": 9,
        "sales_source_recorded_at": "2026-08-29T09:58:00+00:00",
    })

    sales = source.sales("sku-1")

    assert sales["sales_source_recorded_at"] == (
        "2026-08-29T09:58:00+00:00"
    )


def test_v219_sales_alias_is_not_promoted_to_source_timestamp():
    source = _metrics_source(finance={
        "error": False,
        "sales_count": 9,
        "recorded_at": "2026-08-29T09:58:00+00:00",
    })

    sales = source.sales("sku-1")

    assert "sales_source_recorded_at" not in sales


def test_v220_stock_exact_source_timestamp_is_preserved():
    source = _metrics_source(stock={
        "error": False,
        "stock_source_recorded_at": "2026-08-29T09:57:00+00:00",
        "metrics": {"fbo_available": 18},
    })

    stock = source.stock("sku-1")

    assert stock["stock_source_recorded_at"] == (
        "2026-08-29T09:57:00+00:00"
    )


def test_v220_nested_stock_exact_source_timestamp_is_preserved():
    source = _metrics_source(stock={
        "error": False,
        "metrics": {
            "fbo_available": 18,
            "stock_source_recorded_at": "2026-08-29T09:57:00+00:00",
        },
    })

    stock = source.stock("sku-1")

    assert stock["stock_source_recorded_at"] == (
        "2026-08-29T09:57:00+00:00"
    )


def test_v221_current_unit_economics_preserves_only_exact_provenance_fields():
    facts = {
        "product_id": "p1",
        "sku": "sku-1",
        "seller_price": 100,
        "buyer_price": 100,
        "commission_amount": 10,
        "logistics": 10,
        "last_mile": 1,
        "acquiring_average": 1,
        "unit_economics_source_recorded_at": "2026-08-29T09:56:00+00:00",
        "unit_economics_observed_at": "2026-08-29T10:00:00+00:00",
        "source_recorded_at": "must-not-be-promoted",
    }

    result = ProductUnitEconomicsProvider().build_current(
        facts,
        product_cost=20,
    )

    assert result["unit_economics_source_recorded_at"] == (
        "2026-08-29T09:56:00+00:00"
    )
    assert result["unit_economics_observed_at"] == (
        "2026-08-29T10:00:00+00:00"
    )
    assert "source_recorded_at" not in result


def test_v222_missing_upstream_source_evidence_remains_absent():
    sales = _metrics_source().sales("sku-1")
    stock = _metrics_source().stock("sku-1")
    economics = ProductUnitEconomicsProvider().build_current(
        {
            "product_id": "p1",
            "sku": "sku-1",
            "seller_price": 100,
            "buyer_price": 100,
            "commission_amount": 10,
            "logistics": 10,
            "last_mile": 1,
            "acquiring_average": 1,
        },
        product_cost=20,
    )

    assert "sales_source_recorded_at" not in sales
    assert "stock_source_recorded_at" not in stock
    assert "unit_economics_source_recorded_at" not in economics


def test_v223_malformed_exact_timestamp_fails_closed_downstream():
    decision = {
        "sku": "sku-1",
        "product_id": "p1",
        "recorded_at": "2026-08-29T10:00:00+00:00",
        "sales_source_recorded_at": "not-a-timestamp",
    }
    draft = ProductActionTaskDraftService().create_from_confirmation(
        decision,
        {
            "proposal_type": "REVIEW_REPLENISHMENT",
            "action_required": True,
        },
    )["task_draft"]

    result = ProductTaskDraftFreshnessService(
        clock=lambda: datetime(
            2026, 8, 29, 10, 5, tzinfo=timezone.utc
        )
    ).evaluate(draft)

    assert result["components"]["sales"]["status"] == "UNKNOWN"
    assert result["execution_ready"] is False
    assert result["executed"] is False


def test_v224_exact_source_evidence_can_make_required_component_fresh_only():
    sales = _metrics_source(finance={
        "error": False,
        "sales_count": 9,
        "sales_source_recorded_at": "2026-08-29T09:58:00+00:00",
    }).sales("sku-1")

    prepared = ProductDecisionInputProvider().build(
        sales_metrics=sales,
        stock_metrics={
            "product_id": "p1",
            "sku": "sku-1",
            "current_stock": 18,
            "days_of_stock": 18.0,
            "priority": "LOW",
            "missing_data": [],
        },
        unit_economics={
            "product_id": "p1",
            "sku": "sku-1",
            "net_profit_per_unit": 20.0,
            "margin_percent": 20.0,
            "missing_data": [],
        },
    )

    assert prepared["sales_source_recorded_at"] == (
        "2026-08-29T09:58:00+00:00"
    )

    decision = {
        "sku": "sku-1",
        "product_id": "p1",
        "recorded_at": "2026-08-29T10:00:00+00:00",
        "sales_source_recorded_at": prepared["sales_source_recorded_at"],
    }
    draft = ProductActionTaskDraftService().create_from_confirmation(
        decision,
        {
            "proposal_type": "REVIEW_REPLENISHMENT",
            "action_required": True,
        },
    )["task_draft"]

    result = ProductTaskDraftFreshnessService(
        clock=lambda: datetime(
            2026, 8, 29, 10, 5, tzinfo=timezone.utc
        )
    ).evaluate(draft)

    assert result["components"]["sales"]["status"] == "FRESH"
    assert result["execution_ready"] is False
    assert result["executed"] is False
