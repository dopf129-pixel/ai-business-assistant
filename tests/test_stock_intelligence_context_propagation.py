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


def test_entry_adds_prepared_stock_context_to_report():

    stock_context = {
        "stock_data": {
            "product_id": "SKU-1",
            "current_stock": 12
        },
        "sales_data": {
            "product_id": "SKU-1",
            "sales_count": 28
        },
        "period_days": 14
    }

    main_flow = FakeMainFlowService()

    AssistantEntryService(
        main_flow
    ).handle(
        "Проверь остатки",
        context={
            "stock_context": stock_context
        },
        user_id=1
    )

    assert (
        main_flow.report[
            "stock_context"
        ]
        ==
        stock_context
    )


def test_stock_context_propagates_from_recommendation_to_action():

    stock_context = {
        "stock_data": {
            "product_id": "SKU-1",
            "current_stock": 12
        },
        "sales_data": {
            "product_id": "SKU-1",
            "sales_count": 28
        },
        "period_days": 14
    }

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            {
                "low_stock": True,
                "stock_context": stock_context
            }
        )
    )

    recommendation_context = (
        recommendations[
            "recommendations"
        ][0]["context"]
    )

    plan = (
        AssistantPlanningService()
        .build_plan(
            recommendations[
                "recommendations"
            ]
        )
    )

    assert (
        plan["plan"][0]["context"]
        ==
        stock_context
    )

    generated = (
        AssistantActionGeneratorService()
        .generate(
            plan["plan"]
        )
    )

    action = generated["actions"][0]

    assert action["type"] == "stock"
    assert (
        action["context"]["stock_data"]
        ==
        stock_context["stock_data"]
    )
    assert (
        action["context"]["sales_data"]
        ==
        stock_context["sales_data"]
    )
    assert (
        action["context"]["period_days"]
        ==
        stock_context["period_days"]
    )

    assert recommendation_context == stock_context
    assert "reason" not in recommendation_context
