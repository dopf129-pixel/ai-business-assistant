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


def test_entry_adds_prepared_finance_context_to_report():

    finance_context = {
        "finance_data": {
            "revenue": 1000,
            "expenses": 600,
            "profit": 400,
            "margin": 40
        },
        "previous_data": {
            "revenue": 900,
            "expenses": 550,
            "profit": 350,
            "margin": 38.89
        }
    }

    main_flow = FakeMainFlowService()

    AssistantEntryService(
        main_flow
    ).handle(
        "Проверь финансы",
        context={
            "finance_context": finance_context
        },
        user_id=1
    )

    assert (
        main_flow.report[
            "finance_context"
        ]
        ==
        finance_context
    )


def test_finance_context_propagates_from_recommendation_to_action():

    finance_context = {
        "finance_data": {
            "revenue": 1000,
            "expenses": 600,
            "profit": 400,
            "margin": 40
        },
        "previous_data": {
            "revenue": 900,
            "expenses": 550,
            "profit": 350,
            "margin": 38.89
        }
    }

    original_context = {
        "finance_data": dict(
            finance_context[
                "finance_data"
            ]
        ),
        "previous_data": dict(
            finance_context[
                "previous_data"
            ]
        )
    }

    recommendations = (
        AssistantRecommendationService()
        .analyze(
            {
                "finance_context": finance_context
            }
        )
    )

    finance_recommendation = (
        recommendations[
            "recommendations"
        ][0]
    )

    assert (
        finance_recommendation[
            "type"
        ]
        ==
        "finance"
    )

    recommendation_context = (
        finance_recommendation[
            "context"
        ]
    )

    assert (
        recommendation_context
        ==
        finance_context
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
        finance_context
    )

    generated = (
        AssistantActionGeneratorService()
        .generate(
            plan["plan"]
        )
    )

    action = generated["actions"][0]

    assert action["type"] == "finance"
    assert (
        action["context"]["finance_data"]
        ==
        finance_context["finance_data"]
    )
    assert (
        action["context"]["previous_data"]
        ==
        finance_context["previous_data"]
    )

    assert finance_context == original_context
    assert recommendation_context == original_context
    assert "reason" not in recommendation_context
