from product_decision_user_action_checklist_status import (
    build_product_decision_user_action_checklist_status,
)


def _ids():
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
    return application_id, verification_id, guidance_id, checklist_id


def _checklist(**values):
    application_id, verification_id, guidance_id, checklist_id = _ids()
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY",
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "externally_verified": False,
        "persistent": True,
        "items": [
            {
                "item_id": "manual-step-1",
                "position": 1,
                "instruction": "Проверить остаток.",
                "completion_source": "USER",
                "completed": False,
            },
            {
                "item_id": "manual-step-2",
                "position": 2,
                "instruction": "Определить действие вручную.",
                "completion_source": "USER",
                "completed": False,
            },
        ],
        "item_count": 2,
        "completed_count": 0,
        "completion_recording_allowed": False,
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _report(item_id, completed, revision=1, **values):
    application_id, verification_id, guidance_id, checklist_id = _ids()
    instructions = {
        "manual-step-1": "Проверить остаток.",
        "manual-step-2": "Определить действие вручную.",
    }
    root_id = (
        "product-decision-user-action-completion-evidence:%s:%s"
        % (checklist_id, item_id)
    )
    evidence_id = (
        root_id
        if revision == 1
        else "%s:revision:%d" % (root_id, revision)
    )
    previous_id = (
        None
        if revision == 1
        else (
            root_id
            if revision == 2
            else "%s:revision:%d" % (root_id, revision - 1)
        )
    )
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED",
        "completion_evidence_root_id": root_id,
        "user_action_completion_evidence_id": evidence_id,
        "previous_user_action_completion_evidence_id": previous_id,
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "verified_recorded_at": "2026-09-01T12:00:00+00:00",
        "decision_persistence_verified": True,
        "item_id": item_id,
        "instruction": instructions[item_id],
        "completion_revision": revision,
        "completion_decision": (
            "CONFIRM_COMPLETED"
            if completed
            else "NOT_COMPLETED"
        ),
        "user_reported_completed": completed,
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


def test_no_reports_status():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [],
    )
    assert result["aggregate_status"] == "NO_USER_REPORTS"
    assert result["reported_count"] == 0


def test_partial_status():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [_report("manual-step-1", True)],
    )
    assert result["aggregate_status"] == "USER_REPORTED_PARTIAL"
    assert result["completed_count"] == 1


def test_all_completed_status_is_still_not_external_verification():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [
            _report("manual-step-1", True),
            _report("manual-step-2", True),
        ],
    )
    assert result["aggregate_status"] == "USER_REPORTED_COMPLETE"
    assert result["completed_count"] == 2
    assert result["externally_verified"] is False
    assert result["executed"] is False


def test_latest_revision_wins():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [
            _report("manual-step-1", False, revision=1),
            _report("manual-step-1", True, revision=2),
            _report("manual-step-2", True, revision=1),
        ],
    )
    assert result["aggregate_status"] == "USER_REPORTED_COMPLETE"


def test_later_not_completed_revision_can_reverse_reported_status():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [
            _report("manual-step-1", True, revision=1),
            _report("manual-step-1", False, revision=2),
            _report("manual-step-2", True, revision=1),
        ],
    )
    assert result["aggregate_status"] == "USER_REPORTED_PARTIAL"
    assert result["completed_count"] == 1


def test_foreign_checklist_reports_are_ignored():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [
            _report(
                "manual-step-1",
                True,
                user_action_checklist_id="other",
            )
        ],
    )
    assert result["aggregate_status"] == "NO_USER_REPORTS"


def test_unsafe_checklist_blocks():
    result = build_product_decision_user_action_checklist_status(
        _checklist(executed=True),
        [],
    )
    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_STATUS_SAFETY_BOUNDARY_VIOLATION"
    )


def test_duplicate_item_ids_block():
    items = _checklist()["items"]
    items[1]["item_id"] = items[0]["item_id"]
    result = build_product_decision_user_action_checklist_status(
        _checklist(items=items),
        [],
    )
    assert result["code"] == "USER_ACTION_CHECKLIST_STATUS_ITEMS_INVALID"
