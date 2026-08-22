import sys

sys.path.insert(
    0,
    "app"
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


def test_sales_context_propagates_from_recommendation_to_action():

    profits = [
        {
            "sku": "SKU-1",
            "profit": 150
        }
    ]

    previous_result = {
        "store_profit": {
            "gross_sales": 1000
        }
    }

    sales_context = {
        "profits": profits,
        "previous_result": previous_result,
        "period": "current"
    }

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            {
                "sales_down": True,
                "sales_context": sales_context
            }
        )
    )

    plan = (
        AssistantPlanningService()
        .build_plan(
            recommendations[
                "recommendations"
            ]
        )
    )

    generated = (
        AssistantActionGeneratorService()
        .generate(
            plan["plan"]
        )
    )

    action = generated["actions"][0]

    assert action["type"] == "sales"
    assert action["context"]["profits"] == profits
    assert (
        action["context"]["previous_result"]
        ==
        previous_result
    )
    assert action["context"]["period"] == "current"


def test_planning_copies_sales_context_before_action_enrichment():

    sales_context = {
        "profits": [],
        "previous_result": None
    }

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            {
                "sales_down": True,
                "sales_context": sales_context
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

    AssistantActionGeneratorService().generate(
        plan["plan"]
    )

    assert recommendation_context == sales_context
    assert "reason" not in recommendation_context
