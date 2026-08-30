import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core


def _service():
    core = create_telegram_core()

    return (
        core["core"]
        .orchestrator_service
        .entry_service
        .main_flow_service
        .business_service
        .business_flow_service
        .planner_service
        .recommendation_service
    )


def test_marketing_problem_without_evidence_is_not_actionable():

    result = _service().analyze(
        {
            "marketing_problem": True
        }
    )

    assert result["error"] is False
    assert result["recommendations"] == [
        {
            "type": "general",
            "message": "Недостаточно данных для полной оценки бизнеса"
        }
    ]


def test_marketing_recommendation_requires_verified_evidence_context():

    result = _service().analyze(
        {
            "marketing_problem": True,
            "marketing_evidence_available": True,
            "marketing_context": {
                "evidence": [
                    "CTR снизился"
                ],
                "reason": "Проверить кампанию"
            }
        }
    )

    recommendation = result["recommendations"][0]

    assert recommendation["type"] == "marketing"
    assert recommendation["context"] == {
        "evidence": [
            "CTR снизился"
        ],
        "reason": "Проверить кампанию"
    }
