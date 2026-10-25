from dataclasses import dataclass
import subprocess

import pytest

from bot_update import main as update_cli_main
from services.bot_instance_lifecycle_service import (
    BotInstanceLease,
    BotLifecycleError,
    BotStartupMaintenanceGuard,
    project_root_fingerprint,
)
from services.bot_update_runtime_service import (
    BotUpdateRuntimeService,
    _CheckoutUpdateLock,
    _UpdateLockBusy,
)


BASE = "1" * 40
TARGET = "2" * 40


@dataclass
class _CommandResult:
    returncode: int = 0
    stdout: str = ""


class _Lock:
    def __init__(self, *, busy=False):
        self.busy = busy
        self.acquired = False
        self.released = False

    def acquire(self):
        if self.busy:
            from services.bot_update_runtime_service import _UpdateLockBusy

            raise _UpdateLockBusy()
        self.acquired = True

    def release(self):
        self.released = True


class _Preflight:
    def __init__(self, root, *, process_state="STOPPED", target=TARGET,
                 current=BASE, already_current=False, blocked=False,
                 incoming_paths=("app.py",)):
        self.root = root
        self.process_state = process_state
        self.target = target
        self.current = current
        self.already_current = already_current
        self.blocked = blocked
        self.incoming_paths = list(incoming_paths)
        self.inspect_calls = 0
        self.identity_calls = 0

    def inspect_repository_identity(self):
        self.identity_calls += 1
        return {"error": False, "blockers": []}

    def inspect(self):
        self.inspect_calls += 1
        state = self.process_state if self.inspect_calls == 1 else "STOPPED"
        return {
            "error": self.blocked,
            "blockers": [{"code": "SYNTHETIC_BLOCKER"}] if self.blocked else [],
            "current_revision": self.current,
            "target_revision": self.target,
            "already_current": self.already_current,
            "process_state": state,
            "process_checkout_matches": state == "RUNNING",
            "incoming_paths": self.incoming_paths,
        }


class _Backup:
    def __init__(self, *, backup_error=False, verify_error=False):
        self.backup_error = backup_error
        self.verify_error = verify_error
        self.backup_calls = 0
        self.verify_calls = []
        self.guards = []

    def backup(self):
        self.backup_calls += 1
        if self.backup_error:
            return {"error": True, "code": "SYNTHETIC_BACKUP_ERROR"}
        return {"error": False, "backup_path": "C:/synthetic/verified-backup.zip"}

    def backup_under_guard(self, guard):
        assert guard.is_acquired is True
        self.guards.append(guard)
        return self.backup()

    def verify_archive(self, path):
        self.verify_calls.append(path)
        return {"error": self.verify_error, "status": "VERIFIED"}


class _Harness:
    def __init__(self, tmp_path, *, process_state="STOPPED", already_current=False,
                 blocked=False, backup_error=False, verify_error=False,
                 fetch_ok=True, merge_ok=True, command_fail=None,
                 target=TARGET, incoming_paths=("app.py",), lock_busy=False,
                 ready=True, ready_state="RUNNING", ready_revision=TARGET,
                 ready_fingerprint=None):
        self.root = tmp_path
        self.state = process_state
        self.revision = BASE
        self.fingerprint = project_root_fingerprint(tmp_path)
        self.preflight = _Preflight(
            tmp_path,
            process_state=process_state,
            target=target,
            already_current=already_current,
            blocked=blocked,
            incoming_paths=incoming_paths,
        )
        self.backup = _Backup(backup_error=backup_error, verify_error=verify_error)
        self.git_calls = []
        self.command_calls = []
        self.stop_calls = []
        self.lock = _Lock(busy=lock_busy)
        self.fetch_ok = fetch_ok
        self.merge_ok = merge_ok
        self.command_fail = command_fail
        self.ready = ready
        self.ready_state = ready_state
        self.ready_revision = ready_revision
        self.ready_fingerprint = ready_fingerprint
        self.service = BotUpdateRuntimeService(
            tmp_path,
            lifecycle_token="synthetic-token",
            preflight=self.preflight,
            backup_service=self.backup,
            process_inspector=self.inspect_process,
            stop_requester=self.stop,
            git_runner=self.git,
            command_runner=self.command,
            lock_factory=lambda _root: self.lock,
            startup_guard_factory=lambda token: BotStartupMaintenanceGuard(
                token, state_root=self.root / ".synthetic-lifecycle"
            ),
            sleep=lambda _seconds: None,
            monotonic=self.clock,
            platform="nt",
            python_executable="synthetic-python",
            powershell_executable="synthetic-powershell",
            readiness_timeout_seconds=1,
        )
        self.clock_value = 0.0

    def clock(self):
        self.clock_value += 0.1
        return self.clock_value

    def git(self, _root, arguments):
        arguments = tuple(arguments)
        self.git_calls.append(arguments)
        if arguments[0] == "fetch":
            return _CommandResult(0 if self.fetch_ok else 1)
        if arguments[0] == "merge":
            if self.merge_ok:
                self.revision = arguments[-1]
            return _CommandResult(0 if self.merge_ok else 1)
        if arguments[:3] == ("rev-parse", "--verify", "HEAD"):
            return _CommandResult(0, self.revision)
        return _CommandResult(0)

    def command(self, arguments, *, cwd, timeout):
        self.command_calls.append((tuple(arguments), cwd, timeout))
        if self.command_fail and self.command_fail in arguments:
            return _CommandResult(1)
        if any(str(argument).casefold().endswith("start_bot.ps1") for argument in arguments):
            if self.ready:
                self.state = self.ready_state
                self.revision = self.ready_revision
                if self.ready_fingerprint is not None:
                    self.fingerprint = self.ready_fingerprint
        return _CommandResult(0)

    def inspect_process(self, _token):
        return {
            "state": self.state,
            "revision": self.revision,
            "project_root_fingerprint": self.fingerprint,
        }

    def stop(self, token, *, expected_project_root_fingerprint):
        self.stop_calls.append((token, expected_project_root_fingerprint))
        self.state = "STOPPED"
        return {"stopped": True, "state": "STOPPED"}


