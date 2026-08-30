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


OPERATOR_ID = 7101
OTHER_ID = 7102


class _CountingOperational:
    def __init__(self, report=None):
        self.calls = 0
        self.report = report or {
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

    def build_report(self):
        self.calls += 1
        return dict(self.report)


class _EntryRuntime:
    def __init__(self):
        self.user_ids = []

    def handle_text(self, text, user_id=None):
        self.user_ids.append(user_id)
        return {
            "error": False,
            "status": "TASK_PERSISTENCE_OPERATIONAL_READINESS",
            "operator_authorized": True,
            "read_only": True,
            "executed": False,
        }


class _MainFlow:
    def process(self, text, report, context, user_id):
        return {"source": "main-flow"}


def _runtime(allowed_ids=None, report=None):
    operational = _CountingOperational(report=report)
    return (
        AssistantTaskPersistenceOperationalRuntimeService(
            operational_service=operational,
            access_policy=TaskPersistenceOperatorAccessPolicy(
                allowed_ids
            ),
            presentation_service=TaskPersistenceOperatorPresentationService(),
        ),
        operational,
    )


def test_v368_access_policy_is_default_deny_and_hides_ids():
    policy = TaskPersistenceOperatorAccessPolicy()

    assert policy.is_allowed(OPERATOR_ID) is False
    diagnostics = policy.get_diagnostics()
    assert diagnostics["configured"] is False
    assert diagnostics["allowed_count"] == 0
    assert diagnostics["default_deny"] is True
    assert diagnostics["user_ids_exposed"] is False
    assert str(OPERATOR_ID) not in repr(diagnostics)


def test_v369_access_policy_accepts_only_explicit_positive_integer_ids():
    policy = TaskPersistenceOperatorAccessPolicy([OPERATOR_ID])

    assert policy.is_allowed(OPERATOR_ID) is True
    assert policy.is_allowed(OTHER_ID) is False
    assert policy.is_allowed(str(OPERATOR_ID)) is False
    assert policy.is_allowed(True) is False

    for invalid in (0, -1, True, "7101", None):
        with pytest.raises(
            ValueError,
            match="INVALID_TASK_PERSISTENCE_OPERATOR_USER_ID",
        ):
            TaskPersistenceOperatorAccessPolicy([invalid])

    for malformed in (OPERATOR_ID, str(OPERATOR_ID), object()):
        with pytest.raises(
            ValueError,
            match="INVALID_TASK_PERSISTENCE_OPERATOR_ALLOWLIST",
        ):
            TaskPersistenceOperatorAccessPolicy(malformed)


def test_v370_unauthorized_runtime_never_reads_persistence_diagnostics():
    runtime, operational = _runtime([OPERATOR_ID])

    result = runtime.handle_text(
        "task persistence status",
        user_id=OTHER_ID,
    )

    assert operational.calls == 0
    assert result["code"] == "TASK_PERSISTENCE_OPERATOR_ACCESS_DENIED"
    assert result["operator_authorized"] is False
    assert result["read_only"] is True
    assert result["executed"] is False


def test_v371_telegram_factory_is_default_deny_even_with_hardened_owner(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "tasks.json")
    )
    composition = create_telegram_core(task_service=owner)
    runtime = composition["task_persistence_operational_runtime_service"]

    result = runtime.handle_text(
        "статус хранилища задач",
        user_id=OPERATOR_ID,
    )

    assert result["code"] == "TASK_PERSISTENCE_OPERATOR_ACCESS_DENIED"
    assert result["operator_authorized"] is False


def test_v372_authorized_ready_report_gets_human_readable_message():
    runtime, operational = _runtime([OPERATOR_ID])

    result = runtime.handle_text(
        "статус хранилища задач",
        user_id=OPERATOR_ID,
    )

    assert operational.calls == 1
    assert result["operator_authorized"] is True
    assert result["operator_message_generated"] is True
    assert result["message"].startswith("Хранилище задач: готово.")
    assert result["path_exposed"] is False
    assert result["user_id_exposed"] is False


def test_v373_kernel_lock_contention_message_never_authorizes_coordination_file_delete():
    report = _CountingOperational().report
    report.update({
        "operational_state": "BLOCKED",
        "operator_attention_required": True,
        "next_action": "WAIT_FOR_ACTIVE_WRITER_AND_RETRY_MANUALLY",
        "blocker_count": 1,
        "blockers": ["TASK_FILE_WRITE_LOCKED"],
        "write_lock_present": None,
        "write_lock_ownership_state": "UNKNOWN",
    })
    runtime, _ = _runtime([OPERATOR_ID], report=report)

    result = runtime.handle_text(
        "/task-persistence",
        user_id=OPERATOR_ID,
    )

    assert "Не удаляйте coordination file" in result["message"]
    assert result["automatic_lock_recovery_allowed"] is False
    assert result["manual_lock_removal_allowed"] is False
    assert result["write_lock_stale_proven"] is False
    assert result["lock_owner_inferred"] is False
    assert result["lock_age_inferred"] is False


def test_v374_durability_warning_message_preserves_committed_write_semantics():
    report = _CountingOperational().report
    report.update({
        "operational_state": "WARNING",
        "operator_attention_required": True,
        "next_action": "CHECK_FILESYSTEM_DURABILITY",
        "warning_count": 1,
        "warnings": ["TASK_DIRECTORY_FSYNC_ERROR"],
    })
    runtime, _ = _runtime([OPERATOR_ID], report=report)

    result = runtime.handle_text(
        "task persistence diagnostics",
        user_id=OPERATOR_ID,
    )

    assert "Запись завершилась" in result["message"]
    assert "crash-durability" in result["message"]
    assert result["mutation_ready"] is False
    assert result["executed"] is False


def test_v375_explicit_slash_command_is_authorized_and_unrelated_text_falls_through():
    runtime, operational = _runtime([OPERATOR_ID])

    assert runtime.handle_text(
        "обычный вопрос",
        user_id=OPERATOR_ID,
    ) is None
    assert operational.calls == 0

    result = runtime.handle_text(
        "/task-persistence",
        user_id=OPERATOR_ID,
    )

    assert result["operator_authorized"] is True
    assert operational.calls == 1


def test_v376_entry_passes_user_id_only_to_persistence_operator_runtime():
    runtime = _EntryRuntime()
    entry = AssistantEntryService(
        main_flow_service=_MainFlow(),
        task_persistence_operational_runtime_service=runtime,
    )

    result = entry.handle(
        "task persistence status",
        user_id=OPERATOR_ID,
    )

    assert result["operator_authorized"] is True
    assert runtime.user_ids == [OPERATOR_ID]


def test_v377_authorized_factory_route_returns_message_without_user_id_or_path(tmp_path):
    owner = TerminalSafeAssistantTaskService(
        file_path=str(tmp_path / "private-tasks.json")
    )
    composition = create_telegram_core(
        task_service=owner,
        task_persistence_operator_user_ids=[OPERATOR_ID],
    )

    runtime = composition["task_persistence_operational_runtime_service"]
    result = runtime.handle_text(
        "/task-persistence",
        user_id=OPERATOR_ID,
    )

    rendered = repr(result)
    assert result["operator_authorized"] is True
    assert result["message"]
    assert str(OPERATOR_ID) not in rendered
    assert str(tmp_path) not in rendered
    assert result["business_execution_ready"] is False
    assert result["mutation_ready"] is False
    assert result["automatic_lock_recovery_allowed"] is False
    assert result["manual_lock_removal_allowed"] is False
    assert result["executed"] is False
