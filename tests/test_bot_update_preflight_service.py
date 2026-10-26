import json
import subprocess
from pathlib import Path

import pytest

from bot_update import main as update_cli_main
from services.bot_update_preflight_service import BotUpdatePreflightService
from services.bot_instance_lifecycle_service import project_root_fingerprint


REMOTE_URL = "https://github.com/dopf129-pixel/ai-business-assistant.git"


def _git(root, *arguments):
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _write(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _repository(root):
    root.mkdir(parents=True)
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "Synthetic Test")
    _git(root, "config", "user.email", "synthetic@example.invalid")
    _write(root, "app.py", "value = 'base'\n")
    _write(root, "requirements.txt", "synthetic-package==1\n")
    _write(root, "data/tasks.json", "{}\n")
    _write(root, "data/users.json", "{}\n")
    _git(root, "add", "app.py", "requirements.txt", "data/tasks.json", "data/users.json")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "remote", "add", "origin", REMOTE_URL)
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    _git(root, "branch", "--set-upstream-to=origin/main", "main")
    return base


def _publish_remote_commit(root, base, *, edits, additions=(), force_additions=()):
    for relative, content in edits.items():
        _write(root, relative, content)
    for relative, content in additions:
        _write(root, relative, content)
    _git(root, "add", "--all")
    for relative in force_additions:
        _git(root, "add", "-f", "--", relative)
    _git(root, "commit", "-m", "synthetic remote update")
    target = _git(root, "rev-parse", "HEAD")
    _git(root, "reset", "--hard", base)
    _git(root, "update-ref", "refs/remotes/origin/main", target)
    return target


def _service(root, *, state="STOPPED", token="synthetic-token", git_runner=None):
    process_calls = []

    def inspect_process(received_token):
        process_calls.append(received_token)
        return {
            "state": state,
            "revision": "a" * 40,
            "project_root_fingerprint": project_root_fingerprint(root),
        }

    service = BotUpdatePreflightService(
        root,
        lifecycle_token=token,
        process_inspector=inspect_process,
        git_runner=git_runner,
    )
    return service, process_calls


def _blocker_codes(result):
    return {item["code"] for item in result.get("blockers", [])}


def test_check_only_reports_cached_target_without_mutating_git_or_running_process(tmp_path):
    root = tmp_path / "project with spaces"
    base = _repository(root)
    target = _publish_remote_commit(
        root,
        base,
        edits={"app.py": "value = 'updated'\n", "requirements.txt": "synthetic-package==2\n"},
    )
    calls = []

    def runner(project_root, arguments):
        calls.append(tuple(arguments))
        return BotUpdatePreflightService._run_git(project_root, arguments)

    service, process_calls = _service(root, state="RUNNING", git_runner=runner)
    head_before = _git(root, "rev-parse", "HEAD")
    status_before = _git(root, "status", "--porcelain=v1")

    result = service.inspect()

    assert result["error"] is False
    assert result["target_revision"] == target
    assert result["target_version"] == "origin/main@" + target[:12]
    assert result["behind_count"] == 1
    assert result["dependencies_needed"] is True
    assert result["backup_required_before_update"] is True
    assert result["process_state"] == "RUNNING"
    assert result["required_action"] == "STOP_OWN_TOKEN_BOUND_INSTANCE_BEFORE_UPDATE"
    assert process_calls == ["synthetic-token"]
    assert not any(arguments[0] in {"fetch", "pull", "reset", "checkout", "clean"} for arguments in calls)
    assert _git(root, "rev-parse", "HEAD") == head_before
    assert _git(root, "status", "--porcelain=v1") == status_before
    assert result["network_requests"] == result["filesystem_writes"] == 0
    assert result["git_mutations"] == result["lifecycle_mutations"] == 0


def test_only_non_overlapping_legacy_tasks_and_users_changes_can_be_preserved(tmp_path):
    root = tmp_path / "project"
    base = _repository(root)
    target = _publish_remote_commit(root, base, edits={"app.py": "value = 'updated'\n"})
    _write(root, "data/tasks.json", '{"local":"preserve"}\n')
    _write(root, "data/users.json", '{"local-user":"preserve"}\n')
    service, _ = _service(root)

    result = service.inspect()

    assert result["error"] is False
    assert result["target_revision"] == target
    assert result["preservable_local_data_paths"] == [
        "data/tasks.json",
        "data/users.json",
    ]
    assert (root / "data" / "tasks.json").read_text(encoding="utf-8") == (
        '{"local":"preserve"}\n'
    )


def test_ignored_legacy_user_file_is_checked_and_preserved(tmp_path):
    root = tmp_path / "project"
    _repository(root)
    _git(root, "rm", "--cached", "data/users.json")
    _write(root, ".gitignore", "data/users.json\n")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "keep synthetic user file local")
    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "HEAD"))
    user_data = '{"local-owner":"preserve"}\n'
    (root / "data" / "users.json").write_text(user_data, encoding="utf-8")
    service, _ = _service(root)

    result = service.inspect()

    assert result["error"] is False
    assert result["preservable_local_data_paths"] == ["data/users.json"]
    assert (root / "data" / "users.json").read_text(encoding="utf-8") == user_data


