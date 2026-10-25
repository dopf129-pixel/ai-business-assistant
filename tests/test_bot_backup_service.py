import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import zipfile

from services.expense_repository import ExpenseRepository
from services.bot_backup_service import BotBackupService
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
    return BotBackupService(
        project_root=project,
        storage_root=storage or project,
        backup_directory=project / ".local-backups",
        lifecycle_token="synthetic-token",
        lifecycle_inspector=lambda _token: {"state": "STOPPED"},
        revision_reader=lambda _root: "abc1234",
        **kwargs,
    )


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
    target = tmp_path / "cli-target"

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
