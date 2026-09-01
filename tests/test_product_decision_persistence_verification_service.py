from copy import deepcopy

from services.product_decision_persistence_verification_service import (
    ProductDecisionPersistenceVerificationService,
)


class FakeHistoryService:
    def __init__(self, latest=None, fail=False):
        self.latest_value = deepcopy(latest)
        self.fail = fail
        self.calls = []

    def latest(self, sku):
        self.calls.append(sku)
        if self.fail:
            raise OSError("read failed")
        return deepcopy(self.latest_value)


def _ids():
    preview_id = "product-decision-recompute-preview:auth-1"
    delta_id = "product-decision-preview-delta:" + preview_id
    review_id = "product-decision-preview-review:" + delta_id
    eligibility_id = "product-decision-persistence-eligibility:" + review_id
    authorization_id = "product-decision-persistence-authorization:" + eligibility_id
    readiness_id = "product-decision-persistence-application-readiness:" + authorization_id
    application_id = "product-decision-persistence-application:" + readiness_id
    return preview_id, delta_id, review_id, eligibility_id, authorization_id, readiness_id, application_id


def _lineage():
    (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        application_id,
    ) = _ids()
    return {
        "decision_persistence_application_id": application_id,
        "decision_persistence_application_readiness_id": readiness_id,
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": "draft-1",
        "sku": "hook-2",
    }


def _decision(**values):
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


def _snapshot(**values):
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
        "profit_per_unit": 35.10,
        "margin_percent": 36.56,
        "economics_basis": "CURRENT_PRICE",
        "recorded_at": "2026-08-29T15:10:00+00:00",
        "persistence_application_lineage": _lineage(),
    }
    result.update(values)
    return result


def _application(**values):
    preview_id, delta_id, review_id, eligibility_id, authorization_id, readiness_id, application_id = _ids()
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLIED",
        "decision_persistence_application_id": application_id,
        "decision_persistence_application_readiness_id": readiness_id,
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_persistence_allowed": True,
        "decision_persistence_application_ready": True,
        "decision_persistence_application_started": True,
        "decision_persistence_application_completed": True,
        "history_context": {
            "decision_history_available": True,
            "decision_recorded_at": "2026-08-29T15:10:00+00:00",
            "decision_history_count": 2,
        },
        "history_persistence_receipt": {
            "error": False,
            "code": None,
            "sku": "hook-2",
            "saved": True,
            "persistence_state": "COMMITTED",
            "decision_recorded_at": "2026-08-29T15:10:00+00:00",
            "decision_history_count": 2,
            "history_context": {
                "decision_history_available": True,
                "decision_recorded_at": "2026-08-29T15:10:00+00:00",
                "decision_history_count": 2,
            },
            "persistence_application_lineage": _lineage(),
        },
        "persisted_preview_decision": _decision(),
        "persistent": True,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_persisted_decision_is_verified_by_read_back_without_mutation():
    history = FakeHistoryService(_snapshot())
    service = ProductDecisionPersistenceVerificationService(history)
    application = _application()
    before = deepcopy(application)

    result = service.verify(application)

    assert result["status"] == "PRODUCT_DECISION_PERSISTENCE_VERIFIED"
    assert result["decision_persistence_verified"] is True
    assert result["product_decision_persisted"] is True
    assert result["verified_snapshot"]["decision_type"] == "HOLD_STOCK"
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert history.calls == ["hook-2"]
    assert application == before


def test_forged_application_id_is_blocked_before_read():
    history = FakeHistoryService(_snapshot())
    result = ProductDecisionPersistenceVerificationService(history).verify(
        _application(decision_persistence_application_id="forged")
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_ID_MISMATCH"
    assert history.calls == []


def test_forged_intermediate_lineage_is_blocked_before_read():
    history = FakeHistoryService(_snapshot())
    result = ProductDecisionPersistenceVerificationService(history).verify(
        _application(decision_preview_review_id="forged")
    )
    assert result["code"] == "DECISION_PERSISTENCE_ELIGIBILITY_ID_MISMATCH"
    assert history.calls == []


def test_non_applied_status_is_blocked_before_read():
    history = FakeHistoryService(_snapshot())
    result = ProductDecisionPersistenceVerificationService(history).verify(
        _application(status="PRODUCT_DECISION_PERSISTENCE_APPLICATION_BLOCKED")
    )
    assert result["code"] == "DECISION_PERSISTENCE_APPLICATION_STATUS_INVALID"
    assert history.calls == []


def test_execution_boundary_violation_is_blocked_before_read():
    history = FakeHistoryService(_snapshot())
    result = ProductDecisionPersistenceVerificationService(history).verify(
        _application(execution_ready=True)
    )
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_SAFETY_BOUNDARY_VIOLATION"
    assert history.calls == []


def test_expected_preview_sku_mismatch_is_blocked_before_read():
    history = FakeHistoryService(_snapshot())
    decision = _decision(sku="other")
    result = ProductDecisionPersistenceVerificationService(history).verify(
        _application(persisted_preview_decision=decision)
    )
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_SKU_MISMATCH"
    assert history.calls == []


def test_history_read_failure_is_fail_closed():
    history = FakeHistoryService(_snapshot(), fail=True)
    result = ProductDecisionPersistenceVerificationService(history).verify(_application())
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_READ_FAILED"
    assert result["decision_persistence_verified"] is False


def test_missing_history_snapshot_is_blocked():
    history = FakeHistoryService(None)
    result = ProductDecisionPersistenceVerificationService(history).verify(_application())
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_HISTORY_NOT_FOUND"


def test_recorded_at_mismatch_is_blocked():
    history = FakeHistoryService(_snapshot(recorded_at="other"))
    result = ProductDecisionPersistenceVerificationService(history).verify(_application())
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_RECORDED_AT_MISMATCH"


def test_snapshot_business_metric_mismatch_is_reported():
    history = FakeHistoryService(_snapshot(profit_per_unit=12.34))
    result = ProductDecisionPersistenceVerificationService(history).verify(_application())
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_SNAPSHOT_MISMATCH"
    assert result["mismatched_fields"] == ["decision_profit_per_unit"]


def test_snapshot_reasons_mismatch_is_reported():
    history = FakeHistoryService(_snapshot(reasons=["OTHER"]))
    result = ProductDecisionPersistenceVerificationService(history).verify(_application())
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_SNAPSHOT_MISMATCH"
    assert result["mismatched_fields"] == ["reasons"]


def test_missing_context_is_blocked_before_read():
    history = FakeHistoryService(_snapshot())
    result = ProductDecisionPersistenceVerificationService(history).verify(
        _application(draft_id="")
    )
    assert result["code"] == "DECISION_PERSISTENCE_VERIFICATION_CONTEXT_REQUIRED"
    assert history.calls == []