def test_update_no_start_pins_sha_verifies_backup_and_runs_local_checks(tmp_path):
    harness = _Harness(tmp_path, incoming_paths=("app.py", "requirements.txt"))

    result = harness.service.update(no_start=True)

    assert result["error"] is False
    assert result["status"] == "BOT_UPDATE_COMPLETE_NO_START"
    assert result["current_revision"] == result["target_revision"] == TARGET
    assert result["bot_stopped"] is True
    assert result["steps_completed"] == [
        "repository_identity", "fetch", "preflight", "verified_backup",
        "fast_forward", "dependencies", "local_checks",
    ]
    assert harness.git_calls[0][0] == "fetch"
    assert harness.git_calls[1] == ("merge", "--ff-only", "--no-edit", TARGET)
    assert harness.backup.backup_calls == 1
    assert harness.backup.verify_calls == ["C:/synthetic/verified-backup.zip"]
    assert harness.stop_calls == []
    assert any(
        "install" in call[0]
        and any(str(argument).casefold().endswith("requirements.txt") for argument in call[0])
        for call in harness.command_calls
    )
    assert harness.state == "STOPPED"
    assert harness.lock.acquired and harness.lock.released


def test_update_stops_only_owned_checkout_and_confirms_exact_revision_readiness(tmp_path):
    harness = _Harness(tmp_path, process_state="RUNNING")

    result = harness.service.update()

    assert result["error"] is False
    assert result["status"] == "BOT_UPDATE_COMPLETE"
    assert result["readiness_confirmed"] is True
    assert result["process_state"] == "RUNNING"
    assert harness.stop_calls == [
        ("synthetic-token", project_root_fingerprint(tmp_path))
    ]
    assert result["steps_completed"][-2:] == ["start_requested", "polling_ready"]
    assert any(
        any(str(argument).casefold().endswith("start_bot.ps1") for argument in call[0])
        for call in harness.command_calls
    )


def test_update_guard_blocks_startup_through_merge_and_releases_for_normal_start(tmp_path):
    harness = _Harness(tmp_path)
    state_root = tmp_path / ".synthetic-lifecycle"
    lease = BotInstanceLease("synthetic-token", state_root=state_root)
    merge_start_codes = []
    start_gate_was_open = []
    original_git = harness.service.git_runner
    original_command = harness.service.command_runner

    def git(root, arguments):
        if arguments[0] == "merge":
            try:
                lease.acquire()
            except BotLifecycleError as error:
                merge_start_codes.append(error.code)
            else:
                lease.close()
                pytest.fail("startup escaped the update maintenance guard during merge")
        return original_git(root, arguments)

    def command(arguments, *, cwd, timeout):
        if any(str(argument).casefold().endswith("start_bot.ps1") for argument in arguments):
            try:
                lease.acquire()
            except BotLifecycleError as error:
                start_gate_was_open.append(False)
                pytest.fail(f"startup guard remained held at handoff: {error.code}")
            else:
                start_gate_was_open.append(True)
                lease.close()
        return original_command(arguments, cwd=cwd, timeout=timeout)

    harness.service.git_runner = git
    harness.service.command_runner = command

    result = harness.service.update()

    assert result["error"] is False
    assert merge_start_codes == ["BOT_INSTANCE_MAINTENANCE_ACTIVE"]
    assert start_gate_was_open == [True]
    assert harness.backup.guards
    assert harness.backup.guards[0].is_acquired is False
    lease.acquire()
    lease.close()


