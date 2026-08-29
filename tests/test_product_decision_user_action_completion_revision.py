from copy import deepcopy

from product_decision_user_action_completion_revision import (
    build_product_decision_user_action_completion_revision,
)


def _persisted(**values):
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED",
        "user_action_completion_evidence_id": "root-1",
        "user_action_checklist_id": "check-1",
        "user_action_guidance_id": "guidance-1",
        "sku": "hook-2",
        "item_id": "manual-step-1",
        "user_reported_completed": False,
        "completion_evidence_source": "USER_REPORT",
        "completion_persisted": True,
        "externally_verified": False,
        "persistent": True,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_not_completed_can_be_revised_to_completed_without_mutating_source():
    source = _persisted()
    before = deepcopy(source)
    result = build_product_decision_user_action_completion_revision(source, "CONFIRM_COMPLETED")
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED"
    assert result["completion_revision"] == 2
    assert result["user_action_completion_evidence_id"] == "root-1:revision:2"
    assert result["user_reported_completed"] is True
    assert result["persistent"] is False
    assert result["executed"] is False
    assert source == before


def test_revision_chain_increments_existing_revision():
    result = build_product_decision_user_action_completion_revision(
        _persisted(
            user_action_completion_evidence_id="root-1:revision:2",
            completion_evidence_root_id="root-1",
            completion_revision=2,
        ),
        "NOT_COMPLETED",
    )
    assert result["completion_revision"] == 3
    assert result["user_action_completion_evidence_id"] == "root-1:revision:3"
    assert result["status"] == "PRODUCT_DECISION_USER_ACTION_COMPLETION_DECLINED"


def test_invalid_decision_blocks():
    result = build_product_decision_user_action_completion_revision(_persisted(), "YES")
    assert result["code"] == "USER_ACTION_COMPLETION_REVISION_DECISION_INVALID"


def test_unpersisted_source_blocks():
    result = build_product_decision_user_action_completion_revision(
        _persisted(persistent=False), "CONFIRM_COMPLETED"
    )
    assert result["code"] == "USER_ACTION_COMPLETION_REVISION_PERSISTED_SOURCE_REQUIRED"


def test_external_verification_claim_blocks():
    result = build_product_decision_user_action_completion_revision(
        _persisted(externally_verified=True), "CONFIRM_COMPLETED"
    )
    assert result["code"] == "USER_ACTION_COMPLETION_REVISION_SOURCE_INVALID"


def test_execution_boundary_violation_blocks():
    result = build_product_decision_user_action_completion_revision(
        _persisted(execution_allowed=True), "CONFIRM_COMPLETED"
    )
    assert result["code"] == "USER_ACTION_COMPLETION_REVISION_SAFETY_BOUNDARY_VIOLATION"


def test_invalid_revision_number_blocks():
    result = build_product_decision_user_action_completion_revision(
        _persisted(completion_revision="bad"), "CONFIRM_COMPLETED"
    )
    assert result["code"] == "USER_ACTION_COMPLETION_REVISION_NUMBER_INVALID"
