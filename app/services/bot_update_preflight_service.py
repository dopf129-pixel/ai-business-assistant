"""Read-only local preflight for the supported fast-forward bot update path."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from services.bot_instance_lifecycle_service import (
    inspect_bot_instance,
    project_root_fingerprint,
)


class BotUpdatePreflightService:
    ALLOWED_REMOTE_URLS = frozenset({
        "https://github.com/dopf129-pixel/ai-business-assistant.git",
        "https://github.com/dopf129-pixel/ai-business-assistant",
        "git@github.com:dopf129-pixel/ai-business-assistant.git",
        "ssh://git@github.com/dopf129-pixel/ai-business-assistant.git",
    })
    PRESERVABLE_DATA_PATHS = frozenset({
        "data/tasks.json",
        "data/users.json",
    })
    TARGET_REF = "refs/remotes/origin/main"

    def __init__(
        self,
        project_root,
        *,
        lifecycle_token=None,
        process_inspector=None,
        git_runner=None,
    ):
        self.project_root = Path(project_root).resolve(strict=False)
        self.checkout_fingerprint = project_root_fingerprint(self.project_root)
        self.lifecycle_token = str(lifecycle_token or "").strip()
        self.process_inspector = process_inspector or inspect_bot_instance
        self.git_runner = git_runner or self._run_git

    def inspect(self):
        """Return a plan based only on local checkout and cached refs."""
        blockers = []
        try:
            actual_root = self._git_text("rev-parse", "--show-toplevel")
            current_revision = self._git_text("rev-parse", "--verify", "HEAD")
            current_branch = self._git_text("branch", "--show-current")
            upstream = self._git_text(
                "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"
            )
            remote_url = self._git_text("remote", "get-url", "origin")
            target_revision = self._git_text("rev-parse", "--verify", self.TARGET_REF)
            relation = self._git_text(
                "rev-list", "--left-right", "--count", f"HEAD...{self.TARGET_REF}"
            )
            local_status = self._git_text(
                "status", "--porcelain=v1", "-z", "--untracked-files=all"
            )
            protected_status = self._git_text(
                "status",
                "--porcelain=v1",
                "-z",
                "--ignored=matching",
                "--",
                "data/tasks.json",
                "data/users.json",
            )
            incoming_status = self._git_text(
                "diff", "--name-only", "-z", "HEAD", self.TARGET_REF
            )
            target_tree = self._git_text("ls-tree", "-r", "--name-only", "-z", self.TARGET_REF)
        except _PreflightFailure as failure:
            return self._blocked(failure.code)

        if not self._same_path(actual_root, self.project_root):
            blockers.append({"code": "BOT_UPDATE_WRONG_REPOSITORY_ROOT"})
        if current_branch != "main":
            blockers.append({"code": "BOT_UPDATE_WRONG_BRANCH"})
        if upstream != "origin/main":
            blockers.append({"code": "BOT_UPDATE_WRONG_UPSTREAM"})
        if remote_url not in self.ALLOWED_REMOTE_URLS:
            blockers.append({"code": "BOT_UPDATE_REMOTE_NOT_ALLOWED"})

        try:
            ahead, behind = (int(value) for value in relation.split())
        except (TypeError, ValueError):
            return self._blocked("BOT_UPDATE_GIT_RELATION_INVALID")
        if ahead:
            blockers.append({"code": "BOT_UPDATE_LOCAL_COMMITS_AHEAD", "count": ahead})

        incoming_paths = self._nul_paths(incoming_status)
        target_paths = {
            self._normalize_path(path)
            for path in self._nul_paths(target_tree)
        }
        local_entries = self._parse_status(local_status)
        protected_entries = self._parse_status(protected_status)
        by_path = {}
        for status, path in [*local_entries, *protected_entries]:
            by_path[self._normalize_path(path)] = (status, path)

        unsafe_local = []
        preservable_local = []
        untracked_conflicts = []
        ignored_overwrite_conflicts = []
        for normalized_path, (status, original_path) in sorted(by_path.items()):
            if normalized_path in self.PRESERVABLE_DATA_PATHS:
                if self._paths_intersect_any(normalized_path, incoming_paths):
                    blockers.append({
                        "code": "BOT_UPDATE_LOCAL_DATA_OVERLAP",
                        "path": original_path,
                    })
                else:
                    preservable_local.append(original_path)
                continue
            if status == "!!":
                continue
            if status == "??":
                if self._paths_intersect_any(normalized_path, target_paths):
                    untracked_conflicts.append(original_path)
                else:
                    unsafe_local.append(original_path)
                continue
            unsafe_local.append(original_path)

        if unsafe_local:
            blockers.append({
                "code": "BOT_UPDATE_LOCAL_CHANGES_UNSAFE",
                "paths": sorted(set(unsafe_local)),
            })
        if untracked_conflicts:
            blockers.append({
                "code": "BOT_UPDATE_UNTRACKED_OVERWRITE_CONFLICT",
                "paths": sorted(set(untracked_conflicts)),
            })
        for path in sorted(set(incoming_paths)):
            if not self._local_path_exists(path):
                continue
            ignored = self._check_ignored_path(path)
            if ignored is None:
                blockers.append({"code": "BOT_UPDATE_IGNORED_PATH_CHECK_FAILED"})
                break
            if ignored:
                ignored_overwrite_conflicts.append(path)
        if ignored_overwrite_conflicts:
            blockers.append({
                "code": "BOT_UPDATE_IGNORED_OVERWRITE_CONFLICT",
                "paths": sorted(set(ignored_overwrite_conflicts)),
            })
        protected_incoming = sorted(
            path for path in incoming_paths
            if self._normalize_path(path) in self.PRESERVABLE_DATA_PATHS
        )
        if protected_incoming:
            blockers.append({
                "code": "BOT_UPDATE_INCOMING_PROTECTED_DATA_CHANGE",
                "paths": protected_incoming,
            })

        process = self._inspect_process()
        if process["state"] == "UNKNOWN":
            blockers.append({"code": "BOT_UPDATE_PROCESS_STATE_UNKNOWN"})
        process_checkout_matches = None
        if process["state"] in {"RUNNING", "STARTING", "STOPPING"}:
            if process.get("project_root_fingerprint") is None:
                blockers.append({"code": "BOT_UPDATE_PROCESS_CHECKOUT_UNKNOWN"})
            else:
                process_checkout_matches = (
                    process["project_root_fingerprint"] == self.checkout_fingerprint
                )
                if not process_checkout_matches:
                    blockers.append({"code": "BOT_UPDATE_PROCESS_OTHER_CHECKOUT"})

        ready = not blockers
        dependencies_needed = any(
            self._normalize_path(path) == "requirements.txt"
            for path in incoming_paths
        )
        return {
            "error": not ready,
            "status": "BOT_UPDATE_CHECK_READY" if ready else "BOT_UPDATE_CHECK_BLOCKED",
            "current_revision": current_revision,
            "current_branch": current_branch,
            "tracking_branch": upstream,
            "target_revision": target_revision,
            "target_version": "origin/main@" + target_revision[:12],
            "behind_count": behind,
            "already_current": behind == 0 and current_revision == target_revision,
            "remote_allowed": remote_url in self.ALLOWED_REMOTE_URLS,
            "cached_remote_ref_may_be_stale": True,
            "incoming_paths": sorted(set(incoming_paths)),
            "preservable_local_data_paths": sorted(set(preservable_local)),
            "dependencies_needed": dependencies_needed,
            "backup_required_before_update": behind > 0,
            "process_state": process["state"],
            "process_revision": process.get("revision"),
            "process_checkout_matches": process_checkout_matches,
            "required_action": (
                "STOP_OWN_TOKEN_BOUND_INSTANCE_BEFORE_UPDATE"
                if behind > 0 and process["state"] in {"RUNNING", "STARTING", "STOPPING"}
                else None
            ),
            "blockers": blockers,
            "network_requests": 0,
            "filesystem_writes": 0,
            "git_mutations": 0,
            "lifecycle_mutations": 0,
            "read_only": True,
            "executed": False,
        }

    def inspect_repository_identity(self):
        """Validate only local root/branch/tracking/remote before any fetch."""
        try:
            actual_root = self._git_text("rev-parse", "--show-toplevel")
            branch = self._git_text("branch", "--show-current")
            upstream = self._git_text(
                "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"
            )
            remote_url = self._git_text("remote", "get-url", "origin")
        except _PreflightFailure as failure:
            return self._blocked(failure.code)
        blockers = []
        if not self._same_path(actual_root, self.project_root):
            blockers.append({"code": "BOT_UPDATE_WRONG_REPOSITORY_ROOT"})
        if branch != "main":
            blockers.append({"code": "BOT_UPDATE_WRONG_BRANCH"})
        if upstream != "origin/main":
            blockers.append({"code": "BOT_UPDATE_WRONG_UPSTREAM"})
        if remote_url not in self.ALLOWED_REMOTE_URLS:
            blockers.append({"code": "BOT_UPDATE_REMOTE_NOT_ALLOWED"})
        return {
            "error": bool(blockers),
            "blockers": blockers,
            "read_only": True,
            "executed": False,
        }

    def _inspect_process(self):
        if not self.lifecycle_token:
            return {"state": "UNKNOWN", "revision": None, "project_root_fingerprint": None}
        try:
            result = self.process_inspector(self.lifecycle_token)
        except Exception:
            return {"state": "UNKNOWN", "revision": None, "project_root_fingerprint": None}
        state = result.get("state") if isinstance(result, dict) else None
        if state not in {"STOPPED", "STARTING", "RUNNING", "STOPPING", "UNKNOWN"}:
            state = "UNKNOWN"
        revision = result.get("revision") if isinstance(result, dict) else None
        if not isinstance(revision, str):
            revision = None
        checkout_fingerprint = (
            result.get("project_root_fingerprint") if isinstance(result, dict) else None
        )
        if not isinstance(checkout_fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", checkout_fingerprint
        ):
            checkout_fingerprint = None
        return {
            "state": state,
            "revision": revision,
            "project_root_fingerprint": checkout_fingerprint,
        }

    def _git_text(self, *arguments):
        try:
            result = self.git_runner(self.project_root, list(arguments))
        except Exception as error:
            raise _PreflightFailure("BOT_UPDATE_GIT_UNAVAILABLE") from error
        returncode = getattr(result, "returncode", None)
        stdout = getattr(result, "stdout", None)
        if returncode != 0 or not isinstance(stdout, str):
            raise _PreflightFailure("BOT_UPDATE_GIT_COMMAND_FAILED")
        return stdout.strip("\r\n")

    def _check_ignored_path(self, relative_path):
        """Return whether an existing incoming path is ignored, or None on error."""
        try:
            result = self.git_runner(
                self.project_root,
                ["check-ignore", "-q", "--", relative_path],
            )
        except Exception:
            return None
        returncode = getattr(result, "returncode", None)
        if returncode == 0:
            return True
        if returncode == 1:
            return False
        return None

    def _local_path_exists(self, relative_path):
        original = str(relative_path or "").replace("\\", "/")
        parts = original.split("/")
        if (
            not original
            or original.startswith("/")
            or ":" in parts[0]
            or any(part in {"", ".", ".."} for part in parts)
        ):
            return False
        candidate = self.project_root.joinpath(*parts)
        try:
            return os.path.lexists(candidate)
        except OSError:
            return False

    @staticmethod
    def _run_git(project_root, arguments):
        return subprocess.run(
            ["git", "-C", str(project_root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )

    @classmethod
    def _parse_status(cls, output):
        values = output.split("\0")
        entries = []
        index = 0
        while index < len(values):
            token = values[index]
            index += 1
            if len(token) < 4:
                continue
            status = token[:2]
            path = token[3:]
            if path:
                entries.append((status, path))
            if "R" in status or "C" in status:
                if index < len(values) and values[index]:
                    entries.append((status, values[index]))
                index += 1
        return entries

    @staticmethod
    def _nul_paths(output):
        return [value for value in output.split("\0") if value]

    @staticmethod
    def _normalize_path(path):
        return str(path or "").replace("\\", "/").removeprefix("./").casefold()

    @classmethod
    def _paths_intersect_any(cls, path, candidates):
        return any(cls._paths_intersect(path, candidate) for candidate in candidates)

    @classmethod
    def _paths_intersect(cls, left, right):
        left = cls._normalize_path(left)
        right = cls._normalize_path(right)
        return (
            left == right
            or left.startswith(right + "/")
            or right.startswith(left + "/")
        )

    @staticmethod
    def _same_path(left, right):
        try:
            return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
                str(Path(right).resolve())
            )
        except OSError:
            return False

    @staticmethod
    def _blocked(code):
        return {
            "error": True,
            "status": "BOT_UPDATE_CHECK_BLOCKED",
            "blockers": [{"code": code}],
            "network_requests": 0,
            "filesystem_writes": 0,
            "git_mutations": 0,
            "lifecycle_mutations": 0,
            "read_only": True,
            "executed": False,
        }


class _PreflightFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)
