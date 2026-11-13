"""Durable, separately confirmed physical-sales evidence for FIFO cases."""

from __future__ import annotations

from services.fifo_cost_physical_sales_import_service import (
    FifoCostPhysicalSalesImportService,
    FifoPhysicalSalesDocument,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    TransitionBridgeEvidence,
    TransitionBridgeEvidenceKind,
    TransitionEvidenceConfirmation,
    TransitionEvidenceConfirmationKind,
    TransitionMetadata,
    normalize_date_only,
    normalize_store_timezone,
    normalize_utc_timestamp,
)


class FifoCostPhysicalSalesEvidenceService:
    """Persist an owner CSV and bind a later confirmation to its exact revision."""

    EVIDENCE_KIND = TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT
    CONFIRMATION_KIND = TransitionEvidenceConfirmationKind.PHYSICAL_SALES
    SEMANTICS = "PHYSICAL_OUTFLOW"

    def __init__(self, *, importer=None):
        self._importer = importer or FifoCostPhysicalSalesImportService()

    def preview_document(self, *, document, period_from, period_to, timezone_name):
        """Build the safe preview fields; never include posting or row references."""
        if not isinstance(document, FifoPhysicalSalesDocument):
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID")
        normalized = self._normalize_period(
            document=document, period_from=period_from,
            period_to=period_to, timezone_name=timezone_name,
        )
        if normalized.get("error"):
            return normalized
        return {
            "error": False,
            "code": "FIFO_PHYSICAL_SALES_PREVIEW_READY",
            "row_count": document.row_count,
            "unit_count": document.unit_count,
            "row_date_from": document.period_from,
            "row_date_to": document.period_to,
            "period_from": normalized["period_from"],
            "period_to": normalized["period_to"],
            "timezone": normalized["timezone"],
            "semantics": self.SEMANTICS,
            "source_kind": EvidenceSourceKind.OWNER_IMPORTED.value,
            "completeness": EvidenceCompleteness.PARTIAL.value,
            "coverage_verified": False,
            "document_fingerprint": document.document_fingerprint,
            "identity_fingerprint": document.identity_fingerprint,
            "rows_fingerprint": document.row_references_fingerprint,
            "confirmed": False,
        }

    def save_document(
        self, *, repository, case_id, scope, filename, payload, document,
        period_from, period_to, timezone_name, captured_at,
        expected_case_revision, idempotency_key,
    ):
        """Append the exact parsed UTF-8 source bytes as encrypted evidence."""
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_TRANSITION_SCOPE_MISMATCH")
        if not isinstance(document, FifoPhysicalSalesDocument):
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID")
        if isinstance(payload, memoryview):
            payload = payload.tobytes()
        if not isinstance(payload, (bytes, bytearray)):
            return self._error("FIFO_REPORT_PAYLOAD_INVALID")
        raw = bytes(payload)
        parsed = self._importer.parse_csv(
            filename=filename, payload=raw, scope=scope,
        )
        if parsed.document is None or parsed.document != document:
            return self._error(
                parsed.issue_codes[0] if parsed.issue_codes
                else "FIFO_REPORT_WORKER_RESULT_INVALID",
            )
        period = self._normalize_period(
            document=document, period_from=period_from,
            period_to=period_to, timezone_name=timezone_name,
        )
        if period.get("error"):
            return period
        capture = self._normalize_capture(captured_at)
        if capture is None:
            return self._error("FIFO_TRANSITION_TIMESTAMP_INVALID")
        case = self._read_case(
            repository=repository, case_id=case_id, scope=scope,
        )
        if case.get("error"):
            return case
        case_timezone = case["case_timezone"]
        if case_timezone != period["timezone"]:
            return self._error("FIFO_TRANSITION_TIMEZONE_MISMATCH")
        try:
            metadata = TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.PARTIAL,
                source_fingerprint=document.normalized_fingerprint,
                store_timezone=period["timezone"],
            )
            evidence = TransitionBridgeEvidence(
                metadata=metadata,
                evidence_kind=self.EVIDENCE_KIND,
                captured_at=capture,
                period_from=period["period_from"],
                period_to=period["period_to"],
                row_count=document.row_count,
                payload={
                    "document_fingerprint": document.document_fingerprint,
                    "row_count": document.row_count,
                    "period_from": period["period_from"],
                    "period_to": period["period_to"],
                    "timezone": period["timezone"],
                    "semantics": self.SEMANTICS,
                    "identity_fingerprint": document.identity_fingerprint,
                },
                # UTF-8 round-tripping retains an optional BOM and exact bytes.
                sensitive_payload=raw.decode("utf-8", errors="strict"),
            )
        except (TypeError, ValueError, UnicodeError):
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID")
        result = repository.append_transition_bridge_evidence(
            case_id=case_id,
            evidence=evidence,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )
        if result.get("error"):
            return result
        replay_value = result.get("result")
        if isinstance(replay_value, dict):
            result = {
                **replay_value,
                **{key: value for key, value in result.items() if key != "result"},
            }
        return {
            **result,
            "preview": self.preview_document(
                document=document,
                period_from=period["period_from"],
                period_to=period["period_to"],
                timezone_name=period["timezone"],
            ),
        }

    def read_document(self, *, repository, case_id, scope, evidence_id):
        """Rebuild one exact encrypted document after restart, without raw output."""
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_TRANSITION_SCOPE_MISMATCH")
        result = repository.read_transition_bridge_evidence(
            case_id=case_id,
            store_id=scope.store_id,
            product_id=scope.product_id,
            offer_id=scope.offer_id,
            sku=scope.sku,
            evidence_kind=self.EVIDENCE_KIND,
            evidence_id=evidence_id,
            limit=1,
            include_sensitive_payload=True,
        )
        if result.get("error"):
            return result
        items = result.get("items")
        if not isinstance(items, list) or len(items) != 1:
            return self._error("FIFO_TRANSITION_EVIDENCE_MISSING")
        item = items[0]
        if item.get("sensitive_payload_available") is not True:
            return self._error(item.get("blocker", "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE"))
        loaded = self._reconstruct_item(item, scope)
        if loaded.get("error"):
            return loaded
        preview = self.preview_document(
            document=loaded["document"],
            period_from=item["period_from"],
            period_to=item["period_to"],
            timezone_name=item["payload"]["timezone"],
        )
        if preview.get("error"):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        return {
            "error": False,
            "code": "FIFO_PHYSICAL_SALES_DOCUMENT_FOUND",
            "case_revision": result.get("case_revision"),
            "case_state": result.get("state"),
            "evidence_id": item["evidence_id"],
            "evidence_revision": item["evidence_revision"],
            "payload_fingerprint": item["payload_fingerprint"],
            "preview": {**preview, "confirmed": loaded["confirmed"]},
            "document": loaded["document"],
            "confirmed": loaded["confirmed"],
            "confirmation_id": loaded["confirmation_id"],
            "confirmed_fields": loaded["confirmed_fields"],
            "confirmation_revision": loaded["confirmation_revision"],
        }

    def list_confirmed_documents(self, *, repository, case_id, scope):
        """Return safe summaries of confirmed CSV versions for an owner decision."""
        if not isinstance(scope, ScopeIdentity):
            return self._error("FIFO_TRANSITION_SCOPE_MISMATCH")
        listed = repository.read_transition_bridge_evidence(
            case_id=case_id, store_id=scope.store_id,
            product_id=scope.product_id, offer_id=scope.offer_id, sku=scope.sku,
            evidence_kind=self.EVIDENCE_KIND, limit=100,
            include_sensitive_payload=True,
        )
        if listed.get("error"):
            return listed
        items = listed.get("items")
        if not isinstance(items, list) or len(items) > 100:
            return self._error("FIFO_PHYSICAL_SALES_EVIDENCE_LIMIT_REACHED")
        documents = []
        for item in items:
            read = self.read_document(
                repository=repository, case_id=case_id, scope=scope,
                evidence_id=item.get("evidence_id"),
            )
            if read.get("error"):
                return read
            if read.get("confirmed") is True:
                documents.append({
                    "evidence_id": read["evidence_id"],
                    "payload_fingerprint": read["payload_fingerprint"],
                    "confirmation_revision": read["confirmation_revision"],
                    "preview": read["preview"],
                })
        return {
            "error": False,
            "code": "FIFO_PHYSICAL_SALES_CONFIRMED_VERSIONS_FOUND",
            "documents": tuple(sorted(
                documents,
                key=lambda value: (
                    value["confirmation_revision"], value["payload_fingerprint"],
                ),
            )),
        }

    def confirm_document(
        self, *, repository, case_id, scope, evidence_id,
        expected_evidence_fingerprint, expected_case_revision,
        expected_document_fingerprint, expected_rows_fingerprint,
        expected_identity_fingerprint, expected_row_count,
        period_from, period_to, timezone_name, semantics, idempotency_key,
        select_as_current=False, expected_superseded_evidence_fingerprints=None,
    ):
        """Confirm all rows and provenance only after exact durable reconstruction."""
        loaded = self.read_document(
            repository=repository, case_id=case_id, scope=scope,
            evidence_id=evidence_id,
        )
        if loaded.get("error"):
            return loaded
        document = loaded["document"]
        period = self._normalize_period(
            document=document, period_from=period_from,
            period_to=period_to, timezone_name=timezone_name,
        )
        if period.get("error"):
            return period
        item_fingerprint = loaded["payload_fingerprint"]
        if item_fingerprint != expected_evidence_fingerprint:
            return self._error("FIFO_TRANSITION_EVIDENCE_MISMATCH")
        expected_fields = {
            "document_fingerprint": document.document_fingerprint,
            "row_count": document.row_count,
            "rows_fingerprint": document.row_references_fingerprint,
            "period_from": period["period_from"],
            "period_to": period["period_to"],
            "timezone": period["timezone"],
            "semantics": self.SEMANTICS,
        }
        if type(select_as_current) is not bool:
            return self._error("FIFO_PHYSICAL_SALES_VERSION_SELECTION_INVALID")
        if select_as_current:
            listed = self.list_confirmed_documents(
                repository=repository, case_id=case_id, scope=scope,
            )
            if listed.get("error"):
                return listed
            superseded = tuple(sorted(
                item["payload_fingerprint"]
                for item in listed["documents"]
                if item["evidence_id"] != evidence_id
            ))
            if (
                expected_superseded_evidence_fingerprints is not None
                and tuple(expected_superseded_evidence_fingerprints) != superseded
            ):
                return self._error("FIFO_PHYSICAL_SALES_VERSION_SELECTION_STALE")
            expected_fields.update({
                "selected_as_current": True,
                "supersedes_evidence_fingerprints": list(superseded),
            })
        if (
            expected_document_fingerprint != document.document_fingerprint
            or expected_rows_fingerprint != document.row_references_fingerprint
            or expected_identity_fingerprint != document.identity_fingerprint
            or type(expected_row_count) is not int
            or expected_row_count != document.row_count
            or semantics != self.SEMANTICS
            or loaded["preview"]["period_from"] != period["period_from"]
            or loaded["preview"]["period_to"] != period["period_to"]
            or loaded["preview"]["timezone"] != period["timezone"]
        ):
            return self._error("FIFO_TRANSITION_PREVIEW_STALE")
        case = self._read_case(
            repository=repository, case_id=case_id, scope=scope,
        )
        if case.get("error"):
            return case
        if case["case_timezone"] != period["timezone"]:
            return self._error("FIFO_TRANSITION_TIMEZONE_MISMATCH")
        try:
            confirmation = TransitionEvidenceConfirmation(
                confirmation_kind=self.CONFIRMATION_KIND,
                confirmed_fields=expected_fields,
            )
            metadata = TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.PARTIAL,
                source_fingerprint=document.normalized_fingerprint,
                store_timezone=period["timezone"],
            )
        except (TypeError, ValueError):
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_INVALID")
        confirmed = repository.confirm_transition_evidence(
            case_id=case_id,
            metadata=metadata,
            evidence_id=evidence_id,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            confirmation=confirmation,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )
        if confirmed.get("error"):
            return confirmed
        return {
            **confirmed,
            "confirmed": True,
            "row_count": document.row_count,
            "unit_count": document.unit_count,
            "document_fingerprint": document.document_fingerprint,
            "rows_fingerprint": document.row_references_fingerprint,
            "selected_as_current": select_as_current,
        }

    def _reconstruct_item(self, item, scope):
        payload = item.get("payload")
        source = item.get("sensitive_payload")
        if not isinstance(payload, dict) or not isinstance(source, str):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        if (
            item.get("evidence_kind") != self.EVIDENCE_KIND.value
            or item.get("source_kind") != EvidenceSourceKind.OWNER_IMPORTED.value
            or item.get("completeness") != EvidenceCompleteness.PARTIAL.value
            or payload.get("semantics") != self.SEMANTICS
        ):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        try:
            raw = source.encode("utf-8", errors="strict")
            parsed = self._importer.parse_csv(
                filename="physical-sales.csv", payload=raw, scope=scope,
            )
        except (UnicodeError, TypeError, ValueError):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        document = parsed.document
        if document is None:
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        if (
            item.get("source_fingerprint") != document.normalized_fingerprint
            or item.get("row_count") != document.row_count
            or payload.get("document_fingerprint") != document.document_fingerprint
            or payload.get("row_count") != document.row_count
            or payload.get("identity_fingerprint") != document.identity_fingerprint
            or item.get("period_from") != payload.get("period_from")
            or item.get("period_to") != payload.get("period_to")
            or not self._date_range_covers(
                document, item.get("period_from"), item.get("period_to"),
            )
        ):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        try:
            timezone_name = normalize_store_timezone(payload.get("timezone"))
            normalize_date_only(item.get("period_from"))
            normalize_date_only(item.get("period_to"))
        except (TypeError, ValueError):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        expected_fields = {
            "document_fingerprint": document.document_fingerprint,
            "row_count": document.row_count,
            "rows_fingerprint": document.row_references_fingerprint,
            "period_from": item["period_from"],
            "period_to": item["period_to"],
            "timezone": timezone_name,
            "semantics": self.SEMANTICS,
        }
        matching = []
        for value in item.get("confirmations", []):
            if value.get("confirmation_kind") != self.CONFIRMATION_KIND.value:
                continue
            confirmed_fields = value.get("confirmed_fields")
            if not isinstance(confirmed_fields, dict) or any(
                confirmed_fields.get(key) != expected
                for key, expected in expected_fields.items()
            ):
                return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
            selection_keys = set(confirmed_fields) - set(expected_fields)
            if selection_keys not in (
                set(), {"selected_as_current", "supersedes_evidence_fingerprints"},
            ):
                return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
            if selection_keys and (
                confirmed_fields.get("selected_as_current") is not True
                or not isinstance(
                    confirmed_fields.get("supersedes_evidence_fingerprints"),
                    (list, tuple),
                )
            ):
                return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
            if selection_keys:
                try:
                    TransitionEvidenceConfirmation(
                        confirmation_kind=self.CONFIRMATION_KIND,
                        confirmed_fields=confirmed_fields,
                    )
                except (TypeError, ValueError):
                    return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
            matching.append(value)
        revisions = [
            value.get("expected_case_revision") for value in matching
        ]
        if any(type(value) is not int or value < 1 for value in revisions):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        if len(revisions) != len(set(revisions)):
            return self._error("FIFO_TRANSITION_EVIDENCE_CORRUPT")
        latest = max(matching, key=lambda value: value["expected_case_revision"]) if matching else None
        return {
            "error": False,
            "document": document,
            "confirmed": latest is not None,
            "confirmation_id": latest.get("confirmation_id") if latest else None,
            "confirmed_fields": dict(latest["confirmed_fields"]) if latest else None,
            "confirmation_revision": (
                latest.get("expected_case_revision") if latest else None
            ),
        }

    def _read_case(self, *, repository, case_id, scope):
        result = repository.read_transition_case(
            case_id=case_id,
            store_id=scope.store_id,
            product_id=scope.product_id,
            offer_id=scope.offer_id,
            sku=scope.sku,
        )
        if result.get("error"):
            return result
        try:
            case_timezone = normalize_store_timezone(
                result["case"]["metadata"]["store_timezone"],
            )
        except (KeyError, TypeError, ValueError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
        return {"error": False, "case_timezone": case_timezone}

    @staticmethod
    def _normalize_period(*, document, period_from, period_to, timezone_name):
        try:
            start = normalize_date_only(period_from)
            end = normalize_date_only(period_to)
            timezone_value = normalize_store_timezone(timezone_name)
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_DATE_INVALID"}
        if (
            end < start or document.period_from < start
            or document.period_to > end
        ):
            return {"error": True, "code": "FIFO_PHYSICAL_SALES_DATE_OUTSIDE_PERIOD"}
        return {
            "error": False,
            "period_from": start,
            "period_to": end,
            "timezone": timezone_value,
        }

    @staticmethod
    def _date_range_covers(document, period_from, period_to):
        try:
            start = normalize_date_only(period_from)
            end = normalize_date_only(period_to)
        except (TypeError, ValueError):
            return False
        return end >= start and document.period_from >= start and document.period_to <= end

    @staticmethod
    def _normalize_capture(value):
        try:
            return normalize_utc_timestamp(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
