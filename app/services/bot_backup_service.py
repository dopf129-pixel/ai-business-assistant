"""Create and verify local backups of the application's durable seller data."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import uuid
import zipfile


class BotBackupService:
    FORMAT = "ai-assistant-backup"
    SCHEMA_VERSION = 1
    COMPLETE_FORMAT = "ai-assistant-backup-complete"
    MAX_FILES = 5000
    MAX_FILE_BYTES = 512 * 1024 * 1024
    MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
    MAX_MANIFEST_BYTES = 4 * 1024 * 1024
    MAX_JSON_BYTES = 32 * 1024 * 1024
    TENANT_DIRECTORY_RE = re.compile(r"^[0-9a-f]{24}$")
    SQLITE_NAME = "ozon_assistant.db"

    ROOT_JSON_FILES = (
        "actions.json",
        "assistant_memory.json",
        "assistant_session.json",
        "assistant_user_memory.json",
        "conversation_history.json",
        "store_reports.json",
    )
    PROJECT_DATA_JSON_FILES = (
        "users.json",
        "tasks.json",
        "profiles.json",
        "period_profit_mapping_registry.json",
        "tax_configuration.json",
        "product_decision_history.json",
        "product_action_task_drafts.json",
        "product_decision_user_action_completion.json",
    )
    LIST_JSON_FILES = {
        "product_decision_history.json",
        "product_action_task_drafts.json",
        "product_decision_user_action_completion.json",
    }

    def __init__(
        self,
        project_root,
        storage_root=None,
        backup_directory=None,
        lifecycle_token=None,
        lifecycle_inspector=None,
        revision_reader=None,
        now_provider=None,
    ):
        self.project_root = Path(project_root).resolve(strict=True)
        configured_root = storage_root
        if configured_root is None:
            configured_root = os.getenv("AI_ASSISTANT_STORAGE_ROOT") or None
        if configured_root:
            storage_candidate = Path(configured_root)
            if not storage_candidate.is_absolute():
                storage_candidate = self.project_root / storage_candidate
            self.storage_root = storage_candidate.resolve(strict=False)
        else:
            self.storage_root = self.project_root
        self.backup_directory = Path(backup_directory) if backup_directory else (
            self.project_root / ".local-backups"
        )
        if not self.backup_directory.is_absolute():
            self.backup_directory = self.project_root / self.backup_directory
        self.lifecycle_token = str(lifecycle_token or "").strip()
        if lifecycle_inspector is None:
            from services.bot_instance_lifecycle_service import inspect_bot_instance

            lifecycle_inspector = inspect_bot_instance
        self.lifecycle_inspector = lifecycle_inspector
        self.revision_reader = revision_reader or self._read_revision
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def backup(self):
        """Write a verified archive only when the token-bound bot is stopped."""
        try:
            lifecycle = self._lifecycle_status()
            if lifecycle.get("state") != "STOPPED":
                return self._error("BOT_BACKUP_BOT_NOT_STOPPED")

            roots = self._approved_roots()
            candidates = self._discover_files(roots)
            if not candidates:
                return self._error("BOT_BACKUP_NO_SUPPORTED_DATA")
            if len(candidates) > self.MAX_FILES:
                return self._error("BOT_BACKUP_FILE_COUNT_LIMIT")

            backup_directory = self._validate_backup_directory(roots, candidates)
            backup_directory.mkdir(parents=True, exist_ok=True)
            now = self.now_provider()
            if not isinstance(now, datetime) or now.tzinfo is None:
                return self._error("BOT_BACKUP_CLOCK_INVALID")
            timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            final_path = backup_directory / (
                "ai-assistant-backup-" + timestamp + "-" + uuid.uuid4().hex[:12] + ".zip"
            )
            partial_path = backup_directory / ("." + final_path.name + ".partial")

            manifest_entries = []
            total_bytes = 0
            with zipfile.ZipFile(
                partial_path,
                mode="x",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as archive:
                for root_name, root_path, relative_path, source_path in candidates:
                    payload, metadata = self._read_candidate(source_path)
                    total_bytes += len(payload)
                    if len(payload) > self.MAX_FILE_BYTES:
                        raise _BackupFailure("BOT_BACKUP_FILE_SIZE_LIMIT")
                    if total_bytes > self.MAX_TOTAL_BYTES:
                        raise _BackupFailure("BOT_BACKUP_TOTAL_SIZE_LIMIT")
                    archive_name = "files/" + root_name + "/" + relative_path.as_posix()
                    archive.writestr(archive_name, payload)
                    manifest_entries.append({
                        "root": root_name,
                        "path": relative_path.as_posix(),
                        "size_bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "format": metadata["format"],
                        "metadata": metadata["metadata"],
                    })

                manifest = {
                    "format": self.FORMAT,
                    "schema_version": self.SCHEMA_VERSION,
                    "created_at_utc": now.astimezone(timezone.utc).isoformat(),
                    "application_revision": self._safe_revision(),
                    "roots": [root_name for root_name, _ in roots],
                    "file_count": len(manifest_entries),
                    "total_size_bytes": total_bytes,
                    "entries": manifest_entries,
                }
                manifest_bytes = self._canonical_json(manifest)
                if len(manifest_bytes) > self.MAX_MANIFEST_BYTES:
                    raise _BackupFailure("BOT_BACKUP_MANIFEST_SIZE_LIMIT")
                archive.writestr("manifest.json", manifest_bytes)

            verified = self._verify_archive(partial_path, require_complete=False)
            if verified.get("error") is True:
                raise _BackupFailure(verified.get("code", "BOT_BACKUP_VERIFY_FAILED"))

            completion = {
                "format": self.COMPLETE_FORMAT,
                "status": "COMPLETE",
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "file_count": len(manifest_entries),
            }
            with zipfile.ZipFile(partial_path, mode="a", allowZip64=True) as archive:
                archive.writestr("COMPLETED.json", self._canonical_json(completion))

            verified = self._verify_archive(partial_path, require_complete=True)
            if verified.get("error") is True:
                raise _BackupFailure(verified.get("code", "BOT_BACKUP_VERIFY_FAILED"))
            with partial_path.open("r+b") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            if final_path.exists():
                raise _BackupFailure("BOT_BACKUP_OUTPUT_ALREADY_EXISTS")
            os.replace(partial_path, final_path)
            return {
                "error": False,
                "status": "BOT_BACKUP_READY",
                "backup_path": str(final_path),
                "file_count": len(manifest_entries),
                "total_size_bytes": total_bytes,
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "application_revision": manifest["application_revision"],
                "read_only": True,
                "executed": False,
            }
        except _BackupFailure as error:
            self._remove_partial(locals().get("partial_path"))
            return self._error(error.code)
        except Exception:
            self._remove_partial(locals().get("partial_path"))
            return self._error("BOT_BACKUP_FAILED")

    def verify_archive(self, archive_path):
        """Verify a completed archive without extracting or writing its contents."""
        return self._verify_archive(Path(archive_path), require_complete=True)

    def restore_archive(self, archive_path, target_directory, dry_run=False):
        """Restore a verified backup under a new project/storage root."""
        staging = None
        try:
            archive_path = Path(archive_path).resolve(strict=True)
            if not archive_path.is_file() or self._is_reparse_point(archive_path):
                raise _BackupFailure("BOT_RESTORE_ARCHIVE_INVALID")
            verified = self.verify_archive(archive_path)
            if verified.get("error") is True:
                return verified

            target = self._validate_restore_target(target_directory)
            for _, source_root in self._approved_roots():
                if (
                    self._is_relative_to(target, source_root)
                    or self._is_relative_to(source_root, target)
                ):
                    raise _BackupFailure("BOT_RESTORE_TARGET_OVERLAPS_LIVE_ROOT")

            credential_key_note = (
                "ORIGINAL_OZON_CREDENTIAL_MASTER_KEY_REQUIRED_IF_ENCRYPTED_CREDENTIALS_ARE_PRESENT"
            )
            if dry_run:
                return {
                    "error": False,
                    "status": "BOT_RESTORE_PLAN_READY",
                    "file_count": verified["file_count"],
                    "total_size_bytes": verified["total_size_bytes"],
                    "manifest_sha256": verified["manifest_sha256"],
                    "layout": "target/project and target/storage",
                    "target_path": str(target),
                    "credential_key_note": credential_key_note,
                    "read_only": True,
                    "executed": False,
                }

            staging = target.parent / (
                "." + target.name + ".restore-" + uuid.uuid4().hex + ".partial"
            )
            staging.mkdir(mode=0o700)
            with zipfile.ZipFile(archive_path, mode="r") as archive:
                manifest_bytes = archive.read("manifest.json")
                manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
                if manifest_digest != verified["manifest_sha256"]:
                    raise _BackupFailure("BOT_RESTORE_ARCHIVE_CHANGED")
                manifest = json.loads(manifest_bytes.decode("utf-8"))
                for entry in manifest["entries"]:
                    root_name = entry["root"]
                    relative_path = Path(*entry["path"].split("/"))
                    if not self._restore_path_allowed(root_name, relative_path):
                        raise _BackupFailure("BOT_RESTORE_PATH_UNSUPPORTED")
                    archive_name = "files/" + root_name + "/" + entry["path"]
                    payload = archive.read(archive_name)
                    if (
                        len(payload) != entry["size_bytes"]
                        or hashlib.sha256(payload).hexdigest() != entry["sha256"]
                    ):
                        raise _BackupFailure("BOT_RESTORE_CHECKSUM_FAILED")
                    content_error = self._validate_archive_payload(entry, payload)
                    if content_error:
                        raise _BackupFailure(content_error)
                    output_path = staging / root_name / relative_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    self._write_new_file(output_path, payload)

                marker = {
                    "format": "ai-assistant-restore-complete",
                    "status": "COMPLETE",
                    "manifest_sha256": manifest_digest,
                    "file_count": verified["file_count"],
                    "credential_key_note": credential_key_note,
                }
                self._write_new_file(staging / "RESTORED.json", self._canonical_json(marker))

            if target.exists() or self._is_reparse_point(target):
                raise _BackupFailure("BOT_RESTORE_TARGET_NOT_NEW")
            os.rename(staging, target)
            staging = None
            return {
                "error": False,
                "status": "BOT_RESTORE_COMPLETE",
                "file_count": verified["file_count"],
                "total_size_bytes": verified["total_size_bytes"],
                "manifest_sha256": manifest_digest,
                "layout": "target/project and target/storage",
                "target_path": str(target),
                "credential_key_note": credential_key_note,
                "read_only": False,
                "executed": True,
            }
        except _BackupFailure as error:
            self._remove_staging(staging)
            return self._error(error.code)
        except Exception:
            self._remove_staging(staging)
            return self._error("BOT_RESTORE_FAILED")

    def _validate_restore_target(self, target_directory):
        raw_target = Path(target_directory)
        if not raw_target.is_absolute():
            raw_target = Path.cwd() / raw_target
        if ".." in raw_target.parts or not raw_target.name or raw_target.name in {".", ".."}:
            raise _BackupFailure("BOT_RESTORE_TARGET_INVALID")
        if raw_target.exists() or self._is_reparse_point(raw_target):
            raise _BackupFailure("BOT_RESTORE_TARGET_NOT_NEW")
        raw_parent = raw_target.parent
        if not raw_parent.is_dir():
            raise _BackupFailure("BOT_RESTORE_PARENT_UNAVAILABLE")
        for ancestor in reversed((raw_parent, *raw_parent.parents)):
            if self._is_reparse_point(ancestor):
                raise _BackupFailure("BOT_RESTORE_TARGET_REPARSE_POINT")
        try:
            parent = raw_parent.resolve(strict=True)
        except OSError as error:
            raise _BackupFailure("BOT_RESTORE_PARENT_UNAVAILABLE") from error
        return parent / raw_target.name

    def _restore_path_allowed(self, root_name, relative_path):
        parts = relative_path.parts
        if root_name not in {"project", "storage"} or relative_path.is_absolute() or ".." in parts or not parts:
            return False
        if len(parts) == 1:
            return parts[0] == self.SQLITE_NAME or parts[0] in self.ROOT_JSON_FILES
        if len(parts) == 2 and parts[0] == "data":
            return (
                parts[1] in self.PROJECT_DATA_JSON_FILES
                or parts[1].lower() == "period_profit_mapping_registry.json"
            )
        if len(parts) == 4 and parts[:2] == ("data", "tenants"):
            return bool(
                self.TENANT_DIRECTORY_RE.fullmatch(parts[2])
                and (parts[3] == self.SQLITE_NAME or parts[3].lower().endswith(".json"))
            )
        return False

    @staticmethod
    def _write_new_file(path, payload):
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _remove_staging(path):
        if path is None:
            return
        candidate = Path(path)
        if ".restore-" not in candidate.name or not candidate.name.endswith(".partial"):
            return
        try:
            if candidate.is_dir() and not BotBackupService._is_reparse_point(candidate):
                shutil.rmtree(candidate)
        except OSError:
            pass

    def _lifecycle_status(self):
        if not self.lifecycle_token:
            raise _BackupFailure("BOT_BACKUP_LIFECYCLE_UNAVAILABLE")
        try:
            result = self.lifecycle_inspector(self.lifecycle_token)
        except Exception as error:
            raise _BackupFailure("BOT_BACKUP_LIFECYCLE_UNAVAILABLE") from error
        if not isinstance(result, dict) or not isinstance(result.get("state"), str):
            raise _BackupFailure("BOT_BACKUP_LIFECYCLE_UNAVAILABLE")
        return result

    def _approved_roots(self):
        if not self.project_root.is_dir() or self._is_reparse_point(self.project_root):
            raise _BackupFailure("BOT_BACKUP_PROJECT_ROOT_INVALID")
        if self.storage_root != self.project_root:
            try:
                self.storage_root.relative_to(self.project_root)
            except ValueError:
                try:
                    self.project_root.relative_to(self.storage_root)
                except ValueError:
                    pass
                else:
                    raise _BackupFailure("BOT_BACKUP_STORAGE_ROOT_SCOPE_UNSUPPORTED")
            if self._is_reparse_point(self.storage_root):
                raise _BackupFailure("BOT_BACKUP_STORAGE_ROOT_INVALID")
        return [("project", self.project_root)] + (
            [("storage", self.storage_root)]
            if self.storage_root != self.project_root
            else []
        )

    def _discover_files(self, roots):
        candidates = []
        mapping_override = os.getenv("PERIOD_PROFIT_MAPPING_REGISTRY_PATH")
        override_target = None
        if mapping_override:
            override_path = Path(mapping_override)
            if not override_path.is_absolute():
                override_path = self.project_root / override_path
            override_path = override_path.resolve(strict=False)
            override_target = self._path_in_roots(override_path, roots)
            if override_target is None or override_path.suffix.lower() != ".json":
                raise _BackupFailure("BOT_BACKUP_EXTERNAL_STATE_UNSUPPORTED")

        for root_name, root_path in roots:
            direct_relatives = [
                Path(self.SQLITE_NAME),
                *(Path(item) for item in self.ROOT_JSON_FILES),
                *(Path("data") / item for item in self.PROJECT_DATA_JSON_FILES),
            ]
            for relative in direct_relatives:
                path = root_path / relative
                if path.exists() or self._is_reparse_point(path):
                    candidates.append((root_name, root_path, relative, path))
            if override_target and override_target[0] == root_name:
                relative = override_target[1]
                path = root_path / relative
                if path.exists() or self._is_reparse_point(path):
                    candidates.append((root_name, root_path, relative, path))
            candidates.extend(self._discover_tenant_files(root_name, root_path))

        unique = {}
        for item in candidates:
            key = (item[0], item[2].as_posix().lower())
            unique[key] = item
        normalized = [unique[key] for key in sorted(unique)]
        for root_name, root_path, relative, path in normalized:
            self._validate_source_path(root_path, relative, path)
        return normalized

    def _discover_tenant_files(self, root_name, root_path):
        tenant_root = root_path / "data" / "tenants"
        if not tenant_root.exists() and not self._is_reparse_point(tenant_root):
            return []
        self._validate_source_path(
            root_path,
            Path("data/tenants"),
            tenant_root,
            allow_missing=False,
            expected_type="directory",
        )
        if not tenant_root.is_dir():
            raise _BackupFailure("BOT_BACKUP_UNSUPPORTED_LAYOUT")
        found = []
        try:
            entries = sorted(os.scandir(tenant_root), key=lambda entry: entry.name.lower())
        except OSError as error:
            raise _BackupFailure("BOT_BACKUP_SOURCE_UNREADABLE") from error
        for entry in entries:
            tenant_path = Path(entry.path)
            if entry.is_symlink() or self._is_reparse_point(tenant_path):
                raise _BackupFailure("BOT_BACKUP_REPARSE_POINT")
            if not self.TENANT_DIRECTORY_RE.fullmatch(entry.name) or not entry.is_dir(follow_symlinks=False):
                raise _BackupFailure("BOT_BACKUP_TENANT_LAYOUT_INVALID")
            tenant_relative = Path("data") / "tenants" / entry.name
            try:
                children = sorted(os.scandir(tenant_path), key=lambda child: child.name.lower())
            except OSError as error:
                raise _BackupFailure("BOT_BACKUP_SOURCE_UNREADABLE") from error
            for child in children:
                child_path = Path(child.path)
                if child.is_symlink() or self._is_reparse_point(child_path):
                    raise _BackupFailure("BOT_BACKUP_REPARSE_POINT")
                if not child.is_file(follow_symlinks=False):
                    raise _BackupFailure("BOT_BACKUP_UNSUPPORTED_LAYOUT")
                if child.name.endswith((".tmp", ".lock", ".wal", ".shm")) or ".quarantine" in child.name:
                    continue
                if child.name == self.SQLITE_NAME or child.name.lower().endswith(".json"):
                    found.append((root_name, root_path, tenant_relative / child.name, child_path))
                else:
                    raise _BackupFailure("BOT_BACKUP_UNSUPPORTED_FILE_TYPE")
        return found

    def _validate_source_path(
        self,
        root_path,
        relative,
        path,
        allow_missing=True,
        expected_type="file",
    ):
        if relative.is_absolute() or ".." in relative.parts:
            raise _BackupFailure("BOT_BACKUP_PATH_INVALID")
        current = root_path
        for part in relative.parts:
            current = current / part
            if not current.exists() and not self._is_reparse_point(current):
                if allow_missing:
                    return
                raise _BackupFailure("BOT_BACKUP_SOURCE_UNREADABLE")
            if self._is_reparse_point(current):
                raise _BackupFailure("BOT_BACKUP_REPARSE_POINT")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root_path)
        except (OSError, ValueError) as error:
            raise _BackupFailure("BOT_BACKUP_PATH_ESCAPE") from error
        if expected_type == "directory" and not resolved.is_dir():
            raise _BackupFailure("BOT_BACKUP_SOURCE_TYPE_INVALID")
        if expected_type == "file" and not resolved.is_file():
            raise _BackupFailure("BOT_BACKUP_SOURCE_TYPE_INVALID")

    def _validate_backup_directory(self, roots, candidates):
        try:
            target = self.backup_directory.resolve(strict=False)
            target.relative_to(self.project_root)
        except (OSError, ValueError) as error:
            raise _BackupFailure("BOT_BACKUP_DESTINATION_INVALID") from error
        if target == self.project_root:
            raise _BackupFailure("BOT_BACKUP_DESTINATION_INVALID")
        current = self.project_root
        for part in target.relative_to(self.project_root).parts:
            current = current / part
            if current.exists() and self._is_reparse_point(current):
                raise _BackupFailure("BOT_BACKUP_DESTINATION_REPARSE_POINT")
        for _, root_path, relative, _ in candidates:
            source = (root_path / relative).resolve(strict=False)
            if source == target or self._is_relative_to(source, target):
                raise _BackupFailure("BOT_BACKUP_DESTINATION_OVERLAPS_SOURCE")
        for _, root_path in roots:
            candidate_source_dir = root_path / "data" / "tenants"
            if candidate_source_dir.exists() and self._is_relative_to(target, candidate_source_dir.resolve()):
                raise _BackupFailure("BOT_BACKUP_DESTINATION_OVERLAPS_SOURCE")
        return target

    def _read_candidate(self, path):
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                size = path.stat().st_size
                if size > self.MAX_JSON_BYTES:
                    raise _BackupFailure("BOT_BACKUP_JSON_SIZE_LIMIT")
                payload = path.read_bytes()
                parsed = json.loads(
                    payload.decode("utf-8-sig"),
                    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
                )
            except _BackupFailure:
                raise
            except Exception as error:
                raise _BackupFailure("BOT_BACKUP_JSON_INVALID") from error
            expected_type = list if path.name in self.LIST_JSON_FILES else dict
            if not isinstance(parsed, expected_type):
                raise _BackupFailure("BOT_BACKUP_JSON_CONTRACT_INVALID")
            metadata = {"format": "json", "metadata": {"root_type": "list" if isinstance(parsed, list) else "object"}}
            return payload, metadata
        if suffix in {".db", ".sqlite", ".sqlite3"}:
            payload, db_metadata = self._snapshot_sqlite(path)
            if len(payload) > self.MAX_FILE_BYTES:
                raise _BackupFailure("BOT_BACKUP_FILE_SIZE_LIMIT")
            return payload, {"format": "sqlite", "metadata": db_metadata}
        raise _BackupFailure("BOT_BACKUP_UNSUPPORTED_FILE_TYPE")

    def _snapshot_sqlite(self, source_path):
        temporary_path = None
        source = None
        destination = None
        try:
            if source_path.stat().st_size > self.MAX_FILE_BYTES:
                raise _BackupFailure("BOT_BACKUP_FILE_SIZE_LIMIT")
            fd, temporary_path = tempfile.mkstemp(prefix="ai-assistant-backup-", suffix=".db")
            os.close(fd)
            uri_path = source_path.resolve(strict=True).as_uri() + "?mode=ro"
            source = sqlite3.connect(uri_path, uri=True, timeout=5.0)
            source.execute("PRAGMA query_only = ON")
            destination = sqlite3.connect(temporary_path)
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise _BackupFailure("BOT_BACKUP_SQLITE_INTEGRITY_FAILED")
            user_version = destination.execute("PRAGMA user_version").fetchone()[0]
            table_count = destination.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            destination.close()
            destination = None
            payload = Path(temporary_path).read_bytes()
            return payload, {
                "integrity_check": "ok",
                "user_version": int(user_version),
                "table_count": int(table_count),
            }
        except _BackupFailure:
            raise
        except Exception as error:
            raise _BackupFailure("BOT_BACKUP_SQLITE_INVALID") from error
        finally:
            if destination is not None:
                destination.close()
            if source is not None:
                source.close()
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    def _verify_archive(self, archive_path, require_complete):
        try:
            with zipfile.ZipFile(archive_path, mode="r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) > self.MAX_FILES + 2 or len(names) != len(set(names)):
                    return self._error("BOT_BACKUP_ARCHIVE_ENTRY_COUNT_INVALID")
                if any(not self._valid_archive_name(name) for name in names):
                    return self._error("BOT_BACKUP_ARCHIVE_PATH_INVALID")
                if len({name.casefold() for name in names}) != len(names):
                    return self._error("BOT_BACKUP_ARCHIVE_ENTRY_COUNT_INVALID")
                for info in infos:
                    unix_mode = (info.external_attr >> 16) & 0xFFFF
                    dos_attributes = info.external_attr & 0xFFFF
                    if (
                        stat.S_ISLNK(unix_mode)
                        or dos_attributes & 0x400
                        or info.is_dir()
                    ):
                        return self._error("BOT_BACKUP_ARCHIVE_LINK_UNSUPPORTED")
                expanded_total = 0
                for info in infos:
                    if info.file_size < 0 or info.file_size > self.MAX_FILE_BYTES:
                        return self._error("BOT_BACKUP_FILE_SIZE_LIMIT")
                    expanded_total += info.file_size
                    if expanded_total > self.MAX_TOTAL_BYTES + self.MAX_MANIFEST_BYTES + 1024 * 1024:
                        return self._error("BOT_BACKUP_TOTAL_SIZE_LIMIT")
                required_names = {"manifest.json"}
                if require_complete:
                    required_names.add("COMPLETED.json")
                if not required_names.issubset(names):
                    return self._error("BOT_BACKUP_ARCHIVE_INVALID")
                bad_member = archive.testzip()
                if bad_member is not None:
                    return self._error("BOT_BACKUP_ARCHIVE_CRC_FAILED")
                manifest_bytes = archive.read("manifest.json")
                if len(manifest_bytes) > self.MAX_MANIFEST_BYTES:
                    return self._error("BOT_BACKUP_MANIFEST_SIZE_LIMIT")
                manifest = json.loads(manifest_bytes.decode("utf-8"))
                if (
                    not isinstance(manifest, dict)
                    or manifest.get("format") != self.FORMAT
                    or manifest.get("schema_version") != self.SCHEMA_VERSION
                    or not isinstance(manifest.get("entries"), list)
                    or len(manifest["entries"]) > self.MAX_FILES
                ):
                    return self._error("BOT_BACKUP_MANIFEST_INVALID")
                total = 0
                expected_names = {"manifest.json"}
                if require_complete:
                    expected_names.add("COMPLETED.json")
                normalized_paths = set()
                for entry in manifest["entries"]:
                    if not isinstance(entry, dict):
                        return self._error("BOT_BACKUP_MANIFEST_INVALID")
                    root_name = entry.get("root")
                    relative_path = entry.get("path")
                    if (
                        root_name not in {"project", "storage"}
                        or not isinstance(relative_path, str)
                        or not self._valid_archive_name(relative_path)
                        or relative_path.startswith("files/")
                        or ":" in relative_path
                        or any(part in {"", ".", ".."} for part in relative_path.split("/"))
                    ):
                        return self._error("BOT_BACKUP_MANIFEST_INVALID")
                    path_key = (root_name + "/" + relative_path).casefold()
                    if path_key in normalized_paths:
                        return self._error("BOT_BACKUP_MANIFEST_INVALID")
                    normalized_paths.add(path_key)
                    expected = "files/" + root_name + "/" + relative_path
                    if expected not in names:
                        return self._error("BOT_BACKUP_MANIFEST_INVALID")
                    expected_names.add(expected)
                    payload = archive.read(expected)
                    size = entry.get("size_bytes")
                    digest = entry.get("sha256")
                    if (
                        type(size) is not int
                        or size < 0
                        or size > self.MAX_FILE_BYTES
                        or len(payload) != size
                        or not isinstance(digest, str)
                        or hashlib.sha256(payload).hexdigest() != digest
                    ):
                        return self._error("BOT_BACKUP_CHECKSUM_FAILED")
                    total += size
                    if total > self.MAX_TOTAL_BYTES:
                        return self._error("BOT_BACKUP_TOTAL_SIZE_LIMIT")
                    content_error = self._validate_archive_payload(entry, payload)
                    if content_error:
                        return self._error(content_error)
                if total != manifest.get("total_size_bytes") or len(manifest["entries"]) != manifest.get("file_count"):
                    return self._error("BOT_BACKUP_MANIFEST_TOTALS_INVALID")
                if set(names) != expected_names:
                    return self._error("BOT_BACKUP_ARCHIVE_UNEXPECTED_ENTRY")
                if require_complete:
                    completion = json.loads(archive.read("COMPLETED.json").decode("utf-8"))
                    if (
                        not isinstance(completion, dict)
                        or completion.get("format") != self.COMPLETE_FORMAT
                        or completion.get("status") != "COMPLETE"
                        or completion.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest()
                        or completion.get("file_count") != len(manifest["entries"])
                    ):
                        return self._error("BOT_BACKUP_COMPLETION_MARKER_INVALID")
                return {
                    "error": False,
                    "status": "BOT_BACKUP_ARCHIVE_VERIFIED",
                    "file_count": len(manifest["entries"]),
                    "total_size_bytes": total,
                    "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                    "application_revision": manifest.get("application_revision"),
                    "read_only": True,
                    "executed": False,
                }
        except (
            OSError,
            KeyError,
            ValueError,
            TypeError,
            RuntimeError,
            zipfile.BadZipFile,
            UnicodeError,
        ):
            return self._error("BOT_BACKUP_ARCHIVE_INVALID")

    def _validate_archive_payload(self, entry, payload):
        if entry.get("format") == "json":
            if len(payload) > self.MAX_JSON_BYTES:
                return "BOT_BACKUP_JSON_SIZE_LIMIT"
            try:
                value = json.loads(
                    payload.decode("utf-8-sig"),
                    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
                )
            except Exception:
                return "BOT_BACKUP_JSON_INVALID"
            expected_type = list if Path(entry.get("path", "")).name in self.LIST_JSON_FILES else dict
            return None if isinstance(value, expected_type) else "BOT_BACKUP_JSON_CONTRACT_INVALID"
        if entry.get("format") == "sqlite":
            temporary_path = None
            try:
                fd, temporary_path = tempfile.mkstemp(
                    prefix="ai-assistant-verify-", suffix=".db"
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                uri_path = Path(temporary_path).resolve().as_uri() + "?mode=ro"
                connection = sqlite3.connect(uri_path, uri=True, timeout=5.0)
                try:
                    if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        return "BOT_BACKUP_SQLITE_INTEGRITY_FAILED"
                finally:
                    connection.close()
            except Exception:
                return "BOT_BACKUP_SQLITE_INVALID"
            finally:
                if temporary_path:
                    try:
                        os.unlink(temporary_path)
                    except OSError:
                        pass
            return None
        return "BOT_BACKUP_UNSUPPORTED_FILE_TYPE"

    def _path_in_roots(self, path, roots):
        for root_name, root_path in roots:
            try:
                return root_name, path.relative_to(root_path)
            except ValueError:
                continue
        return None

    def _safe_revision(self):
        try:
            value = self.revision_reader(self.project_root)
        except Exception:
            value = None
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", value.strip()):
            return "UNAVAILABLE"
        return value.strip().lower()

    @staticmethod
    def _read_revision(project_root):
        result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    @staticmethod
    def _canonical_json(value):
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @staticmethod
    def _valid_archive_name(value):
        if (
            not isinstance(value, str)
            or not value
            or "\\" in value
            or ":" in value
            or "\x00" in value
        ):
            return False
        from pathlib import PurePosixPath

        path = PurePosixPath(value)
        return (
            not path.is_absolute()
            and ".." not in path.parts
            and not value.startswith("/")
            and not value.startswith("//")
            and all(part not in {"", "."} for part in value.split("/"))
        )

    @staticmethod
    def _is_relative_to(path, root):
        try:
            Path(path).relative_to(Path(root))
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_reparse_point(path):
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return False
        attributes = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)

    @staticmethod
    def _remove_partial(path):
        if path is None:
            return
        try:
            candidate = Path(path)
            if candidate.name.endswith(".partial") and candidate.is_file():
                candidate.unlink()
        except OSError:
            pass

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "status": "BOT_BACKUP_UNAVAILABLE",
            "code": code,
            "read_only": True,
            "executed": False,
        }


class _BackupFailure(Exception):
    def __init__(self, code):
        self.code = str(code or "BOT_BACKUP_FAILED")
        super().__init__(self.code)
