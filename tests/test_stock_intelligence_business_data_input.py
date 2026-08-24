import sys

sys.path.insert(
    0,
    "app"
)

from services.assistant_entry_service import (
    AssistantEntryService
)
from services.assistant_recommendation_service import (
    AssistantRecommendationService
)
from services.assistant_planning_service import (
    AssistantPlanningService
)
from services.assistant_action_generator_service import (
    AssistantActionGeneratorService
)


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


class FakeProductService:

    def load_products(self):
        return [
            (
                101,
                "offer-101",
                "SKU-101"
            )
        ]


class FakeMetricsService:

    def get_product_metrics(
        self,
        product_id
    ):
        return {
            "product_id": str(product_id),
            "metrics": {
                "fbo_available": 6
            }
        }


class MissingMetricsService:

    def get_product_metrics(
        self,
        product_id
    ):
        return {
            "product_id": str(product_id),
            "message": "Нет данных"
        }


class FakeAnalyticsService:

    def get_period(self):
        return {
            "error": False,
            "days": 7,
            "date_from": "2026-08-16",
            "date_to": "2026-08-22"
        }

    def analyze_finance(
        self,
        sku=None
    ):
        return {
            "error": False,
            "sku": sku,
            "sales_count": 14
        }

    def get_previous_period(self):
        return {
            "error": True
        }


class FakePeriodProfitService:

    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):
        return {
            "error": False,
            "profits": []
        }


def test_real_stock_data_reaches_action_context():

    main_flow = FakeMainFlowService()

    entry = AssistantEntryService(
        main_flow_service=main_flow,
        product_service=FakeProductService(),
        period_profit_service=(
            FakePeriodProfitService()
        ),
        analytics_service=(
            FakeAnalyticsService()
        ),
        metrics_service=(
            FakeMetricsService()
        )
    )

    entry.handle(
        "Какие товары заканчиваются?",
        user_id=1
    )

    stock_context = (
        main_flow.report[
            "stock_context"
        ]
    )

    assert stock_context == {
        "stock_data": {
            "product_id": "101",
            "current_stock": 6
        },
        "sales_data": {
            "product_id": "101",
            "sales_count": 14
        },
        "period_days": 7
    }

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            main_flow.report
        )
    )

    stock_recommendation = next(
        item
        for item in recommendations[
            "recommendations"
        ]
        if item["type"] == "stock"
    )

    assert (
        stock_recommendation[
            "context"
        ]
        ==
        stock_context
    )

    plan = (
        AssistantPlanningService()
        .build_plan(
            [stock_recommendation]
        )
    )

    action = (
        AssistantActionGeneratorService()
        .generate(
            plan["plan"]
        )[
            "actions"
        ][0]
    )

    assert action["type"] == "stock"
    assert (
        action["context"][
            "stock_data"
        ]
        ==
        stock_context[
            "stock_data"
        ]
    )
    assert (
        action["context"][
            "sales_data"
        ]
        ==
        stock_context[
            "sales_data"
        ]
    )
    assert (
        action["context"][
            "period_days"
        ]
        == 7
    )


def test_missing_stock_data_uses_safe_fallback():

    main_flow = FakeMainFlowService()

    entry = AssistantEntryService(
        main_flow_service=main_flow,
        product_service=FakeProductService(),
        period_profit_service=(
            FakePeriodProfitService()
        ),
        analytics_service=(
            FakeAnalyticsService()
        ),
        metrics_service=(
            MissingMetricsService()
        )
    )

    entry.handle(
        "Проверь остатки",
        user_id=1
    )

    assert main_flow.report["low_stock"] is False
    assert "stock_context" not in main_flow.report

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            main_flow.report
        )
    )

    assert all(
        item["type"] != "stock"
        for item in recommendations[
            "recommendations"
        ]
    )
