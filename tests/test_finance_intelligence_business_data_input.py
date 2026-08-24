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
            {
                "product_id": 101,
                "offer_id": "offer-101",
                "sku": "sku-101"
            }
        ]


class FakePeriodProfitService:

    def __init__(
        self,
        current_profits,
        previous_profits
    ):
        self.current_profits = current_profits
        self.previous_profits = previous_profits
        self.calls = []

    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):
        self.calls.append(
            (
                date_from,
                date_to,
                products
            )
        )

        if date_from == "2026-08-18":
            profits = self.current_profits
        else:
            profits = self.previous_profits

        return {
            "error": False,
            "products_count": len(
                profits
            ),
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
            "error": False
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


def test_real_period_profit_data_builds_finance_context_and_reaches_action():

    current_profits = [
        {
            "error": False,
            "gross_sales": 1000,
            "gross_profit": 300
        },
        {
            "error": False,
            "gross_sales": 500,
            "gross_profit": 100
        }
    ]

    previous_profits = [
        {
            "error": False,
            "gross_sales": 1200,
            "gross_profit": 500
        }
    ]

    period_profit = FakePeriodProfitService(
        current_profits=current_profits,
        previous_profits=previous_profits
    )
    main_flow = FakeMainFlowService()

    AssistantEntryService(
        main_flow_service=main_flow,
        product_service=FakeProductService(),
        period_profit_service=period_profit,
        analytics_service=FakeAnalyticsService()
    ).handle(
        "Проверь финансы",
        user_id=1
    )

    finance_context = (
        main_flow.report[
            "finance_context"
        ]
    )

    assert period_profit.calls[0][0:2] == (
        "2026-08-18",
        "2026-08-24"
    )
    assert period_profit.calls[1][0:2] == (
        "2026-08-11",
        "2026-08-17"
    )

    assert finance_context == {
        "finance_data": {
            "revenue": 1500.0,
            "expenses": 1100.0,
            "profit": 400.0,
            "margin": 26.67
        },
        "previous_data": {
            "revenue": 1200.0,
            "expenses": 700.0,
            "profit": 500.0,
            "margin": 41.67
        }
    }

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            main_flow.report
        )
    )

    finance_recommendation = next(
        item
        for item in recommendations[
            "recommendations"
        ]
        if item.get("type") == "finance"
    )

    assert (
        finance_recommendation[
            "context"
        ]
        ==
        finance_context
    )

    plan = (
        AssistantPlanningService()
        .build_plan(
            [finance_recommendation]
        )
    )

    generated = (
        AssistantActionGeneratorService()
        .generate(
            plan["plan"]
        )
    )

    action = generated["action"]

    assert action["type"] == "finance"
    assert (
        action["context"][
            "finance_data"
        ]
        ==
        finance_context[
            "finance_data"
        ]
    )
    assert (
        action["context"][
            "previous_data"
        ]
        ==
        finance_context[
            "previous_data"
        ]
    )


def test_missing_period_profit_data_skips_finance_context_safely():

    main_flow = FakeMainFlowService()

    AssistantEntryService(
        main_flow_service=main_flow,
        product_service=FakeProductService(),
        period_profit_service=(
            FakePeriodProfitService(
                current_profits=[],
                previous_profits=[]
            )
        ),
        analytics_service=FakeAnalyticsService()
    ).handle(
        "Проверь финансы",
        user_id=1
    )

    assert (
        "finance_context"
        not in main_flow.report
    )

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            main_flow.report
        )
    )

    assert all(
        item.get("type") != "finance"
        for item in recommendations[
            "recommendations"
        ]
    )
