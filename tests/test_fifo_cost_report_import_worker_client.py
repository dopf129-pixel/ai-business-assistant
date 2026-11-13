from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import subprocess
from threading import Event, Lock

from openpyxl import Workbook

from services.fifo_cost_report_import_service import FifoCostReportImportService
from services.fifo_cost_physical_sales_import_service import FifoCostPhysicalSalesImportService
from services.fifo_cost_report_import_worker_client import (
    FifoCostReportImportWorkerClient,
)
from services.fifo_cost_transition_contracts import ReportType, ScopeIdentity


SCOPE = ScopeIdentity(
    owner_id="owner-1", store_id="store-1", product_id="product-1",
    offer_id="hook-2", sku="3921245627",
)


def _payload():
    parser = FifoCostReportImportService()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = parser.SHEET_NAME
    for address, value in parser._EXPECTED_HEADERS.items():
        sheet[address] = value
    values = [0] * 40
    values[0] = int(SCOPE.sku)
    values[3:11] = [2740, 0, 2, 1, 1, 1, 75, 1672]
    values[18] = 9
    values[19:26] = [775, 0, 5, 0, 0, 0, 0]
    values[26] = 4
    values[27:35] = [1988, 0, 2, 6, 0, 0, 70, 1646]
    values[35:39] = [4492, 0, 780, 3712]
    for column, value in enumerate(values, start=1):
        sheet.cell(row=4, column=column, value=value)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class _MalformedProcess:
    def __init__(self, output=b"{}"):
        self.output = output
        self.returncode = None
        self.terminated = False

    def communicate(self, *, input, timeout):
        assert timeout == 15
        self.returncode = 0
        return self.output, b""

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def _request(**kwargs):
    return {
        "report_type": ReportType.TURNOVER,
        "filename": "turnover_04112026-05112026.xlsx",
        "payload": b"xlsx",
        "scope": SCOPE,
        **kwargs,
    }


def _physical_payload():
    service = FifoCostPhysicalSalesImportService()
    return (
        service.TEMPLATE_HEADER
        + "\r\nposting-1;3921245627;2;2026-11-05;row-1\r\n"
    ).encode("utf-8")


def test_worker_subprocess_parses_allowlisted_report_and_returns_normalized_evidence():
    result = FifoCostReportImportWorkerClient(
        extra_python_paths=(".fl12-deps",),
    ).parse(
        **_request(payload=_payload()),
    )
    assert result.status == "COMPLETE", result.issue_codes
    assert result.read_only is True and result.executed is False
    assert result.report_evidence.report_type is ReportType.TURNOVER
    assert result.report_evidence.normalized_fields["closing_total"] == 3712
    assert result.report_evidence.metadata.scope == SCOPE


def test_physical_sales_subprocess_revalidates_and_returns_server_manifests():
    result = FifoCostReportImportWorkerClient(
        extra_python_paths=(".fl12-deps",),
    ).parse_physical_sales(
        filename="physical-sales.csv", payload=_physical_payload(), scope=SCOPE,
    )
    assert result.status == "COMPLETE", result.issue_codes
    assert result.document.row_count == 1
    assert result.document.unit_count == 2
    assert result.document.period_from == "2026-11-05"
    assert len(result.document.file_sha256) == 64


def test_physical_sales_client_rejects_tampered_worker_manifest():
    service = FifoCostPhysicalSalesImportService()
    payload = _physical_payload()
    document = service.build_document(
        payload=payload,
        scope=SCOPE,
        rows=[{
            "posting_number": "posting-1", "finance_sku": SCOPE.sku,
            "quantity": 900, "physical_effective_date": "2026-11-06",
            "row_reference": "row-1",
        }],
    )
    result_payload = {
        "error": False,
        "document_kind": "PHYSICAL_SALES_CSV",
        "document": document.to_worker_summary_payload(),
    }
    process = _MalformedProcess(json.dumps(result_payload).encode())
    result = FifoCostReportImportWorkerClient(
        popen_factory=lambda *args, **kwargs: process,
    ).parse_physical_sales(
        filename="physical-sales.csv", payload=_physical_payload(), scope=SCOPE,
    )
    assert result.status == "ERROR"
    assert result.issue_codes == ("FIFO_REPORT_WORKER_RESULT_INVALID",)


