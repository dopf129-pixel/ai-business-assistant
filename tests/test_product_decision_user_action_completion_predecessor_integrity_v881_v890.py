from copy import deepcopy

from product_decision_user_action_completion_revision import (
    build_product_decision_user_action_completion_revision,
)
from services.product_decision_user_action_completion_persistence_service import (
    ProductDecisionUserActionCompletionPersistenceService,
)


class Storage:
    def __init__(self, records=None):
        self.records = deepcopy([] if records is None else records)
        self.save_calls = []

    def load(self):
        return deepcopy(self.records)

    def save(self, records):
        self.save_calls.append(deepcopy(records))
        self.records = deepcopy(records)
        return True


def _root_evidence(**values):
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


def _root_and_revision():
    storage = Storage()
    service = ProductDecisionUserActionCompletionPersistenceService(storage)
    root_source = _root_evidence()
    root_receipt = service.persist(root_source)
    revision_source = build_product_decision_user_action_completion_revision(
        root_receipt,
        "NOT_COMPLETED",
    )
    return storage, service, root_source, root_receipt, revision_source


def test_v881_revision_without_persisted_predecessor_fails_closed():
    _, _, _, _, revision_source = _root_and_revision()
    empty = Storage()
    result = (
        ProductDecisionUserActionCompletionPersistenceService(empty)
        .persist(revision_source)
    )

    assert result["error"] is True
    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_REQUIRED"
    )
    assert empty.save_calls == []


def test_v882_duplicate_predecessor_is_ambiguous_and_blocks():
    _, _, root_source, _, revision_source = _root_and_revision()
    storage = Storage([root_source, deepcopy(root_source)])

    result = (
        ProductDecisionUserActionCompletionPersistenceService(storage)
        .persist(revision_source)
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_AMBIGUOUS"
    )
    assert storage.save_calls == []


def test_v883_predecessor_verified_lineage_must_match_revision():
    _, _, root_source, _, revision_source = _root_and_revision()
    forged = deepcopy(root_source)
    forged["decision_persistence_application_id"] = "other-app"
    storage = Storage([forged])

    result = (
        ProductDecisionUserActionCompletionPersistenceService(storage)
        .persist(revision_source)
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_LINEAGE_MISMATCH"
    )
    assert storage.save_calls == []


def test_v884_predecessor_safety_overclaim_blocks_revision():
    _, _, root_source, _, revision_source = _root_and_revision()
    unsafe = deepcopy(root_source)
    unsafe["externally_verified"] = True
    storage = Storage([unsafe])

    result = (
        ProductDecisionUserActionCompletionPersistenceService(storage)
        .persist(revision_source)
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_SAFETY_INVALID"
    )
    assert storage.save_calls == []


def test_v885_predecessor_status_and_decision_must_agree():
    _, _, root_source, _, revision_source = _root_and_revision()
    contradictory = deepcopy(root_source)
    contradictory["completion_decision"] = "NOT_COMPLETED"
    contradictory["user_reported_completed"] = False
    storage = Storage([contradictory])

    result = (
        ProductDecisionUserActionCompletionPersistenceService(storage)
        .persist(revision_source)
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_DECISION_INVALID"
    )
    assert storage.save_calls == []


def test_v886_missing_predecessor_success_marker_is_not_trusted():
    _, _, root_source, _, revision_source = _root_and_revision()
    malformed = deepcopy(root_source)
    malformed.pop("error")
    storage = Storage([malformed])

    result = (
        ProductDecisionUserActionCompletionPersistenceService(storage)
        .persist(revision_source)
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_RESULT_INVALID"
    )
    assert storage.save_calls == []


def test_v887_revision_three_requires_canonical_revision_two_predecessor():
    storage, service, _, _, revision_two = _root_and_revision()
    revision_two_receipt = service.persist(revision_two)
    revision_three = build_product_decision_user_action_completion_revision(
        revision_two_receipt,
        "CONFIRM_COMPLETED",
    )

    storage.records[-1]["completion_revision"] = 7

    result = service.persist(revision_three)

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_REVISION_INVALID"
    )
    assert len(storage.records) == 2


def test_v888_predecessor_item_instruction_must_remain_exact():
    _, _, root_source, _, revision_source = _root_and_revision()
    forged = deepcopy(root_source)
    forged["instruction"] = "Другая инструкция."
    storage = Storage([forged])

    result = (
        ProductDecisionUserActionCompletionPersistenceService(storage)
        .persist(revision_source)
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_PREDECESSOR_LINEAGE_MISMATCH"
    )
    assert storage.save_calls == []


def test_v889_duplicate_current_revision_id_is_storage_ambiguity():
    _, _, root_source, _, revision_source = _root_and_revision()
    storage = Storage(
        [root_source, deepcopy(revision_source), deepcopy(revision_source)]
    )

    result = (
        ProductDecisionUserActionCompletionPersistenceService(storage)
        .persist(revision_source)
    )

    assert (
        result["code"]
        == "USER_ACTION_COMPLETION_PERSISTENCE_ID_AMBIGUOUS"
    )
    assert storage.save_calls == []


def test_v890_root_revision_two_revision_three_chain_is_persistable():
    storage = Storage()
    service = ProductDecisionUserActionCompletionPersistenceService(storage)

    root_receipt = service.persist(_root_evidence())
    revision_two_source = (
        build_product_decision_user_action_completion_revision(
            root_receipt,
            "NOT_COMPLETED",
        )
    )
    revision_two_receipt = service.persist(revision_two_source)
    revision_three_source = (
        build_product_decision_user_action_completion_revision(
            revision_two_receipt,
            "CONFIRM_COMPLETED",
        )
    )
    revision_three_receipt = service.persist(revision_three_source)

    assert root_receipt["error"] is False
    assert revision_two_receipt["error"] is False
    assert revision_three_receipt["error"] is False
    assert root_receipt["completion_revision"] == 1
    assert revision_two_receipt["completion_revision"] == 2
    assert revision_three_receipt["completion_revision"] == 3
    assert (
        revision_three_receipt[
            "previous_user_action_completion_evidence_id"
        ]
        == revision_two_receipt["user_action_completion_evidence_id"]
    )
    assert revision_three_receipt["decision_persistence_verified"] is True
    assert revision_three_receipt["externally_verified"] is False
    assert revision_three_receipt["executed"] is False
    assert len(storage.records) == 3
