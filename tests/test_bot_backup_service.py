import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import time
import zipfile

import pytest

from services.expense_repository import ExpenseRepository
from services.action_storage_service import ActionStorageService
from services.conversation_history_storage_service import ConversationHistoryStorageService
from services.store_report_storage_service import StoreReportStorageService
from services.bot_backup_service import BotBackupService
from services.bot_backup_service import _BackupFailure
from services.bot_instance_lifecycle_service import (
    BotInstanceLease,
    BotLifecycleError,
    BotStartupMaintenanceGuard,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from bot_backup import main as backup_cli_main


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _write_database(path, table_name):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"CREATE TABLE {table_name} (value TEXT NOT NULL)")
        connection.execute(f"INSERT INTO {table_name} VALUES (?)", ("synthetic",))
        connection.commit()
    finally:
        connection.close()


def _service(project, storage, **kwargs):
    lifecycle_state_root = kwargs.pop(
        "lifecycle_state_root", project / ".synthetic-lifecycle"
    )
    return BotBackupService(
        project_root=project,
        storage_root=storage or project,
        backup_directory=project / ".local-backups",
        lifecycle_token="synthetic-token",
        lifecycle_inspector=lambda _token: {"state": "STOPPED"},
        lifecycle_state_root=lifecycle_state_root,
        revision_reader=lambda _root: "abc1234",
        **kwargs,
    )


