from datetime import datetime, timezone
from services.fifo_cost_provisional_evidence_reader import FifoCostProvisionalEvidenceReader
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness, EvidenceSourceKind, PeriodProvenance, ReportEvidence, ReportType,
    ScopeIdentity, TransitionMetadata,
)

SCOPE = ScopeIdentity(owner_id="owner-test", store_id="store-test", product_id="1", offer_id=None, sku="SKU-TEST")
IDENTITY = {"store_id": "store-test", "product_id": "1", "offer_id": None, "sku": "SKU-TEST"}

def _report(digest, *, period_from="2026-11-05", period_to="2026-11-05", scope=SCOPE,
            kind=ReportType.TURNOVER, provenance=PeriodProvenance.OWNER_CONFIRMED,
            completeness=EvidenceCompleteness.COMPLETE):
    return ReportEvidence(
        metadata=TransitionMetadata(scope=scope, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
            completeness=completeness, source_fingerprint=digest, store_timezone="Europe/Moscow"),
        report_type=kind, period_from=period_from, period_to=period_to,
        period_provenance=provenance, captured_at=datetime(2026, 11, 22, tzinfo=timezone.utc),
        file_sha256=digest, parser_version="fifo-turnover-v1", cell_references=(), normalized_fields={},
    )

class _Repository:
    def __init__(self, rows): self.rows = rows
    def read_transition_evidence(self, **kwargs):
        assert kwargs["kind"] == "REPORT_EVIDENCE"
        return {"error": False, "items": self.rows[:kwargs["limit"]]}

class _Transition:
    def __init__(self, rows, reports=None, *, revision=4, state="DRAFT"):
        self.repository = _Repository(rows); self.reports = reports or {}
        self.revision = revision; self.state = state; self.reads = 0
    def get_case(self, **kwargs):
        return {"error": False, "case_revision": self.revision, "state": self.state,
                "case": {"metadata": {"scope": {"owner_id": "owner-test", **IDENTITY},
                                           "store_timezone": "Europe/Moscow"}}}
    @staticmethod
    def _case_from_payload(payload):
        from types import SimpleNamespace
        data=payload["metadata"]; scope=data["scope"]
        return SimpleNamespace(metadata=SimpleNamespace(
            scope=SCOPE, store_timezone=data["store_timezone"]))
    def _read_saved_transition_report(self, **kwargs):
        self.reads += 1
        return self.reports.get(kwargs["file_sha256"])

def test_reader_returns_only_exact_case_confirmed_complete_turnover_documents():
    valid = _report("a" * 64)
    candidate = _report("b" * 64, provenance=PeriodProvenance.FILENAME_CANDIDATE)
    partial = _report("c" * 64, completeness=EvidenceCompleteness.PARTIAL)
    other = _report("d" * 64, kind=ReportType.STOCK_MANAGEMENT)
    rows = [{"file_sha256": x} for x in (valid.file_sha256, candidate.file_sha256, partial.file_sha256, other.file_sha256)]
    service = FifoCostProvisionalEvidenceReader(transition_service=_Transition(rows, {x.file_sha256:x for x in (valid,candidate,partial,other)}))
    result = service.list_turnover_reports(case_id="case_opaque", identity=IDENTITY, expected_case_revision=4)
    assert result["error"] is False
    assert [x["file_fingerprint"] for x in result["reports"]] == [valid.file_sha256]
    assert result["read_only"] is True

def test_reader_fails_closed_on_stale_case_or_report_quota():
    transition = _Transition([{"file_sha256": "a" * 64}], revision=5)
    result = FifoCostProvisionalEvidenceReader(transition_service=transition).list_turnover_reports(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4)
    assert result["code"] == "FIFO_PROVISIONAL_STALE"
    transition = _Transition([{"file_sha256": str(i) * 64} for i in range(1, 102)])
    result = FifoCostProvisionalEvidenceReader(transition_service=transition).list_turnover_reports(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4)
    assert result["code"] == "FIFO_PROVISIONAL_REPORT_LIMIT"

