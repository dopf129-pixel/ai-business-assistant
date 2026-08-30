from pathlib import Path

import services.terminal_safe_assistant_task_service as terminal_module
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
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)


REVISION = "a" * 40
OTHER_REVISION = "b" * 40
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


def _verification_manifest(tmp_path, sha=REVISION, **counts):
    junit = tmp_path / "pytest-junit.xml"
    _write_junit(junit, **counts)
    return AssistantCiVerificationManifestService().build_from_junit(
        junit_path=str(junit),
        commit_sha=sha,
        workflow="Verify",
        event="push",
        run_id=777,
        run_number=44,
    )


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
    bridge = TaskPersistenceVerificationManifestProvenanceService(
        capability_provenance_service=provenance,
        verification_manifest_service=(
            AssistantCiVerificationManifestService()
        ),
    )
    return owner, release, provenance, bridge


def test_v433_green_manifest_import_binds_exact_revision_without_ci_success_claim(tmp_path):
    _, release, _, bridge = _services(tmp_path)
    snapshot = release.build_snapshot()
    manifest = _verification_manifest(tmp_path, tests=12)

    imported = bridge.import_manifest(
        snapshot,
        manifest,
        REVISION,
    )

    assert imported["status"] == (
        "TASK_PERSISTENCE_VERIFICATION_MANIFEST_IMPORTED"
    )
    assert imported["revision_id"] == REVISION
    assert imported["test_suite_passed"] is True
    assert imported["verification_manifest_bound"] is True
    assert imported["ci_evidence_bound"] is False
    assert imported["final_ci_run_success_confirmed"] is False
    assert imported["externally_verified"] is False


def test_v434_failed_test_manifest_is_preserved_as_failed_evidence_not_rejected(tmp_path):
    _, release, _, bridge = _services(tmp_path)
    snapshot = release.build_snapshot()
    manifest = _verification_manifest(
        tmp_path,
        tests=10,
        failures=2,
    )

    imported = bridge.import_manifest(
        snapshot,
        manifest,
        REVISION,
    )

    assert imported["error"] is False
    assert imported["test_suite_passed"] is False
    assert imported["passed"] == 8
    assert imported["failed"] == 2
    assert imported["total"] == 10
    assert imported["final_ci_run_success_confirmed"] is False


def test_v435_exact_revision_mismatch_fails_closed(tmp_path):
    _, release, _, bridge = _services(tmp_path)
    snapshot = release.build_snapshot()
    manifest = _verification_manifest(
        tmp_path,
        sha=OTHER_REVISION,
        tests=5,
    )

    result = bridge.import_manifest(
        snapshot,
        manifest,
        REVISION,
    )

    assert result["error"] is True
    assert result["code"] == (
        "TASK_PERSISTENCE_VERIFICATION_MANIFEST_SHA_MISMATCH"
    )
    assert result["verification_manifest_bound"] is False


def test_v436_tampered_manifest_is_rejected_before_provenance_import(tmp_path):
    _, release, _, bridge = _services(tmp_path)
    snapshot = release.build_snapshot()
    manifest = _verification_manifest(tmp_path, tests=5)
    manifest["passed"] = 4

    result = bridge.import_manifest(
        snapshot,
        manifest,
        REVISION,
    )

    assert result["error"] is True
    assert result["code"] == (
        "TASK_PERSISTENCE_VERIFICATION_MANIFEST_INVALID"
    )


def test_v436_forged_imported_mirrored_fields_fail_before_binding(tmp_path):
    _, release, provenance, bridge = _services(tmp_path)
    snapshot = release.build_snapshot()
    verification = _verification_manifest(tmp_path, tests=5)
    imported = bridge.import_manifest(
        snapshot,
        verification,
        REVISION,
    )
    imported["passed"] = 4
    manifest = provenance.build_manifest(
        snapshot,
        revision_id=REVISION,
    )

    rejected = bridge.build_binding(
        snapshot,
        manifest,
        verification,
        imported,
    )

    assert rejected["error"] is True
    assert rejected["code"] == (
        "TASK_PERSISTENCE_VERIFICATION_IMPORT_INVALID"
    )


