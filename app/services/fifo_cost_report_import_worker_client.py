"""Parent-side bounded subprocess client for FIFO workbook parsing."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore

from services.fifo_cost_report_import_service import (
    FifoCostReportImportResult,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    TransitionMetadata,
)


_WORKER_SLOTS = BoundedSemaphore(3)
_MAX_OUTPUT_BYTES = 384 * 1024


class FifoCostReportImportWorkerClient:
    """Run a parser in a killable process with a strict wall-clock budget."""

    TIMEOUT_SECONDS = 15
    MAX_FILE_BYTES = 10 * 1024 * 1024

    def __init__(
        self, *, popen_factory=None, python_executable=None, repo_root=None,
        extra_python_paths=(),
    ):
        self._popen = popen_factory or subprocess.Popen
        self._python = python_executable or sys.executable
        self._repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
        self._app_root = self._repo_root / "app"
        self._extra_python_paths = tuple(str(Path(item).resolve()) for item in extra_python_paths)

    def parse(self, *, report_type, filename, payload, scope):
        try:
            report_type = report_type if isinstance(report_type, ReportType) else ReportType(str(report_type))
        except (TypeError, ValueError):
            return self._error("FIFO_REPORT_FORMAT_UNSUPPORTED")
        if report_type not in {ReportType.TURNOVER, ReportType.STOCK_MANAGEMENT}:
            return self._error("FIFO_REPORT_FORMAT_UNSUPPORTED")
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_REPORT_SCOPE_INVALID")
        if not isinstance(filename, str) or not filename.strip() or len(filename) > 255:
            return self._error("FIFO_REPORT_FILENAME_INVALID")
        if isinstance(payload, memoryview):
            if payload.nbytes > self.MAX_FILE_BYTES:
                return self._error("FIFO_REPORT_FILE_SIZE_INVALID")
            payload = payload.tobytes()
        if not isinstance(payload, (bytes, bytearray)):
            return self._error("FIFO_REPORT_PAYLOAD_INVALID")
        payload = bytes(payload)
        if not payload or len(payload) > self.MAX_FILE_BYTES:
            return self._error("FIFO_REPORT_FILE_SIZE_INVALID")
        if not _WORKER_SLOTS.acquire(blocking=False):
            return self._error("FIFO_REPORT_WORKER_BUSY")
        process = None
        try:
            header = {
                "report_type": report_type.value,
                "filename": filename,
                "payload_bytes": len(payload),
                "scope": {
                    "owner_id": scope.owner_id,
                    "store_id": scope.store_id,
                    "product_id": scope.product_id,
                    "offer_id": scope.offer_id,
                    "sku": scope.sku,
                },
            }
            request = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(request) > 4096:
                return self._error("FIFO_REPORT_WORKER_HEADER_INVALID")
            environment = self._worker_environment()
            command = [self._python, "-m", "services.fifo_cost_report_import_worker"]
            kwargs = {
                "cwd": str(self._repo_root),
                "env": environment,
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.DEVNULL,
                "shell": False,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = self._popen(command, **kwargs)
            try:
                stdout, _stderr = process.communicate(
                    input=request + b"\n" + payload,
                    timeout=self.TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                self._stop_own_worker(process)
                return self._error("FIFO_REPORT_WORKER_TIMEOUT")
            if process.returncode != 0:
                return self._error("FIFO_REPORT_WORKER_FAILED")
            if not isinstance(stdout, bytes) or not stdout or len(stdout) > _MAX_OUTPUT_BYTES:
                return self._error("FIFO_REPORT_WORKER_RESULT_INVALID")
            return self._decode_result(stdout, scope)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._error("FIFO_REPORT_WORKER_FAILED")
        finally:
            if process is not None and process.poll() is None:
                self._stop_own_worker(process)
            _WORKER_SLOTS.release()

    def _worker_environment(self):
        allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR")
        environment = {key: os.environ[key] for key in allowed if os.environ.get(key)}
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(self._app_root), *self._extra_python_paths)
        )
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    @staticmethod
    def _stop_own_worker(process):
        try:
            process.terminate()
            process.wait(timeout=0.5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                pass

    @classmethod
    def _decode_result(cls, output, scope):
        try:
            value = json.loads(output.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        if not isinstance(value, dict) or type(value.get("error")) is not bool:
            return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        if value["error"]:
            code = value.get("code")
            if not isinstance(code, str) or not code.startswith("FIFO_") or len(code) > 96:
                return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
            return cls._error(code)
        status = value.get("status")
        issues = value.get("issue_codes")
        report_value = value.get("report")
        if status not in {"COMPLETE", "PARTIAL", "ERROR"} or not isinstance(issues, list):
            return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        if len(issues) > 100 or any(not isinstance(code, str) or len(code) > 96 for code in issues):
            return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        if report_value is None:
            return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        try:
            if not isinstance(report_value, dict):
                raise ValueError
            normalized_fields = report_value["normalized_fields"]
            cell_references = report_value["cell_references"]
            if not isinstance(normalized_fields, dict) or not isinstance(cell_references, list):
                raise ValueError
            if len(cell_references) > 100_000 or any(not isinstance(item, str) for item in cell_references):
                raise ValueError
            report_type = ReportType(report_value["report_type"])
            completeness = EvidenceCompleteness(report_value["completeness"])
            provenance = PeriodProvenance(report_value["period_provenance"])
            if (report_type is ReportType.TURNOVER) != ("source_sheet" in normalized_fields):
                raise ValueError
            metadata = TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=completeness,
                source_fingerprint=report_value["source_fingerprint"],
            )
            report = ReportEvidence(
                metadata=metadata,
                report_type=report_type,
                period_from=report_value.get("period_from"),
                period_to=report_value.get("period_to"),
                period_provenance=provenance,
                captured_at=report_value["captured_at"],
                file_sha256=report_value["file_sha256"],
                parser_version=report_value["parser_version"],
                cell_references=tuple(cell_references),
                normalized_fields=normalized_fields,
            )
            cls._check_persisted_payload_size(report)
        except ValueError as error:
            if str(error) == "FIFO_TRANSITION_PAYLOAD_TOO_LARGE":
                return cls._error("FIFO_TRANSITION_PAYLOAD_TOO_LARGE")
            return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        except (KeyError, TypeError):
            return cls._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        return FifoCostReportImportResult(
            status=status,
            read_only=True,
            executed=False,
            report_evidence=report,
            file_sha256=report.file_sha256,
            issue_codes=tuple(dict.fromkeys(issues)),
        )

    @staticmethod
    def _check_persisted_payload_size(report):
        from services.fifo_cost_transition_store import FifoCostTransitionStore

        payload = FifoCostTransitionStore._evidence_payload(report)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 262_144:
            raise ValueError("FIFO_TRANSITION_PAYLOAD_TOO_LARGE")

    @staticmethod
    def _error(code):
        return FifoCostReportImportResult(
            status="ERROR",
            read_only=True,
            executed=False,
            report_evidence=None,
            file_sha256=None,
            issue_codes=(code,),
        )
