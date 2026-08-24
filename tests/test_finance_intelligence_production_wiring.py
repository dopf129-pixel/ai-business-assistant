import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core
from services.assistant_finance_executor_service import (
    AssistantFinanceExecutorService
)
from services.finance_intelligence_service import (
    FinanceIntelligenceService
)


def test_production_core_wires_finance_intelligence_service():

    core = create_telegram_core()
    router = core["action_router"]

    finance_executor = (
        router.executors["finance"]
    )

    assert isinstance(
        finance_executor,
        AssistantFinanceExecutorService
    )

    assert isinstance(
        finance_executor.finance_intelligence_service,
        FinanceIntelligenceService
    )

    assert "sales" in router.executors
    assert "stock" in router.executors
