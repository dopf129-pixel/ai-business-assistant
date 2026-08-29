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


class _ProductService:
    def load_products(self):
        return [
            {
                "product_id": "p1",
                "offer_id": "sku-1",
                "sku": "sku-1",
            }
        ]


class _FinanceAnalytics:
    def get_period_finance(self, date_from, date_to, sku=None):
        return {"error": False, "sales_count": 5}


class _AnalyticsService:
    def __init__(self):
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
        return {"error": False, "sales_count": 9}


class _MetricsService:
    def get_product_metrics(self, product_id):
        return {
            "error": False,
            "metrics": {"fbo_available": 18},
        }


class _StockIntelligenceService:
    def analyze(self, stock_data, sales_data, period_days):
        return {
            "error": False,
            "sales_velocity": 1.0,
            "days_of_stock": 18.0,
            "priority": "LOW",
        }


def _source():
    return ProductDecisionMetricsSource(
        product_service=_ProductService(),
        analytics_service=_AnalyticsService(),
        metrics_service=_MetricsService(),
        stock_intelligence_service=_StockIntelligenceService(),
        observation_clock=lambda: datetime(
            2026, 8, 29, 10, 0, tzinfo=timezone.utc
        ),
    )


def test_sales_metrics_expose_period_and_observation_time():
    sales = _source().sales("sku-1")

    assert sales["sales_period_from"] == "2026-08-20"
    assert sales["sales_period_to"] == "2026-08-28"
    assert sales["sales_observed_at"] == "2026-08-29T10:00:00+00:00"


def test_sales_metrics_do_not_fabricate_source_recorded_at():
    sales = _source().sales("sku-1")

    assert "sales_source_recorded_at" not in sales


def test_sales_observation_time_reaches_decision_input_without_source_time():
    sales = _source().sales("sku-1")

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

    assert prepared["sales_observed_at"] == "2026-08-29T10:00:00+00:00"
    assert "sales_source_recorded_at" not in prepared


def test_fresh_sales_observation_alone_still_leaves_sales_unknown():
    sales = _source().sales("sku-1")
    decision = {
        "sku": "sku-1",
        "product_id": "p1",
        "recorded_at": "2026-08-29T10:00:00+00:00",
        "sales_observed_at": sales["sales_observed_at"],
    }

    draft = ProductActionTaskDraftService().create_from_confirmation(
        decision,
        {
            "proposal_type": "REVIEW_REPLENISHMENT",
            "action_required": True,
        },
    )["task_draft"]

    freshness = ProductTaskDraftFreshnessService(
        clock=lambda: datetime(2026, 8, 29, 10, 5, tzinfo=timezone.utc)
    ).evaluate(draft)

    assert draft["sales_observed_at"] == "2026-08-29T10:00:00+00:00"
    assert "sales_source_recorded_at" not in draft
    assert freshness["components"]["sales"]["status"] == "UNKNOWN"
    assert freshness["status"] == "UNKNOWN"
    assert freshness["execution_ready"] is False
    assert freshness["executed"] is False
