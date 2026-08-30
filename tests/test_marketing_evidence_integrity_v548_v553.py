import sys

sys.path.insert(0, "app")

from services.assistant_action_router_service import AssistantActionRouterService
from services.assistant_marketing_executor_service import AssistantMarketingExecutorService


def test_v548_malformed_marketing_evidence_fails_closed():

    router = AssistantActionRouterService(
        executors={
            "marketing": AssistantMarketingExecutorService()
        }
    )

    for context in (
        None,
        {},
        {"evidence": []},
        {"evidence": [None]},
        {"evidence": [""]},
    ):
        result = router.execute(
            {
                "type": "marketing",
                "context": context
            }
        )

        assert result["error"] is True


def test_v553_persisted_run_raises_on_missing_marketing_evidence():

    router = AssistantActionRouterService(
        executors={
            "marketing": AssistantMarketingExecutorService()
        }
    )

    try:
        router.run(
            {
                "type": "marketing",
                "context": {}
            }
        )
    except RuntimeError as exc:
        assert str(exc) == "Недостаточно данных для анализа маркетинга"
    else:
        raise AssertionError("marketing error result must enter FAILED lifecycle")
