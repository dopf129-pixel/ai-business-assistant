from copy import deepcopy

from services.product_decision_user_action_completion_persistence_service import ProductDecisionUserActionCompletionPersistenceService


class Storage:
    def __init__(self, records=None, fail_load=False, fail_save=False):
        self.records = deepcopy(records or [])
        self.fail_load = fail_load
        self.fail_save = fail_save
    def load(self):
        if self.fail_load: raise OSError("load")
        return deepcopy(self.records)
    def save(self, records):
        if self.fail_save: raise OSError("save")
        self.records = deepcopy(records)
        return True


def _evidence(**values):
    application_id = "app-1"
    verification_id = (
        "product-decision-persistence-verification:" + application_id
    )
    guidance_id = (
        "product-decision-user-action-guidance:" + verification_id
    )
    checklist_id = (
        "product-decision-user-action-checklist:" + guidance_id
    )
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED",
        "user_action_completion_evidence_id": (
            "product-decision-user-action-completion-evidence:"
            + checklist_id
            + ":manual-step-1"
        ),
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "item_id": "manual-step-1",
        "instruction": "Проверить остаток.",
        "completion_decision": "CONFIRM_COMPLETED",
        "user_reported_completed": True,
        "completion_evidence_source": "USER_REPORT",
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result

def test_persists_user_report_without_execution():
    storage = Storage()
    result = ProductDecisionUserActionCompletionPersistenceService(storage).persist(_evidence())
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED"
    assert result["saved"] is True
    assert result["persistent"] is True
    assert result["externally_verified"] is False
    assert result["executed"] is False
    assert len(storage.records) == 1


def test_retry_is_idempotent():
    evidence = _evidence()
    storage = Storage([evidence])
    result = ProductDecisionUserActionCompletionPersistenceService(storage).persist(evidence)
    assert result["saved"] is False
    assert len(storage.records) == 1


def test_same_id_different_payload_blocks():
    old = _evidence(user_reported_completed=False)
    result = ProductDecisionUserActionCompletionPersistenceService(Storage([old])).persist(_evidence())
    assert result["code"] == "USER_ACTION_COMPLETION_PERSISTENCE_ID_CONFLICT"


def test_unsafe_execution_state_blocks():
    result = ProductDecisionUserActionCompletionPersistenceService(Storage()).persist(_evidence(executed=True))
    assert result["code"] == "USER_ACTION_COMPLETION_PERSISTENCE_SAFETY_BOUNDARY_VIOLATION"


def test_wrong_source_blocks():
    result = ProductDecisionUserActionCompletionPersistenceService(Storage()).persist(_evidence(completion_evidence_source="SYSTEM"))
    assert result["code"] == "USER_ACTION_COMPLETION_PERSISTENCE_SOURCE_INVALID"


def test_read_failure_blocks():
    result = ProductDecisionUserActionCompletionPersistenceService(Storage(fail_load=True)).persist(_evidence())
    assert result["code"] == "USER_ACTION_COMPLETION_PERSISTENCE_READ_FAILED"


def test_write_failure_blocks():
    result = ProductDecisionUserActionCompletionPersistenceService(Storage(fail_save=True)).persist(_evidence())
    assert result["code"] == "USER_ACTION_COMPLETION_PERSISTENCE_WRITE_FAILED"
