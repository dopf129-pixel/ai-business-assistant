from services.assistant_business_planner_service import (
    AssistantBusinessPlannerService,
)
from services.assistant_recommendation_service import (
    AssistantRecommendationService,
)


def _general_message(result):
    return result["recommendations"][0]["message"]


def test_v561_non_dict_report_fails_closed():
    result = AssistantRecommendationService().analyze(
        ["bad-report"]
    )

    assert result == {
        "error": True,
        "message": "Недостаточно данных для рекомендаций",
        "recommendations": [],
        "count": 0,
    }


def test_v562_sales_flag_without_context_is_not_actionable():
    result = AssistantRecommendationService().analyze({
        "sales_down": True,
    })

    assert result["error"] is False
    assert result["count"] == 1
    assert result["recommendations"][0]["type"] == "general"
    assert _general_message(result) == (
        "Недостаточно данных для полной оценки бизнеса"
    )


def test_v562_sales_flag_with_malformed_context_is_not_actionable():
    result = AssistantRecommendationService().analyze({
        "sales_down": True,
        "sales_context": ["bad-context"],
    })

    assert result["recommendations"][0]["type"] == "general"
    assert _general_message(result) == (
        "Недостаточно данных для полной оценки бизнеса"
    )


def test_v562_valid_sales_context_preserves_existing_action_contract():
    context = {
        "profits": [{"gross_sales": 100}],
        "previous_result": {"gross_sales": 120},
    }

    result = AssistantRecommendationService().analyze({
        "sales_down": True,
        "sales_context": context,
    })

    assert result["recommendations"] == [{
        "type": "sales",
        "message": "Проверить причины падения продаж",
        "context": context,
    }]


def test_v563_stock_flag_without_context_is_not_actionable():
    result = AssistantRecommendationService().analyze({
        "low_stock": True,
    })

    assert result["recommendations"][0]["type"] == "general"
    assert _general_message(result) == (
        "Недостаточно данных для полной оценки бизнеса"
    )


def test_v563_valid_stock_context_preserves_existing_action_contract():
    context = {
        "stock_data": {"product_id": "1", "current_stock": 2},
        "sales_data": {"product_id": "1", "sales_count": 5},
        "period_days": 7,
    }

    result = AssistantRecommendationService().analyze({
        "low_stock": True,
        "stock_context": context,
    })

    assert result["recommendations"] == [{
        "type": "stock",
        "message": "Проверить остатки товара",
        "context": context,
    }]


def test_v564_malformed_finance_context_fails_closed_without_exception():
    result = AssistantRecommendationService().analyze({
        "finance_context": ["bad-context"],
        "finance_evidence_available": True,
    })

    assert result["error"] is False
    assert result["recommendations"][0]["type"] == "general"
    assert _general_message(result) == (
        "Недостаточно данных для полной оценки бизнеса"
    )


def test_v564_valid_finance_context_remains_actionable():
    context = {
        "finance_data": {
            "revenue": 100,
            "expenses": 70,
            "profit": 30,
            "margin": 30,
        }
    }

    result = AssistantRecommendationService().analyze({
        "finance_context": context,
        "finance_evidence_available": True,
    })

    assert result["recommendations"] == [{
        "type": "finance",
        "message": "Проверить финансовые показатели",
        "context": context,
    }]


def test_v565_general_fallback_is_presentation_only_not_plan_execution():
    class _Recommendation:
        def analyze(self, report):
            return {
                "error": False,
                "recommendations": [{
                    "type": "general",
                    "message": "Недостаточно данных для полной оценки бизнеса",
                }],
                "count": 1,
            }

    class _Planning:
        def __init__(self):
            self.calls = []

        def build_plan(self, recommendations):
            self.calls.append(recommendations)
            raise AssertionError("general recommendation reached planner")

    class _Executor:
        def __init__(self):
            self.calls = []

        def execute_plan(self, plan):
            self.calls.append(plan)
            raise AssertionError("general recommendation reached executor")

    class _Tasks:
        def __init__(self):
            self.calls = []

        def create_task(self, *args):
            self.calls.append(args)
            raise AssertionError("general recommendation created a task")

    planning = _Planning()
    executor = _Executor()
    tasks = _Tasks()

    result = AssistantBusinessPlannerService(
        recommendation_service=_Recommendation(),
        planning_service=planning,
        executor_service=executor,
        task_service=tasks,
    ).build_plan({}, user_id=7)

    assert result["error"] is False
    assert result["actions"] == []
    assert result["count"] == 0
    assert planning.calls == []
    assert executor.calls == []
    assert tasks.calls == []


def test_v566_actionable_recommendation_still_uses_existing_planner_path():
    recommendation = {
        "type": "sales",
        "message": "Проверить причины падения продаж",
        "context": {"profits": [{"gross_sales": 100}]},
    }

    class _Recommendation:
        def analyze(self, report):
            return {
                "error": False,
                "recommendations": [recommendation],
                "count": 1,
            }

    class _Planning:
        def __init__(self):
            self.calls = []

        def build_plan(self, recommendations):
            self.calls.append(recommendations)
            return {
                "error": False,
                "plan": [{"type": "sales"}],
            }

    class _Executor:
        def __init__(self):
            self.calls = []

        def execute_plan(self, plan):
            self.calls.append(plan)
            return {
                "error": False,
                "actions": [{"type": "sales"}],
                "count": 1,
            }

    planning = _Planning()
    executor = _Executor()

    result = AssistantBusinessPlannerService(
        recommendation_service=_Recommendation(),
        planning_service=planning,
        executor_service=executor,
    ).build_plan({})

    assert planning.calls == [[recommendation]]
    assert executor.calls == [[{"type": "sales"}]]
    assert result["actions"] == [{"type": "sales"}]
    assert result["count"] == 1


def test_v567_general_clean_state_is_also_non_actionable():
    service = AssistantRecommendationService()

    recommendation = service.analyze({
        "sales_down": False,
        "low_stock": False,
        "sales_evidence_available": True,
        "stock_evidence_available": True,
        "finance_evidence_available": True,
    })

    assert recommendation["recommendations"] == [{
        "type": "general",
        "message": "Критичных проблем не найдено",
    }]
