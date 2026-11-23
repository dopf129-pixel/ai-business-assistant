"""Scoped, read-only adapter for reports already attached to one FIFO case."""
from __future__ import annotations
from services.fifo_cost_transition_contracts import EvidenceCompleteness, PeriodProvenance, ReportType

class FifoCostProvisionalEvidenceReader:
    MAX_REPORTS_PER_CASE = 100
    _EDITABLE_STATES = frozenset({"DRAFT", "AWAITING_EVIDENCE"})

    def __init__(self, *, transition_service):
        self.transition_service = transition_service

    def list_turnover_reports(self, *, case_id, identity, expected_case_revision):
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
                if (report is None or report.report_type is not ReportType.TURNOVER
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
                item["captured_at"], item["file_fingerprint"],
            ))
            return {"error": False, "case_revision": expected_case_revision,
                    "store_timezone": case.metadata.store_timezone, "reports": tuple(reports),
                    "read_only": True}
        except (TypeError, ValueError, KeyError, AttributeError):
            return self._error("FIFO_PROVISIONAL_REPORTS_UNAVAILABLE")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "reports": (), "read_only": True}
