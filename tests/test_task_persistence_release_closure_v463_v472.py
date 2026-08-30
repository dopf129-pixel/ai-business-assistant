import json

import pytest

from core.task_states import TaskStatus
from services.assistant_ci_verification_manifest_service import (
    AssistantCiVerificationManifestService,
)
from services.task_persistence_capability_provenance_service import (
    TaskPersistenceCapabilityProvenanceService,
)
from services.task_persistence_operational_service import (
    TaskPersistenceOperationalService,
)
from services.task_persistence_release_closure_service import (
    TaskPersistenceReleaseClosureService,
)
from services.task_persistence_release_observability_service import (
    TaskPersistenceReleaseObservabilityService,
)
from services.task_persistence_verification_manifest_provenance_service import (
    TaskPersistenceVerificationManifestProvenanceService,
)
from services.task_persistence_workflow_run_evidence_service import (
    TaskPersistenceWorkflowRunEvidenceService,
)
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)


REVISION = "a" * 40
RUN_ID = 555001
RUN_NUMBER = 53
USER_ID = 12001


def _action(title="Шаг"):
    return {
        "title": title,
        "type": "test",
        "status": "NEW",
        "priority": "HIGH",
    }


def _persisted_task():
    return {
        "task": "Исходная задача",
        "status": TaskStatus.ACTIVE,
        "actions": [_action()],
        "pending_action": None,
    }


def _write_store(path):
    path.write_text(
        json.dumps(
            {str(USER_ID): _persisted_task()},
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )


def _write_junit(path, tests=10, failures=0):
    path.write_text(
        (
            '<testsuites><testsuite name="pytest" '
            f'tests="{tests}" failures="{failures}" '
            'errors="0" skipped="0"></testsuite></testsuites>'
        ),
        encoding="utf-8",
    )


def _manifest(tmp_path, failures=0):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(junit, tests=10, failures=failures)
    return AssistantCiVerificationManifestService().build_from_junit(
        junit_path=str(junit),
        commit_sha=REVISION,
        workflow="Verify",
        event="push",
        run_id=RUN_ID,
        run_number=RUN_NUMBER,
    )


def _run_metadata(conclusion="success"):
    return {
        "head_sha": REVISION,
        "workflow": "Verify",
        "event": "push",
        "run_id": RUN_ID,
        "run_number": RUN_NUMBER,
        "status": "completed",
        "conclusion": conclusion,
    }


def _services(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    operational = TaskPersistenceOperationalService(owner)
    release = TaskPersistenceReleaseObservabilityService(
        task_service=owner,
        operational_service=operational,
    )
    capability = TaskPersistenceCapabilityProvenanceService(
        release_observability_service=release,
    )
    manifest_service = AssistantCiVerificationManifestService()
    manifest_provenance = (
        TaskPersistenceVerificationManifestProvenanceService(
            capability_provenance_service=capability,
            verification_manifest_service=manifest_service,
        )
    )
    workflow = TaskPersistenceWorkflowRunEvidenceService(
        verification_manifest_service=manifest_service,
        verification_manifest_provenance_service=manifest_provenance,
    )
    closure = TaskPersistenceReleaseClosureService(
        release_observability_service=release,
        workflow_run_evidence_service=workflow,
    )
    return owner, closure


def test_v463_clean_exact_sha_evidence_is_ready_for_manual_release_review(tmp_path):
    _, closure = _services(tmp_path)

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    assert report["status"] == "TASK_PERSISTENCE_RELEASE_CLOSURE_READY"
    assert report["closure_state"] == "READY_FOR_RELEASE_REVIEW"
    assert report["release_review_ready"] is True
    assert report["blockers"] == []
    assert report["warnings"] == []
    assert report["check_count"] == report["satisfied_count"]
    assert report["deployment_allowed"] is False
    assert report["release_approved"] is False
    assert report["deployed"] is False
    assert report["executed"] is False


def test_v464_closure_requires_all_six_persistence_capabilities(tmp_path):
    _, closure = _services(tmp_path)

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    capability_ids = {
        item["id"]
        for item in report["checklist"]
        if item["id"].startswith("CAPABILITY:")
    }
    assert capability_ids == {
        "CAPABILITY:optimistic_concurrency_guard",
        "CAPABILITY:kernel_lock_guard",
        "CAPABILITY:atomic_replace_required",
        "CAPABILITY:file_fsync_required",
        "CAPABILITY:directory_fsync_required",
        "CAPABILITY:coordination_file_ownership_neutral",
    }


def test_v465_durability_warning_blocks_release_review_and_adds_manual_runbook_step(
    tmp_path,
    monkeypatch,
):
    owner, closure = _services(tmp_path)
    monkeypatch.setattr(
        owner,
        "_sync_parent_directory",
        lambda: "TASK_DIRECTORY_FSYNC_ERROR",
    )
    owner.create_task(USER_ID, "Сохранено", [_action()])

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    assert report["closure_state"] == "BLOCKED"
    assert report["release_review_ready"] is False
    assert "TASK_DIRECTORY_FSYNC_ERROR" in report["warnings"]
    assert "NO_RUNTIME_WARNINGS" in report["blockers"]
    actions = [step["action"] for step in report["runbook"]]
    assert "INSPECT_DURABILITY_BOUNDARY" in actions
    assert "RESOLVE_AND_REBUILD_CHECKLIST" in actions
    assert all(step["automatic"] is False for step in report["runbook"])


def test_v466_real_lock_contention_blocks_release_and_never_recommends_lock_delete(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))

    operational = TaskPersistenceOperationalService(second)
    release = TaskPersistenceReleaseObservabilityService(
        task_service=second,
        operational_service=operational,
    )
    capability = TaskPersistenceCapabilityProvenanceService(
        release_observability_service=release,
    )
    manifest_service = AssistantCiVerificationManifestService()
    manifest_provenance = (
        TaskPersistenceVerificationManifestProvenanceService(
            capability_provenance_service=capability,
            verification_manifest_service=manifest_service,
        )
    )
    workflow = TaskPersistenceWorkflowRunEvidenceService(
        verification_manifest_service=manifest_service,
        verification_manifest_provenance_service=manifest_provenance,
    )
    closure = TaskPersistenceReleaseClosureService(
        release_observability_service=release,
        workflow_run_evidence_service=workflow,
    )

    first._acquire_write_lock()
    try:
        with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCKED"):
            second.set_pending_action(USER_ID, {"title": "blocked"})
    finally:
        first._release_write_lock()

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    assert report["closure_state"] == "BLOCKED"
    assert "NO_RUNTIME_BLOCKERS" in report["blockers"]
    actions = [step["action"] for step in report["runbook"]]
    assert "WAIT_FOR_ACTIVE_WRITER" in actions
    assert report["manual_lock_removal_allowed"] is False
    rendered = repr(report["runbook"]).lower()
    assert "coordination file не удалять" in rendered


def test_v467_failed_test_manifest_blocks_release_review(tmp_path):
    _, closure = _services(tmp_path)

    report = closure.build_report(
        _manifest(tmp_path, failures=1),
        REVISION,
        _run_metadata(conclusion="failure"),
    )

    assert report["closure_state"] == "BLOCKED"
    assert "TEST_SUITE_PASSED" in report["blockers"]
    assert "FINAL_WORKFLOW_RUN_SUCCESS_REPORTED" in report["blockers"]
    assert report["release_review_ready"] is False


def test_v468_green_tests_but_failed_final_run_is_not_release_ready(tmp_path):
    _, closure = _services(tmp_path)

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(conclusion="failure"),
    )

    assert report["closure_state"] == "BLOCKED"
    assert "FINAL_WORKFLOW_RUN_SUCCESS_REPORTED" in report["blockers"]
    assert "NO_POST_TEST_FAILURE" in report["blockers"]
    assert report["final_ci_run_success_reported"] is False


