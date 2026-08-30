import os

import pytest

from services.assistant_entry_service import AssistantEntryService
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
from services.terminal_safe_assistant_task_service import (
    TerminalSafeAssistantTaskService,
)
from telegram_core_factory import create_telegram_core


class _MainFlow:
    def __init__(self):
        self.calls = 0

    def process(self, text, report, context, user_id):
        self.calls += 1
        return {"source": "main-flow"}


class _Runtime:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def handle_text(self, text, user_id=None):
        self.calls += 1
        self.user_id = user_id
        return self.result


class _FakeTaskService:
    def __init__(self, load=None, persistence=None, lock=None):
        self.load = load or {
            "error": False,
            "status": "TASK_PERSISTENCE_LOAD_DIAGNOSTICS",
            "source_state": "ABSENT",
            "issue_count": 0,
            "issues": [],
            "loaded_task_count": 0,
            "read_only": True,
            "executed": False,
        }
        self.persistence = persistence or {
            "error": False,
            "status": "TASK_PERSISTENCE_DIAGNOSTICS",
            "load_source_state": "ABSENT",
            "last_save_state": "NEVER_ATTEMPTED",
            "last_save_issue": None,
            "last_save_rolled_back": False,
            "optimistic_concurrency_guard": True,
            "write_lock_guard": True,
            "directory_fsync_required": True,
            "last_lock_release_issue": None,
            "loaded_task_count": 0,
            "read_only": True,
            "executed": False,
        }
        self.lock = lock or {
            "error": False,
            "status": "TASK_WRITE_LOCK_DIAGNOSTICS",
            "inspection_state": "NO_ACTIVE_LOCK_EVIDENCE",
            "lock_present": None,
            "ownership_state": "UNKNOWN",
            "coordination_file_present": False,
            "kernel_lock_guard": True,
            "orphan_file_blocks_writes": False,
            "stale_proven": False,
            "automatic_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "manual_intervention_required": False,
            "path_exposed": False,
            "read_only": True,
            "executed": False,
        }

    def get_load_diagnostics(self):
        return self.load

    def get_persistence_diagnostics(self):
        return self.persistence

    def get_write_lock_diagnostics(self):
        return self.lock


def test_v358_absent_lock_is_read_only_and_not_stale(tmp_path):
    service = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )

    diagnostics = service.get_write_lock_diagnostics()

    assert diagnostics == {
        "error": False,
        "status": "TASK_WRITE_LOCK_DIAGNOSTICS",
        "inspection_state": "NO_ACTIVE_LOCK_EVIDENCE",
        "lock_present": None,
        "ownership_state": "UNKNOWN",
        "coordination_file_present": False,
        "kernel_lock_guard": True,
        "orphan_file_blocks_writes": False,
        "stale_proven": False,
        "automatic_recovery_allowed": False,
        "manual_lock_removal_allowed": False,
        "manual_intervention_required": False,
        "path_exposed": False,
        "read_only": True,
        "executed": False,
    }


def test_v359_coordination_file_presence_never_infers_active_owner_or_staleness(tmp_path):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    (tmp_path / "tasks.json.lock").write_bytes(b"")

    diagnostics = service.get_write_lock_diagnostics()

    assert diagnostics["inspection_state"] == "NO_ACTIVE_LOCK_EVIDENCE"
    assert diagnostics["lock_present"] is None
    assert diagnostics["ownership_state"] == "UNKNOWN"
    assert diagnostics["coordination_file_present"] is True
    assert diagnostics["kernel_lock_guard"] is True
    assert diagnostics["orphan_file_blocks_writes"] is False
    assert diagnostics["stale_proven"] is False
    assert diagnostics["manual_intervention_required"] is False
    assert diagnostics["automatic_recovery_allowed"] is False
    assert diagnostics["manual_lock_removal_allowed"] is False
    assert str(path) not in repr(diagnostics)


