from copy import deepcopy

from services.product_decision_persistence_application_service import (
    ProductDecisionPersistenceApplicationService,
)


class FakeHistoryService:
    def __init__(self, previous=None, record_result=None, fail_latest=False, fail_record=False):
        self.previous = deepcopy(previous)
        self.record_result = record_result or {
            "decision_history_available": True,
            "decision_changed": True,
            "decision_recorded_at": "2026-08-29T15:10:00+00:00",
            "decision_history_count": 2,
        }
        self.fail_latest = fail_latest
        self.fail_record = fail_record
        self.record_calls = []

    def latest(self, sku):
        if self.fail_latest:
            raise OSError("read failed")
        return deepcopy(self.previous)

    def record(self, decision):
        if self.fail_record:
            raise OSError("write failed")
        self.record_calls.append(deepcopy(decision))
        return deepcopy(self.record_result)


def _readiness(**values):
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY",
        "decision_persistence_application_readiness_id": "product-decision-persistence-application-readiness:auth-1",
        "decision_persistence_authorization_id": "auth-1",
        "sku": "hook-2",
        "decision_persistence_allowed": True,
        "decision_persistence_application_ready": True,
        "decision_persistence_application_started": False,
        "ready_changed_fields": ["decision_type", "priority", "reasons"],
        "ready_changes": {
            "decision_type": {"before": "REPLENISH_NORMAL", "after": "HOLD_STOCK"},
            "priority": {"before": "HIGH", "after": "LOW"},
            "reasons": {"before": ["DAYS_OF_STOCK_LOW"], "after": ["POSITIVE_UNIT_PROFIT"]},
        },
        "ready_preview_decision": {
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
        },
        "persistent": False,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _full_preview(**values):
    result = {
        "sku": "hook-2",
        "product_id": 123,
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "confidence": "HIGH",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
        "sales_velocity": 4.2,
        "current_stock": 30,
        "days_of_stock": 7.1,
        "decision_profit_per_unit": 35.10,
        "decision_margin_percent": 36.56,
        "economics_basis": "CURRENT_PRICE",
    }
    result.update(values)
    return result


def test_authorized_ready_preview_is_recorded_without_execution():
    history = FakeHistoryService(
        previous={"sku": "hook-2", "decision_type": "REPLENISH_NORMAL", "priority": "HIGH"}
    )
    service = ProductDecisionPersistenceApplicationService(history)
    readiness = _readiness()
    preview = _full_preview()
    before_readiness = deepcopy(readiness)
    before_preview = deepcopy(preview)

    result = service.apply(readiness, preview)

    assert result["status"] == "PRODUCT_DECISION_PERSISTENCE_APPLIED"
    assert result["decision_persistence_application_started"] is True
    assert result["decision_persistence_application_completed"] is True
    assert result["persistent"] is True
    assert result["product_decision_persisted"] is True
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert history.record_calls == [preview]
    assert readiness == before_readiness
    assert preview == before_preview


def test_full_preview_business_metrics_are_preserved_for_history_record():
    history = FakeHistoryService()
    preview = _full_preview()
    result = ProductDecisionPersistenceApplicationService(history).apply(_readiness(), preview)
    assert result["error"] is False
    assert history.record_calls[0]["sales_velocity"] == 4.2
    assert history.record_calls[0]["decision_profit_per_unit"] == 35.10
    assert history.record_calls[0]["economics_basis"] == "CURRENT_PRICE"


def test_forged_readiness_id_is_blocked_without_write():
    history = FakeHistoryService()
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(decision_persistence_application_readiness_id="forged"), _full_preview()
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_READINESS_ID_MISMATCH"
    assert history.record_calls == []


def test_not_ready_is_blocked_without_write():
    history = FakeHistoryService()
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(decision_persistence_application_ready=False), _full_preview()
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_NOT_READY"
    assert history.record_calls == []


def test_already_started_is_blocked_without_write():
    history = FakeHistoryService()
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(decision_persistence_application_started=True), _full_preview()
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_ALREADY_STARTED"
    assert history.record_calls == []


def test_execution_boundary_is_blocked_without_write():
    history = FakeHistoryService()
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(execution_ready=True), _full_preview()
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_SAFETY_BOUNDARY_VIOLATION"
    assert history.record_calls == []


def test_full_preview_sku_mismatch_is_blocked_without_write():
    history = FakeHistoryService()
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(), _full_preview(sku="other")
    )
    assert result["code"] == "DECISION_PERSISTENCE_FULL_PREVIEW_SKU_MISMATCH"
    assert history.record_calls == []


def test_full_preview_stable_field_mismatch_is_blocked_without_write():
    history = FakeHistoryService()
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(), _full_preview(confidence="LOW")
    )
    assert result["code"] == "DECISION_PERSISTENCE_FULL_PREVIEW_MISMATCH"
    assert history.record_calls == []


def test_unsafe_full_preview_is_blocked_without_write():
    history = FakeHistoryService()
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(), _full_preview(execution_allowed=True)
    )
    assert result["code"] == "DECISION_PERSISTENCE_FULL_PREVIEW_SAFETY_VIOLATION"
    assert history.record_calls == []


def test_change_after_must_match_full_preview():
    history = FakeHistoryService()
    changes = deepcopy(_readiness()["ready_changes"])
    changes["priority"]["after"] = "CRITICAL"
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(ready_changes=changes), _full_preview()
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_CHANGE_PREVIEW_MISMATCH"
    assert history.record_calls == []


def test_existing_history_signature_blocks_non_recordable_change():
    history = FakeHistoryService(
        previous={
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "LOW",
            "reasons": ["OLD_REASON"],
        }
    )
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(), _full_preview()
    )
    assert result["code"] == "DECISION_HISTORY_SIGNATURE_UNCHANGED"
    assert history.record_calls == []


def test_history_read_failure_is_fail_closed():
    history = FakeHistoryService(fail_latest=True)
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(), _full_preview()
    )
    assert result["code"] == "DECISION_HISTORY_READ_FAILED"
    assert history.record_calls == []


def test_history_write_failure_is_fail_closed():
    history = FakeHistoryService(fail_record=True)
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(), _full_preview()
    )
    assert result["code"] == "DECISION_HISTORY_WRITE_FAILED"
    assert result["product_decision_persisted"] is False
    assert result["execution_allowed"] is False


def test_unconfirmed_history_write_is_blocked():
    history = FakeHistoryService(record_result={"decision_history_available": False})
    result = ProductDecisionPersistenceApplicationService(history).apply(
        _readiness(), _full_preview()
    )
    assert result["code"] == "DECISION_HISTORY_WRITE_NOT_CONFIRMED"
    assert result["product_decision_persisted"] is False
