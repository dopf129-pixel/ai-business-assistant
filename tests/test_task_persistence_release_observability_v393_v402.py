import json

import pytest

import services.terminal_safe_assistant_task_service as terminal_module
from core.task_states import TaskStatus
from services.assistant_task_persistence_operational_runtime_service import (
    AssistantTaskPersistenceOperationalRuntimeService,
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


USER_ID = 11001
OPERATOR_ID = 7201
OTHER_ID = 7202


def _action(title="Шаг"):
    return {
        "title": title,
        "type": "test",
        "status": "NEW",
        "priority": "HIGH",
    }


def _task():
    return {
        "task": "Исходная задача",
        "status": TaskStatus.ACTIVE,
        "actions": [_action()],
        "pending_action": None,
    }


def _write_store(path):
    path.write_text(
        json.dumps({str(USER_ID): _task()}, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def _release_service(owner):
    operational = TaskPersistenceOperationalService(owner)
    return TaskPersistenceReleaseObservabilityService(
        task_service=owner,
        operational_service=operational,
    )


class _CountingRelease:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def build_release_report(self):
        self.calls += 1
        return dict(self.result)


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


def _release_result():
    return {
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


def test_v393_persistence_diagnostics_expose_release_capabilities_without_paths(tmp_path):
    path = tmp_path / "tasks.json"
    owner = TerminalSafeAssistantTaskService(file_path=str(path))

    diagnostics = owner.get_persistence_diagnostics()

    assert diagnostics["optimistic_concurrency_guard"] is True
    assert diagnostics["write_lock_guard"] is True
    assert diagnostics["atomic_replace_required"] is True
    assert diagnostics["file_fsync_required"] is True
    assert diagnostics["directory_fsync_required"] is True
    assert diagnostics["coordination_file_ownership_neutral"] is True
    assert str(path) not in repr(diagnostics)


def test_v394_clean_runtime_snapshot_is_release_ready(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )

    snapshot = _release_service(owner).build_snapshot()

    assert snapshot["status"] == "TASK_PERSISTENCE_RELEASE_SNAPSHOT_READY"
    assert snapshot["release_ready"] is True
    assert snapshot["blockers"] == []
    assert snapshot["missing_capabilities"] == []
    assert all(snapshot["capabilities"].values())
    assert snapshot["read_only"] is True
    assert snapshot["executed"] is False


def test_v395_missing_kernel_lock_capability_blocks_release_fail_closed(tmp_path, monkeypatch):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    monkeypatch.setattr(terminal_module, "fcntl", None)

    snapshot = _release_service(owner).build_snapshot()

    assert snapshot["release_ready"] is False
    assert "RELEASE_CAPABILITY_MISSING:kernel_lock_guard" in snapshot["blockers"]
    assert "kernel_lock_guard" in snapshot["missing_capabilities"]
    assert "TASK_WRITE_LOCK_INSPECTION_FAILED" in snapshot["blockers"]
    assert snapshot["automatic_retry_allowed"] is False


def test_v396_real_kernel_contention_is_classified_from_save_evidence(tmp_path):
    path = tmp_path / "tasks.json"
    _write_store(path)
    first = TerminalSafeAssistantTaskService(file_path=str(path))
    second = TerminalSafeAssistantTaskService(file_path=str(path))

    first._acquire_write_lock()
    try:
        with pytest.raises(RuntimeError, match="TASK_FILE_WRITE_LOCKED"):
            second.set_pending_action(USER_ID, {"title": "blocked"})
    finally:
        first._release_write_lock()

    service = _release_service(second)
    snapshot = service.build_snapshot()
    incident = service.classify_incident(snapshot)

    assert snapshot["release_ready"] is False
    assert snapshot["blockers"] == ["TASK_FILE_WRITE_LOCKED"]
    assert incident["incident_detected"] is True
    assert incident["incident_categories"] == ["LOCK_CONTENTION"]
    assert incident["human_review_required"] is True
    assert incident["automatic_retry_allowed"] is False
    assert incident["manual_lock_removal_allowed"] is False


def test_v397_audit_receipt_is_deterministic_and_contains_no_fabricated_timestamp(tmp_path):
    path = tmp_path / "private-tasks.json"
    owner = TerminalSafeAssistantTaskService(file_path=str(path))
    service = _release_service(owner)

    snapshot = service.build_snapshot()
    incident = service.classify_incident(snapshot)
    first = service.build_audit_receipt(snapshot, incident)
    second = service.build_audit_receipt(snapshot, incident)

    assert first == second
    assert first["receipt_id"].startswith("task-persistence-release:")
    rendered = repr(first)
    assert "observed_at" not in rendered
    assert "timestamp" not in rendered
    assert str(path) not in rendered
    assert str(USER_ID) not in rendered
    assert first["read_only"] is True
    assert first["executed"] is False


def test_v398_release_presentation_is_human_readable_and_non_mutating():
    presentation = TaskPersistenceOperatorPresentationService()

    result = presentation.present_release(_release_result())

    assert result["message"].startswith("Release-готовность persistence: готово.")
    assert result["operator_message_generated"] is True
    assert result["path_exposed"] is False
    assert result["lock_owner_inferred"] is False
    assert result["lock_age_inferred"] is False
    assert result["mutation_ready"] is False
    assert result["executed"] is False


def test_v399_release_route_is_default_deny_before_release_diagnostics():
    release = _CountingRelease(_release_result())
    runtime = AssistantTaskPersistenceOperationalRuntimeService(
        operational_service=_Operational(),
        access_policy=TaskPersistenceOperatorAccessPolicy([OPERATOR_ID]),
        presentation_service=TaskPersistenceOperatorPresentationService(),
        release_observability_service=release,
    )

    denied = runtime.handle_text(
        "/task-persistence-release",
        user_id=OTHER_ID,
    )

    assert denied["code"] == "TASK_PERSISTENCE_OPERATOR_ACCESS_DENIED"
    assert denied["operator_authorized"] is False
    assert release.calls == 0


def test_v400_telegram_factory_composes_authorized_release_route(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    composition = create_telegram_core(
        task_service=owner,
        task_persistence_operator_user_ids=[OPERATOR_ID],
    )

    release_service = composition[
        "task_persistence_release_observability_service"
    ]
    runtime = composition[
        "task_persistence_operational_runtime_service"
    ]

    assert isinstance(
        release_service,
        TaskPersistenceReleaseObservabilityService,
    )

    result = runtime.handle_text(
        "/task-persistence-release",
        user_id=OPERATOR_ID,
    )

    assert result["status"] == "TASK_PERSISTENCE_RELEASE_READINESS"
    assert result["release_ready"] is True
    assert result["operator_authorized"] is True
    assert result["message"]
    assert result["read_only"] is True
    assert result["executed"] is False


def test_v401_forged_snapshot_and_incident_are_rejected_before_audit(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    service = _release_service(owner)
    snapshot = service.build_snapshot()
    incident = service.classify_incident(snapshot)

    forged_snapshot = dict(snapshot)
    forged_snapshot["capabilities"] = dict(snapshot["capabilities"])
    forged_snapshot["capabilities"]["kernel_lock_guard"] = False

    rejected_snapshot = service.classify_incident(forged_snapshot)
    assert rejected_snapshot["error"] is True
    assert rejected_snapshot["code"] == "TASK_PERSISTENCE_RELEASE_SNAPSHOT_REQUIRED"

    forged_incident = dict(incident)
    forged_incident["incident_categories"] = ["LOCK_CONTENTION"]

    rejected_incident = service.build_audit_receipt(
        snapshot,
        forged_incident,
    )
    assert rejected_incident["error"] is True
    assert rejected_incident["code"] == "TASK_PERSISTENCE_RELEASE_INCIDENT_INVALID"


def test_v402_release_observability_never_enables_retry_lock_delete_or_business_execution(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    report = _release_service(owner).build_release_report()

    assert report["automatic_retry_allowed"] is False
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False
    assert report["business_execution_ready"] is False
    assert report["mutation_ready"] is False
    assert report["read_only"] is True
    assert report["executed"] is False
