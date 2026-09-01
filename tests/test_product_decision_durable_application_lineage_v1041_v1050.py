from copy import deepcopy

from app.services.product_decision_history_service import (
    ProductDecisionHistoryService,
)
from app.services.product_decision_history_storage_service import (
    ProductDecisionHistoryStorageService,
)
from app.services.product_decision_persistence_application_service import (
    ProductDecisionPersistenceApplicationService,
)
from app.services.product_decision_persistence_verification_service import (
    ProductDecisionPersistenceVerificationService,
)


class _Storage:
    def __init__(self):
        self.records = []
        self.save_calls = 0

    def load(self):
        return deepcopy(self.records)

    def save(self, records):
        self.save_calls += 1
        self.records = deepcopy(records)
        return True


class _LineageSpyHistory:
    def __init__(self, forged_lineage=None):
        self.lineage = None
        self.forged_lineage = forged_lineage

    def latest(self, sku):
        return None

    def record_persistent(
        self,
        decision,
        application_lineage=None,
    ):
        self.lineage = deepcopy(application_lineage)
        context = {
            "decision_history_available": True,
            "decision_changed": False,
            "previous_decision_type": None,
            "previous_priority": None,
            "decision_recorded_at": "t1",
            "decision_history_count": 1,
            "previous_feedback": None,
            "decision_outcome": None,
        }
        lineage = (
            deepcopy(self.forged_lineage)
            if self.forged_lineage is not None
            else deepcopy(application_lineage)
        )
        return {
            "error": False,
            "code": None,
            "sku": decision["sku"],
            "saved": True,
            "persistence_state": "COMMITTED",
            "decision_recorded_at": "t1",
            "decision_history_count": 1,
            "history_context": context,
            "persistence_application_lineage": lineage,
        }


def _ids():
    preview_id = "product-decision-recompute-preview:auth-1"
    delta_id = "product-decision-preview-delta:" + preview_id
    review_id = "product-decision-preview-review:" + delta_id
    eligibility_id = (
        "product-decision-persistence-eligibility:" + review_id
    )
    authorization_id = (
        "product-decision-persistence-authorization:" + eligibility_id
    )
    readiness_id = (
        "product-decision-persistence-application-readiness:"
        + authorization_id
    )
    application_id = (
        "product-decision-persistence-application:" + readiness_id
    )
    return (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        application_id,
    )


def _lineage(**values):
    (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        application_id,
    ) = _ids()
    result = {
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
    result.update(values)
    return result


def _readiness(**values):
    (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        _,
    ) = _ids()
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY",
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


def test_v1041_application_passes_exact_lineage_to_history_owner():
    history = _LineageSpyHistory()

    result = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    assert result["error"] is False
    assert history.lineage == _lineage()
    assert (
        result["decision_persistence_application_id"]
        == _lineage()["decision_persistence_application_id"]
    )


def test_v1042_durable_snapshot_and_receipt_carry_same_lineage():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )

    receipt = history.record_persistent(
        _decision(),
        application_lineage=_lineage(),
    )

    assert receipt["error"] is False
    assert receipt["persistence_application_lineage"] == _lineage()
    assert storage.records[0][
        "persistence_application_lineage"
    ] == _lineage()


def test_v1043_malformed_lineage_is_rejected_before_storage_write():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )
    lineage = _lineage()
    lineage.pop("draft_id")

    receipt = history.record_persistent(
        _decision(),
        application_lineage=lineage,
    )

    assert receipt["error"] is True
    assert receipt["code"] == (
        "DECISION_HISTORY_PERSISTENCE_APPLICATION_LINEAGE_INVALID"
    )
    assert storage.save_calls == 0
    assert history.history("hook-2") == []


def test_v1044_cross_sku_lineage_is_rejected_before_storage_write():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )

    receipt = history.record_persistent(
        _decision(),
        application_lineage=_lineage(sku="other"),
    )

    assert receipt["error"] is True
    assert storage.save_calls == 0


def test_v1045_application_rejects_forged_commit_receipt_lineage():
    forged = _lineage(draft_id="forged-draft")
    history = _LineageSpyHistory(forged_lineage=forged)

    result = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    assert result["error"] is True
    assert result["code"] == (
        "DECISION_HISTORY_PERSISTENCE_RECEIPT_INVALID"
    )
    assert result["product_decision_persisted"] is False


def test_v1046_verifier_rejects_forged_receipt_lineage_before_readback():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )
    application = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())
    application["history_persistence_receipt"][
        "persistence_application_lineage"
    ]["draft_id"] = "forged"

    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify(application)

    assert result["code"] == (
        "DECISION_PERSISTENCE_VERIFICATION_COMMIT_RECEIPT_INVALID"
    )
    assert result["decision_persistence_verified"] is False


def test_v1047_verifier_rejects_history_snapshot_lineage_mismatch():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )
    application = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())
    history.records[-1][
        "persistence_application_lineage"
    ]["draft_id"] = "forged"

    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify(application)

    assert result["code"] == (
        "DECISION_PERSISTENCE_VERIFICATION_HISTORY_LINEAGE_MISMATCH"
    )


def test_v1048_json_storage_recovers_application_lineage(tmp_path):
    path = tmp_path / "decision-history.json"
    storage = ProductDecisionHistoryStorageService(file_path=path)
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )
    application = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    restarted = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        )
    )
    latest = restarted.latest("hook-2")

    assert application["error"] is False
    assert latest["persistence_application_lineage"] == _lineage()


def test_v1049_feedback_mutation_preserves_application_lineage():
    storage = _Storage()
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=iter(["t1", "t2"]).__next__,
    )
    result = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())
    assert result["error"] is False

    feedback = history.record_feedback("hook-2", "USEFUL")

    assert feedback["error"] is False
    assert history.latest("hook-2")[
        "persistence_application_lineage"
    ] == _lineage()


def test_v1050_restart_readback_verifies_without_execution(tmp_path):
    path = tmp_path / "decision-history.json"
    history = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        ),
        clock=lambda: "t1",
    )
    application = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())

    restarted = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        )
    )
    result = ProductDecisionPersistenceVerificationService(
        restarted
    ).verify(application)

    assert result["error"] is False
    assert result["decision_persistence_verified"] is True
    assert result["verified_snapshot"][
        "persistence_application_lineage"
    ] == _lineage()
    assert result["externally_verified"] is False
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
