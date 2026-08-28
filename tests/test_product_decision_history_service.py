from app.services.product_decision_history_service import (
    ProductDecisionHistoryService,
)
from app.services.product_decision_history_storage_service import (
    ProductDecisionHistoryStorageService,
)


class MemoryStorage:
    def __init__(self, records=None):
        self.records = list(records or [])
        self.save_calls = 0

    def load(self):
        return list(self.records)

    def save(self, records):
        self.records = list(records)
        self.save_calls += 1
        return True


def _decision(**overrides):
    result = {
        "error": False,
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "REPLENISH_HIGH_PRIORITY",
        "priority": "CRITICAL",
        "confidence": "HIGH",
        "sales_velocity": 4.0,
        "days_of_stock": 2.0,
        "decision_profit_per_unit": 35.1,
        "decision_margin_percent": 36.56,
        "economics_basis": "ESTIMATED_RETURNS",
    }
    result.update(overrides)
    return result


def test_history_records_baseline_once_and_real_transition():
    storage = MemoryStorage()
    timestamps = iter(["t1", "t2"])
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: next(timestamps),
    )

    baseline = service.record(_decision())
    repeated = service.record(_decision(days_of_stock=1.0))
    changed = service.record(_decision(
        decision_type="INVESTIGATE_LOW_PROFIT",
        priority="HIGH",
    ))

    assert baseline["decision_changed"] is False
    assert repeated["decision_changed"] is False
    assert changed["decision_changed"] is True
    assert changed["previous_decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert changed["previous_priority"] == "CRITICAL"
    assert len(service.history("hook-2")) == 2
    assert storage.save_calls == 2


def test_history_ignores_errors_and_insufficient_data():
    storage = MemoryStorage()
    service = ProductDecisionHistoryService(storage_service=storage)

    error_context = service.record(_decision(error=True))
    missing_context = service.record(_decision(
        decision_type="INSUFFICIENT_DATA",
        priority="NONE",
    ))

    assert error_context["decision_history_available"] is False
    assert missing_context["decision_history_available"] is False
    assert service.history("hook-2") == []
    assert storage.save_calls == 0


def test_history_retains_bounded_number_of_changes_per_sku():
    storage = MemoryStorage()
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "now",
        max_records_per_sku=2,
    )

    service.record(_decision(decision_type="HOLD_STOCK", priority="LOW"))
    service.record(_decision(decision_type="WATCH_LOW_MARGIN", priority="NORMAL"))
    service.record(_decision(decision_type="INVESTIGATE_LOW_PROFIT", priority="HIGH"))

    history = service.history("hook-2")
    assert len(history) == 2
    assert history[0]["decision_type"] == "INVESTIGATE_LOW_PROFIT"
    assert history[1]["decision_type"] == "WATCH_LOW_MARGIN"


def test_json_storage_persists_and_recovers_history(tmp_path):
    file_path = tmp_path / "decision-history.json"
    storage = ProductDecisionHistoryStorageService(file_path=file_path)
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "2026-08-28T10:00:00+00:00",
    )

    service.record(_decision())
    restored = ProductDecisionHistoryService(storage_service=storage)

    assert restored.latest("hook-2")["decision_type"] == (
        "REPLENISH_HIGH_PRIORITY"
    )
    assert not file_path.with_suffix(".json.tmp").exists()
