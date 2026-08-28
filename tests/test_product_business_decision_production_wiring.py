from product_business_decision_factory import (
    create_product_business_decision_query,
    create_product_decision_history,
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
    def get_period_finance(
        self,
        date_from,
        date_to,
        sku=None,
    ):
        return {
            "error": False,
            "sku": sku,
            "sales_count": 5,
        }


class StubComparisonService:
    def compare_value(self, name, current, previous):
        change = current - previous
        return {
            "name": name,
            "change_percent": change,
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
    def __init__(self, economics=None):
        self.product_service = StubProductService()
        self.analytics_service = StubAnalyticsService()
        self.economics = economics or {
            "error": False,
            "available": True,
            "product_id": "101",
            "sku": "hook-2",
            "net_profit_per_unit": 510.0,
            "margin_percent": 34.0,
            "missing_fields": [],
        }

    def query(self, sku):
        result = dict(self.economics)
        result.setdefault("sku", sku)
        return result


def _core(economics=None):
    return {
        "unit_economics_query": StubUnitEconomicsQuery(
            economics=economics
        )
    }


def test_production_factory_builds_business_decision_query():
    query = create_product_business_decision_query(
        core_components=_core(),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
    )

    assert query.product_service is not None
    assert query.unit_economics_query_service is not None
    assert query.decision_input_provider is not None
    assert query.decision_service is not None
    assert query.action_proposal_service is not None
    assert callable(query.sales_metrics_source)
    assert callable(query.stock_metrics_source)


def test_production_factory_wires_storage_only_proposal_confirmation():
    history = create_product_decision_history(
        file_path="unused-product-decision-history.json"
    )
    query = create_product_business_decision_query(
        core_components=_core(),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
        decision_history_service=history,
    )

    confirmation = query.action_proposal_confirmation_service
    assert confirmation is not None
    assert confirmation.history_service is history
    assert confirmation.proposal_service is query.action_proposal_service
    assert confirmation.task_draft_service is not None
    assert query.action_task_draft_service is (
        confirmation.task_draft_service
    )


def test_production_query_uses_real_prepared_stock_and_sales_path():
    query = create_product_business_decision_query(
        core_components=_core(),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
    )

    result = query.query("hook-2")

    assert result["error"] is False
    assert result["code"] is None
    assert result["product_id"] == "101"
    assert result["sku"] == "hook-2"
    assert result["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert result["priority"] == "CRITICAL"
    assert result["confidence"] == "HIGH"


def test_production_source_preserves_product_sales_trend():
    query = create_product_business_decision_query(
        core_components=_core(),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
    )

    sales = query.sales_metrics_source("hook-2")
    stock = query.stock_metrics_source("hook-2")

    assert sales == {
        "product_id": "101",
        "sku": "hook-2",
        "sales_velocity": 2.0,
        "sales_trend": "GROWING",
        "missing_data": [],
    }
    assert stock == {
        "product_id": "101",
        "sku": "hook-2",
        "current_stock": 4,
        "days_of_stock": 2.0,
        "priority": "CRITICAL",
        "missing_data": [],
    }


def test_production_query_keeps_unknown_tax_as_insufficient_data():
    query = create_product_business_decision_query(
        core_components=_core(
            economics={
                "error": False,
                "available": True,
                "product_id": "101",
                "sku": "hook-2",
                "net_profit_per_unit": None,
                "margin_percent": None,
                "missing_fields": [
                    "tax",
                    "advertising",
                    "storage",
                    "returns",
                ],
            }
        ),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
    )

    result = query.query("hook-2")

    assert result["code"] == "INSUFFICIENT_DATA"
    assert result["decision_type"] == "INSUFFICIENT_DATA"
    assert "tax" in result["missing_data"]
    assert "profit_per_unit" in result["missing_data"]
    assert "margin_percent" in result["missing_data"]


def test_existing_unit_economics_query_object_is_reused():
    core = _core()

    query = create_product_business_decision_query(
        core_components=core,
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
    )

    assert (
        query.unit_economics_query_service
        is core["unit_economics_query"]
    )


def test_explicit_current_unit_economics_query_overrides_core_query():
    core = _core()
    current_query = StubUnitEconomicsQuery()

    query = create_product_business_decision_query(
        core_components=core,
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
        unit_economics_query=current_query,
    )

    assert query.unit_economics_query_service is current_query
    assert query.unit_economics_query_service is not core["unit_economics_query"]


def test_factory_reuses_explicit_product_decision_history_service():
    history = create_product_decision_history(
        file_path="unused-product-decision-history.json"
    )

    query = create_product_business_decision_query(
        core_components=_core(),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
        decision_history_service=history,
    )

    assert query.decision_history_service is history


def test_production_query_exposes_non_executable_action_proposal():
    query = create_product_business_decision_query(
        core_components=_core(),
        metrics_service=StubMetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
    )

    result = query.query("hook-2")

    assert result["action_proposal"]["available"] is True
    assert result["action_proposal"]["proposal_type"] == (
        "REVIEW_REPLENISHMENT"
    )
    assert result["action_proposal"]["execution_allowed"] is False