def test_confirmed_reader_includes_stock_anchors_but_turnover_compatibility_stays_narrow():
    turnover = _report("a" * 64)
    stock = _report("b" * 64, kind=ReportType.STOCK_MANAGEMENT)
    candidate = _report("c" * 64, kind=ReportType.STOCK_MANAGEMENT,
                        provenance=PeriodProvenance.FILENAME_CANDIDATE)
    rows = [{"file_sha256": value.file_sha256} for value in (turnover, stock, candidate)]
    service = FifoCostProvisionalEvidenceReader(transition_service=_Transition(
        rows, {value.file_sha256: value for value in (turnover, stock, candidate)},
    ))
    confirmed = service.list_confirmed_reports(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4,
    )
    assert confirmed["error"] is False
    assert {item["report"].report_type for item in confirmed["reports"]} == {
        ReportType.TURNOVER, ReportType.STOCK_MANAGEMENT,
    }
    assert service.list_turnover_reports(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4,
    )["reports"] == tuple(
        item for item in confirmed["reports"]
        if item["report"].report_type is ReportType.TURNOVER
    )

def test_timeline_source_read_is_exact_revision_read_only_and_maps_missing_sales_safely():
    valid = _report("a" * 64)
    rows = [{"file_sha256": valid.file_sha256}]
    document = object()
    confirmation = object()

    class _PhysicalReader:
        def __init__(self, result): self.result = result; self.calls = 0
        def read_confirmed_physical_sales(self, **kwargs):
            self.calls += 1
            assert kwargs == {
                "case_id": "case_opaque", "identity": IDENTITY,
                "expected_case_revision": 4,
            }
            return self.result

    physical = _PhysicalReader({
        "error": False, "document": document, "confirmation": confirmation,
        "fingerprint": "f" * 64, "read_only": True,
    })
    reader = FifoCostProvisionalEvidenceReader(
        transition_service=_Transition(rows, {valid.file_sha256: valid}),
        transition_evidence_service=physical,
    )
    result = reader.read_timeline_sources(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4,
    )
    assert result["error"] is False
    assert result["physical_sales"] == (document, confirmation)
    assert result["physical_sales_status"] == "CONFIRMED"
    assert result["fingerprint"] == "f" * 64
    assert result["read_only"] is True
    assert physical.calls == 1

    physical.result["fingerprint"] = "e" * 64
    replaced = reader.read_timeline_sources(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4,
    )
    assert replaced["fingerprint"] == "e" * 64

    del physical.result["fingerprint"]
    unverified = reader.read_timeline_sources(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4,
    )
    assert unverified["physical_sales_status"] == "UNAVAILABLE"
    assert unverified["physical_sales"] is None
    assert unverified["fingerprint"] is None

    missing = FifoCostProvisionalEvidenceReader(
        transition_service=_Transition(rows, {valid.file_sha256: valid}),
        transition_evidence_service=_PhysicalReader({
            "error": True, "code": "FIFO_PHYSICAL_SALES_DOCUMENT_MISSING",
        }),
    ).read_timeline_sources(
        case_id="case_opaque", identity=IDENTITY, expected_case_revision=4,
    )
    assert missing["physical_sales"] is None
    assert missing["physical_sales_status"] == "MISSING"


def test_history_reads_turnover_on_closed_cases_without_opening_calculation():
    report = _report("a" * 64)
    transition = _Transition(
        [{"file_sha256": report.file_sha256}],
        {report.file_sha256: report},
    )
    service = FifoCostProvisionalEvidenceReader(transition_service=transition)
    args = {"case_id": "case_opaque", "identity": IDENTITY, "expected_case_revision": 4}
    for state in ("READY_TO_CONFIRM", "APPLIED", "CANCELLED"):
        transition.state = state
        history = service.list_history_turnover_reports(**args)
        assert history["read_only"] is True
        assert [item["file_fingerprint"] for item in history["reports"]] == [report.file_sha256]
        assert service.list_turnover_reports(**args)["code"] == "FIFO_PROVISIONAL_CASE_NOT_EDITABLE"
    transition.revision += 1
    assert service.list_history_turnover_reports(**args)["code"] == "FIFO_PROVISIONAL_STALE"
