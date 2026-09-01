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
    instruction = {
        "manual-step-1": "Проверить остаток.",
        "manual-step-2": "Определить действие вручную.",
    }[item_id]
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
        "instruction": instruction,
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


def test_v891_non_mapping_checklist_fails_closed():
    result = build_product_decision_user_action_checklist_status(
        ["not", "a", "mapping"],
        [],
    )

    assert result["error"] is True
    assert result["code"] == "USER_ACTION_CHECKLIST_STATUS_INPUT_INVALID"


def test_v892_non_list_report_collection_fails_closed():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        {"report": "not-a-list"},
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_STATUS_REPORTS_INPUT_INVALID"
    )


def test_v893_missing_explicit_checklist_success_marker_is_not_trusted():
    source = _checklist()
    source.pop("error")

    result = build_product_decision_user_action_checklist_status(
        source,
        [],
    )

    assert result["code"] == "USER_ACTION_CHECKLIST_STATUS_SOURCE_INVALID"


def test_v894_numeric_checklist_identity_is_not_coerced():
    result = build_product_decision_user_action_checklist_status(
        _checklist(sku=123),
        [],
    )

    assert result["code"] == "USER_ACTION_CHECKLIST_STATUS_CONTEXT_REQUIRED"


def test_v895_matching_malformed_persisted_report_fails_closed():
    report = _report("manual-step-1", True)
    report.pop("error")

    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [report],
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_STATUS_REPORT_RESULT_INVALID"
    )
    assert result["aggregate_status"] is None


def test_v896_matching_report_must_preserve_application_lineage():
    report = _report(
        "manual-step-1",
        True,
        decision_persistence_application_id="other-app",
    )

    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [report],
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_STATUS_REPORT_LINEAGE_MISMATCH"
    )


def test_v897_string_revision_is_not_coerced_to_integer():
    report = _report("manual-step-1", True)
    report["completion_revision"] = "1"

    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [report],
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_STATUS_REPORT_REVISION_INVALID"
    )


def test_v898_duplicate_item_revision_is_ambiguous():
    report = _report("manual-step-1", True)

    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [report, dict(report)],
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_STATUS_REPORT_REVISION_AMBIGUOUS"
    )


def test_v899_revision_chain_cannot_start_at_revision_two():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [_report("manual-step-1", True, revision=2)],
    )

    assert (
        result["code"]
        == "USER_ACTION_CHECKLIST_STATUS_REPORT_CHAIN_INCOMPLETE"
    )


def test_v900_valid_latest_revision_preserves_verified_lineage():
    result = build_product_decision_user_action_checklist_status(
        _checklist(),
        [
            _report("manual-step-1", False, revision=1),
            _report("manual-step-1", True, revision=2),
            _report("manual-step-2", True, revision=1),
        ],
    )

    assert result["error"] is False
    assert (
        result["status"]
        == "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_READY"
    )
    assert result["aggregate_status"] == "USER_REPORTED_COMPLETE"
    assert result["reported_count"] == 2
    assert result["completed_count"] == 2
    assert result["decision_persistence_application_id"] == "app-1"
    assert result["decision_persistence_verified"] is True
    assert (
        result["verified_recorded_at"]
        == "2026-09-01T12:00:00+00:00"
    )
    assert result["completion_evidence_source"] == "USER_REPORT"
    assert result["externally_verified"] is False
    assert result["persistent"] is False
    assert result["checklist_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
