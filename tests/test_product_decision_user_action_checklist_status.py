from product_decision_user_action_checklist_status import build_product_decision_user_action_checklist_status


def _checklist(**values):
    guidance_id = "product-decision-user-action-guidance:verify-1"
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY",
        "user_action_checklist_id": "product-decision-user-action-checklist:" + guidance_id,
        "user_action_guidance_id": guidance_id,
        "sku": "hook-2",
        "items": [
            {"item_id": "manual-step-1"},
            {"item_id": "manual-step-2"},
        ],
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
    result = {
        "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED",
        "user_action_checklist_id": _checklist()["user_action_checklist_id"],
        "sku": "hook-2",
        "item_id": item_id,
        "completion_revision": revision,
        "user_reported_completed": completed,
        "completion_evidence_source": "USER_REPORT",
        "completion_persisted": True,
        "externally_verified": False,
        "persistent": True,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_no_reports_status():
    result = build_product_decision_user_action_checklist_status(_checklist(), [])
    assert result["aggregate_status"] == "NO_USER_REPORTS"
    assert result["reported_count"] == 0


def test_partial_status():
    result = build_product_decision_user_action_checklist_status(
        _checklist(), [_report("manual-step-1", True)]
    )
    assert result["aggregate_status"] == "USER_REPORTED_PARTIAL"
    assert result["completed_count"] == 1


def test_all_completed_status_is_still_not_external_verification():
    result = build_product_decision_user_action_checklist_status(
        _checklist(), [_report("manual-step-1", True), _report("manual-step-2", True)]
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
        _checklist(), [_report("manual-step-1", True, user_action_checklist_id="other")]
    )
    assert result["aggregate_status"] == "NO_USER_REPORTS"


def test_unsafe_checklist_blocks():
    result = build_product_decision_user_action_checklist_status(
        _checklist(executed=True), []
    )
    assert result["code"] == "USER_ACTION_CHECKLIST_STATUS_SAFETY_BOUNDARY_VIOLATION"


def test_duplicate_item_ids_block():
    result = build_product_decision_user_action_checklist_status(
        _checklist(items=[{"item_id": "x"}, {"item_id": "x"}]), []
    )
    assert result["code"] == "USER_ACTION_CHECKLIST_STATUS_ITEMS_INVALID"