def test_physical_sales_worker_uses_the_shared_hard_timeout():
    class TimeoutProcess(_MalformedProcess):
        def communicate(self, *, input, timeout):
            assert timeout == 15
            raise subprocess.TimeoutExpired("fifo-worker", timeout)

    process = TimeoutProcess()
    result = FifoCostReportImportWorkerClient(
        popen_factory=lambda *args, **kwargs: process,
    ).parse_physical_sales(
        filename="physical-sales.csv", payload=_physical_payload(), scope=SCOPE,
    )
    assert result.issue_codes == ("FIFO_REPORT_WORKER_TIMEOUT",)
    assert process.terminated is True


def test_oversize_and_malformed_worker_result_fail_closed():
    spawned = []

    def popen(*args, **kwargs):
        process = _MalformedProcess()
        spawned.append(process)
        return process

    client = FifoCostReportImportWorkerClient(popen_factory=popen)
    oversize = client.parse(**_request(payload=b"x" * (client.MAX_FILE_BYTES + 1)))
    assert oversize.issue_codes == ("FIFO_REPORT_FILE_SIZE_INVALID",)
    assert spawned == []
    malformed = client.parse(**_request())
    assert malformed.issue_codes == ("FIFO_REPORT_WORKER_RESULT_INVALID",)
    assert len(spawned) == 1


def test_worker_timeout_terminates_only_started_worker():
    class TimeoutProcess(_MalformedProcess):
        def communicate(self, *, input, timeout):
            raise subprocess.TimeoutExpired("fifo-worker", timeout)

    processes = []

    def popen(*args, **kwargs):
        process = TimeoutProcess()
        processes.append(process)
        return process

    result = FifoCostReportImportWorkerClient(popen_factory=popen).parse(**_request())
    assert result.issue_codes == ("FIFO_REPORT_WORKER_TIMEOUT",)
    assert processes[0].terminated is True


def test_worker_slot_limit_rejects_fourth_concurrent_import():
    started = Event()
    release = Event()
    lock = Lock()
    count = 0

    class WaitingProcess(_MalformedProcess):
        def communicate(self, *, input, timeout):
            nonlocal count
            with lock:
                count += 1
                if count == 3:
                    started.set()
            assert release.wait(3)
            self.returncode = 0
            return json.dumps({"error": True, "code": "FIFO_TEST_DONE"}).encode(), b""

    client = FifoCostReportImportWorkerClient(popen_factory=lambda *args, **kwargs: WaitingProcess())
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(client.parse, **_request()) for _ in range(3)]
        assert started.wait(2)
        busy = client.parse(**_request())
        assert busy.issue_codes == ("FIFO_REPORT_WORKER_BUSY",)
        physical_busy = client.parse_physical_sales(
            filename="physical-sales.csv", payload=_physical_payload(), scope=SCOPE,
        )
        assert physical_busy.issue_codes == ("FIFO_REPORT_WORKER_BUSY",)
        release.set()
        results = [task.result(timeout=3) for task in tasks]
    assert all(result.issue_codes == ("FIFO_TEST_DONE",) for result in results)


def test_worker_rejects_evidence_larger_than_repository_payload_limit():
    payload = {
        "error": False,
        "status": "COMPLETE",
        "issue_codes": [],
        "report": {
            "report_type": "TURNOVER",
            "period_from": None,
            "period_to": None,
            "period_provenance": "UNKNOWN",
            "captured_at": "2026-11-08T12:00:00Z",
            "file_sha256": "a" * 64,
            "parser_version": "fifo-turnover-v1",
            "cell_references": ["A1"] * 53_000,
            "normalized_fields": {"source_sheet": "x"},
            "completeness": "COMPLETE",
            "source_fingerprint": "b" * 64,
        },
    }
    process = _MalformedProcess(json.dumps(payload).encode())
    result = FifoCostReportImportWorkerClient(
        popen_factory=lambda *args, **kwargs: process,
    ).parse(**_request())
    assert result.issue_codes == ("FIFO_TRANSITION_PAYLOAD_TOO_LARGE",)
    assert result.report_evidence is None
