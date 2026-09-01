from copy import deepcopy

import pytest

from app.services.product_decision_history_service import (
    ProductDecisionHistoryService,
)
from app.services.product_decision_persistence_application_service import (
    ProductDecisionPersistenceApplicationService,
)
from app.services.product_decision_persistence_verification_service import (
    ProductDecisionPersistenceVerificationService,
)


class _Storage:
    def __init__(self, save_result=True, save_error=None):
        self.records = []
        self.save_result = save_result
        self.save_error = save_error
        self.save_calls = 0

    def load(self):
        return deepcopy(self.records)

    def save(self, records):
        self.save_calls += 1
        if self.save_error is not None:
            raise self.save_error
        if self.save_result is True:
            self.records = deepcopy(records)
        return self.save_result


def _decision(**values):
    result = {
        "error": False,
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


def _readiness(**values):
    preview_id = "product-decision-recompute-preview:auth-1"
    delta_id = "product-decision-preview-delta:" + preview_id
    review_id = "product-decision-preview-review:" + delta_id
    eligibility_id = (
        "product-decision-persistence-eligibility:" + review_id
    )
    authorization_id = (
        "product-decision-persistence-authorization:" + eligibility_id
    )
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY",
        "decision_persistence_application_readiness_id": (
            "product-decision-persistence-application-readiness:"
            + authorization_id
        ),
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_persistence_allowed": True,
        "decision_persistence_application_ready": True,
        "decision_persistence_application_started": False,
        "ready_changed_fields": [
            "decision_type",
            "priority",
            "reasons",
        ],
        "ready_changes": {
            "decision_type": {
                "before": "REPLENISH_NORMAL",
                "after": "HOLD_STOCK",
            },
            "priority": {"before": "HIGH", "after": "LOW"},
            "reasons": {
                "before": ["DAYS_OF_STOCK_LOW"],
                "after": ["POSITIVE_UNIT_PROFIT"],
            },
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


class _NoReceiptHistory:
    def latest(self, sku):
        return None

    def record(self, decision):
        return {
            "decision_history_available": True,
            "decision_recorded_at": "t1",
            "decision_history_count": 1,
        }


def test_v1031_rejected_history_save_cannot_become_available_context():
    storage = _Storage(save_result=False)
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )

    with pytest.raises(
        OSError,
        match="DECISION_HISTORY_SAVE_REJECTED",
    ):
        service.record(_decision())

    assert service.history("hook-2") == []
    assert storage.records == []


def test_v1032_unknown_history_save_state_is_not_retained_as_success():
    storage = _Storage(save_result=None)
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )

    with pytest.raises(
        OSError,
        match="DECISION_HISTORY_SAVE_STATE_UNKNOWN",
    ):
        service.record(_decision())

    assert service.history("hook-2") == []


def test_v1033_persistent_record_requires_durable_storage():
    service = ProductDecisionHistoryService(clock=lambda: "t1")

    receipt = service.record_persistent(_decision())

    assert receipt["error"] is True
    assert receipt["code"] == "DECISION_HISTORY_DURABLE_STORAGE_REQUIRED"
    assert receipt["saved"] is False
    assert receipt["persistence_state"] == "NOT_COMMITTED"
    assert receipt["history_context"] is None


def test_v1034_committed_history_write_returns_explicit_receipt():
    storage = _Storage()
    service = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )

    receipt = service.record_persistent(_decision())

    assert receipt["error"] is False
    assert receipt["saved"] is True
    assert receipt["persistence_state"] == "COMMITTED"
    assert receipt["sku"] == "hook-2"
    assert receipt["decision_recorded_at"] == "t1"
    assert receipt["decision_history_count"] == 1
    assert receipt["history_context"][
        "decision_history_available"
    ] is True
    assert storage.records[0]["recorded_at"] == "t1"


def test_v1035_application_refuses_history_without_commit_receipt_api():
    result = ProductDecisionPersistenceApplicationService(
        _NoReceiptHistory()
    ).apply(_readiness(), _decision())

    assert result["error"] is True
    assert result["code"] == "DECISION_HISTORY_PERSISTENCE_RECEIPT_REQUIRED"
    assert result["product_decision_persisted"] is False


def test_v1036_rejected_durable_write_blocks_persistence_application():
    history = ProductDecisionHistoryService(
        storage_service=_Storage(save_result=False),
        clock=lambda: "t1",
    )

    result = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    assert result["code"] == "DECISION_HISTORY_WRITE_REJECTED"
    assert result["persistent"] is False
    assert result["product_decision_persisted"] is False
    assert history.history("hook-2") == []


def test_v1037_unknown_durable_write_state_never_claims_persisted():
    history = ProductDecisionHistoryService(
        storage_service=_Storage(save_result=None),
        clock=lambda: "t1",
    )

    result = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    assert result["code"] == "DECISION_HISTORY_WRITE_STATE_UNKNOWN"
    assert result["persistent"] is False
    assert result["product_decision_persisted"] is False


def test_v1038_applied_result_carries_defensive_committed_receipt():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )

    result = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    assert result["error"] is False
    receipt = result["history_persistence_receipt"]
    assert receipt["saved"] is True
    assert receipt["persistence_state"] == "COMMITTED"
    assert receipt["decision_recorded_at"] == "t1"
    receipt["history_context"]["decision_history_count"] = 999
    assert history.history("hook-2")[0]["recorded_at"] == "t1"


def test_v1039_verifier_requires_committed_receipt_before_readback():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )
    application = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())
    application.pop("history_persistence_receipt")

    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify(application)

    assert result["error"] is True
    assert result["code"] == (
        "DECISION_PERSISTENCE_VERIFICATION_COMMIT_RECEIPT_REQUIRED"
    )
    assert result["decision_persistence_verified"] is False


def test_v1040_committed_receipt_and_readback_verify_without_execution():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )
    application = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify(application)

    assert result["error"] is False
    assert result["decision_persistence_verified"] is True
    assert result["product_decision_persisted"] is True
    assert result["verified_recorded_at"] == "t1"
    assert result["externally_verified"] is False
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