def test_v469_runbook_ready_case_ends_in_manual_review_not_deploy(tmp_path):
    _, closure = _services(tmp_path)

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    last = report["runbook"][-1]
    assert last["action"] == "MANUAL_RELEASE_REVIEW"
    assert last["automatic"] is False
    assert "Deployment/approval" in last["instruction"]
    assert report["deployment_allowed"] is False
    assert report["release_approved"] is False


def test_v470_closure_audit_is_deterministic_and_rejects_forged_lineage(tmp_path):
    _, closure = _services(tmp_path)
    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    source = dict(report)
    source.pop("closure_audit_receipt_id")
    first = closure.build_audit_receipt(source)
    second = closure.build_audit_receipt(source)

    assert first == second
    assert first["receipt_id"].startswith(
        "task-persistence-release-closure-audit:"
    )

    forged = dict(source)
    forged["workflow_audit_id"] = (
        "task-persistence-workflow-run-audit:" + ("0" * 64)
    )
    rejected = closure.build_audit_receipt(forged)
    assert rejected["error"] is True
    assert rejected["code"] == (
        "TASK_PERSISTENCE_RELEASE_CLOSURE_REPORT_INVALID"
    )


def test_v471_closure_never_claims_external_verification_or_business_execution(tmp_path):
    _, closure = _services(tmp_path)

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    assert report["externally_verified"] is False
    assert report["automatic_retry_allowed"] is False
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False
    assert report["business_execution_ready"] is False
    assert report["mutation_ready"] is False
    assert report["read_only"] is True
    assert report["deployed"] is False
    assert report["executed"] is False


def test_v472_closure_contains_no_path_pid_or_fabricated_timestamp(tmp_path):
    _, closure = _services(tmp_path)

    report = closure.build_report(
        _manifest(tmp_path),
        REVISION,
        _run_metadata(),
    )

    rendered = repr(report)
    assert str(tmp_path) not in rendered
    assert "observed_at" not in rendered
    assert "timestamp" not in rendered
    assert "pid" not in rendered.lower()
