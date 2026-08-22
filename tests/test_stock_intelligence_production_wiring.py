import sys

sys.path.insert(
    0,
    "app"
)

from telegram_core_factory import create_telegram_core
from services.stock_intelligence_service import (
    StockIntelligenceService
)


def test_production_core_wires_stock_intelligence_service():

    core = create_telegram_core()

    stock_executor = (
        core["action_router"]
        .executors["stock"]
    )

    intelligence = (
        stock_executor
        .stock_intelligence_service
    )

    assert isinstance(
        intelligence,
        StockIntelligenceService
    )

    assert intelligence.critical_days == 3
    assert intelligence.high_days == 7
    assert intelligence.medium_days == 14
