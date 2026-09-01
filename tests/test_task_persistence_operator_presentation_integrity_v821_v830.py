from services.task_persistence_operator_presentation_service import (
    TaskPersistenceOperatorPresentationService,
)


def _operational(**values):
    result = {
        "error": False,
        "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
        "operational_state": "READY",
        "operator_attention_required": False,
        "next_action": "NONE",
        "blocker_count": 0,
        "blockers": [],
        "warning_count": 0,
        "warnings": [],
        "load_source_state": "ABSENT",
        "loaded_task_count": 0,
        "write_lock_present": None,
        "write_lock_ownership_state": "UNKNOWN",
        "write_lock_stale_proven": False,
        "automatic_lock_recovery_allowed": False,
        "manual_lock_removal_allowed": False,
        "business_execution_ready": False,
        "mutation_ready": False,
        "read_only": True,
        "executed": False,
    }
    result.update(values)
    return result


def _release(**values):
    result = {
        "error": False,
        "status": "TASK_PERSISTENCE_RELEASE_READINESS",
        "release_ready": True,
        "operational_state": "READY",
        "blockers": [],
        "warnings": [],
        "capabilities": {
            "optimistic_concurrency_guard": True,
            "kernel_lock_guard": True,
            "atomic_replace_required": True,
            "file_fsync_required": True,
            "directory_fsync_required": True,
            "coordination_file_ownership_neutral": True,
        },
        "incident_detected": False,
        "incident_categories": [],
        "human_review_required": False,
        "audit_receipt_id": "task-persistence-release:test",
        "automatic_retry_allowed": False,
        "automatic_lock_recovery_allowed": False,
        "manual_lock_removal_allowed": False,
        "business_execution_ready": False,
        "mutation_ready": False,
        "read_only": True,
        "executed": False,
    }
    result.update(values)
    return result


def _provenance(**values):
    result = {
        "error": False,
        "status": "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_REPORT",
        "manifest_id": "task-persistence-capability-manifest:test",
        "audit_receipt_id": "task-persistence-capability-audit:test",
        "revision_id": None,
        "revision_declared": False,
        "release_ready": True,
        "capability_count": 2,
        "capabilities": [
            {"capability": "atomic_replace_required"},
            {"capability": "kernel_lock_guard"},
        ],
        "implementation_contract_count": 1,
        "runtime_observation_count": 1,
        "ci_evidence_state": "UNBOUND",
        "ci_evidence_bound": False,
        "ci_run_number": None,
        "ci_passed": None,
        "active_probe_performed": False,
        "externally_verified": False,
        "automatic_retry_allowed": False,
        "automatic_lock_recovery_allowed": False,
        "manual_lock_removal_allowed": False,
        "business_execution_ready": False,
        "mutation_ready": False,
        "read_only": True,
        "executed": False,
    }
    result.update(values)
    return result


def test_v821_operational_missing_explicit_error_is_not_presented_as_ready():
    report = _operational()
    report.pop("error")
    result = TaskPersistenceOperatorPresentationService().present(report)
    assert result["error"] is True
    assert result["code"] == "TASK_PERSISTENCE_OPERATOR_PRESENTATION_UNAVAILABLE"


def test_v822_operational_string_blockers_are_not_split_into_fake_codes():
    result = TaskPersistenceOperatorPresentationService().present(
        _operational(
            operational_state="BLOCKED",
            operator_attention_required=True,
            blocker_count=1,
            blockers="TASK_FILE_WRITE_LOCKED",
        )
    )
    assert result["code"] == "TASK_PERSISTENCE_OPERATOR_PRESENTATION_UNAVAILABLE"


def test_v823_ready_state_with_blocker_fails_closed():
    result = TaskPersistenceOperatorPresentationService().present(
        _operational(
            blocker_count=1,
            blockers=["TASK_FILE_WRITE_LOCKED"],
        )
    )
    assert result["error"] is True
    assert result["operational_state"] == "BLOCKED"


def test_v824_operational_mutation_readiness_claim_fails_closed():
    result = TaskPersistenceOperatorPresentationService().present(
        _operational(mutation_ready=True)
    )
    assert result["code"] == "TASK_PERSISTENCE_OPERATOR_PRESENTATION_UNAVAILABLE"
    assert result["mutation_ready"] is False


def test_v825_release_explicit_error_is_not_repackaged_as_release_ready():
    result = TaskPersistenceOperatorPresentationService().present_release(
        _release(error=True)
    )
    assert result["error"] is True
    assert result["release_ready"] is False


def test_v826_release_string_warning_is_not_iterated_as_evidence():
    result = TaskPersistenceOperatorPresentationService().present_release(
        _release(warnings="TASK_DIRECTORY_FSYNC_ERROR")
    )
    assert result["code"] == "TASK_PERSISTENCE_RELEASE_PRESENTATION_UNAVAILABLE"


def test_v827_release_ready_contradiction_fails_closed():
    result = TaskPersistenceOperatorPresentationService().present_release(
        _release(
            release_ready=True,
            operational_state="BLOCKED",
            blockers=["TASK_FILE_WRITE_LOCKED"],
            incident_detected=True,
            incident_categories=["LOCK_CONTENTION"],
            human_review_required=True,
        )
    )
    assert result["error"] is True
    assert result["release_ready"] is False


def test_v828_provenance_missing_explicit_error_fails_closed():
    report = _provenance()
    report.pop("error")
    result = TaskPersistenceOperatorPresentationService().present_provenance(
        report
    )
    assert result["code"] == (
        "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_PRESENTATION_UNAVAILABLE"
    )


def test_v829_provenance_external_verification_overclaim_fails_closed():
    result = TaskPersistenceOperatorPresentationService().present_provenance(
        _provenance(externally_verified=True)
    )
    assert result["error"] is True
    assert result["externally_verified"] is False


def test_v830_valid_reports_remain_read_only_and_human_readable():
    presentation = TaskPersistenceOperatorPresentationService()
    operational = presentation.present(_operational())
    release = presentation.present_release(_release())
    provenance = presentation.present_provenance(_provenance())

    assert operational["error"] is False
    assert operational["message"].startswith("Хранилище задач: готово.")
    assert release["error"] is False
    assert release["message"].startswith("Release-готовность persistence: готово.")
    assert provenance["error"] is False
    assert "External verification отсутствует" in provenance["message"]
    for result in (operational, release, provenance):
        assert result["path_exposed"] is False
        assert result["user_id_exposed"] is False
        assert result["lock_owner_inferred"] is False
        assert result["lock_age_inferred"] is False
        assert result["business_execution_ready"] is False
        assert result["mutation_ready"] is False
        assert result["executed"] is False
