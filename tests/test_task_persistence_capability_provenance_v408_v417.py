import pytest

import services.terminal_safe_assistant_task_service as terminal_module
from services.assistant_task_persistence_operational_runtime_service import (
    AssistantTaskPersistenceOperationalRuntimeService,
)
from services.task_persistence_capability_provenance_service import (
    TaskPersistenceCapabilityProvenanceService,
)
from services.task_persistence_operational_service import (
    TaskPersistenceOperationalService,
)
from services.task_persistence_operator_access_policy import (
    TaskPersistenceOperatorAccessPolicy,
)
from services.task_persistence_operator_presentation_service import (
    TaskPersistenceOperatorPresentationService,
)
from services.task_persistence_release_observability_service import (
    TaskPersistenceReleaseObservabilityService,
)
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)
from telegram_core_factory import create_telegram_core


REVISION = "a" * 40
OTHER_REVISION = "b" * 40
OPERATOR_ID = 7301
OTHER_ID = 7302


def _release(owner):
    operational = TaskPersistenceOperationalService(owner)
    return TaskPersistenceReleaseObservabilityService(
        task_service=owner,
        operational_service=operational,
    )


def _provenance(owner, revision_id=None, ci_evidence=None):
    return TaskPersistenceCapabilityProvenanceService(
        release_observability_service=_release(owner),
        revision_id=revision_id,
        ci_evidence=ci_evidence,
    )


def _ci(target_sha=REVISION, passed=1244, failed=0):
    return {
        "target_sha": target_sha,
        "workflow": "Verify",
        "event": "push",
        "run_number": 99,
        "passed": passed,
        "failed": failed,
        "conclusion": "success",
        "exact_sha_bound": True,
    }