def test_already_current_fetches_but_does_not_stop_back_up_or_restart(tmp_path):
    harness = _Harness(tmp_path, process_state="RUNNING", already_current=True, target=BASE)

    result = harness.service.update()

    assert result["error"] is False
    assert result["status"] == "BOT_UPDATE_ALREADY_CURRENT"
    assert harness.stop_calls == []
    assert harness.backup.backup_calls == 0
    assert harness.command_calls == []
    assert [call[0] for call in harness.git_calls] == ["fetch"]


def test_wrong_repository_identity_stops_before_fetch_or_process_change(tmp_path):
    harness = _Harness(tmp_path)
    harness.preflight.inspect_repository_identity = lambda: {
        "error": True, "blockers": [{"code": "BOT_UPDATE_WRONG_BRANCH"}]
    }

    result = harness.service.update()

    assert result["code"] == "BOT_UPDATE_REPOSITORY_IDENTITY_REJECTED"
    assert harness.git_calls == []
    assert harness.stop_calls == []
    assert harness.backup.backup_calls == 0


def test_fetch_failure_does_not_stop_or_create_backup(tmp_path):
    harness = _Harness(tmp_path, process_state="RUNNING", fetch_ok=False)

    result = harness.service.update()

    assert result["code"] == "BOT_UPDATE_FETCH_FAILED"
    assert harness.stop_calls == []
    assert harness.backup.backup_calls == 0


def test_preflight_block_after_fetch_does_not_stop_or_create_backup(tmp_path):
    harness = _Harness(tmp_path, process_state="RUNNING", blocked=True)

    result = harness.service.update()

    assert result["code"] == "BOT_UPDATE_PREFLIGHT_BLOCKED"
    assert harness.stop_calls == []
    assert harness.backup.backup_calls == 0


def test_failed_graceful_stop_does_not_create_backup_or_update(tmp_path):
    harness = _Harness(tmp_path, process_state="RUNNING")
    harness.stop = lambda *_args, **_kwargs: {"stopped": False, "state": "RUNNING"}
    harness.service.stop_requester = harness.stop

    result = harness.service.update()

    assert result["code"] == "BOT_UPDATE_STOP_FAILED"
    assert result["bot_stopped"] is False
    assert harness.backup.backup_calls == 0
    assert not any(call[0] == "merge" for call in harness.git_calls)


def test_failed_or_unverified_backup_never_merges_or_starts(tmp_path):
    for options, expected in [
        ({"backup_error": True}, "BOT_UPDATE_BACKUP_FAILED"),
        ({"verify_error": True}, "BOT_UPDATE_BACKUP_VERIFY_FAILED"),
    ]:
        harness = _Harness(tmp_path / expected, **options)
        result = harness.service.update()
        assert result["code"] == expected
        assert result["bot_stopped"] is True
        assert not any(call[0] == "merge" for call in harness.git_calls)
        assert not any("start_bot.ps1" in call[0] for call in harness.command_calls)


def test_failed_fast_forward_reports_verified_backup_and_leaves_bot_stopped(tmp_path):
    harness = _Harness(tmp_path, merge_ok=False)

    result = harness.service.update()

    assert result["code"] == "BOT_UPDATE_FAST_FORWARD_FAILED"
    assert result["bot_stopped"] is True
    assert result["backup_path"] == "C:/synthetic/verified-backup.zip"
    assert result["recovery_action"]
    assert not any("start_bot.ps1" in call[0] for call in harness.command_calls)


def test_dependency_or_local_check_failure_does_not_start_bot(tmp_path):
    for failed_argument, expected in [
        ("pip", "BOT_UPDATE_DEPENDENCIES_FAILED"),
        ("compileall", "BOT_UPDATE_COMPILE_FAILED"),
        ("runtime_healthcheck", "BOT_UPDATE_RUNTIME_CHECK_FAILED"),
    ]:
        harness = _Harness(tmp_path / failed_argument, command_fail=failed_argument)
        result = harness.service.update(no_start=True)
        assert result["code"] == expected
        assert result["bot_stopped"] is True
        assert result["backup_path"] == "C:/synthetic/verified-backup.zip"
        assert not any("start_bot.ps1" in call[0] for call in harness.command_calls)