def test_local_data_conflict_is_blocked_when_target_updates_protected_file(tmp_path):
    root = tmp_path / "project"
    base = _repository(root)
    target = _publish_remote_commit(root, base, edits={"data/users.json": '{"version":2}\n'})
    _write(root, "data/users.json", '{"owner":"local"}\n')
    service, _ = _service(root)

    result = service.inspect()

    assert result["target_revision"] == target
    assert result["error"] is True
    assert "BOT_UPDATE_LOCAL_DATA_OVERLAP" in _blocker_codes(result)
    assert "BOT_UPDATE_INCOMING_PROTECTED_DATA_CHANGE" in _blocker_codes(result)
    assert (root / "data" / "users.json").read_text(encoding="utf-8") == (
        '{"owner":"local"}\n'
    )


def test_ignored_local_runtime_file_blocks_incoming_tracked_overwrite(tmp_path):
    root = tmp_path / "project"
    _repository(root)
    _write(root, ".gitignore", "*.db\n")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "ignore local runtime databases")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", base)

    _write(root, "ozon_assistant.db", "incoming synthetic database\n")
    _git(root, "add", "-f", "ozon_assistant.db")
    _git(root, "commit", "-m", "track runtime database in incoming revision")
    target = _git(root, "rev-parse", "HEAD")
    _git(root, "reset", "--hard", base)
    _git(root, "update-ref", "refs/remotes/origin/main", target)
    local_data = "owner local database\n"
    _write(root, "ozon_assistant.db", local_data)
    service, _ = _service(root)

    result = service.inspect()

    assert result["target_revision"] == target
    assert result["error"] is True
    assert any(
        blocker.get("code") == "BOT_UPDATE_IGNORED_OVERWRITE_CONFLICT"
        and blocker.get("paths") == ["ozon_assistant.db"]
        for blocker in result["blockers"]
    )
    assert (root / "ozon_assistant.db").read_text(encoding="utf-8") == local_data


@pytest.mark.parametrize(
    ("ignore_rule", "remote_path", "local_path", "incoming_path"),
    [
        ("runtime.db\n", "runtime.db/marker.txt", "runtime.db", "runtime.db/marker.txt"),
        ("storage/\n", "storage", "storage/ozon_assistant.db", "storage"),
    ],
)
def test_ignored_path_ancestor_and_descendant_collisions_block_update(
    tmp_path, ignore_rule, remote_path, local_path, incoming_path
):
    root = tmp_path / "project"
    _repository(root)
    _write(root, ".gitignore", ignore_rule)
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "ignore local runtime data")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    target = _publish_remote_commit(
        root,
        base,
        edits={},
        additions=((remote_path, "incoming synthetic runtime path\n"),),
        force_additions=(remote_path,),
    )
    local_data = "owner local data\n"
    _write(root, local_path, local_data)
    service, _ = _service(root)

    result = service.inspect()

    assert result["target_revision"] == target
    assert result["error"] is True
    assert any(
        blocker.get("code") == "BOT_UPDATE_IGNORED_OVERWRITE_CONFLICT"
        and incoming_path in blocker.get("paths", [])
        for blocker in result["blockers"]
    )
    local_data_path = root / local_path
    if local_data_path.is_file():
        assert local_data_path.read_text(encoding="utf-8") == local_data
    else:
        assert (
            (local_data_path / "ozon_assistant.db").read_text(encoding="utf-8")
            == local_data
        )