class _CountingProvenance:
    def __init__(self):
        self.calls = 0

    def build_report(self):
        self.calls += 1
        return {
            "error": False,
            "status": "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_REPORT",
            "manifest_id": "task-persistence-capability-manifest:test",
            "audit_receipt_id": "task-persistence-capability-audit:test",
            "revision_id": None,
            "revision_declared": False,
            "release_ready": True,
            "capability_count": 6,
            "capabilities": [],
            "implementation_contract_count": 5,
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


class _Operational:
    def build_report(self):
        return {
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


def test_v408_capability_catalog_is_exact_and_revision_config_fails_closed(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    service = _provenance(owner)

    names = [
        row["capability"]
        for row in service.CAPABILITY_CATALOG
    ]

    assert names == [
        "optimistic_concurrency_guard",
        "kernel_lock_guard",
        "atomic_replace_required",
        "file_fsync_required",
        "directory_fsync_required",
        "coordination_file_ownership_neutral",
    ]

    with pytest.raises(
        ValueError,
        match="INVALID_TASK_PERSISTENCE_REVISION_ID",
    ):
        _provenance(owner, revision_id="not-a-sha")


def test_v409_manifest_distinguishes_implementation_contract_from_runtime_observation(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    service = _provenance(owner)
    snapshot = _release(owner).build_snapshot()

    manifest = service.build_manifest(snapshot)

    assert manifest["capability_count"] == 6
    assert manifest["implementation_contract_count"] == 5
    assert manifest["runtime_observation_count"] == 1
    kernel = next(
        item for item in manifest["capabilities"]
        if item["capability"] == "kernel_lock_guard"
    )
    atomic = next(
        item for item in manifest["capabilities"]
        if item["capability"] == "atomic_replace_required"
    )
    assert kernel["evidence_mode"] == "RUNTIME_DIAGNOSTIC"
    assert kernel["runtime_observed"] is True
    assert atomic["evidence_mode"] == "IMPLEMENTATION_CONTRACT"
    assert atomic["runtime_observed"] is False
    assert all(
        item["externally_verified"] is False
        for item in manifest["capabilities"]
    )


def test_v410_default_report_is_unbound_and_performs_no_active_probe(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )

    report = _provenance(owner).build_report()

    assert report["revision_id"] is None
    assert report["revision_declared"] is False
    assert report["ci_evidence_state"] == "UNBOUND"
    assert report["ci_evidence_bound"] is False
    assert report["active_probe_performed"] is False
    assert report["externally_verified"] is False


def test_v411_ci_metadata_is_structurally_validated_without_external_verification(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    service = _provenance(owner)

    evidence = service.build_ci_verification_evidence(_ci())

    assert evidence["status"] == (
        "TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_READY"
    )
    assert evidence["target_sha"] == REVISION
    assert evidence["ci_success_claim_consistent"] is True
    assert evidence["evidence_source"] == "CALLER_SUPPLIED_CI_METADATA"
    assert evidence["externally_verified"] is False

    rejected = service.build_ci_verification_evidence(
        _ci(failed=1)
    )
    assert rejected["error"] is True
    assert rejected["code"] == (
        "TASK_PERSISTENCE_CI_VERIFICATION_EVIDENCE_INVALID"
    )


def test_v412_ci_binding_requires_declared_exact_matching_sha(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    release = _release(owner)
    snapshot = release.build_snapshot()

    unbound_service = _provenance(owner)
    unbound_manifest = unbound_service.build_manifest(snapshot)
    evidence = unbound_service.build_ci_verification_evidence(_ci())

    unbound = unbound_service.bind_ci_evidence(
        snapshot,
        unbound_manifest,
        evidence,
    )
    assert unbound["error"] is True
    assert unbound["code"] == (
        "TASK_PERSISTENCE_CAPABILITY_REVISION_UNBOUND"
    )

    bound_service = _provenance(owner, revision_id=REVISION)
    manifest = bound_service.build_manifest(snapshot)
    mismatch_evidence = bound_service.build_ci_verification_evidence(
        _ci(target_sha=OTHER_REVISION)
    )
    mismatch = bound_service.bind_ci_evidence(
        snapshot,
        manifest,
        mismatch_evidence,
    )
    assert mismatch["error"] is True
    assert mismatch["code"] == (
        "TASK_PERSISTENCE_CAPABILITY_CI_SHA_MISMATCH"
    )

    binding = bound_service.bind_ci_evidence(
        snapshot,
        manifest,
        evidence,
    )
    assert binding["ci_sha_match"] is True
    assert binding["ci_evidence_bound"] is True
    assert binding["externally_verified"] is False


def test_v413_cross_snapshot_manifest_forgery_is_rejected_before_ci_binding(tmp_path, monkeypatch):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    service = _provenance(owner, revision_id=REVISION)
    good_snapshot = _release(owner).build_snapshot()

    monkeypatch.setattr(terminal_module, "fcntl", None)
    degraded_snapshot = _release(owner).build_snapshot()
    forged_manifest = service.build_manifest(
        degraded_snapshot,
        revision_id=REVISION,
    )
    monkeypatch.undo()

    evidence = service.build_ci_verification_evidence(_ci())
    rejected = service.bind_ci_evidence(
        good_snapshot,
        forged_manifest,
        evidence,
    )

    assert rejected["error"] is True
    assert rejected["code"] == (
        "TASK_PERSISTENCE_CAPABILITY_MANIFEST_LINEAGE_MISMATCH"
    )


def test_v414_audit_receipt_is_deterministic_and_rebinds_snapshot_lineage(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "private-tasks.json")
    )
    service = _provenance(owner, revision_id=REVISION)
    snapshot = _release(owner).build_snapshot()
    manifest = service.build_manifest(snapshot)
    evidence = service.build_ci_verification_evidence(_ci())
    binding = service.bind_ci_evidence(
        snapshot,
        manifest,
        evidence,
    )

    first = service.build_audit_receipt(
        snapshot,
        manifest,
        binding,
    )
    second = service.build_audit_receipt(
        snapshot,
        manifest,
        binding,
    )

    assert first == second
    assert first["ci_evidence_bound"] is True
    assert first["externally_verified"] is False
    rendered = repr(first)
    assert "observed_at" not in rendered
    assert "timestamp" not in rendered
    assert str(tmp_path) not in rendered


def test_v415_operator_presentation_states_ci_metadata_is_not_external_verification(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    report = _provenance(
        owner,
        revision_id=REVISION,
        ci_evidence=_ci(),
    ).build_report()

    presented = (
        TaskPersistenceOperatorPresentationService()
        .present_provenance(report)
    )

    assert "caller-supplied exact-SHA CI metadata" in presented["message"]
    assert "не external verification" in presented["message"]
    assert presented["externally_verified"] is False
    assert presented["path_exposed"] is False
    assert presented["user_id_exposed"] is False


def test_v416_provenance_route_is_default_deny_before_service_call():
    provenance = _CountingProvenance()
    runtime = AssistantTaskPersistenceOperationalRuntimeService(
        operational_service=_Operational(),
        access_policy=TaskPersistenceOperatorAccessPolicy([OPERATOR_ID]),
        presentation_service=TaskPersistenceOperatorPresentationService(),
        capability_provenance_service=provenance,
    )

    result = runtime.handle_text(
        "/task-persistence-provenance",
        user_id=OTHER_ID,
    )

    assert result["code"] == "TASK_PERSISTENCE_OPERATOR_ACCESS_DENIED"
    assert provenance.calls == 0


def test_v417_factory_defaults_to_unbound_and_can_explicitly_bind_revision_ci_metadata(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )

    default_composition = create_telegram_core(
        task_service=owner,
        task_persistence_operator_user_ids=[OPERATOR_ID],
    )
    default_report = default_composition[
        "task_persistence_capability_provenance_service"
    ].build_report()

    assert default_report["ci_evidence_state"] == "UNBOUND"
    assert default_report["revision_id"] is None

    bound_composition = create_telegram_core(
        task_service=owner,
        task_persistence_operator_user_ids=[OPERATOR_ID],
        task_persistence_revision_id=REVISION,
        task_persistence_ci_evidence=_ci(),
    )
    runtime = bound_composition[
        "task_persistence_operational_runtime_service"
    ]
    result = runtime.handle_text(
        "/task-persistence-provenance",
        user_id=OPERATOR_ID,
    )

    assert result["status"] == (
        "TASK_PERSISTENCE_CAPABILITY_PROVENANCE_REPORT"
    )
    assert result["revision_id"] == REVISION
    assert result["ci_evidence_state"] == "BOUND"
    assert result["ci_evidence_bound"] is True
    assert result["ci_passed"] == 1244
    assert result["externally_verified"] is False
    assert result["active_probe_performed"] is False
    assert result["automatic_retry_allowed"] is False
    assert result["manual_lock_removal_allowed"] is False
    assert result["business_execution_ready"] is False
    assert result["mutation_ready"] is False
    assert result["executed"] is False
