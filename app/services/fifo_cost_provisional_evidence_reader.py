"""Scoped, read-only adapter for reports already attached to one FIFO case."""
from __future__ import annotations
from services.fifo_cost_transition_contracts import EvidenceCompleteness, PeriodProvenance, ReportType

class FifoCostProvisionalEvidenceReader:
    MAX_REPORTS_PER_CASE = 100
    _EDITABLE_STATES = frozenset({"DRAFT", "AWAITING_EVIDENCE"})

    def __init__(self, *, transition_service, transition_evidence_service=None):
        self.transition_service = transition_service
        self.transition_evidence_service = transition_evidence_service

    def read_timeline_sources(self, *, case_id, identity, expected_case_revision):
        """Read aggregate report anchors and an optional confirmed sale document."""
        reports = self.list_confirmed_reports(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
        )
        if reports.get("error"):
            return reports
        physical_sales = None
        physical_status = "NOT_CONFIGURED"
        if self.transition_evidence_service is not None:
            result = self.transition_evidence_service.read_confirmed_physical_sales(
                case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
            )
            if result.get("error"):
                code = result.get("code")
                if code == "FIFO_PHYSICAL_SALES_DOCUMENT_MISSING":
                    physical_status = "MISSING"
                elif code in {
                    "FIFO_PHYSICAL_SALES_DOCUMENT_CONFLICT",
                    "FIFO_PHYSICAL_SALES_CONFIRMATION_CORRUPT",
                }:
                    physical_status = "CONFLICT"
                else:
                    physical_status = "UNAVAILABLE"
            else:
                physical_sales = (result["document"], result["confirmation"])
                physical_status = "CONFIRMED"
        return {
            **reports,
            "physical_sales": physical_sales,
            "physical_sales_status": physical_status,
            "read_only": True,
        }

    def list_turnover_reports(self, *, case_id, identity, expected_case_revision):
        result = self.list_confirmed_reports(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
        )
        if result.get("error"):
            return result
        reports = tuple(item for item in result["reports"]
                        if item["report"].report_type is ReportType.TURNOVER)
        return {**result, "reports": reports}

    def list_confirmed_reports(self, *, case_id, identity, expected_case_revision):
        """Return complete, owner-dated reports from this exact editable case.

        This is a read-only adapter. Reports are still aggregate anchors; this
        method does not infer event timestamps or create timeline movements.
        """
        if (not isinstance(identity, dict) or type(expected_case_revision) is not int
                or expected_case_revision < 1):
            return self._error("FIFO_PROVISIONAL_INPUT_INVALID")
        current = self.transition_service.get_case(case_id=case_id, **identity)
        if not isinstance(current, dict) or current.get("error") is not False:
            return self._error("FIFO_PROVISIONAL_CASE_UNAVAILABLE")
        if current.get("case_revision") != expected_case_revision:
            return self._error("FIFO_PROVISIONAL_STALE")
        if current.get("state") not in self._EDITABLE_STATES:
            return self._error("FIFO_PROVISIONAL_CASE_NOT_EDITABLE")
        try:
            case = self.transition_service._case_from_payload(current["case"])
            scope = case.metadata.scope
            if any(getattr(scope, key) != value for key, value in identity.items()):
                return self._error("FIFO_PROVISIONAL_SCOPE_MISMATCH")
            evidence = self.transition_service.repository.read_transition_evidence(
                case_id=case_id, **identity, kind="REPORT_EVIDENCE",
                limit=self.MAX_REPORTS_PER_CASE + 1,
            )
            if (not isinstance(evidence, dict) or evidence.get("error") is not False
                    or not isinstance(evidence.get("items"), list)):
                return self._error("FIFO_PROVISIONAL_REPORTS_UNAVAILABLE")
            if len(evidence["items"]) > self.MAX_REPORTS_PER_CASE:
                return self._error("FIFO_PROVISIONAL_REPORT_LIMIT")
            reports = []
            seen = set()
            for row in evidence["items"]:
                if not isinstance(row, dict):
                    return self._error("FIFO_PROVISIONAL_REPORTS_UNAVAILABLE")
                digest = row.get("file_sha256")
                if not isinstance(digest, str) or digest in seen:
                    continue
                seen.add(digest)
                report = self.transition_service._read_saved_transition_report(
                    case_id=case_id, identity=identity, scope=scope,
                    store_timezone=case.metadata.store_timezone, file_sha256=digest,
                )
                if (report is None or report.report_type not in {
                        ReportType.TURNOVER, ReportType.STOCK_MANAGEMENT,
                    }
                        or report.metadata.scope != scope
                        or report.metadata.store_timezone != case.metadata.store_timezone
                        or report.metadata.completeness is not EvidenceCompleteness.COMPLETE
                        or report.period_provenance is not PeriodProvenance.OWNER_CONFIRMED):
                    continue
                reports.append({
                    "file_fingerprint": report.file_sha256,
                    "period_from": report.period_from,
                    "period_to": report.period_to,
                    "period_confirmed": report.period_provenance is PeriodProvenance.OWNER_CONFIRMED,
                    "complete": report.metadata.completeness is EvidenceCompleteness.COMPLETE,
                    "captured_at": report.captured_at,
                    "report": report,
                })
            reports.sort(key=lambda item: (
                item["period_from"] or "", item["period_to"] or "",
                item["report"].report_type.value, item["captured_at"],
                item["file_fingerprint"],
            ))
            return {"error": False, "case_revision": expected_case_revision,
                    "store_timezone": case.metadata.store_timezone, "reports": tuple(reports),
                    "read_only": True}
        except (TypeError, ValueError, KeyError, AttributeError):
            return self._error("FIFO_PROVISIONAL_REPORTS_UNAVAILABLE")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "reports": (), "read_only": True}