def test_backup_accepts_list_json_written_by_supported_app_storages(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    sample_values = {
        "actions.json": [{"id": "synthetic-action"}],
        "conversation_history.json": [{"role": "user", "content": "synthetic"}],
        "store_reports.json": [{"period": "2026-10", "total": 12}],
    }
    ActionStorageService(project / "actions.json").save(sample_values["actions.json"])
    ConversationHistoryStorageService(project / "conversation_history.json").save(
        sample_values["conversation_history.json"]
    )
    StoreReportStorageService(project / "store_reports.json").save(
        sample_values["store_reports.json"]
    )
    service = _service(project, None)

    result = service.backup()

    assert result["error"] is False, result
    assert service.verify_archive(result["backup_path"])["status"] == (
        "BOT_BACKUP_ARCHIVE_VERIFIED"
    )
    target = tmp_path / "restored-lists"
    plan = service.restore_archive(result["backup_path"], target, dry_run=True)
    assert plan["status"] == "BOT_RESTORE_PLAN_READY", plan
    restored = service.restore_archive(result["backup_path"], target)
    assert restored["status"] == "BOT_RESTORE_COMPLETE", restored
    for filename, expected in sample_values.items():
        actual = json.loads(
            (target / "project" / filename).read_text(encoding="utf-8")
        )
        assert actual == expected


def test_sqlite_snapshot_terminates_when_source_remains_exclusively_locked(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    database = project / "ozon_assistant.db"
    _write_database(database, "synthetic")
    service = _service(
        project,
        None,
        sqlite_backup_timeout_seconds=0.25,
    )
    lock = sqlite3.connect(database, timeout=0.1)
    lock.execute("BEGIN EXCLUSIVE")
    lock.execute("INSERT INTO synthetic VALUES (?)", ("locked",))

    started = time.monotonic()
    try:
        with pytest.raises(_BackupFailure) as error:
            service._snapshot_sqlite(database)
        elapsed = time.monotonic() - started
    finally:
        lock.rollback()
        lock.close()

    assert error.value.code == "BOT_BACKUP_SQLITE_TIMEOUT"
    assert elapsed < 3.0


def test_sqlite_backup_uses_bounded_worker_and_preserves_valid_database(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    database = project / "ozon_assistant.db"
    _write_database(database, "synthetic")
    service = _service(project, None, sqlite_backup_timeout_seconds=5)

    payload, metadata = service._snapshot_sqlite(database)

    assert metadata == {"integrity_check": "ok", "user_version": 0, "table_count": 1}
    assert payload


def test_backup_holds_startup_guard_for_the_entire_snapshot(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    first = project / "assistant_memory.json"
    second = project / "assistant_session.json"
    _write_json(first, {"generation": 0})
    _write_json(second, {"generation": 0})
    lifecycle_state_root = tmp_path / "lifecycle"
    service = _service(
        project, None, lifecycle_state_root=lifecycle_state_root
    )
    original_read = service._read_candidate
    startup_codes = []

    def try_start_during_snapshot(path):
        result = original_read(path)
        if path == first:
            lease = BotInstanceLease(
                "synthetic-token", state_root=lifecycle_state_root
            )
            try:
                lease.acquire()
            except BotLifecycleError as error:
                startup_codes.append(error.code)
            else:
                lease.close()
                pytest.fail("bot startup escaped the backup guard")
        return result

    monkeypatch.setattr(service, "_read_candidate", try_start_during_snapshot)

    result = service.backup()

    assert result["error"] is False, result
    assert startup_codes == ["BOT_INSTANCE_MAINTENANCE_ACTIVE"]
    with zipfile.ZipFile(result["backup_path"]) as archive:
        assert json.loads(archive.read("files/project/assistant_memory.json")) == {
            "generation": 0
        }
        assert json.loads(archive.read("files/project/assistant_session.json")) == {
            "generation": 0
        }


def test_backup_reuses_update_guard_without_releasing_callers_lock(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "data" / "users.json", {"owner": "synthetic"})
    state_root = tmp_path / "lifecycle"
    service = _service(project, None, lifecycle_state_root=state_root)
    guard = service.startup_guard_factory("synthetic-token")
    assert guard.acquire() is True

    try:
        result = service.backup_under_guard(guard)
        assert result["error"] is False, result
        assert service.verify_archive(result["backup_path"])["error"] is False
        assert guard.is_acquired is True
    finally:
        guard.close()

    lease = BotInstanceLease("synthetic-token", state_root=state_root)
    lease.acquire()
    lease.close()


def test_backup_refuses_to_start_while_bot_startup_owns_guard(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "assistant_memory.json", {"safe": True})
    state_root = tmp_path / "lifecycle"
    guard = BotStartupMaintenanceGuard("synthetic-token", state_root=state_root)
    assert guard.acquire() is True
    service = _service(project, None, lifecycle_state_root=state_root)

    try:
        result = service.backup()
    finally:
        guard.close()

    assert result["code"] == "BOT_BACKUP_STARTUP_BUSY"
    assert not (project / ".local-backups").exists()


@pytest.mark.parametrize("storage_layout", ["project", "nested-storage", "separate-storage"])
def test_custom_mapping_override_backup_dry_run_and_restore_are_consistent(
    monkeypatch, tmp_path, storage_layout
):
    project = tmp_path / "project"
    project.mkdir()
    if storage_layout == "project":
        storage = project
        mapping = project / "data" / "custom_mapping.json"
        expected_root = "project"
    elif storage_layout == "nested-storage":
        storage = project / ".runtime-data"
        storage.mkdir()
        mapping = storage / "nested" / "custom_mapping.json"
        expected_root = "storage"
    else:
        storage = tmp_path / "approved-storage"
        storage.mkdir()
        mapping = storage / "data" / "custom_mapping.json"
        expected_root = "storage"
    _write_json(mapping, {"mapping": "synthetic"})
    monkeypatch.setenv("PERIOD_PROFIT_MAPPING_REGISTRY_PATH", str(mapping))
    service = _service(project, storage)

    backup = service.backup()

    assert backup["error"] is False, backup
    with zipfile.ZipFile(backup["backup_path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    override = manifest["mapping_registry_override"]
    assert override == {
        "root": expected_root,
        "path": mapping.relative_to(storage if expected_root == "storage" else project).as_posix(),
    }
    assert service.verify_archive(backup["backup_path"])["status"] == (
        "BOT_BACKUP_ARCHIVE_VERIFIED"
    )
    target = tmp_path / f"restored-{storage_layout}"
    plan = service.restore_archive(backup["backup_path"], target, dry_run=True)
    assert plan["status"] == "BOT_RESTORE_PLAN_READY", plan
    restored = service.restore_archive(backup["backup_path"], target)
    assert restored["status"] == "BOT_RESTORE_COMPLETE", restored
    restored_file = target / expected_root / Path(*override["path"].split("/"))
    assert json.loads(restored_file.read_text(encoding="utf-8")) == {
        "mapping": "synthetic"
    }


def test_backup_archives_supported_roots_and_verifies_without_including_secrets(tmp_path):
    project = tmp_path / "проект с пробелами"
    storage = tmp_path / "private storage"
    project.mkdir()
    storage.mkdir()
    _write_json(project / "data" / "users.json", {"synthetic-user": {"active": True}})
    _write_json(project / "data" / "tasks.json", {"synthetic-task": {"status": "OPEN"}})
    _write_json(storage / "data" / "tax_configuration.json", {"rate": 0.06})
    tenant_id = "0123456789abcdef01234567"
    _write_json(
        storage / "data" / "tenants" / tenant_id / "product_decision_history.json",
        [],
    )
    _write_database(project / "ozon_assistant.db", "legacy_costs")
    _write_database(storage / "ozon_assistant.db", "encrypted_accounts")
    _write_database(
        storage / "data" / "tenants" / tenant_id / "ozon_assistant.db",
        "seller_costs",
    )
    (project / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=synthetic-secret\nOZON_CREDENTIAL_MASTER_KEY=synthetic-key\n",
        encoding="utf-8",
    )
    (storage / "seller.log").write_text("diagnostic content", encoding="utf-8")
    original_json = (project / "data" / "users.json").read_bytes()
    original_db = (project / "ozon_assistant.db").read_bytes()

    service = _service(project, storage)
    result = service.backup()

    assert result["error"] is False, result
    assert result["status"] == "BOT_BACKUP_READY"
    assert result["application_revision"] == "abc1234"
    assert (project / "data" / "users.json").read_bytes() == original_json
    assert (project / "ozon_assistant.db").read_bytes() == original_db
    assert service.verify_archive(result["backup_path"])["status"] == "BOT_BACKUP_ARCHIVE_VERIFIED"

    with zipfile.ZipFile(result["backup_path"]) as archive:
        names = set(archive.namelist())
        manifest_bytes = archive.read("manifest.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        assert "files/project/data/users.json" in names
        assert "files/storage/data/tenants/0123456789abcdef01234567/ozon_assistant.db" in names
        assert "files/storage/data/tax_configuration.json" in names
        assert ".env" not in "\n".join(names)
        assert "seller.log" not in "\n".join(names)
        assert "synthetic-secret" not in manifest_bytes.decode("utf-8")
        assert "synthetic-key" not in manifest_bytes.decode("utf-8")
        assert all(
            name.startswith("files/") or name in {"manifest.json", "COMPLETED.json"}
            for name in names
        )
        assert hashlib.sha256(manifest_bytes).hexdigest() == json.loads(
            archive.read("COMPLETED.json").decode("utf-8")
        )["manifest_sha256"]
        assert all(
            "absolute_path" not in entry
            and ".." not in entry["path"].split("/")
            for entry in manifest["entries"]
        )


def test_backup_fails_closed_when_bot_is_running_without_creating_output(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "data" / "users.json", {})
    service = BotBackupService(
        project_root=project,
        lifecycle_token="synthetic-token",
        lifecycle_inspector=lambda _token: {"state": "RUNNING"},
    )

    result = service.backup()

    assert result["code"] == "BOT_BACKUP_BOT_NOT_STOPPED"
    assert not (project / ".local-backups").exists()
    assert (project / "data" / "users.json").read_text(encoding="utf-8") == "{}"


def test_backup_rejects_invalid_json_and_does_not_publish_partial_archive(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    broken = project / "data" / "tasks.json"
    broken.parent.mkdir()
    broken.write_text("{bad json", encoding="utf-8")
    service = _service(project, None)

    result = service.backup()

    assert result["code"] == "BOT_BACKUP_JSON_INVALID"
    backup_directory = project / ".local-backups"
    assert not list(backup_directory.glob("*.zip"))
    assert broken.read_text(encoding="utf-8") == "{bad json"


def test_backup_rejects_external_mapping_override_before_writing(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "outside" / "mapping.json"
    _write_json(external, {})
    monkeypatch.setenv("PERIOD_PROFIT_MAPPING_REGISTRY_PATH", str(external))

    result = _service(project, None).backup()

    assert result["code"] == "BOT_BACKUP_EXTERNAL_STATE_UNSUPPORTED"
    assert not (project / ".local-backups").exists()


def test_backup_rejects_corrupt_sqlite_without_publishing_archive(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    database = project / "ozon_assistant.db"
    database.write_bytes(b"not a sqlite database")

    result = _service(project, None).backup()

    assert result["code"] == "BOT_BACKUP_SQLITE_INVALID"
    assert not list((project / ".local-backups").glob("*.zip"))
    assert database.read_bytes() == b"not a sqlite database"


def test_backup_removes_interrupted_partial_and_preserves_previous_archive(
    monkeypatch, tmp_path
):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "data" / "users.json", {"synthetic": True})
    service = _service(project, None)
    first = service.backup()
    assert first["error"] is False, first
    previous_archive = (project / ".local-backups" / Path(first["backup_path"]).name)
    previous_contents = previous_archive.read_bytes()

    def fail_replace(*_args, **_kwargs):
        raise OSError("synthetic interrupted publication")

    monkeypatch.setattr("services.bot_backup_service.os.replace", fail_replace)
    second = service.backup()

    assert second["error"] is True
    assert previous_archive.read_bytes() == previous_contents
    assert len(list((project / ".local-backups").glob("*.zip"))) == 1
    assert not list((project / ".local-backups").glob("*.partial"))


def test_archive_verification_rejects_unlisted_member(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "data" / "users.json", {})
    service = _service(project, None)
    result = service.backup()
    assert result["error"] is False, result
    archive_path = Path(result["backup_path"])

    with zipfile.ZipFile(archive_path, mode="a") as archive:
        archive.writestr("files/project/extra.json", b"{}")

    verification = service.verify_archive(archive_path)

    assert verification["code"] == "BOT_BACKUP_ARCHIVE_UNEXPECTED_ENTRY"


def test_restore_dry_run_and_publish_preserve_tenant_data_and_repository_values(
    monkeypatch, tmp_path
):
    project = tmp_path / "project"
    storage = tmp_path / "storage"
    project.mkdir()
    storage.mkdir()
    _write_json(project / "data" / "users.json", {"owner": {"status": "active"}})
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(storage))
    owners_and_amounts = (("synthetic-owner-a", 12.34), ("synthetic-owner-b", 56.78))
    expected_by_owner = {}
    for owner_id, amount in owners_and_amounts:
        context_token = set_current_tenant_user_id(owner_id)
        try:
            added = ExpenseRepository().add_expense(
                "2026-10-20", "advertising", amount, "synthetic record"
            )
            assert added["error"] is False
            expected_by_owner[owner_id] = {
                "expense_date": "2026-10-20",
                "category": "advertising",
                "amount": amount,
                "description": "synthetic record",
            }
        finally:
            reset_current_tenant_user_id(context_token)
    service = _service(project, storage)
    backup_result = service.backup()
    assert backup_result["error"] is False, backup_result
    target = tmp_path / "restored account"

    plan = service.restore_archive(backup_result["backup_path"], target, dry_run=True)

    assert plan["status"] == "BOT_RESTORE_PLAN_READY"
    assert plan["read_only"] is True
    assert not target.exists()

    restored = service.restore_archive(backup_result["backup_path"], target)

    assert restored["status"] == "BOT_RESTORE_COMPLETE"
    assert restored["file_count"] == backup_result["file_count"]
    assert json.loads((target / "project" / "data" / "users.json").read_text(encoding="utf-8")) == {
        "owner": {"status": "active"}
    }
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(target / "storage"))
    for owner_id, _amount in owners_and_amounts:
        context_token = set_current_tenant_user_id(owner_id)
        try:
            rows = ExpenseRepository().get_expenses_by_period("2026-10-20", "2026-10-20")
        finally:
            reset_current_tenant_user_id(context_token)
        assert len(rows) == 1
        assert {key: rows[0][key] for key in expected_by_owner[owner_id]} == (
            expected_by_owner[owner_id]
        )
    assert expected_by_owner[owners_and_amounts[0][0]]["amount"] != (
        expected_by_owner[owners_and_amounts[1][0]]["amount"]
    )
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(storage))
    for owner_id, _amount in owners_and_amounts:
        context_token = set_current_tenant_user_id(owner_id)
        try:
            original_rows = ExpenseRepository().get_expenses_by_period(
                "2026-10-20", "2026-10-20"
            )
        finally:
            reset_current_tenant_user_id(context_token)
        assert len(original_rows) == 1
        assert {key: original_rows[0][key] for key in expected_by_owner[owner_id]} == (
            expected_by_owner[owner_id]
        )
    marker = json.loads((target / "RESTORED.json").read_text(encoding="utf-8"))
    assert marker["status"] == "COMPLETE"
    assert "MASTER_KEY_REQUIRED" in marker["credential_key_note"]
    assert (project / "data" / "users.json").read_text(encoding="utf-8") == (
        '{"owner": {"status": "active"}}'
    )


def test_restore_rejects_existing_or_live_overlapping_target_without_changes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "data" / "users.json", {})
    service = _service(project, None)
    backup_result = service.backup()
    assert backup_result["error"] is False, backup_result
    existing = tmp_path / "existing-empty"
    existing.mkdir()

    existing_result = service.restore_archive(backup_result["backup_path"], existing)
    overlapping_result = service.restore_archive(
        backup_result["backup_path"], project / "restored-inside-live-root"
    )

    assert existing_result["code"] == "BOT_RESTORE_TARGET_NOT_NEW"
    assert overlapping_result["code"] == "BOT_RESTORE_TARGET_OVERLAPS_LIVE_ROOT"
    assert list(existing.iterdir()) == []
    assert not (project / "restored-inside-live-root").exists()


def test_restore_failure_removes_staging_and_never_publishes_target(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "data" / "users.json", {})
    service = _service(project, None)
    backup_result = service.backup()
    assert backup_result["error"] is False, backup_result
    target = tmp_path / "restore-fails"
    writes = 0
    original_writer = BotBackupService._write_new_file

    def fail_on_second_write(path, payload):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("synthetic staging disk failure")
        original_writer(path, payload)

    monkeypatch.setattr(
        BotBackupService,
        "_write_new_file",
        staticmethod(fail_on_second_write),
    )

    result = service.restore_archive(backup_result["backup_path"], target)

    assert result["error"] is True
    assert not target.exists()
    assert not list(tmp_path.glob(".restore-fails.restore-*.partial"))
    assert service.verify_archive(backup_result["backup_path"])["error"] is False


def test_archive_verification_rejects_path_traversal_symlink_and_duplicate_windows_paths(
    tmp_path,
):
    project = tmp_path / "project"
    project.mkdir()
    service = _service(project, None)
    path_archive = tmp_path / "path-traversal.zip"
    with zipfile.ZipFile(path_archive, "w") as archive:
        archive.writestr("../outside.json", b"{}")
    symlink_archive = tmp_path / "symlink.zip"
    symlink_info = zipfile.ZipInfo("files/project/data/users.json")
    symlink_info.create_system = 3
    symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink_archive, "w") as archive:
        archive.writestr(symlink_info, "outside.json")
    duplicate_archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(duplicate_archive, "w") as archive:
        archive.writestr("files/project/data/users.json", b"{}")
        archive.writestr("FILES/PROJECT/DATA/USERS.JSON", b"{}")

    assert service.verify_archive(path_archive)["code"] == "BOT_BACKUP_ARCHIVE_PATH_INVALID"
    assert service.verify_archive(symlink_archive)["code"] == "BOT_BACKUP_ARCHIVE_LINK_UNSUPPORTED"
    assert service.verify_archive(duplicate_archive)["code"] == "BOT_BACKUP_ARCHIVE_ENTRY_COUNT_INVALID"


def test_archive_verification_rejects_expansion_over_configured_limit(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    service = _service(project, None)
    service.MAX_FILE_BYTES = 4
    archive_path = tmp_path / "oversized.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("files/project/data/users.json", b"12345")

    result = service.verify_archive(archive_path)

    assert result["code"] == "BOT_BACKUP_FILE_SIZE_LIMIT"


def test_restore_cli_check_only_verifies_and_does_not_create_target(monkeypatch, tmp_path, capsys):
    project = tmp_path / "project"
    project.mkdir()
    _write_json(project / "data" / "users.json", {})
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(project))
    service = _service(project, None)
    backup_result = service.backup()
    assert backup_result["error"] is False, backup_result
    # The runbook normalizes its parent-relative sibling path before passing it
    # to the restore CLI; raw '..' segments are intentionally rejected.
    target = (project / ".." / "restore-drill").resolve()
    runbook = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "daily-use-recovery-runbook.md"
    ).read_text(encoding="utf-8")
    assert (
        "[System.IO.Path]::GetFullPath((Join-Path (Get-Location) '..\\restore-drill'))"
        in runbook
    )

    exit_code = backup_cli_main([
        "restore",
        backup_result["backup_path"],
        "--target-directory",
        str(target),
        "--dry-run",
        "--project-root",
        str(project),
    ])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "BOT_RESTORE_PLAN_READY"
    assert output["executed"] is False
    assert not target.exists()