@pytest.mark.parametrize(
    ("ignore_rule", "remote_path", "local_path"),
    [
        ("runtime.db\n", "runtime.db/marker.txt", "runtime.db"),
        ("storage/\n", "storage", "storage/ozon_assistant.db"),
    ],
)
def test_git_fast_forward_guard_preserves_ignored_path_shape_collisions(
    tmp_path, ignore_rule, remote_path, local_path
):
    root = tmp_path / "project"
    _repository(root)
    _write(root, ".gitignore", ignore_rule)
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "ignore local runtime data")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    target = _publish_remote_commit(
        root,
        base,
        edits={},
        additions=((remote_path, "incoming synthetic runtime path\n"),),
        force_additions=(remote_path,),
    )
    local_data = "owner local data\n"
    local_data_path = _write(root, local_path, local_data)

    result = subprocess.run(
        [
            "git", "-C", str(root), "merge", "--ff-only", "--no-edit",
            "--no-overwrite-ignore", target,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode != 0
    assert _git(root, "rev-parse", "HEAD") == base
    if local_data_path.is_file():
        assert local_data_path.read_text(encoding="utf-8") == local_data
    else:
        assert (
            (local_data_path / "ozon_assistant.db").read_text(encoding="utf-8")
            == local_data
        )


def test_non_overlapping_ignored_runtime_file_does_not_block_update(tmp_path):
    root = tmp_path / "project"
    base = _repository(root)
    _write(root, ".gitignore", "*.db\n")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "ignore local runtime databases")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    target = _publish_remote_commit(root, base, edits={"app.py": "value = 'updated'\n"})
    _write(root, "ozon_assistant.db", "owner local database\n")
    service, _ = _service(root)

    result = service.inspect()

    assert result["target_revision"] == target
    assert result["error"] is False
    assert (root / "ozon_assistant.db").read_text(encoding="utf-8") == (
        "owner local database\n"
    )


def test_dirty_code_and_untracked_target_overwrite_are_blocked(tmp_path):
    root = tmp_path / "project"
    base = _repository(root)
    _publish_remote_commit(
        root,
        base,
        edits={"app.py": "value = 'updated'\n"},
        additions=(("notes/generated.json", "{}\n"),),
    )
    _write(root, "app.py", "value = 'local edit'\n")
    _write(root, "notes/generated.json", '{"owner":"keep"}\n')
    service, _ = _service(root)

    result = service.inspect()

    assert result["error"] is True
    assert "BOT_UPDATE_LOCAL_CHANGES_UNSAFE" in _blocker_codes(result)
    assert "BOT_UPDATE_UNTRACKED_OVERWRITE_CONFLICT" in _blocker_codes(result)
    assert (root / "app.py").read_text(encoding="utf-8") == "value = 'local edit'\n"


def test_local_commits_ahead_of_cached_origin_are_blocked(tmp_path):
    root = tmp_path / "project"
    _repository(root)
    _write(root, "local.py", "local = True\n")
    _git(root, "add", "local.py")
    _git(root, "commit", "-m", "local commit")
    service, _ = _service(root)

    result = service.inspect()

    assert result["error"] is True
    assert "BOT_UPDATE_LOCAL_COMMITS_AHEAD" in _blocker_codes(result)


def test_wrong_branch_remote_and_upstream_are_blocked(tmp_path):
    root = tmp_path / "project"
    _repository(root)
    _git(root, "branch", "feature")
    _git(root, "update-ref", "refs/remotes/origin/feature", _git(root, "rev-parse", "HEAD"))
    _git(root, "branch", "--set-upstream-to=origin/feature", "feature")
    _git(root, "checkout", "feature")
    service, _ = _service(root)
    branch_result = service.inspect()
    assert "BOT_UPDATE_WRONG_BRANCH" in _blocker_codes(branch_result)
    assert "BOT_UPDATE_WRONG_UPSTREAM" in _blocker_codes(branch_result)

    _git(root, "checkout", "main")
    _git(root, "remote", "set-url", "origin", "https://example.invalid/untrusted.git")
    remote_service, _ = _service(root)
    remote_result = remote_service.inspect()
    assert "BOT_UPDATE_REMOTE_NOT_ALLOWED" in _blocker_codes(remote_result)


def test_wrong_repository_root_and_unknown_process_state_fail_closed(tmp_path):
    root = tmp_path / "project"
    _repository(root)
    nested = root / "nested"
    nested.mkdir()
    wrong_root_service, _ = _service(nested)
    root_result = wrong_root_service.inspect()
    assert "BOT_UPDATE_WRONG_REPOSITORY_ROOT" in _blocker_codes(root_result)

    unknown_service, _ = _service(root, state="UNKNOWN")
    process_result = unknown_service.inspect()
    assert "BOT_UPDATE_PROCESS_STATE_UNKNOWN" in _blocker_codes(process_result)


def test_running_instance_from_another_or_unidentified_checkout_is_never_stopped(tmp_path):
    root = tmp_path / "project"
    _repository(root)
    other_checkout = tmp_path / "other-project"
    other_checkout.mkdir()

    other_service, _other_calls = _service(
        root,
        state="RUNNING",
    )
    other_service.process_inspector = lambda _token: {
        "state": "RUNNING",
        "revision": "a" * 40,
        "project_root_fingerprint": project_root_fingerprint(other_checkout),
    }
    other_result = other_service.inspect()

    old_service, _ = _service(root, state="RUNNING")
    old_service.process_inspector = lambda _token: {
        "state": "RUNNING",
        "revision": "a" * 40,
    }
    old_result = old_service.inspect()

    assert "BOT_UPDATE_PROCESS_OTHER_CHECKOUT" in _blocker_codes(other_result)
    assert "BOT_UPDATE_PROCESS_CHECKOUT_UNKNOWN" in _blocker_codes(old_result)
    assert other_result["process_checkout_matches"] is False
    assert other_result["lifecycle_mutations"] == 0


def test_cli_refuses_update_without_check_only_and_reports_json_plan(monkeypatch, tmp_path, capsys):
    root = tmp_path / "project"
    _repository(root)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-token")

    exit_code = update_cli_main([
        "check", "--check-only", "--project-root", str(root)
    ])
    output = capsys.readouterr().out
    result = json.loads(output.splitlines()[-1])

    assert exit_code == 0
    assert result["already_current"] is True
    assert result["cached_remote_ref_may_be_stale"] is True
    assert result["process_state"] == "STOPPED"
    assert result["read_only"] is True
    assert "synthetic-token" not in output
    assert REMOTE_URL not in output