def test_start_readiness_requires_running_exact_target_and_checkout(tmp_path):
    cases = [
        {"ready": False},
        {"ready_revision": BASE},
        {"ready_fingerprint": "f" * 64},
        {"ready_state": "STARTING"},
    ]
    for index, case in enumerate(cases):
        harness = _Harness(tmp_path / str(index), **case)

        result = harness.service.update()

        assert result["code"] == "BOT_UPDATE_READINESS_NOT_CONFIRMED"
        assert result["readiness_confirmed"] is False
        assert result["process_state"] != "RUNNING" or result["bot_stopped"] is False


def test_updater_lock_busy_has_no_side_effects(tmp_path):
    harness = _Harness(tmp_path, process_state="RUNNING", lock_busy=True)

    result = harness.service.update()

    assert result["code"] == "BOT_UPDATE_ALREADY_RUNNING"
    assert harness.git_calls == []
    assert harness.stop_calls == []
    assert harness.backup.backup_calls == 0


def test_startup_guard_contention_stops_update_before_fetch(tmp_path):
    harness = _Harness(tmp_path)

    class _BusyGuard:
        is_acquired = False

        def acquire(self):
            return False

        def close(self):
            pass

    harness.service.startup_guard_factory = lambda _token: _BusyGuard()

    result = harness.service.update(no_start=True)

    assert result["code"] == "BOT_UPDATE_STARTUP_GUARD_BUSY"
    assert harness.git_calls == []
    assert harness.preflight.identity_calls == 0
    assert harness.lock.released is True


def test_foreign_checkout_process_is_never_stopped(tmp_path):
    harness = _Harness(tmp_path, process_state="RUNNING")
    harness.preflight.inspect = lambda: {
        "error": False,
        "current_revision": BASE,
        "target_revision": TARGET,
        "already_current": False,
        "process_state": "RUNNING",
        "process_checkout_matches": False,
        "incoming_paths": ["app.py"],
        "blockers": [],
    }

    result = harness.service.update()

    assert result["code"] == "BOT_UPDATE_PROCESS_CHECKOUT_UNVERIFIED"
    assert harness.stop_calls == []
    assert harness.backup.backup_calls == 0


def test_changed_target_after_stop_aborts_before_backup(tmp_path):
    harness = _Harness(tmp_path)
    original_inspect = harness.preflight.inspect
    calls = 0

    def inspect():
        nonlocal calls
        calls += 1
        result = original_inspect()
        if calls == 2:
            result["target_revision"] = "3" * 40
        return result

    harness.preflight.inspect = inspect

    result = harness.service.update(no_start=True)

    assert result["code"] == "BOT_UPDATE_REVISION_CHANGED_AFTER_STOP"
    assert result["bot_stopped"] is True
    assert harness.backup.backup_calls == 0
    assert not any(call[0] == "merge" for call in harness.git_calls)


def test_changed_checkout_state_during_backup_aborts_before_merge(tmp_path):
    harness = _Harness(tmp_path)
    original_inspect = harness.preflight.inspect
    calls = 0

    def inspect():
        nonlocal calls
        calls += 1
        result = original_inspect()
        if calls == 3:
            result["current_revision"] = "3" * 40
        return result

    harness.preflight.inspect = inspect

    result = harness.service.update(no_start=True)

    assert result["code"] == "BOT_UPDATE_PRE_MERGE_CHECK_FAILED"
    assert result["backup_path"] == "C:/synthetic/verified-backup.zip"
    assert harness.backup.verify_calls
    assert not any(call[0] == "merge" for call in harness.git_calls)


def test_kernel_lock_serializes_updaters_in_synthetic_git_directory(tmp_path):
    root = tmp_path / "synthetic-repository"
    root.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    first = _CheckoutUpdateLock(root)
    second = _CheckoutUpdateLock(root)
    first.acquire()
    try:
        with pytest.raises(_UpdateLockBusy):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_update_cli_exposes_no_start_without_printing_token(tmp_path, monkeypatch, capsys):
    token = "synthetic-secret-token-never-print-this"
    calls = []

    class _CliService:
        def __init__(self, project_root, *, lifecycle_token):
            assert project_root == tmp_path.resolve()
            assert lifecycle_token == token

        def update(self, *, no_start=False):
            calls.append(no_start)
            return {
                "error": False,
                "status": "BOT_UPDATE_COMPLETE_NO_START",
                "current_revision": TARGET,
                "target_revision": TARGET,
                "backup_path": None,
                "bot_stopped": True,
                "started": False,
                "readiness_confirmed": False,
                "steps_completed": ["local_checks"],
                "read_only": False,
                "executed": True,
            }

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setattr("bot_update.BotUpdateRuntimeService", _CliService)

    result = update_cli_main([
        "update", "--no-start", "--project-root", str(tmp_path)
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert calls == [True]
    assert "бот оставлен остановленным" in output
    assert token not in output
