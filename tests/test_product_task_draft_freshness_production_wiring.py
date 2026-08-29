from product_business_decision_factory import (
    create_product_business_decision_query,
)
from services.product_task_draft_freshness_service import (
    ProductTaskDraftFreshnessService,
)
from services.product_task_draft_readiness_service import (
    ProductTaskDraftReadinessService,
)
from services.stock_intelligence_service import (
    StockIntelligenceService,
)


class StubProductService:
    def load_products(self):
        return [
            {
                "product_id": "101",
                "offer_id": "hook-2",
                "sku": "3921245627",
            }
        ]


class StubFinanceAnalytics:
    def get_period_finance(self, date_from, date_to, sku=None):
        return {
            "error": False,
            "sku": sku,
            "sales_count": 5,
        }


class StubComparisonService:
    def compare_value(self, name, current, previous):
        return {
            "name": name,
            "change_percent": current - previous,
        }


class StubAnalyticsService:
    def __init__(self):
        self.finance_analytics = StubFinanceAnalytics()
        self.comparison_service = StubComparisonService()

    def get_period(self):
        return {
            "error": False,
            "days": 7,
            "date_from": "2026-08-18",
            "date_to": "2026-08-24",
        }

    def get_previous_period(self):
        return {
            "error": False,
            "days": 7,
            "date_from": "2026-08-11",
            "date_to": "2026-08-17",
        }

    def analyze_finance(self, sku=None):
        return {
            "error": False,
            "sku": sku,
            "sales_count": 14,
        }


class StubMetricsService:
    def get_product_metrics(self, product_id):
        return {
            "product_id": str(product_id),
            "metrics": {
                "fbo_available": 4,
            },
        }


class StubUnitEconomicsQuery:
    def __init__(self):
        self.product_service = StubProductService()
        self.analytics_service = StubAnalyticsService()

    def query(self, sku):
        return {
            "error": False,
            "available": True,
            "product_id": "101",
            "sku": sku,
            "net_profit_per_unit": 510.0,
            "margin_percent": 34.0,
            "missing_fields": [],
        }


def _core():
    return {
        "unit_economics_query": StubUnitEconomicsQuery(),
    }


def _factory(**overrides):
    return create_product_business_decision_query(
        core_components=_core(),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
        **overrides,
    )


def test_factory_connects_default_freshness_guard_to_readiness():
    query = _factory()

    readiness = query.task_draft_readiness_service

    assert isinstance(readiness, ProductTaskDraftReadinessService)
    assert isinstance(
        readiness.freshness_service,
        ProductTaskDraftFreshnessService,
    )


def test_factory_reuses_explicit_freshness_service():
    custom_freshness = ProductTaskDraftFreshnessService(
        max_snapshot_age_seconds=7200
    )

    query = _factory(
        task_draft_freshness_service=custom_freshness,
    )

    assert (
        query.task_draft_readiness_service.freshness_service
        is custom_freshness
    )


def test_factory_preserves_explicit_readiness_service_override():
    custom_readiness = ProductTaskDraftReadinessService()

    query = _factory(
        task_draft_readiness_service=custom_readiness,
    )

    assert query.task_draft_readiness_service is custom_readiness
    assert custom_readiness.freshness_service is None
