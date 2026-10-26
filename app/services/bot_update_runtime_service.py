"""Serialized, failure-aware orchestration for the supported local bot update."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from services.bot_backup_service import BotBackupService
from services.bot_instance_lifecycle_service import (
    BotStartupMaintenanceGuard,
    inspect_bot_instance,
    project_root_fingerprint,
    request_graceful_stop,
)
from services.bot_update_preflight_service import BotUpdatePreflightService

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows runtime
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX runtime
    msvcrt = None


_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
_ACTIVE_STATES = {"RUNNING", "STARTING", "STOPPING"}


class BotUpdateRuntimeService:
    """Run update steps in order and report only verified outcomes.

    Every external boundary can be replaced in tests. Production callers should
    use this service only from the explicit PowerShell update command.
    """

    def __init__(
        self,
        project_root,
        *,
        lifecycle_token=None,
        preflight=None,
        backup_service=None,
        process_inspector=None,
        stop_requester=None,
        git_runner=None,
        command_runner=None,
        lock_factory=None,
        startup_guard_factory=None,
        sleep=time.sleep,
        monotonic=time.monotonic,
        platform=None,
        python_executable=None,
        powershell_executable=None,
        readiness_timeout_seconds=60.0,
        step_timeout_seconds=180.0,
    ):
        self.project_root = Path(project_root).resolve(strict=False)
        self.lifecycle_token = str(lifecycle_token or "").strip()
        self.process_inspector = process_inspector or inspect_bot_instance
        self.stop_requester = stop_requester or request_graceful_stop
        self.preflight = preflight or BotUpdatePreflightService(
            self.project_root,
            lifecycle_token=self.lifecycle_token,
            process_inspector=self.process_inspector,
        )
        self.backup_service = backup_service or BotBackupService(
            project_root=self.project_root,
            lifecycle_token=self.lifecycle_token,
            lifecycle_inspector=self.process_inspector,
        )
        self.git_runner = git_runner or self._run_git
        self.command_runner = command_runner or self._run_command
        self.lock_factory = lock_factory or _CheckoutUpdateLock
        self.startup_guard_factory = startup_guard_factory or getattr(
            self.backup_service,
            "startup_guard_factory",
            lambda token: BotStartupMaintenanceGuard(token),
        )
        self.sleep = sleep
        self.monotonic = monotonic
        self.platform = platform or os.name
        self.python_executable = str(python_executable or sys.executable)
        self.powershell_executable = (
            powershell_executable
            or os.getenv("APP_POWER_SHELL_EXECUTABLE")
            or self._find_powershell()
        )
        self.readiness_timeout_seconds = max(0.0, min(float(readiness_timeout_seconds), 180.0))
        self.step_timeout_seconds = max(1.0, min(float(step_timeout_seconds), 600.0))
        self.checkout_fingerprint = project_root_fingerprint(self.project_root)

    def update(self, *, no_start=False):
        """Fetch, recheck, stop, back up, fast-forward and optionally start."""
        if self.platform != "nt":
            return self._failure("BOT_UPDATE_WINDOWS_ONLY")
        if not self.lifecycle_token:
            return self._failure("TELEGRAM_BOT_TOKEN_MISSING")
        if not self.powershell_executable and not no_start:
            return self._failure("BOT_UPDATE_POWERSHELL_UNAVAILABLE")

        lock = None
        startup_guard = None
        try:
            lock = self.lock_factory(self.project_root)
            lock.acquire()
        except _UpdateLockBusy:
            return self._failure("BOT_UPDATE_ALREADY_RUNNING")
        except Exception:
            return self._failure("BOT_UPDATE_LOCK_UNAVAILABLE")

        try:
            try:
                startup_guard = self.startup_guard_factory(self.lifecycle_token)
                if not startup_guard.acquire():
                    return self._failure("BOT_UPDATE_STARTUP_GUARD_BUSY")
            except Exception:
                return self._failure("BOT_UPDATE_STARTUP_GUARD_UNAVAILABLE")
            return self._update_locked(
                no_start=no_start,
                startup_guard=startup_guard,
            )
        finally:
            if startup_guard is not None:
                try:
                    startup_guard.close()
                except Exception:
                    pass
            try:
                if lock is not None:
                    lock.release()
            except Exception:
                pass

    def _update_locked(self, *, no_start, startup_guard):
        identity = self._safe_call(self.preflight.inspect_repository_identity)
        if identity is None:
            return self._failure("BOT_UPDATE_REPOSITORY_IDENTITY_UNAVAILABLE")
        if identity.get("error") is not False:
            return self._failure(
                "BOT_UPDATE_REPOSITORY_IDENTITY_REJECTED",
                blockers=identity.get("blockers", []),
            )

        fetched = self._git(
            "fetch", "--no-tags", "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        )
        if not fetched:
            return self._failure("BOT_UPDATE_FETCH_FAILED")

        plan = self._safe_call(self.preflight.inspect)
        if plan is None:
            return self._failure("BOT_UPDATE_PREFLIGHT_UNAVAILABLE")
        if plan.get("error") is not False:
            return self._failure(
                "BOT_UPDATE_PREFLIGHT_BLOCKED",
                blockers=plan.get("blockers", []),
                current_revision=plan.get("current_revision"),
                target_revision=plan.get("target_revision"),
            )

        current_revision = self._valid_sha(plan.get("current_revision"))
        target_revision = self._valid_sha(plan.get("target_revision"))
        if not current_revision or not target_revision:
            return self._failure("BOT_UPDATE_REVISION_INVALID")
        if plan.get("already_current") is True:
            return {
                "error": False,
                "status": "BOT_UPDATE_ALREADY_CURRENT",
                "current_revision": current_revision,
                "target_revision": target_revision,
                "process_state": plan.get("process_state"),
                "backup_path": None,
                "bot_stopped": False,
                "started": False,
                "readiness_confirmed": False,
                "steps_completed": ["repository_identity", "fetch", "preflight"],
                "read_only": False,
                "executed": True,
            }

        process_state = plan.get("process_state")
        bot_stopped = process_state == "STOPPED"
        steps = ["repository_identity", "fetch", "preflight"]
        if process_state in _ACTIVE_STATES:
            if plan.get("process_checkout_matches") is not True:
                return self._failure(
                    "BOT_UPDATE_PROCESS_CHECKOUT_UNVERIFIED",
                    current_revision=current_revision,
                    target_revision=target_revision,
                )
            stopped = self._safe_stop()
            if not stopped:
                return self._failure(
                    "BOT_UPDATE_STOP_FAILED",
                    current_revision=current_revision,
                    target_revision=target_revision,
                    bot_stopped=False,
                )
            bot_stopped = True
            steps.append("graceful_stop")
        elif process_state != "STOPPED":
            return self._failure(
                "BOT_UPDATE_PROCESS_STATE_UNKNOWN",
                current_revision=current_revision,
                target_revision=target_revision,
            )

        # Revalidate after stopping and pin both the source and target revisions.
        post_stop = self._safe_call(self.preflight.inspect)
        if post_stop is None or post_stop.get("error") is not False:
            return self._failure(
                "BOT_UPDATE_POST_STOP_PREFLIGHT_FAILED",
                blockers=(post_stop or {}).get("blockers", []),
                current_revision=current_revision,
                target_revision=target_revision,
                bot_stopped=bot_stopped,
            )
        if (
            self._valid_sha(post_stop.get("current_revision")) != current_revision
            or self._valid_sha(post_stop.get("target_revision")) != target_revision
            or post_stop.get("process_state") != "STOPPED"
        ):
            return self._failure(
                "BOT_UPDATE_REVISION_CHANGED_AFTER_STOP",
                current_revision=self._valid_sha(post_stop.get("current_revision")),
                target_revision=target_revision,
                bot_stopped=bot_stopped,
            )

        backup_under_guard = getattr(self.backup_service, "backup_under_guard", None)
        if not callable(backup_under_guard):
            return self._failure(
                "BOT_UPDATE_BACKUP_GUARD_UNSUPPORTED",
                current_revision=current_revision,
                target_revision=target_revision,
                bot_stopped=bot_stopped,
            )
        backup = self._safe_call(lambda: backup_under_guard(startup_guard))
        if backup is None or backup.get("error") is not False:
            return self._failure(
                "BOT_UPDATE_BACKUP_FAILED",
                current_revision=current_revision,
                target_revision=target_revision,
                bot_stopped=bot_stopped,
            )
        backup_path = backup.get("backup_path")
        if not isinstance(backup_path, str) or not backup_path.strip():
            return self._failure(
                "BOT_UPDATE_BACKUP_PATH_MISSING",
                current_revision=current_revision,
                target_revision=target_revision,
                bot_stopped=bot_stopped,
            )
        verified = self._safe_call(lambda: self.backup_service.verify_archive(backup_path))
        if verified is None or verified.get("error") is not False:
            return self._failure(
                "BOT_UPDATE_BACKUP_VERIFY_FAILED",
                current_revision=current_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=bot_stopped,
            )
        steps.append("verified_backup")

        # Refuse to update if anything changed during backup creation.
        before_merge = self._safe_call(self.preflight.inspect)
        if (
            before_merge is None
            or before_merge.get("error") is not False
            or self._valid_sha(before_merge.get("current_revision")) != current_revision
            or self._valid_sha(before_merge.get("target_revision")) != target_revision
            or before_merge.get("process_state") != "STOPPED"
        ):
            return self._failure(
                "BOT_UPDATE_PRE_MERGE_CHECK_FAILED",
                blockers=(before_merge or {}).get("blockers", []),
                current_revision=current_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=bot_stopped,
            )

        if not self._git(
            "merge", "--ff-only", "--no-edit", "--no-overwrite-ignore",
            target_revision,
        ):
            return self._failure(
                "BOT_UPDATE_FAST_FORWARD_FAILED",
                current_revision=self._read_head(),
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=bot_stopped,
            )
        updated_revision = self._read_head()
        if updated_revision != target_revision:
            return self._failure(
                "BOT_UPDATE_REVISION_MISMATCH_AFTER_MERGE",
                current_revision=updated_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=bot_stopped,
            )
        steps.append("fast_forward")

        requirements_changed = any(
            str(path).replace("\\", "/").casefold() == "requirements.txt"
            for path in plan.get("incoming_paths", [])
        )
        dependency_result = self._ensure_dependencies(force_install=requirements_changed)
        if not dependency_result:
            return self._failure(
                "BOT_UPDATE_DEPENDENCIES_FAILED",
                current_revision=target_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=bot_stopped,
            )
        steps.append("dependencies")

        if not self._run_python("-m", "compileall", "-q", "app"):
            return self._failure(
                "BOT_UPDATE_COMPILE_FAILED",
                current_revision=target_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=bot_stopped,
            )
        if not self._run_python("-m", "runtime_healthcheck"):
            return self._failure(
                "BOT_UPDATE_RUNTIME_CHECK_FAILED",
                current_revision=target_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=bot_stopped,
            )
        steps.append("local_checks")

        if no_start:
            return {
                "error": False,
                "status": "BOT_UPDATE_COMPLETE_NO_START",
                "current_revision": target_revision,
                "target_revision": target_revision,
                "process_state": "STOPPED",
                "backup_path": backup_path,
                "bot_stopped": True,
                "started": False,
                "readiness_confirmed": False,
                "steps_completed": steps,
                "read_only": False,
                "executed": True,
            }

        # The checkout and dependencies are now ready. Release the startup gate
        # immediately before handing control to the normal startup script.
        startup_guard.close()
        start_args = self._start_arguments()
        if not self._invoke_command(start_args, timeout=self.step_timeout_seconds):
            return self._failure(
                "BOT_UPDATE_START_FAILED",
                current_revision=target_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=self._process_state() == "STOPPED",
                started=False,
                steps_completed=steps,
            )
        steps.append("start_requested")
        ready = self._wait_until_ready(target_revision)
        if not ready:
            return self._failure(
                "BOT_UPDATE_READINESS_NOT_CONFIRMED",
                current_revision=target_revision,
                target_revision=target_revision,
                backup_path=backup_path,
                bot_stopped=self._process_state() == "STOPPED",
                started=True,
                steps_completed=steps,
                process_state=self._process_state(),
            )
        steps.append("polling_ready")
        return {
            "error": False,
            "status": "BOT_UPDATE_COMPLETE",
            "current_revision": target_revision,
            "target_revision": target_revision,
            "process_state": "RUNNING",
            "backup_path": backup_path,
            "bot_stopped": False,
            "started": True,
            "readiness_confirmed": True,
            "steps_completed": steps,
            "read_only": False,
            "executed": True,
        }

    def _safe_stop(self):
        try:
            result = self.stop_requester(
                self.lifecycle_token,
                expected_project_root_fingerprint=self.checkout_fingerprint,
            )
        except Exception:
            return False
        if not isinstance(result, dict) or result.get("stopped") is not True:
            return False
        status = self._inspect_process()
        return status.get("state") == "STOPPED"

    def _ensure_dependencies(self, *, force_install):
        if force_install:
            return self._run_python(
                "-m", "pip", "install", "-r", str(self.project_root / "requirements.txt")
            )
        checked = self._run_python("-m", "pip", "check")
        if checked:
            return True
        return self._run_python(
            "-m", "pip", "install", "-r", str(self.project_root / "requirements.txt")
        )

    def _run_python(self, *arguments):
        return self._invoke_command(
            [self.python_executable, *arguments], timeout=self.step_timeout_seconds
        )

    def _invoke_command(self, arguments, *, timeout):
        try:
            result = self.command_runner(
                list(arguments),
                cwd=self.project_root,
                timeout=timeout,
            )
        except Exception:
            return False
        return getattr(result, "returncode", None) == 0

    def _git(self, *arguments):
        try:
            result = self.git_runner(self.project_root, list(arguments))
        except Exception:
            return False
        return getattr(result, "returncode", None) == 0

    def _read_head(self):
        try:
            result = self.git_runner(
                self.project_root, ["rev-parse", "--verify", "HEAD"]
            )
        except Exception:
            return None
        if getattr(result, "returncode", None) != 0:
            return None
        return self._valid_sha(getattr(result, "stdout", None))

    def _inspect_process(self):
        try:
            result = self.process_inspector(self.lifecycle_token)
        except Exception:
            return {"state": "UNKNOWN", "revision": None, "project_root_fingerprint": None}
        return result if isinstance(result, dict) else {
            "state": "UNKNOWN", "revision": None, "project_root_fingerprint": None,
        }

    def _process_state(self):
        state = self._inspect_process().get("state")
        return state if state in {"STOPPED", *_ACTIVE_STATES, "UNKNOWN"} else "UNKNOWN"

    def _wait_until_ready(self, target_revision):
        deadline = self.monotonic() + self.readiness_timeout_seconds
        while True:
            status = self._inspect_process()
            if (
                status.get("state") == "RUNNING"
                and self._valid_sha(status.get("revision")) == target_revision
                and status.get("project_root_fingerprint") == self.checkout_fingerprint
            ):
                return True
            if self.monotonic() >= deadline:
                return False
            self.sleep(min(0.25, max(0.0, deadline - self.monotonic())))

    def _start_arguments(self):
        return [
            str(self.powershell_executable),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.project_root / "start_bot.ps1"),
            "-Background",
        ]

    @staticmethod
    def _run_git(project_root, arguments):
        return subprocess.run(
            ["git", "-C", str(project_root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    @staticmethod
    def _run_command(arguments, *, cwd, timeout):
        environment = os.environ.copy()
        app_path = str(Path(cwd) / "app")
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = app_path + (os.pathsep + existing if existing else "")
        try:
            return subprocess.run(
                arguments,
                cwd=str(cwd),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return _FailedCommand()

    @staticmethod
    def _find_powershell():
        return shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("powershell") or shutil.which("pwsh")

    @staticmethod
    def _safe_call(callback):
        try:
            result = callback()
        except Exception:
            return None
        return result if isinstance(result, dict) else None

    @staticmethod
    def _valid_sha(value):
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        return normalized if _SHA_RE.fullmatch(normalized) else None

    @staticmethod
    def _failure(
        code,
        *,
        blockers=None,
        current_revision=None,
        target_revision=None,
        backup_path=None,
        bot_stopped=False,
        started=False,
        steps_completed=None,
        process_state=None,
    ):
        return {
            "error": True,
            "status": "BOT_UPDATE_FAILED",
            "code": code,
            "blockers": blockers or [],
            "current_revision": current_revision,
            "target_revision": target_revision,
            "backup_path": backup_path,
            "bot_stopped": bot_stopped,
            "started": started,
            "readiness_confirmed": False,
            "process_state": process_state,
            "steps_completed": steps_completed or [],
            "recovery_action": (
                "Бот подтверждённо остановлен. Сначала проверьте Git/резервную копию; "
                "не запускайте восстановление поверх текущей папки."
                if bot_stopped else None
            ),
            "recovery_command": r".\update_bot.ps1 -CheckOnly" if bot_stopped else None,
            "read_only": False,
            "executed": True,
        }


class _FailedCommand:
    returncode = 1


class _UpdateLockBusy(Exception):
    pass


class _CheckoutUpdateLock:
    """Kernel lock stored in this worktree's private Git directory."""

    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.stream = None

    def acquire(self):
        result = subprocess.run(
            ["git", "-C", str(self.project_root), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise OSError("git directory unavailable")
        git_directory = Path(result.stdout.strip())
        if not git_directory.is_absolute():
            git_directory = self.project_root / git_directory
        lock_path = git_directory.resolve(strict=True) / "ai-assistant-updater.lock"
        self.stream = lock_path.open("a+b")
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b"\0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt" and msvcrt is not None:
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            elif os.name == "posix" and fcntl is not None:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                raise OSError("kernel lock unavailable")
        except OSError as error:
            self.stream.close()
            self.stream = None
            if getattr(error, "winerror", None) in {33, 36} or error.errno in {11, 13, 35}:
                raise _UpdateLockBusy() from error
            raise
        except Exception:
            self.stream.close()
            self.stream = None
            raise

    def release(self):
        if self.stream is None:
            return
        stream, self.stream = self.stream, None
        try:
            stream.seek(0)
            if os.name == "nt" and msvcrt is not None:
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            elif os.name == "posix" and fcntl is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