def test_v360_lock_check_error_preserves_unknown_presence(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    service = TerminalSafeAssistantTaskService(file_path=str(path))
    real_stat = os.stat

    def failing_stat(target, *args, **kwargs):
        if str(target).endswith(".lock"):
            raise PermissionError("sensitive stat detail")
        return real_stat(target, *args, **kwargs)

    monkeypatch.setattr(os, "stat", failing_stat)

    diagnostics = service.get_write_lock_diagnostics()

    assert diagnostics["inspection_state"] == "CHECK_ERROR"
    assert diagnostics["lock_present"] is None
    assert diagnostics["ownership_state"] == "UNKNOWN"
    assert diagnostics["manual_intervention_required"] is True
    assert diagnostics["coordination_file_present"] is None
    assert diagnostics["kernel_lock_guard"] is True
    assert "sensitive stat detail" not in repr(diagnostics)


def test_v361_clean_absent_store_projects_ready_without_write_permission():
    report = TaskPersistenceOperationalService(_FakeTaskService()).build_report()

    assert report["operational_state"] == "READY"
    assert report["operator_attention_required"] is False
    assert report["next_action"] == "NONE"
    assert report["blockers"] == []
    assert report["warnings"] == []
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False
    assert report["business_execution_ready"] is False
    assert report["mutation_ready"] is False
    assert report["executed"] is False


def test_v362_proven_kernel_lock_contention_blocks_without_stale_file_recovery():
    fake = _FakeTaskService(
        persistence={
            "error": False,
            "status": "TASK_PERSISTENCE_DIAGNOSTICS",
            "load_source_state": "ABSENT",
            "last_save_state": "FAILED",
            "last_save_issue": "TASK_FILE_WRITE_LOCKED",
            "last_save_rolled_back": True,
            "optimistic_concurrency_guard": True,
            "write_lock_guard": True,
            "directory_fsync_required": True,
            "last_lock_release_issue": None,
            "loaded_task_count": 0,
            "read_only": True,
            "executed": False,
        }
    )

    report = TaskPersistenceOperationalService(fake).build_report()

    assert report["operational_state"] == "BLOCKED"
    assert report["blockers"] == ["TASK_FILE_WRITE_LOCKED"]
    assert report["next_action"] == "WAIT_FOR_ACTIVE_WRITER_AND_RETRY_MANUALLY"
    assert report["write_lock_stale_proven"] is False
    assert report["automatic_lock_recovery_allowed"] is False
    assert report["manual_lock_removal_allowed"] is False


def test_v363_durability_warning_is_warning_not_false_write_failure():
    fake = _FakeTaskService(
        persistence={
            "error": False,
            "status": "TASK_PERSISTENCE_DIAGNOSTICS",
            "load_source_state": "LOADED",
            "last_save_state": "SUCCEEDED_WITH_DURABILITY_WARNING",
            "last_save_issue": "TASK_DIRECTORY_FSYNC_ERROR",
            "last_save_rolled_back": False,
            "optimistic_concurrency_guard": True,
            "write_lock_guard": True,
            "directory_fsync_required": True,
            "last_lock_release_issue": None,
            "loaded_task_count": 1,
            "read_only": True,
            "executed": False,
        },
        load={
            "error": False,
            "status": "TASK_PERSISTENCE_LOAD_DIAGNOSTICS",
            "source_state": "LOADED",
            "issue_count": 0,
            "issues": [],
            "loaded_task_count": 1,
            "read_only": True,
            "executed": False,
        },
    )

    report = TaskPersistenceOperationalService(fake).build_report()

    assert report["operational_state"] == "WARNING"
    assert report["blockers"] == []
    assert report["warnings"] == ["TASK_DIRECTORY_FSYNC_ERROR"]
    assert report["next_action"] == "CHECK_FILESYSTEM_DURABILITY"


def test_v364_contradictory_lock_diagnostics_fail_closed():
    fake = _FakeTaskService(
        lock={
            "error": False,
            "status": "TASK_WRITE_LOCK_DIAGNOSTICS",
            "inspection_state": "SELF_HELD",
            "lock_present": None,
            "ownership_state": "UNKNOWN",
            "coordination_file_present": True,
            "kernel_lock_guard": True,
            "orphan_file_blocks_writes": False,
            "stale_proven": False,
            "automatic_recovery_allowed": False,
            "manual_lock_removal_allowed": False,
            "manual_intervention_required": False,
            "path_exposed": False,
            "read_only": True,
            "executed": False,
        }
    )

    report = TaskPersistenceOperationalService(fake).build_report()

    assert report["error"] is True
    assert report["operational_state"] == "BLOCKED"
    assert report["code"] == "TASK_WRITE_LOCK_DIAGNOSTICS_INVALID"
    assert report["automatic_lock_recovery_allowed"] is False


def test_v365_runtime_handles_only_explicit_persistence_status_tokens():
    runtime = AssistantTaskPersistenceOperationalRuntimeService(
        operational_service=TaskPersistenceOperationalService(
            _FakeTaskService()
        ),
        access_policy=TaskPersistenceOperatorAccessPolicy([7001]),
        presentation_service=TaskPersistenceOperatorPresentationService(),
    )

    assert runtime.handle_text("покажи продажи", user_id=7001) is None

    report = runtime.handle_text(
        "статус хранилища задач",
        user_id=7001,
    )

    assert report["status"] == "TASK_PERSISTENCE_OPERATIONAL_READINESS"
    assert report["read_only"] is True
    assert report["executed"] is False


def test_v366_entry_routes_operator_status_before_business_flow():
    main = _MainFlow()
    runtime = _Runtime(
        {
            "error": False,
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "read_only": True,
            "executed": False,
        }
    )
    entry = AssistantEntryService(
        main_flow_service=main,
        task_persistence_operational_runtime_service=runtime,
    )

    result = entry.handle(
        "статус хранилища задач",
        user_id=7001,
    )

    assert result["status"] == "TASK_PERSISTENCE_OPERATIONAL_READINESS"
    assert runtime.calls == 1
    assert main.calls == 0


def test_v367_telegram_core_composes_read_only_persistence_runtime_with_injected_owner(tmp_path):
    task_service = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )

    composition = create_telegram_core(
        task_service=task_service,
        task_persistence_operator_user_ids=[7001],
    )

    assert composition["task_service"] is task_service
    runtime = composition["task_persistence_operational_runtime_service"]
    report = runtime.handle_text(
        "task persistence status",
        user_id=7001,
    )

    assert report["operational_state"] == "READY"
    assert report["read_only"] is True
    assert report["business_execution_ready"] is False
    assert report["mutation_ready"] is False
    assert report["executed"] is False


def test_v366_unsafe_task_owner_injection_is_rejected():
    with pytest.raises(ValueError, match="UNSAFE_TASK_SERVICE_INJECTION"):
        create_telegram_core(task_service=object())
