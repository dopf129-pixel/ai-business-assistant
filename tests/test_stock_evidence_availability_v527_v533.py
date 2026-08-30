from services.assistant_recommendation_service import (
    AssistantRecommendationService,
)
from services.stock_context_provider import (
    StockContextProvider,
)
from services.stock_intelligence_service import (
    StockIntelligenceService,
)


class _Products:
    def __init__(self, products):
        self.products = products

    def load_products(self):
        return self.products


class _Metrics:
    def __init__(self, values):
        self.values = values

    def get_product_metrics(self, product_id):
        value = self.values.get(product_id)

        if value == "ERROR":
            return {
                "error": True,
                "message": "Нет данных",
            }

        if value == "MISSING":
            return {
                "error": False,
                "metrics": {},
            }

        return {
            "error": False,
            "metrics": {
                "fbo_available": value,
            },
        }


class _Analytics:
    def __init__(
        self,
        sales,
        period_days=7,
        period_error=False,
    ):
        self.sales = sales
        self.period_days = period_days
        self.period_error = period_error

    def get_period(self):
        if self.period_error:
            return {
                "error": True,
            }

        return {
            "error": False,
            "days": self.period_days,
        }

    def analyze_finance(self, sku=None):
        value = self.sales.get(sku)

        if value == "ERROR":
            return {
                "error": True,
                "message": "Нет продаж",
            }

        return {
            "error": False,
            "sales_count": value,
        }


def _provider(
    products=None,
    stocks=None,
    sales=None,
    period_days=7,
):
    return StockContextProvider(
        product_service=_Products(
            products
            if products is not None
            else [{
                "product_id": 1,
                "sku": "sku-1",
            }]
        ),
        analytics_service=_Analytics(
            sales
            if sales is not None
            else {
                "sku-1": 5,
            },
            period_days=period_days,
        ),
        metrics_service=_Metrics(
            stocks
            if stocks is not None
            else {
                1: 10,
            }
        ),
    )


def test_v527_missing_stock_dependencies_are_unavailable_not_safe():
    result = StockContextProvider().build()

    assert result == {
        "low_stock": False,
        "stock_evidence_available": False,
    }


def test_v527_empty_products_are_unavailable_not_safe():
    result = _provider(
        products=[],
    ).build()

    assert result == {
        "low_stock": False,
        "stock_evidence_available": False,
    }


def test_v528_complete_safe_stock_is_explicitly_available():
    result = _provider().build()

    assert result == {
        "low_stock": False,
        "stock_evidence_available": True,
    }


def test_v528_missing_metrics_do_not_become_safe_stock():
    result = _provider(
        stocks={
            1: "MISSING",
        }
    ).build()

    assert result == {
        "low_stock": False,
        "stock_evidence_available": False,
    }


def test_v528_sales_error_does_not_become_safe_stock():
    result = _provider(
        sales={
            "sku-1": "ERROR",
        }
    ).build()

    assert result == {
        "low_stock": False,
        "stock_evidence_available": False,
    }


def test_v529_partial_assortment_evidence_does_not_become_safe_stock():
    result = _provider(
        products=[
            {
                "product_id": 1,
                "sku": "sku-1",
            },
            {
                "product_id": 2,
                "sku": "sku-2",
            },
        ],
        stocks={
            1: 10,
            2: "ERROR",
        },
        sales={
            "sku-1": 5,
            "sku-2": 5,
        },
    ).build()

    assert result == {
        "low_stock": False,
        "stock_evidence_available": False,
    }


def test_v529_confirmed_low_stock_preserves_existing_action_context_shape():
    result = _provider(
        stocks={
            1: 3,
        },
        sales={
            "sku-1": 7,
        },
    ).build()

    assert result == {
        "low_stock": True,
        "stock_context": {
            "stock_data": {
                "product_id": "1",
                "current_stock": 3,
            },
            "sales_data": {
                "product_id": "1",
                "sales_count": 7,
            },
            "period_days": 7,
        },
    }
    assert "stock_evidence_available" not in result


def test_v530_stock_intelligence_rejects_malformed_numeric_evidence():
    service = StockIntelligenceService()

    cases = [
        (
            {
                "product_id": "1",
                "current_stock": True,
            },
            {
                "product_id": "1",
                "sales_count": 5,
            },
            7,
        ),
        (
            {
                "product_id": "1",
                "current_stock": float("nan"),
            },
            {
                "product_id": "1",
                "sales_count": 5,
            },
            7,
        ),
        (
            {
                "product_id": "1",
                "current_stock": 5,
            },
            {
                "product_id": "1",
                "sales_count": -1,
            },
            7,
        ),
        (
            {
                "product_id": "1",
                "current_stock": 5,
            },
            {
                "product_id": "1",
                "sales_count": 5,
            },
            False,
        ),
    ]

    for stock_data, sales_data, period_days in cases:
        result = service.analyze(
            stock_data,
            sales_data,
            period_days,
        )

        assert result["error"] is True
        assert result["priority"] == "UNKNOWN"
        assert result["days_of_stock"] is None


def test_v531_stock_intelligence_rejects_cross_product_evidence():
    result = StockIntelligenceService().analyze(
        stock_data={
            "product_id": "stock-product",
            "current_stock": 5,
        },
        sales_data={
            "product_id": "sales-product",
            "sales_count": 5,
        },
        period_days=7,
    )

    assert result["error"] is True
    assert result["priority"] == "UNKNOWN"


def test_v531_explicit_zero_sales_remains_valid_no_sales_evidence():
    result = StockIntelligenceService().analyze(
        stock_data={
            "product_id": "1",
            "current_stock": 5,
        },
        sales_data={
            "product_id": "1",
            "sales_count": 0,
        },
        period_days=7,
    )

    assert result["error"] is False
    assert result["sales_velocity"] == 0
    assert result["days_of_stock"] is None
    assert result["priority"] == "NO_SALES"


def test_v532_general_fallback_does_not_claim_clean_state_when_stock_unknown():
    result = AssistantRecommendationService().analyze({
        "sales_down": False,
        "low_stock": False,
        "stock_evidence_available": False,
    })

    assert result["recommendations"] == [{
        "type": "general",
        "message": "Недостаточно данных для полной оценки бизнеса",
    }]


def test_v532_verified_safe_stock_keeps_existing_clean_fallback():
    result = AssistantRecommendationService().analyze({
        "sales_down": False,
        "low_stock": False,
        "stock_evidence_available": True,
    })

    assert result["recommendations"] == [{
        "type": "general",
        "message": "Критичных проблем не найдено",
    }]


def test_v533_stock_provider_rejects_invalid_period_evidence():
    invalid_days = _provider(
        period_days=float("inf"),
    ).build()

    assert invalid_days == {
        "low_stock": False,
        "stock_evidence_available": False,
    }
