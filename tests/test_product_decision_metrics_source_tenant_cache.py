from services.product_decision_metrics_source import ProductDecisionMetricsSource
from services.stock_intelligence_service import StockIntelligenceService
from services.tenant_context import (
    get_current_tenant_user_id,
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


class ProductService:
    def load_products(self):
        tenant = get_current_tenant_user_id()
        product_id = "101" if tenant == "store-A" else "202"
        return [{"product_id": product_id, "offer_id": "shared-offer", "sku": "same-sku"}]


class AnalyticsService:
    finance_analytics = None

    def get_period(self):
        return {"error": False, "date_from": "2026-10-01", "date_to": "2026-10-07", "days": 7}

    def get_previous_period(self):
        return {"error": False, "date_from": "2026-09-24", "date_to": "2026-09-30", "days": 7}

    def analyze_finance(self, sku):
        return {"error": False, "sales_count": 2}


class MetricsService:
    def get_product_metrics(self, product_id):
        stock = 4 if str(product_id) == "101" else 80
        return {"error": False, "metrics": {"fbo_available": stock}}


def test_prepared_sales_and_stock_cache_is_scoped_to_active_store():
    source = ProductDecisionMetricsSource(
        product_service=ProductService(),
        analytics_service=AnalyticsService(),
        metrics_service=MetricsService(),
        stock_intelligence_service=StockIntelligenceService(),
    )
    token_a = set_current_tenant_user_id("store-A")
    try:
        source.sales("shared-offer")
    finally:
        reset_current_tenant_user_id(token_a)

    token_b = set_current_tenant_user_id("store-B")
    try:
        stock_b = source.stock("shared-offer")
    finally:
        reset_current_tenant_user_id(token_b)

    assert stock_b["product_id"] == "202"
    assert stock_b["current_stock"] == 80
