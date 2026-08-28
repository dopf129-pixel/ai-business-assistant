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


def test_feedback_is_attached_to_latest_decision_and_is_idempotent():
    storage = MemoryStorage()
    timestamps = iter(["decision-time", "feedback-time"])
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: next(timestamps),
    )
    service.record(_decision())

    saved = service.record_feedback("hook-2", "useful")
    repeated = service.record_feedback("hook-2", "USEFUL")

    assert saved == {
        "error": False,
        "code": None,
        "sku": "hook-2",
        "feedback": "USEFUL",
        "saved": True,
    }
    assert repeated["saved"] is False
    assert service.latest("hook-2")["feedback"] == "USEFUL"
    assert service.latest("hook-2")["feedback_at"] == "feedback-time"
    assert storage.save_calls == 2


def test_feedback_requires_valid_value_and_existing_decision():
    service = ProductDecisionHistoryService(storage_service=MemoryStorage())

    invalid = service.record_feedback("hook-2", "maybe")
    missing = service.record_feedback("hook-2", "not_relevant")

    assert invalid["code"] == "INVALID_FEEDBACK"
    assert missing["code"] == "DECISION_HISTORY_NOT_FOUND"


def test_proposal_status_is_saved_on_latest_decision_and_is_idempotent():
    storage = MemoryStorage()
    timestamps = iter(["decision-time", "proposal-time"])
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: next(timestamps),
    )
    service.record(_decision())

    saved = service.record_proposal_status(
        "hook-2", "REVIEW_REPLENISHMENT", "confirmed"
    )
    repeated = service.record_proposal_status(
        "hook-2", "REVIEW_REPLENISHMENT", "CONFIRMED"
    )

    assert saved["saved"] is True
    assert repeated["saved"] is False
    latest = service.latest("hook-2")
    assert latest["proposal_type"] == "REVIEW_REPLENISHMENT"
    assert latest["proposal_status"] == "CONFIRMED"
    assert latest["proposal_status_at"] == "proposal-time"


def test_proposal_status_requires_valid_value_and_existing_decision():
    service = ProductDecisionHistoryService(storage_service=MemoryStorage())

    invalid = service.record_proposal_status(
        "hook-2", "REVIEW_MARGIN", "EXECUTED"
    )
    missing = service.record_proposal_status(
        "hook-2", "REVIEW_MARGIN", "DISMISSED"
    )

    assert invalid["code"] == "INVALID_PROPOSAL_STATUS"
    assert missing["code"] == "DECISION_HISTORY_NOT_FOUND"


def test_next_decision_correlates_feedback_with_lower_priority():
    service = ProductDecisionHistoryService(
        storage_service=MemoryStorage(),
        clock=lambda: "now",
    )
    service.record(_decision(priority="CRITICAL"))
    service.record_feedback("hook-2", "USEFUL")

    context = service.record(_decision(
        decision_type="HOLD_STOCK",
        priority="LOW",
    ))

    assert context["previous_feedback"] == "USEFUL"
    assert context["decision_outcome"] == "PRIORITY_DECREASED"
    latest = service.latest("hook-2")
    assert latest["source_feedback"] == "USEFUL"
    assert latest["outcome"] == "PRIORITY_DECREASED"


def test_next_decision_detects_higher_or_equal_priority_outcomes():
    service = ProductDecisionHistoryService(
        storage_service=MemoryStorage(),
        clock=lambda: "now",
    )
    service.record(_decision(
        sku="growing-risk",
        decision_type="HOLD_STOCK",
        priority="LOW",
    ))
    service.record_feedback("growing-risk", "NOT_RELEVANT")
    increased = service.record(_decision(
        sku="growing-risk",
        decision_type="REPLENISH_HIGH_PRIORITY",
        priority="CRITICAL",
    ))

    service.record(_decision(
        sku="same-priority",
        decision_type="WATCH_LOW_MARGIN",
        priority="NORMAL",
    ))
    service.record_feedback("same-priority", "USEFUL")
    changed = service.record(_decision(
        sku="same-priority",
        decision_type="HOLD_STOCK",
        priority="NORMAL",
    ))

    assert increased["decision_outcome"] == "PRIORITY_INCREASED"
    assert changed["decision_outcome"] == "DECISION_CHANGED"


def test_decision_change_without_feedback_has_no_inferred_outcome():
    service = ProductDecisionHistoryService(
        storage_service=MemoryStorage(),
        clock=lambda: "now",
    )
    service.record(_decision())

    context = service.record(_decision(
        decision_type="HOLD_STOCK",
        priority="LOW",
    ))

    assert context["previous_feedback"] is None
    assert context["decision_outcome"] is None


def test_learning_summary_counts_products_feedback_and_outcomes():
    service = ProductDecisionHistoryService(
        storage_service=MemoryStorage(),
        clock=lambda: "now",
    )
    service.record(_decision(sku="hook-2", priority="CRITICAL"))
    service.record_feedback("hook-2", "USEFUL")
    service.record(_decision(
        sku="hook-2",
        decision_type="HOLD_STOCK",
        priority="LOW",
    ))
    service.record(_decision(
        sku="hook-3",
        decision_type="WATCH_LOW_MARGIN",
        priority="NORMAL",
    ))
    service.record_feedback("hook-3", "NOT_RELEVANT")

    summary = service.learning_summary()

    assert summary == {
        "error": False,
        "products_count": 2,
        "decision_snapshots_count": 3,
        "feedback_count": 2,
        "feedback_counts": {
            "USEFUL": 1,
            "NOT_RELEVANT": 1,
        },
        "outcome_count": 1,
        "outcome_counts": {
            "PRIORITY_DECREASED": 1,
            "PRIORITY_INCREASED": 0,
            "DECISION_CHANGED": 0,
        },
    }
