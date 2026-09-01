from copy import deepcopy

from product_decision_user_action_completion_revision import (
    build_product_decision_user_action_completion_revision,
)
from services.product_decision_user_action_completion_persistence_service import (
    ProductDecisionUserActionCompletionPersistenceService,
)


class Storage:
    def __init__(
        self,
        records=None,
        fail_load=False,
        fail_save=False,
        save_result=True,
    ):
        self.records = deepcopy([] if records is None else records)
        self.fail_load = fail_load
        self.fail_save = fail_save
        self.save_result = save_result
        self.save_calls = []

    def load(self):
        if self.fail_load:
            raise OSError("load")
        return deepcopy(self.records)

    def save(self, records):
        self.save_calls.append(deepcopy(records))
        if self.fail_save:
            raise OSError("save")
        if self.save_result is True:
            self.records = deepcopy(records)
        return self.save_result


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
    item_id = "manual-step-1"
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED",
        "user_action_completion_evidence_id": (
            "product-decision-user-action-completion-evidence:%s:%s"
            % (checklist_id, item_id)
        ),
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "item_id": item_id,
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


def _persist(evidence=None, storage=None):
    storage = storage or Storage()
    service = ProductDecisionUserActionCompletionPersistenceService(storage)
    return service.persist(evidence if evidence is not None else _evidence()), storage


def test_v871_non_mapping_evidence_fails_closed():
    result, storage = _persist(["not", "a", "mapping"])

    assert result["error"] is True
    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_INPUT_INVALID"
    )
    assert storage.save_calls == []


def test_v872_missing_explicit_success_marker_is_not_persisted():
    source = _evidence()
    source.pop("error")

    result, storage = _persist(source)

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_RESULT_INVALID"
    )
    assert storage.save_calls == []


def test_v873_numeric_identity_is_not_coerced_into_persistence_lineage():
    result, storage = _persist(_evidence(sku=123))

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_CONTEXT_REQUIRED"
    )
    assert storage.save_calls == []


def test_v874_verification_must_remain_bound_to_application():
    result, storage = _persist(
        _evidence(decision_persistence_application_id="other-app")
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_VERIFICATION_ID_MISMATCH"
    )
    assert storage.save_calls == []


def test_v875_completion_status_and_user_report_must_agree():
    result, storage = _persist(
        _evidence(
            completion_decision="NOT_COMPLETED",
            user_reported_completed=False,
        )
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_DECISION_MISMATCH"
    )
    assert storage.save_calls == []


def test_v876_malformed_storage_container_fails_closed():
    result, storage = _persist(storage=Storage(records={"not": "a list"}))

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_STORAGE_INVALID"
    )
    assert storage.save_calls == []


def test_v877_malformed_existing_record_is_not_silently_dropped():
    result, storage = _persist(storage=Storage(records=[{"ok": True}, 123]))

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_STORAGE_INVALID"
    )
    assert storage.save_calls == []


def test_v878_explicit_false_save_result_is_not_reported_as_persisted():
    storage = Storage(save_result=False)

    result, storage = _persist(storage=storage)

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_WRITE_NOT_CONFIRMED"
    )
    assert result["completion_persisted"] is False
    assert result["persistent"] is False
    assert len(storage.save_calls) == 1
    assert storage.records == []


def test_v879_forged_root_evidence_id_cannot_be_persisted():
    result, storage = _persist(
        _evidence(user_action_completion_evidence_id="forged")
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_EVIDENCE_ID_MISMATCH"
    )
    assert storage.save_calls == []


def test_v880_root_and_revision_persistence_preserve_verified_lineage():
    storage = Storage()
    service = ProductDecisionUserActionCompletionPersistenceService(storage)

    root_source = _evidence()
    root = service.persist(root_source)

    assert root["error"] is False
    assert root["saved"] is True
    assert root["completion_revision"] == 1
    assert root["decision_persistence_application_id"] == "app-1"
    assert root["decision_persistence_verified"] is True
    assert root["item_id"] == "manual-step-1"
    assert root["instruction"] == "Проверить остаток."
    assert (
        root["verified_recorded_at"]
        == "2026-09-01T12:00:00+00:00"
    )
    assert root["externally_verified"] is False
    assert root["executed"] is False

    revision_source = build_product_decision_user_action_completion_revision(
        root,
        "NOT_COMPLETED",
    )
    assert revision_source["error"] is False
    assert revision_source["completion_revision"] == 2
    assert revision_source["decision_persistence_verified"] is True

    revision = service.persist(revision_source)

    assert revision["error"] is False
    assert revision["saved"] is True
    assert revision["completion_revision"] == 2
    assert (
        revision["completion_evidence_root_id"]
        == root["user_action_completion_evidence_id"]
    )
    assert (
        revision["previous_user_action_completion_evidence_id"]
        == root["user_action_completion_evidence_id"]
    )
    assert revision["completion_decision"] == "NOT_COMPLETED"
    assert revision["user_reported_completed"] is False
    assert revision["decision_persistence_application_id"] == "app-1"
    assert revision["decision_persistence_verified"] is True
    assert revision["externally_verified"] is False
    assert revision["executed"] is False
    assert len(storage.records) == 2
