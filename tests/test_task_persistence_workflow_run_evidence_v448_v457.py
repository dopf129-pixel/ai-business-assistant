from pathlib import Path

from services.assistant_ci_verification_manifest_service import (
    AssistantCiVerificationManifestService,
)
from services.task_persistence_capability_provenance_service import (
    TaskPersistenceCapabilityProvenanceService,
)
from services.task_persistence_operational_service import (
    TaskPersistenceOperationalService,
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
OTHER_REVISION = "b" * 40
RUN_ID = 123456
RUN_NUMBER = 48
ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT / "app" / "telegram_core_factory.py"


def _write_junit(path, tests=10, failures=0, errors=0, skipped=0):
    path.write_text(
        (
            '<testsuites><testsuite name="pytest" '
            f'tests="{tests}" '
            f'failures="{failures}" '
            f'errors="{errors}" '
            f'skipped="{skipped}"></testsuite></testsuites>'
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


def _run_metadata(
    *,
    head_sha=REVISION,
    run_id=RUN_ID,
    run_number=RUN_NUMBER,
    status="completed",
    conclusion="success",
):
    return {
        "head_sha": head_sha,
        "workflow": "Verify",
        "event": "push",
        "run_id": run_id,
        "run_number": run_number,
        "status": status,
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
    provenance = TaskPersistenceCapabilityProvenanceService(
        release_observability_service=release,
    )
    manifest_service = AssistantCiVerificationManifestService()
    verification_bridge = (
        TaskPersistenceVerificationManifestProvenanceService(
            capability_provenance_service=provenance,
            verification_manifest_service=manifest_service,
        )
    )
    workflow = TaskPersistenceWorkflowRunEvidenceService(
        verification_manifest_service=manifest_service,
        verification_manifest_provenance_service=verification_bridge,
    )
    return workflow


def test_v448_completed_workflow_run_evidence_has_separate_machine_and_run_status(tmp_path):
    service = _services(tmp_path)

    evidence = service.build_run_evidence(_run_metadata())

    assert evidence["status"] == (
        "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_READY"
    )
    assert evidence["run_status"] == "completed"
    assert evidence["run_success"] is True
    assert evidence["head_sha"] == REVISION
    assert evidence["network_fetch_performed"] is False
    assert evidence["externally_verified"] is False


def test_v449_non_completed_or_malformed_run_metadata_fails_closed(tmp_path):
    service = _services(tmp_path)

    running = service.build_run_evidence(
        _run_metadata(status="in_progress")
    )
    invalid_sha = service.build_run_evidence(
        _run_metadata(head_sha="main")
    )

    assert running["error"] is True
    assert running["code"] == (
        "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_INVALID"
    )
    assert invalid_sha["error"] is True


def test_v450_exact_workflow_run_binds_to_matching_verification_manifest(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)
    run = service.build_run_evidence(_run_metadata())

    binding = service.bind_manifest(manifest, run)

    assert binding["status"] == (
        "TASK_PERSISTENCE_WORKFLOW_RUN_MANIFEST_BOUND"
    )
    assert binding["revision_id"] == REVISION
    assert binding["run_id"] == RUN_ID
    assert binding["run_number"] == RUN_NUMBER
    assert binding["test_suite_passed"] is True
    assert binding["final_ci_run_success_reported"] is True
    assert binding["post_test_failure_possible"] is False


def test_v451_green_tests_plus_failed_final_run_preserves_post_test_failure(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)
    run = service.build_run_evidence(
        _run_metadata(conclusion="failure")
    )

    binding = service.bind_manifest(manifest, run)

    assert binding["error"] is False
    assert binding["test_suite_passed"] is True
    assert binding["final_ci_run_success_reported"] is False
    assert binding["post_test_failure_possible"] is True
    assert binding["run_conclusion"] == "failure"


def test_v452_final_success_with_failed_test_manifest_is_rejected_as_contradictory(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path, failures=1)
    run = service.build_run_evidence(_run_metadata())

    result = service.bind_manifest(manifest, run)

    assert result["error"] is True
    assert result["code"] == (
        "TASK_PERSISTENCE_WORKFLOW_RUN_STATE_CONTRADICTORY"
    )


def test_v453_sha_run_id_or_run_number_mismatch_fails_exact_binding(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)

    mismatches = [
        _run_metadata(head_sha=OTHER_REVISION),
        _run_metadata(run_id=RUN_ID + 1),
        _run_metadata(run_number=RUN_NUMBER + 1),
    ]

    for metadata in mismatches:
        run = service.build_run_evidence(metadata)
        result = service.bind_manifest(manifest, run)
        assert result["error"] is True
        assert result["code"] == (
            "TASK_PERSISTENCE_WORKFLOW_RUN_MANIFEST_MISMATCH"
        )


def test_v454_full_report_enriches_exact_capabilities_with_completed_run_evidence(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)

    report = service.build_report(
        manifest,
        REVISION,
        _run_metadata(),
    )

    assert report["status"] == (
        "TASK_PERSISTENCE_WORKFLOW_RUN_PROVENANCE_REPORT"
    )
    assert report["completed_workflow_run_bound"] is True
    assert report["verification_manifest_bound"] is True
    assert report["final_ci_run_success_reported"] is True
    assert len(report["capabilities"]) == 6
    assert all(
        item["completed_workflow_run_bound"] is True
        for item in report["capabilities"]
    )
    assert all(
        item["final_ci_run_success_reported"] is True
        for item in report["capabilities"]
    )
    assert all(
        item["externally_verified"] is False
        for item in report["capabilities"]
    )


def test_v455_report_and_audit_are_deterministic_for_same_evidence(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)
    metadata = _run_metadata()

    first = service.build_report(
        manifest,
        REVISION,
        metadata,
    )
    second = service.build_report(
        manifest,
        REVISION,
        metadata,
    )

    assert first == second
    assert first["provenance_binding_id"].startswith(
        "task-persistence-workflow-provenance-binding:"
    )
    assert first["audit_receipt_id"].startswith(
        "task-persistence-workflow-run-audit:"
    )


def test_v455_forged_capability_manifest_id_breaks_workflow_audit(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)
    metadata = _run_metadata()

    provenance = (
        service.verification_manifest_provenance_service
        .build_report(
            manifest,
            REVISION,
        )
    )
    run = service.build_run_evidence(metadata)
    binding = service.bind_manifest(manifest, run)
    report = service.build_report(
        manifest,
        REVISION,
        metadata,
    )
    report["capability_manifest_id"] = (
        "task-persistence-capability-manifest:" + ("0" * 64)
    )

    rejected = service.build_audit_receipt(
        provenance,
        manifest,
        run,
        binding,
        report,
    )

    assert rejected["error"] is True
    assert rejected["code"] == (
        "TASK_PERSISTENCE_WORKFLOW_REPORT_INVALID"
    )


def test_v456_tampered_run_evidence_identity_is_rejected_before_manifest_binding(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)
    run = service.build_run_evidence(_run_metadata())
    run["conclusion"] = "failure"

    result = service.bind_manifest(manifest, run)

    assert result["error"] is True
    assert result["code"] == (
        "TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_REQUIRED"
    )


def test_v457_completed_run_evidence_remains_non_external_non_mutating_and_not_auto_wired(tmp_path):
    service = _services(tmp_path)
    manifest = _manifest(tmp_path)

    report = service.build_report(
        manifest,
        REVISION,
        _run_metadata(),
    )

    assert report["ci_evidence_bound"] is False
    assert report["network_fetch_performed"] is False
    assert report["externally_verified"] is False
    assert report["automatic_retry_allowed"] is False
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False
    assert report["business_execution_ready"] is False
    assert report["mutation_ready"] is False
    assert report["read_only"] is True
    assert report["executed"] is False

    factory_text = FACTORY.read_text(encoding="utf-8")
    assert "TaskPersistenceWorkflowRunEvidenceService" not in factory_text