def test_v437_binding_enriches_exact_canonical_capabilities(tmp_path):
    _, release, provenance, bridge = _services(tmp_path)
    snapshot = release.build_snapshot()
    verification = _verification_manifest(tmp_path, tests=9)
    imported = bridge.import_manifest(
        snapshot,
        verification,
        REVISION,
    )
    manifest = provenance.build_manifest(
        snapshot,
        revision_id=REVISION,
    )

    binding = bridge.build_binding(
        snapshot,
        manifest,
        verification,
        imported,
    )

    assert binding["status"] == (
        "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_BOUND"
    )
    assert binding["verification_manifest_bound"] is True
    assert binding["test_suite_passed"] is True
    assert len(binding["capabilities"]) == 6
    assert all(
        item["verification_manifest_bound"] is True
        for item in binding["capabilities"]
    )
    assert all(
        item["test_suite_manifest_passed"] is True
        for item in binding["capabilities"]
    )
    assert all(
        item["externally_verified"] is False
        for item in binding["capabilities"]
    )


def test_v438_cross_snapshot_capability_manifest_fails_lineage_check(tmp_path, monkeypatch):
    owner, release, provenance, bridge = _services(tmp_path)
    good_snapshot = release.build_snapshot()
    verification = _verification_manifest(tmp_path, tests=7)
    imported = bridge.import_manifest(
        good_snapshot,
        verification,
        REVISION,
    )

    monkeypatch.setattr(terminal_module, "fcntl", None)
    degraded_snapshot = release.build_snapshot()
    degraded_manifest = provenance.build_manifest(
        degraded_snapshot,
        revision_id=REVISION,
    )
    monkeypatch.undo()

    rejected = bridge.build_binding(
        good_snapshot,
        degraded_manifest,
        verification,
        imported,
    )

    assert rejected["error"] is True
    assert rejected["code"] == (
        "TASK_PERSISTENCE_CAPABILITY_MANIFEST_LINEAGE_MISMATCH"
    )
    assert owner.get_persistence_diagnostics()["read_only"] is True


def test_v439_audit_receipt_is_deterministic_and_contains_no_timestamp_or_path(tmp_path):
    _, release, provenance, bridge = _services(tmp_path)
    snapshot = release.build_snapshot()
    verification = _verification_manifest(tmp_path, tests=6)
    imported = bridge.import_manifest(
        snapshot,
        verification,
        REVISION,
    )
    manifest = provenance.build_manifest(
        snapshot,
        revision_id=REVISION,
    )
    binding = bridge.build_binding(
        snapshot,
        manifest,
        verification,
        imported,
    )

    first = bridge.build_audit_receipt(
        snapshot,
        manifest,
        verification,
        imported,
        binding,
    )
    second = bridge.build_audit_receipt(
        snapshot,
        manifest,
        verification,
        imported,
        binding,
    )

    assert first == second
    assert first["receipt_id"].startswith(
        "task-persistence-verification-audit:"
    )
    rendered = repr(first)
    assert "observed_at" not in rendered
    assert "timestamp" not in rendered
    assert str(tmp_path) not in rendered


def test_v440_report_preserves_test_manifest_vs_final_ci_run_distinction(tmp_path):
    _, _, _, bridge = _services(tmp_path)
    verification = _verification_manifest(tmp_path, tests=11)

    report = bridge.build_report(
        verification,
        REVISION,
    )

    assert report["status"] == (
        "TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_REPORT"
    )
    assert report["test_suite_passed"] is True
    assert report["verification_manifest_bound"] is True
    assert report["ci_evidence_bound"] is False
    assert report["final_ci_run_success_confirmed"] is False
    assert report["network_fetch_performed"] is False


def test_v441_bridge_never_enables_external_verification_or_execution(tmp_path):
    _, _, _, bridge = _services(tmp_path)
    verification = _verification_manifest(tmp_path, tests=4)

    report = bridge.build_report(
        verification,
        REVISION,
    )

    assert report["externally_verified"] is False
    assert report["active_probe_performed"] is False
    assert report["network_fetch_performed"] is False
    assert report["automatic_retry_allowed"] is False
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False
    assert report["business_execution_ready"] is False
    assert report["mutation_ready"] is False
    assert report["read_only"] is True
    assert report["executed"] is False


def test_v442_bridge_is_not_auto_wired_into_production_telegram_factory():
    text = FACTORY.read_text(encoding="utf-8")

    assert (
        "TaskPersistenceVerificationManifestProvenanceService"
        not in text
    )
    assert "task_persistence_verification_manifest" not in text
