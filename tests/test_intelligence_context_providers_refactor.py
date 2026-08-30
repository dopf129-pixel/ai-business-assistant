import sys

sys.path.insert(0, "app")

from services.assistant_entry_service import AssistantEntryService
from services.finance_context_provider import FinanceContextProvider
from services.sales_context_provider import SalesContextProvider
from services.stock_context_provider import StockContextProvider


class FakeProductService:
    def load_products(self):
        return [
            {
                "product_id": 101,
                "offer_id": "offer-101",
                "sku": "sku-101"
            }
        ]


class FakePeriodProfitService:
    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):
        if date_from == "2026-08-18":
            profits = [
                {
                    "error": False,
                    "gross_sales": 1000,
                    "gross_profit": 300
                }
            ]
        else:
            profits = [
                {
                    "error": False,
                    "gross_sales": 1200,
                    "gross_profit": 500
                }
            ]

        return {
            "error": False,
            "products_count": len(profits),
            "profits": profits
        }


class FakeAnalyticsService:
    def get_period(self):
        return {
            "error": False,
            "code": "7D",
            "days": 7,
            "date_from": "2026-08-18",
            "date_to": "2026-08-24"
        }

    def get_previous_period(self):
        return {
            "error": False,
            "code": "7D",
            "days": 7,
            "date_from": "2026-08-11",
            "date_to": "2026-08-17"
        }

    def analyze(
        self,
        profits,
        previous_result=None
    ):
        result = {
            "error": False,
            "store_profit": {
                "gross_sales": 0
            }
        }

        if previous_result is not None:
            result["comparison"] = {
                "comparison": {
                    "revenue": {
                        "change_percent": -10
                    }
                }
            }

        return result

    def analyze_finance(self, sku=None):
        return {
            "error": False,
            "sales_count": 14
        }


class FakeMetricsService:
    def get_product_metrics(self, product_id):
        return {
            "error": False,
            "metrics": {
                "fbo_available": 7
            }
        }


class FakeMainFlowService:
    def __init__(self):
        self.report = None

    def process(
        self,
        text,
        report,
        context,
        user_id
    ):
        self.report = report
        return {
            "error": False
        }


def test_sales_provider_preserves_sales_contract_and_period_snapshot():
    result = SalesContextProvider(
        product_service=FakeProductService(),
        period_profit_service=FakePeriodProfitService(),
        analytics_service=FakeAnalyticsService()
    ).build()

    assert result["report"] == {
        "sales_down": True,
        "sales_context": {
            "profits": [
                {
                    "error": False,
                    "gross_sales": 1000,
                    "gross_profit": 300
                }
            ],
            "previous_result": {
                "error": False,
                "store_profit": {
                    "gross_sales": 0
                }
            }
        }
    }
    assert result["period_data"]["previous_profits"][0][
        "gross_profit"
    ] == 500


def test_stock_provider_preserves_stock_context_contract():
    result = StockContextProvider(
        product_service=FakeProductService(),
        analytics_service=FakeAnalyticsService(),
        metrics_service=FakeMetricsService()
    ).build()

    assert result == {
        "low_stock": True,
        "stock_context": {
            "stock_data": {
                "product_id": "101",
                "current_stock": 7
            },
            "sales_data": {
                "product_id": "101",
                "sales_count": 14
            },
            "period_days": 7
        }
    }


def test_finance_provider_preserves_finance_context_contract():
    result = FinanceContextProvider().build(
        {
            "current_profits": [
                {
                    "error": False,
                    "gross_sales": 1000,
                    "gross_profit": 300
                }
            ],
            "previous_profits": [
                {
                    "error": False,
                    "gross_sales": 1200,
                    "gross_profit": 500
                }
            ]
        }
    )

    assert result == {
        "finance_context": {
            "finance_data": {
                "revenue": 1000.0,
                "expenses": 700.0,
                "profit": 300.0,
                "margin": 30.0,
                "profit_scope": "PERIOD_GROSS_PROFIT"
            },
            "previous_data": {
                "revenue": 1200.0,
                "expenses": 700.0,
                "profit": 500.0,
                "margin": 41.67,
                "profit_scope": "PERIOD_GROSS_PROFIT"
            }
        }
    }


def test_entry_assembles_provider_results_and_preserves_prepared_overrides():
    main_flow = FakeMainFlowService()
    prepared_finance = {
        "finance_data": {
            "revenue": 10,
            "expenses": 5,
            "profit": 5,
            "margin": 50
        },
        "previous_data": {
            "revenue": 8,
            "expenses": 4,
            "profit": 4,
            "margin": 50
        }
    }

    entry = AssistantEntryService(
        main_flow_service=main_flow,
        sales_context_provider=SalesContextProvider(
            product_service=FakeProductService(),
            period_profit_service=FakePeriodProfitService(),
            analytics_service=FakeAnalyticsService()
        ),
        stock_context_provider=StockContextProvider(
            product_service=FakeProductService(),
            analytics_service=FakeAnalyticsService(),
            metrics_service=FakeMetricsService()
        ),
        finance_context_provider=FinanceContextProvider()
    )

    entry.handle(
        "Проверь бизнес",
        context={
            "finance_context": prepared_finance
        },
        user_id=1
    )

    assert main_flow.report["sales_down"] is True
    assert main_flow.report["low_stock"] is True
    assert main_flow.report["sales_context"]["profits"][0][
        "gross_sales"
    ] == 1000
    assert main_flow.report["stock_context"]["period_days"] == 7
    assert main_flow.report["finance_context"] == prepared_finance
