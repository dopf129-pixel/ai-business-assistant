"""Rebuild exact FIFO transition bridge inputs from durable evidence.

The service never calls Ozon or Telegram. Source collection is a separate
bounded operation; this module persists typed snapshots and rehydrates them
after process restart. Missing physical-movement coverage remains explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from datetime import date, timedelta
import json

from services.fifo_cost_cutoff_bridge_service import (
    FifoCutoffMovementCoverage,
    FifoCutoffMovementReference,
    FifoDocumentedPhysicalSaleDocument,
    FifoDocumentedPhysicalSaleRow,
    FifoFinanceSaleIdentity,
    FifoFinanceSaleIdentityBatch,
    FifoOwnerSupplierReceivingConfirmation,
    FifoPhysicalSaleDocumentConfirmation,
)
from services.fifo_cost_physical_sales_evidence_service import (
    FifoCostPhysicalSalesEvidenceService,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    SourceProof,
    TransitionBridgeEvidence,
    TransitionBridgeEvidenceKind,
    TransitionEvidenceConfirmation,
    TransitionEvidenceConfirmationKind,
    TransitionMetadata,
    TransitionCase,
    FifoFinancialPeriodSummary,
    source_fingerprint,
)
from services.fifo_cost_transition_service import FifoCostTransitionService


@dataclass(frozen=True)
class FifoCostTransitionEvidenceBundle:
    """Exact durable inputs for one read-only review at one case revision."""

    case: TransitionCase
    stock_evidence: object = None
    finance_batch: FifoFinanceSaleIdentityBatch | None = None
    period_summaries: tuple[FifoFinancialPeriodSummary, ...] = ()
    physical_sale_document: FifoDocumentedPhysicalSaleDocument | None = None
    owner_confirmation: FifoPhysicalSaleDocumentConfirmation | None = None
    movement_coverage: FifoCutoffMovementCoverage | None = None
    cutoff_evidence_id: str | None = None
    owner_supplier_receiving_confirmation: FifoOwnerSupplierReceivingConfirmation | None = None
    opening_composition_fingerprint: str | None = None
    source_fingerprints: tuple[str, ...] = ()
    missing_requirements: tuple[str, ...] = ()


class FifoCostTransitionEvidenceService:
    """Persist bounded source DTOs and reconstruct their exact scoped bundle."""

    MAX_FINANCE_BATCHES = 24
    MAX_FINANCE_ROWS = 100_000
    MAX_MOVEMENTS = 100_000
    _IDENTITY_KEYS = frozenset({"store_id", "product_id", "offer_id", "sku"})

    def __init__(self, transition_service, *, physical_sales_service=None):
        if not isinstance(transition_service, FifoCostTransitionService):
            raise TypeError("FIFO_TRANSITION_SERVICE_REQUIRED")
        self.transition_service = transition_service
        self.repository = transition_service.repository
        self.physical_sales_service = (
            physical_sales_service or FifoCostPhysicalSalesEvidenceService()
        )

    def record_finance_identity_batches(
        self, *, case_id, identity, batches, requested_period_from,
        requested_period_to, source_complete, expected_case_revision,
        idempotency_key,
    ):
        """Save normalized monthly finance identities, encrypted and case-bound."""
        loaded = self._case_context(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        if (
            type(source_complete) is not bool
            or not isinstance(batches, tuple)
            or not 1 <= len(batches) <= self.MAX_FINANCE_BATCHES
            or any(not isinstance(batch, FifoFinanceSaleIdentityBatch) for batch in batches)
        ):
            return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_INVALID")
        try:
            requested_start = date.fromisoformat(requested_period_from)
            requested_end = date.fromisoformat(requested_period_to)
            if requested_start.isoformat() != requested_period_from or requested_end.isoformat() != requested_period_to or requested_end < requested_start:
                raise ValueError
            if not 1 <= len(batches) <= self.MAX_FINANCE_BATCHES:
                raise ValueError
            scope = loaded["case"].metadata.scope
            ordered = tuple(sorted(batches, key=lambda item: (item.period_from, item.period_to)))
            rows = []
            period_end = None
            for batch in ordered:
                if (
                    not isinstance(batch, FifoFinanceSaleIdentityBatch)
                    or batch.metadata_scope != scope
                    or not batch.proof.api_read_complete
                ):
                    raise ValueError("FIFO_FINANCE_IDENTITY_COVERAGE_INCOMPLETE")
                start = date.fromisoformat(batch.period_from)
                end = date.fromisoformat(batch.period_to)
                if period_end is not None and start != period_end + timedelta(days=1):
                    raise ValueError("FIFO_FINANCE_IDENTITY_PERIOD_GAP")
                period_end = end
                batch_period = batch.period_from[:7]
                if batch.period_to[:7] != batch_period:
                    raise ValueError("FIFO_FINANCE_IDENTITY_MONTH_UNRESOLVED")
                batch_rows = [{
                    "posting_number": row.posting_number,
                    "finance_sku": row.finance_sku,
                    "offer_id": row.offer_id,
                    "product_id": row.product_id,
                    "financial_period": row.financial_period or batch_period,
                } for row in batch.rows]
                if any(row["financial_period"] != batch_period for row in batch_rows):
                    raise ValueError("FIFO_FINANCE_IDENTITY_PERIOD_MISMATCH")
                rows.extend(batch_rows)
            if len(rows) > self.MAX_FINANCE_ROWS:
                raise ValueError("FIFO_FINANCE_IDENTITY_ROW_LIMIT")
            if len(rows) != len({(row["posting_number"], row["finance_sku"]) for row in rows}):
                raise ValueError("FIFO_FINANCE_IDENTITY_DUPLICATE")
            source_batches = [batch.source_fingerprint for batch in ordered]
            combined_from = ordered[0].period_from
            combined_to = ordered[-1].period_to
            if source_complete and (
                date.fromisoformat(combined_from) > requested_start
                or date.fromisoformat(combined_to) < requested_end
            ):
                raise ValueError("FIFO_FINANCE_IDENTITY_COVERAGE_GAP")
            rows.sort(key=lambda row: (
                row["posting_number"], row["finance_sku"],
                row["offer_id"] or "", row["product_id"] or "",
            ))
            rows_fingerprint = source_fingerprint(rows)
            proof_as_of_values = [batch.proof.source_as_of for batch in ordered]
            source_as_of = max((value for value in proof_as_of_values if value), default=None)
            all_scope_complete = all(batch.proof.scope_complete for batch in ordered)
            all_pages_complete = all(batch.proof.pagination_complete for batch in ordered)
            complete = bool(
                source_complete and all_scope_complete and all_pages_complete
                and date.fromisoformat(combined_from) <= requested_start
                and date.fromisoformat(combined_to) >= requested_end
            )
            proof_fingerprint = source_fingerprint({
                "kind": "FIFO_FINANCE_IDENTITY_PROOF_SET_V1",
                "source_proofs": [batch.proof.metadata.source_fingerprint for batch in ordered],
                "source_as_of": proof_as_of_values,
                "scope_complete": all_scope_complete,
                "pagination_complete": all_pages_complete,
            })
            batch_fingerprint = source_fingerprint({
                "kind": "FIFO_FINANCE_IDENTITY_BATCH_SET_V1",
                "source_batches": source_batches,
                "rows_fingerprint": rows_fingerprint,
                "period_from": combined_from,
                "period_to": combined_to,
                "source_complete": complete,
            })
            identity_fingerprint = self.transition_service._transition_identity_fingerprint(scope)
            completeness = EvidenceCompleteness.COMPLETE if complete else EvidenceCompleteness.PARTIAL
            proof_metadata = TransitionMetadata(
                scope=scope, source_kind=EvidenceSourceKind.OZON_API,
                completeness=completeness, source_fingerprint=proof_fingerprint,
                store_timezone=loaded["case"].metadata.store_timezone,
            )
            metadata = TransitionMetadata(
                scope=scope, source_kind=EvidenceSourceKind.OZON_API,
                completeness=completeness, source_fingerprint=batch_fingerprint,
                store_timezone=loaded["case"].metadata.store_timezone,
            )
            evidence = TransitionBridgeEvidence(
                metadata=metadata,
                evidence_kind=TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT,
                captured_at=self.transition_service._transition_now(),
                period_from=combined_from, period_to=combined_to,
                row_count=len(rows) if rows else None,
                payload={
                    "snapshot_fingerprint": batch_fingerprint,
                    "identity_fingerprint": identity_fingerprint,
                    "row_count": len(rows), "matched_rows": len(rows),
                    "page_count": len(ordered),
                    "scope_complete": all_scope_complete,
                    "pagination_complete": all_pages_complete,
                },
                sensitive_payload=self._json({
                    "schema_version": 2,
                    "requested_period_from": requested_period_from,
                    "requested_period_to": requested_period_to,
                    "source_complete": complete,
                    "batch_fingerprint": batch_fingerprint,
                    "source_batches": source_batches,
                    "rows_fingerprint": rows_fingerprint,
                    "rows": rows,
                    "proof_source_fingerprint": proof_fingerprint,
                    "proof_source_fingerprints": [
                        batch.proof.metadata.source_fingerprint for batch in ordered
                    ],
                    "proof_source_as_of_values": proof_as_of_values,
                    "proof_source_as_of": source_as_of,
                }),
            )
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            code = str(exc)
            if code.startswith("FIFO_"):
                return self._error(code)
            return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_INVALID")
        return self.repository.append_transition_bridge_evidence(
            case_id=case_id, evidence=evidence,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def record_movement_coverage(
        self, *, case_id, identity, coverage, expected_case_revision,
        idempotency_key,
    ):
        """Persist exact movement references without upgrading source proof."""
        loaded = self._case_context(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        if (
            not isinstance(coverage, FifoCutoffMovementCoverage)
            or coverage.scope != loaded["case"].metadata.scope
            or len(coverage.movements) > self.MAX_MOVEMENTS
        ):
            return self._error("FIFO_MOVEMENT_COVERAGE_SNAPSHOT_INVALID")
        try:
            identity_fingerprint = self.transition_service._transition_identity_fingerprint(
                loaded["case"].metadata.scope,
            )
            safe_movements = [self._movement_payload(item) for item in coverage.movements]
            movement_fingerprint = source_fingerprint(safe_movements)
            coverage_fingerprint = source_fingerprint({
                "source_fingerprint": coverage.source_fingerprint,
                "period_from": coverage.period_from,
                "complete_through": coverage.complete_through,
                "page_count": coverage.page_count,
                "scope_complete": coverage.proof.scope_complete,
                "pagination_complete": coverage.proof.pagination_complete,
                "source_as_of": coverage.proof.source_as_of,
                "movements_fingerprint": movement_fingerprint,
            })
            payload = {
                "snapshot_fingerprint": coverage_fingerprint,
                "identity_fingerprint": identity_fingerprint,
                "event_count": len(safe_movements),
                "period_from": coverage.period_from,
                "complete_through": coverage.complete_through,
                "page_count": coverage.page_count,
                "scope_complete": coverage.proof.scope_complete,
                "pagination_complete": coverage.proof.pagination_complete,
            }
            metadata = TransitionMetadata(
                scope=coverage.scope,
                source_kind=coverage.proof.metadata.source_kind,
                completeness=coverage.proof.metadata.completeness,
                source_fingerprint=coverage_fingerprint,
                store_timezone=loaded["case"].metadata.store_timezone,
            )
            evidence = TransitionBridgeEvidence(
                metadata=metadata,
                evidence_kind=TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE,
                captured_at=self.transition_service._transition_now(),
                period_from=coverage.period_from,
                period_to=coverage.complete_through,
                complete_through=coverage.complete_through,
                row_count=len(safe_movements) or None,
                payload=payload,
                sensitive_payload=self._json({
                    "schema_version": 1,
                    "source_fingerprint": coverage.source_fingerprint,
                    "proof_source_fingerprint": coverage.proof.metadata.source_fingerprint,
                    "proof_source_as_of": coverage.proof.source_as_of,
                    "coverage_fingerprint": coverage_fingerprint,
                    "movements_fingerprint": movement_fingerprint,
                    "movements": safe_movements,
                }),
            )
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            code = str(exc)
            if code.startswith("FIFO_"):
                return self._error(code)
            return self._error("FIFO_MOVEMENT_COVERAGE_SNAPSHOT_INVALID")
        return self.repository.append_transition_bridge_evidence(
            case_id=case_id, evidence=evidence,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def record_period_profit_summary(
        self, *, case_id, identity, summary, expected_case_revision,
        idempotency_key,
    ):
        """Persist one complete canonical Period Profit financial-period freeze."""
        loaded = self._case_context(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        if not isinstance(summary, FifoFinancialPeriodSummary):
            return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
        if summary.complete is not True:
            return self._error("FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE")
        scope = loaded["case"].metadata.scope
        try:
            identity_fingerprint = (
                self.transition_service._transition_identity_fingerprint(scope)
            )
            safe_summary = summary.as_impact_summary()
            evidence = TransitionBridgeEvidence(
                metadata=TransitionMetadata(
                    scope=scope,
                    source_kind=EvidenceSourceKind.LOCAL_DERIVED,
                    completeness=EvidenceCompleteness.COMPLETE,
                    source_fingerprint=summary.source_fingerprint,
                    store_timezone=loaded["case"].metadata.store_timezone,
                ),
                evidence_kind=TransitionBridgeEvidenceKind.PERIOD_SUMMARY_SNAPSHOT,
                captured_at=self.transition_service._transition_now(),
                period_from=summary.period_from,
                period_to=summary.period_to,
                row_count=1,
                payload={
                    "report_type": "PERIOD_PROFIT_FINANCIAL_SUMMARY",
                    "period_from": summary.period_from,
                    "period_to": summary.period_to,
                    "row_count": 1,
                    "summary_fingerprint": summary.source_fingerprint,
                    "identity_fingerprint": identity_fingerprint,
                },
                sensitive_payload=self._json({
                    "schema_version": 1,
                    "identity_fingerprint": identity_fingerprint,
                    "summary": safe_summary,
                }),
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
        return self.repository.append_transition_bridge_evidence(
            case_id=case_id, evidence=evidence,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def confirm_movement_coverage(
        self, *, case_id, identity, evidence_id, expected_evidence_fingerprint,
        expected_case_revision, idempotency_key,
    ):
        """Confirm coverage only for the exact durable movement snapshot."""
        loaded = self._case_context(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        read = self.repository.read_transition_bridge_evidence(
            case_id=case_id, **identity,
            evidence_kind=TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE,
            evidence_id=evidence_id, limit=1,
        )
        if read.get("error") or not read.get("items"):
            return self._error("FIFO_MOVEMENT_COVERAGE_EVIDENCE_MISSING")
        item = read["items"][0]
        payload = item.get("payload")
        if (
            item.get("payload_fingerprint") != expected_evidence_fingerprint
            or not isinstance(payload, dict)
            or payload.get("snapshot_fingerprint") != item.get("source_fingerprint")
        ):
            return self._error("FIFO_MOVEMENT_COVERAGE_EVIDENCE_MISMATCH")
        try:
            confirmation = TransitionEvidenceConfirmation(
                confirmation_kind=TransitionEvidenceConfirmationKind.MOVEMENT_COVERAGE,
                confirmed_fields={
                    "coverage_fingerprint": payload["snapshot_fingerprint"],
                    "complete_through": payload["complete_through"],
                    "event_count": payload["event_count"],
                },
            )
            metadata = TransitionMetadata(
                scope=loaded["case"].metadata.scope,
                source_kind=EvidenceSourceKind(item["source_kind"]),
                completeness=EvidenceCompleteness(item["completeness"]),
                source_fingerprint=item["source_fingerprint"],
                store_timezone=loaded["case"].metadata.store_timezone,
            )
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_MOVEMENT_COVERAGE_EVIDENCE_CORRUPT")
        return self.repository.confirm_transition_evidence(
            case_id=case_id, metadata=metadata, evidence_id=evidence_id,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            confirmation=confirmation, expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def load(
        self, *, case_id, identity, expected_case_revision,
        require_opening_composition=True, sealed_preview_id=None,
    ):
        """Rehydrate typed evidence at one exact case revision, without HTTP."""
        if (
            type(require_opening_composition) is not bool
            or (
                sealed_preview_id is not None
                and not isinstance(sealed_preview_id, str)
            )
        ):
            return self._error("FIFO_TRANSITION_EVIDENCE_INVALID")
        loaded = self._case_context(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
            sealed_preview_id=sealed_preview_id,
        )
        if loaded.get("error"):
            return loaded
        case = loaded["case"]
        scope = case.metadata.scope
        missing: list[str] = []
        fingerprints: list[str] = []

        cutoff = self.transition_service.read_confirmed_cutoff_selection(
            case_id=case_id, **identity,
        )
        stock_evidence = None
        cutoff_evidence_id = None
        owner_supplier_receiving_confirmation = None
        if cutoff.get("error"):
            if cutoff.get("code") == "FIFO_CUTOFF_SELECTION_NOT_CONFIRMED":
                missing.append("OWNER_CUTOFF_CONFIRMATION_REQUIRED")
            elif cutoff.get("code") == "FIFO_CUTOFF_SELECTION_STALE":
                missing.append("OWNER_CUTOFF_RECONFIRMATION_REQUIRED")
            else:
                return cutoff
        else:
            cutoff_evidence_id = cutoff["evidence_id"]
            fingerprints.append(cutoff["evidence_fingerprint"])
            stock_evidence = self.transition_service._read_saved_transition_report(
                case_id=case_id, identity=identity, scope=scope,
                store_timezone=case.metadata.store_timezone,
                file_sha256=cutoff["stock_report_fingerprint"],
            )
            if stock_evidence is None:
                missing.append("CUTOFF_STOCK_REPORT_MISSING")
            else:
                fingerprints.append(stock_evidence.file_sha256)
                buckets = stock_evidence.normalized_fields.get("stock_buckets")
                reported_receiving = (
                    buckets.get("supplier_receiving")
                    if isinstance(buckets, Mapping) else None
                )
                owner_receiving = cutoff.get(
                    "owner_confirmed_supplier_receiving_units",
                )
                if reported_receiving is None:
                    if owner_receiving is None:
                        missing.append(
                            "OWNER_SUPPLIER_RECEIVING_CONFIRMATION_REQUIRED",
                        )
                    else:
                        try:
                            owner_supplier_receiving_confirmation = (
                                FifoOwnerSupplierReceivingConfirmation(
                                    scope=scope,
                                    case_id=case_id,
                                    case_revision=case.case_revision,
                                    cutoff_date=cutoff["descriptor"]["cutoff_date"],
                                    stock_report_fingerprint=(
                                        cutoff["stock_report_fingerprint"]
                                    ),
                                    supplier_receiving_units=owner_receiving,
                                    evidence_fingerprint=(
                                        cutoff["evidence_fingerprint"]
                                    ),
                                )
                            )
                        except (TypeError, ValueError, KeyError):
                            return self._error(
                                "FIFO_CUTOFF_SELECTION_INVALID",
                            )

        opening = None
        if require_opening_composition:
            opening = self.transition_service.read_confirmed_opening_composition(
                case_id=case_id, **identity,
            )
            if opening.get("error"):
                if opening.get("code") == "FIFO_OPENING_COMPOSITION_STALE":
                    missing.append("OPENING_COMPOSITION_RECONFIRMATION_REQUIRED")
                elif opening.get("code") == "FIFO_OPENING_COMPOSITION_NOT_CONFIRMED":
                    missing.append("OPENING_COMPOSITION_CONFIRMATION_REQUIRED")
                else:
                    return opening
            else:
                fingerprints.append(opening["composition_fingerprint"])
                if (
                    cutoff_evidence_id != opening.get("cutoff_evidence_id")
                    or (
                        cutoff.get("error") is False
                        and opening.get("cutoff_evidence_fingerprint")
                        != cutoff.get("evidence_fingerprint")
                    )
                ):
                    missing.append("OPENING_COMPOSITION_STALE")

        finance = self._read_finance_identity(case_id=case_id, identity=identity, scope=scope)
        if finance.get("error"):
            finance_missing = {
                "FIFO_FINANCE_IDENTITY_SNAPSHOT_MISSING": "FINANCE_IDENTITY_SNAPSHOT_MISSING",
                "FIFO_FINANCE_IDENTITY_COVERAGE_INCOMPLETE": "FINANCE_IDENTITY_COVERAGE_INCOMPLETE",
                "FIFO_FINANCE_IDENTITY_PERIOD_GAP": "FINANCE_IDENTITY_PERIOD_GAP",
                "FIFO_FINANCE_IDENTITY_START_GAP": "FINANCE_IDENTITY_START_GAP",
                "FIFO_FINANCE_IDENTITY_END_GAP": "FINANCE_IDENTITY_END_GAP",
                "FIFO_FINANCE_IDENTITY_DUPLICATE": "FINANCE_IDENTITY_CONFLICT",
            }
            blocker = finance_missing.get(finance.get("code"))
            if blocker:
                missing.append(blocker)
            else:
                return finance
        else:
            fingerprints.append(finance["fingerprint"])
            if finance["batch"].metadata.completeness is not EvidenceCompleteness.COMPLETE:
                missing.append("FINANCE_IDENTITY_COVERAGE_INCOMPLETE")
            elif case.dispatch_date is None or (
                finance["batch"].period_from > case.dispatch_date
            ):
                missing.append("FINANCE_IDENTITY_START_GAP")

        period_summaries = self._read_period_profit_summaries(
            case_id=case_id, identity=identity, scope=scope,
        )
        if period_summaries.get("error"):
            summary_missing = {
                "FIFO_PERIOD_SUMMARY_SNAPSHOT_MISSING": (
                    "FINANCIAL_PERIOD_SUMMARY_SNAPSHOT_MISSING"
                ),
                "FIFO_PERIOD_SUMMARY_SNAPSHOT_CONFLICT": (
                    "FINANCIAL_PERIOD_SUMMARY_VERSION_CONFLICT"
                ),
                "FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID": (
                    "FINANCIAL_PERIOD_SUMMARY_SNAPSHOT_INVALID"
                ),
                "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE": (
                    "FINANCIAL_PERIOD_SUMMARY_ENCRYPTION_UNAVAILABLE"
                ),
            }
            blocker = summary_missing.get(period_summaries.get("code"))
            if blocker:
                missing.append(blocker)
            else:
                return period_summaries
        else:
            fingerprints.extend(period_summaries["fingerprints"])

        physical = self._read_physical_document(
            case_id=case_id, identity=identity, scope=scope, case=case,
        )
        if physical.get("error"):
            physical_missing = {
                "FIFO_PHYSICAL_SALES_DOCUMENT_MISSING": "PHYSICAL_SALES_DOCUMENT_MISSING",
                "FIFO_PHYSICAL_SALES_CONFIRMATION_REQUIRED": "OWNER_PHYSICAL_DATE_CONFIRMATION_REQUIRED",
                "FIFO_PHYSICAL_SALES_DOCUMENT_CONFLICT": "PHYSICAL_SALES_DOCUMENT_CONFLICT",
            }
            blocker = physical_missing.get(physical.get("code"))
            if blocker:
                missing.append(blocker)
            else:
                return physical
        else:
            fingerprints.append(physical["fingerprint"])

        movement = self._read_movement_coverage(
            case_id=case_id, identity=identity, scope=scope, case=case,
        )
        if movement.get("error"):
            if movement.get("code") == "FIFO_MOVEMENT_COVERAGE_SNAPSHOT_MISSING":
                missing.append("MOVEMENT_COVERAGE_SNAPSHOT_MISSING")
            elif movement.get("code") == "FIFO_MOVEMENT_COVERAGE_CONFIRMATION_REQUIRED":
                missing.append("MOVEMENT_COVERAGE_CONFIRMATION_REQUIRED")
            elif movement.get("code") == "FIFO_MOVEMENT_COVERAGE_INCOMPLETE":
                missing.append("MOVEMENT_COVERAGE_INCOMPLETE")
            elif movement.get("code") == "FIFO_MOVEMENT_COVERAGE_SCOPE_MISMATCH":
                missing.append("MOVEMENT_COVERAGE_SCOPE_CONFLICT")
            else:
                return movement
        else:
            fingerprints.append(movement["fingerprint"])

        if (
            physical.get("error") is False
            and finance.get("error") is False
            and movement.get("error") is False
            and physical["document"].period_to < movement["coverage"].complete_through
        ):
            missing.append("PHYSICAL_SALES_DOCUMENT_COVERAGE_GAP")
        if (
            finance.get("error") is False
            and movement.get("error") is False
            and finance["batch"].period_to < movement["coverage"].complete_through
        ):
            missing.append("FINANCE_IDENTITY_END_GAP")

        current_basis = self._case_context(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
            sealed_preview_id=sealed_preview_id,
        )
        if current_basis.get("error") or (
            self.transition_service._transition_case_basis_fingerprint(
                current_basis.get("case"),
            ) != self.transition_service._transition_case_basis_fingerprint(case)
        ):
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")

        bundle = FifoCostTransitionEvidenceBundle(
            case=case,
            stock_evidence=stock_evidence,
            finance_batch=finance.get("batch") if finance.get("error") is False else None,
            period_summaries=(
                period_summaries["summaries"]
                if period_summaries.get("error") is False else ()
            ),
            physical_sale_document=physical.get("document") if physical.get("error") is False else None,
            owner_confirmation=physical.get("confirmation") if physical.get("error") is False else None,
            movement_coverage=movement.get("coverage") if movement.get("error") is False else None,
            cutoff_evidence_id=cutoff_evidence_id,
            owner_supplier_receiving_confirmation=(
                owner_supplier_receiving_confirmation
            ),
            opening_composition_fingerprint=(
                opening.get("composition_fingerprint")
                if isinstance(opening, dict) and opening.get("error") is False
                else None
            ),
            source_fingerprints=tuple(sorted(set(fingerprints))),
            missing_requirements=tuple(sorted(set(missing))),
        )
        return {
            "error": False,
            "code": "FIFO_TRANSITION_EVIDENCE_LOADED" if not missing else "FIFO_TRANSITION_EVIDENCE_PARTIAL",
            "case_id": case_id,
            "case_revision": expected_case_revision,
            "bundle": bundle,
            "missing_requirements": bundle.missing_requirements,
            "source_fingerprints": bundle.source_fingerprints,
            "preview_only": True,
        }

    def build_cutoff_bridge(self, *, bundle, proposal):
        """Call the production bridge only when every typed source is present."""
        if not isinstance(bundle, FifoCostTransitionEvidenceBundle):
            return self._error("FIFO_TRANSITION_EVIDENCE_INVALID")
        bridge_missing = tuple(
            code for code in bundle.missing_requirements
            if not code.startswith("FINANCIAL_PERIOD_SUMMARY_")
            and code != "OWNER_SUPPLIER_RECEIVING_CONFIRMATION_REQUIRED"
        )
        if bridge_missing:
            return {
                "error": False, "result": None,
                "missing_requirements": bridge_missing,
            }
        if any(value is None for value in (
            bundle.stock_evidence, bundle.finance_batch,
            bundle.physical_sale_document, bundle.owner_confirmation,
            bundle.movement_coverage,
        )):
            return self._error("FIFO_TRANSITION_EVIDENCE_INVALID")
        if (
            getattr(proposal, "case_id", None) != bundle.case.case_id
            or getattr(proposal, "case_revision", None) != bundle.case.case_revision
            or getattr(proposal, "scope", None) != bundle.case.metadata.scope
            or getattr(proposal, "confirmed_cutoff_date", None) is None
        ):
            return self._error("FIFO_TRANSITION_PROPOSAL_STALE")
        requested_end = bundle.movement_coverage.complete_through
        result = self.transition_service.build_cutoff_bridge(
            case=bundle.case, proposal=proposal,
            stock_evidence=bundle.stock_evidence,
            finance_batch=bundle.finance_batch,
            physical_sale_document=bundle.physical_sale_document,
            owner_confirmation=bundle.owner_confirmation,
            movement_coverage=bundle.movement_coverage,
            owner_supplier_receiving_confirmation=(
                bundle.owner_supplier_receiving_confirmation
            ),
            requested_complete_through=requested_end,
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return result if isinstance(result, dict) else self._error(
                "FIFO_CUTOFF_BRIDGE_BUILD_FAILED",
            )
        bridge = result.get("result")
        return {
            "error": False,
            "result": bridge,
            "missing_requirements": tuple(
                "CUTOFF_BRIDGE:" + code for code in bridge.unresolved_issues
            ) if bridge.status != "READY" else (),
            "source_fingerprints": bundle.source_fingerprints,
            "preview_only": True,
        }

    def _read_period_profit_summaries(self, *, case_id, identity, scope):
        """Load encrypted, conflict-free monthly freezes without recalculation."""
        result = self.repository.read_transition_bridge_evidence(
            case_id=case_id, **identity,
            evidence_kind=TransitionBridgeEvidenceKind.PERIOD_SUMMARY_SNAPSHOT,
            limit=100, include_sensitive_payload=True,
        )
        if result.get("error"):
            return result
        items = result.get("items")
        if not isinstance(items, list) or len(items) > 100:
            return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
        if not items:
            return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_MISSING")

        expected_identity = self.transition_service._transition_identity_fingerprint(scope)
        by_period = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("payload"), dict):
                continue
            safe = item["payload"]
            if safe.get("report_type") != "PERIOD_PROFIT_FINANCIAL_SUMMARY":
                continue
            if (
                item.get("source_kind") != "DERIVED"
                or item.get("completeness") != EvidenceCompleteness.COMPLETE.value
            ):
                return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
            if item.get("sensitive_payload_available") is not True:
                return self._error(
                    item.get("blocker") or "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE",
                )
            period_from = item.get("period_from")
            period_to = item.get("period_to")
            if (
                not isinstance(period_from, str)
                or not isinstance(period_to, str)
                or len(period_from) < 7
                or period_from[:7] != period_to[:7]
            ):
                return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
            period = period_from[:7]
            identity_fingerprint = safe.get("identity_fingerprint")
            if identity_fingerprint != expected_identity:
                return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
            try:
                raw = json.loads(item.get("sensitive_payload") or "")
                if (
                    not isinstance(raw, dict)
                    or raw.get("schema_version") != 1
                    or raw.get("identity_fingerprint") != expected_identity
                    or not isinstance(raw.get("summary"), dict)
                ):
                    raise ValueError
                summary = self._period_summary_from_payload(raw["summary"])
                if (
                    summary.period != period
                    or summary.period_from != period_from
                    or summary.period_to != period_to
                    or summary.source_fingerprint != item.get("source_fingerprint")
                    or safe.get("summary_fingerprint") != summary.source_fingerprint
                    or item.get("row_count") != 1
                    or safe.get("row_count") != 1
                    or safe.get("period_from") != period_from
                    or safe.get("period_to") != period_to
                ):
                    raise ValueError
            except (TypeError, ValueError, KeyError, OverflowError):
                return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
            existing = by_period.get(period)
            if existing is not None and existing.source_fingerprint != summary.source_fingerprint:
                return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_CONFLICT")
            by_period[period] = summary

        if not by_period:
            return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_MISSING")
        summaries = tuple(by_period[period] for period in sorted(by_period))
        return {
            "error": False,
            "code": "FIFO_PERIOD_SUMMARY_SNAPSHOTS_READY",
            "summaries": summaries,
            "fingerprints": tuple(sorted({
                summary.source_fingerprint for summary in summaries
            })),
            "periods": tuple(summary.period for summary in summaries),
            "read_only": True,
        }

    @staticmethod
    def _period_summary_from_payload(raw):
        if not isinstance(raw, dict):
            raise ValueError("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
        return FifoFinancialPeriodSummary(
            period_from=raw.get("period_from"),
            period_to=raw.get("period_to"),
            source_fingerprint=raw.get("source_fingerprint"),
            reconstruction_fingerprint=raw.get("reconstruction_fingerprint"),
            tax_policy_fingerprint=raw.get("tax_policy_fingerprint"),
            sale_identity_digests=tuple(raw.get("sale_identity_digests") or ()),
            revenue_rub=raw.get("revenue"),
            discount_points_rub=raw.get("discount_points"),
            net_accrual_rub=raw.get("net_accrual"),
            current_total_product_cost_rub=raw.get("current_total_product_cost"),
            current_sku_product_cost_rub=raw.get("current_sku_product_cost"),
            complete=raw.get("complete"),
        )

    def _read_finance_identity(self, *, case_id, identity, scope):
        result = self.repository.read_transition_bridge_evidence(
            case_id=case_id, **identity,
            evidence_kind=TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT,
            limit=100, include_sensitive_payload=True,
        )
        if result.get("error"):
            return result
        items = result.get("items")
        if not isinstance(items, list) or len(items) > 100:
            return self._error("FIFO_FINANCE_IDENTITY_EVIDENCE_LIMIT_REACHED")
        if not items:
            return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_MISSING")
        item = max(items, key=lambda value: value.get("evidence_revision", 0))
        if item.get("sensitive_payload_available") is not True:
            return self._error(item.get("blocker", "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE"))
        safe = item.get("payload")
        if (
            item.get("source_kind") != EvidenceSourceKind.OZON_API.value
            or not isinstance(safe, dict)
            or safe.get("identity_fingerprint")
            != self.transition_service._transition_identity_fingerprint(scope)
        ):
            return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_SCOPE_MISMATCH")
        try:
            payload = json.loads(item["sensitive_payload"])
            if not isinstance(payload, dict):
                return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_CORRUPT")
            rows = payload["rows"]
            source_batches = payload.get("source_batches")
            proof_source_fingerprints = payload.get("proof_source_fingerprints")
            proof_source_as_of_values = payload.get("proof_source_as_of_values")
            proof_source_fingerprint = payload.get("proof_source_fingerprint")
            if (
                not isinstance(source_batches, list)
                or not source_batches
                or len(source_batches) > self.MAX_FINANCE_BATCHES
                or not isinstance(proof_source_fingerprints, list)
                or len(proof_source_fingerprints) != len(source_batches)
                or not isinstance(proof_source_as_of_values, list)
                or len(proof_source_as_of_values) != len(source_batches)
                or any(not isinstance(value, str) for value in (*source_batches, *proof_source_fingerprints))
            ):
                return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_CORRUPT")
            expected_proof_fingerprint = source_fingerprint({
                "kind": "FIFO_FINANCE_IDENTITY_PROOF_SET_V1",
                "source_proofs": proof_source_fingerprints,
                "source_as_of": proof_source_as_of_values,
                "scope_complete": safe.get("scope_complete"),
                "pagination_complete": safe.get("pagination_complete"),
            })
            expected_batch_fingerprint = source_fingerprint({
                "kind": "FIFO_FINANCE_IDENTITY_BATCH_SET_V1",
                "source_batches": source_batches,
                "rows_fingerprint": payload.get("rows_fingerprint"),
                "period_from": item.get("period_from"),
                "period_to": item.get("period_to"),
                "source_complete": payload.get("source_complete"),
            })
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version") not in {1, 2}
                or not isinstance(rows, list)
                or len(rows) != safe.get("row_count")
                or source_fingerprint(rows) != payload.get("rows_fingerprint")
                or payload.get("source_complete") is not (
                    item.get("completeness") == EvidenceCompleteness.COMPLETE.value
                )
                or payload.get("batch_fingerprint") != item.get("source_fingerprint")
                or payload.get("proof_source_fingerprint") != expected_proof_fingerprint
                or proof_source_fingerprint != expected_proof_fingerprint
                or payload.get("batch_fingerprint") != expected_batch_fingerprint
                or (len(rows) or None) != item.get("row_count")
                or safe.get("page_count") != len(source_batches)
            ):
                return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_CORRUPT")
            if (
                item.get("completeness") != EvidenceCompleteness.COMPLETE.value
                or safe.get("scope_complete") is not True
                or safe.get("pagination_complete") is not True
            ):
                return self._error("FIFO_FINANCE_IDENTITY_COVERAGE_INCOMPLETE")
            identities = []
            for row in rows:
                base_keys = {
                    "posting_number", "finance_sku", "offer_id", "product_id",
                }
                expected_keys = base_keys | (
                    {"financial_period"}
                    if payload.get("schema_version") == 2 else set()
                )
                if not isinstance(row, dict) or set(row) != expected_keys:
                    return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_CORRUPT")
                identities.append(FifoFinanceSaleIdentity(**row))
            proof_fp = payload["proof_source_fingerprint"]
            proof_metadata = TransitionMetadata(
                scope=scope, source_kind=EvidenceSourceKind.OZON_API,
                completeness=EvidenceCompleteness(item["completeness"]),
                source_fingerprint=proof_fp,
                store_timezone=self._case_timezone(case_id, identity),
            )
            proof = SourceProof(
                metadata=proof_metadata,
                scope_complete=safe["scope_complete"],
                pagination_complete=safe["pagination_complete"],
                source_as_of=payload.get("proof_source_as_of"),
            )
            metadata = TransitionMetadata(
                scope=scope, source_kind=EvidenceSourceKind.OZON_API,
                completeness=EvidenceCompleteness(item["completeness"]),
                source_fingerprint=item["source_fingerprint"],
                store_timezone=self._case_timezone(case_id, identity),
            )
            batch = FifoFinanceSaleIdentityBatch(
                metadata=metadata,
                source_fingerprint=item["source_fingerprint"],
                period_from=item["period_from"], period_to=item["period_to"],
                source_as_of=payload.get("proof_source_as_of"),
                proof=proof, rows=tuple(identities),
            )
            if (
                batch.period_from != item.get("period_from")
                or batch.period_to != item.get("period_to")
                or batch.source_as_of != payload.get("proof_source_as_of")
            ):
                return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_CORRUPT")
        except (TypeError, ValueError, KeyError, OverflowError):
            return self._error("FIFO_FINANCE_IDENTITY_SNAPSHOT_CORRUPT")
        return {
            "error": False, "batch": batch,
            "fingerprint": item["payload_fingerprint"],
        }

    def _read_physical_document(self, *, case_id, identity, scope, case):
        listed = self.repository.read_transition_bridge_evidence(
            case_id=case_id, **identity,
            evidence_kind=TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT,
            limit=100,
        )
        if listed.get("error"):
            return listed
        items = listed.get("items")
        if not isinstance(items, list) or len(items) > 100:
            return self._error("FIFO_PHYSICAL_SALES_EVIDENCE_LIMIT_REACHED")
        if not items:
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_MISSING")
        candidates = []
        found_unconfirmed = False
        for item in items:
            read = self.physical_sales_service.read_document(
                repository=self.repository, case_id=case_id,
                scope=scope, evidence_id=item["evidence_id"],
            )
            if read.get("error"):
                return read
            if not read.get("confirmed"):
                found_unconfirmed = True
                continue
            confirmations = [
                value for value in item.get("confirmations", ())
                if value.get("confirmation_kind")
                == TransitionEvidenceConfirmationKind.PHYSICAL_SALES.value
                and value.get("confirmed_fields") == read.get("confirmed_fields")
            ]
            if not confirmations:
                return self._error("FIFO_PHYSICAL_SALES_CONFIRMATION_CORRUPT")
            document_period_from = item.get("period_from")
            if (
                isinstance(document_period_from, str)
                and document_period_from <= (case.dispatch_date or document_period_from)
            ):
                candidates.append((item, read, confirmations[-1]))
        if len(candidates) != 1:
            if not candidates and found_unconfirmed:
                return self._error("FIFO_PHYSICAL_SALES_CONFIRMATION_REQUIRED")
            if not candidates:
                return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_MISSING")
            return self._error("FIFO_PHYSICAL_SALES_DOCUMENT_CONFLICT")
        item, read, confirmed = candidates[0]
        document = read["document"]
        try:
            bridge_rows = tuple(FifoDocumentedPhysicalSaleRow(
                posting_number=row.posting_number,
                finance_sku=row.finance_sku,
                quantity=row.quantity,
                physical_effective_date=row.physical_effective_date,
                row_reference=row.row_reference,
            ) for row in document.rows)
            bridge_document = FifoDocumentedPhysicalSaleDocument(
                metadata=TransitionMetadata(
                    scope=scope, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                    completeness=EvidenceCompleteness.COMPLETE,
                    source_fingerprint=document.document_fingerprint,
                    store_timezone=case.metadata.store_timezone,
                ),
                case_id=case_id,
                document_kind="OWNER_DOCUMENTED_PHYSICAL_SALES_V1",
                document_fingerprint=document.document_fingerprint,
                parser_version="fifo-owner-physical-sales-v1",
                period_from=item["period_from"], period_to=item["period_to"],
                rows=bridge_rows,
            )
            fields = read["confirmed_fields"]
            confirmation = FifoPhysicalSaleDocumentConfirmation(
                metadata=TransitionMetadata(
                    scope=scope, source_kind=EvidenceSourceKind.OWNER_INPUT,
                    completeness=EvidenceCompleteness.COMPLETE,
                    source_fingerprint=document.document_fingerprint,
                    store_timezone=case.metadata.store_timezone,
                ),
                owner_id=scope.owner_id, case_id=case_id,
                document_fingerprint=document.document_fingerprint,
                confirmed_row_references=tuple(sorted(
                    row.row_reference for row in bridge_rows
                )),
                confirmed_fields=frozenset({
                    "posting_number", "finance_sku", "quantity", "physical_effective_date",
                }),
                physical_date_semantics=fields["semantics"],
                physical_date_timezone=fields["timezone"],
                physical_date_precision="STORE_LOCAL_DATE",
                confirmed_at=confirmed["confirmed_at"],
            )
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_PHYSICAL_SALES_CONFIRMATION_CORRUPT")
        return {
            "error": False, "document": bridge_document,
            "confirmation": confirmation,
            "fingerprint": item["payload_fingerprint"],
        }

    def _read_movement_coverage(self, *, case_id, identity, scope, case):
        result = self.repository.read_transition_bridge_evidence(
            case_id=case_id, **identity,
            evidence_kind=TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE,
            limit=100, include_sensitive_payload=True,
        )
        if result.get("error"):
            return result
        items = result.get("items")
        if not isinstance(items, list) or len(items) > 100:
            return self._error("FIFO_MOVEMENT_COVERAGE_EVIDENCE_LIMIT_REACHED")
        if not items:
            return self._error("FIFO_MOVEMENT_COVERAGE_SNAPSHOT_MISSING")
        item = max(items, key=lambda value: value.get("evidence_revision", 0))
        safe = item.get("payload")
        if item.get("sensitive_payload_available") is not True:
            return self._error(item.get("blocker", "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE"))
        if (
            not isinstance(safe, dict)
            or safe.get("identity_fingerprint")
            != self.transition_service._transition_identity_fingerprint(scope)
        ):
            return self._error("FIFO_MOVEMENT_COVERAGE_SCOPE_MISMATCH")
        expected_fields = {
            "coverage_fingerprint": safe.get("snapshot_fingerprint"),
            "complete_through": safe.get("complete_through"),
            "event_count": safe.get("event_count"),
        }
        if not any(
            row.get("confirmation_kind") == TransitionEvidenceConfirmationKind.MOVEMENT_COVERAGE.value
            and row.get("confirmed_fields") == expected_fields
            for row in item.get("confirmations", ())
        ):
            return self._error("FIFO_MOVEMENT_COVERAGE_CONFIRMATION_REQUIRED")
        try:
            payload = json.loads(item["sensitive_payload"])
            if not isinstance(payload, dict):
                return self._error("FIFO_MOVEMENT_COVERAGE_SNAPSHOT_CORRUPT")
            movements_data = payload["movements"]
            expected_coverage_fingerprint = source_fingerprint({
                "source_fingerprint": payload.get("source_fingerprint"),
                "period_from": safe.get("period_from"),
                "complete_through": safe.get("complete_through"),
                "page_count": safe.get("page_count"),
                "scope_complete": safe.get("scope_complete"),
                "pagination_complete": safe.get("pagination_complete"),
                "source_as_of": payload.get("proof_source_as_of"),
                "movements_fingerprint": payload.get("movements_fingerprint"),
            })
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version") != 1
                or payload.get("coverage_fingerprint") != item.get("source_fingerprint")
                or payload.get("coverage_fingerprint") != safe.get("snapshot_fingerprint")
                or payload.get("coverage_fingerprint") != expected_coverage_fingerprint
                or item.get("period_from") != safe.get("period_from")
                or item.get("period_to") != safe.get("complete_through")
                or item.get("complete_through") != safe.get("complete_through")
                or item.get("row_count") != (safe.get("event_count") or None)
                or payload.get("source_fingerprint") != payload.get("proof_source_fingerprint")
                or payload.get("movements_fingerprint") is None
                or source_fingerprint(movements_data) != payload["movements_fingerprint"]
                or len(movements_data) != safe.get("event_count")
            ):
                return self._error("FIFO_MOVEMENT_COVERAGE_SNAPSHOT_CORRUPT")
            proof_fp = payload["proof_source_fingerprint"]
            proof_metadata = TransitionMetadata(
                scope=scope, source_kind=EvidenceSourceKind(item["source_kind"]),
                completeness=EvidenceCompleteness(item["completeness"]),
                source_fingerprint=proof_fp,
                store_timezone=case.metadata.store_timezone,
            )
            proof = SourceProof(
                metadata=proof_metadata,
                scope_complete=safe["scope_complete"],
                pagination_complete=safe["pagination_complete"],
                source_as_of=payload.get("proof_source_as_of"),
            )
            movements = tuple(FifoCutoffMovementReference(**row) for row in movements_data)
            coverage = FifoCutoffMovementCoverage(
                scope=scope, period_from=safe["period_from"],
                complete_through=safe["complete_through"],
                source_fingerprint=payload["source_fingerprint"],
                proof=proof, movements=movements,
                page_count=safe["page_count"],
            )
            if coverage.source_fingerprint != proof.metadata.source_fingerprint:
                return self._error("FIFO_MOVEMENT_COVERAGE_SNAPSHOT_CORRUPT")
        except (TypeError, ValueError, KeyError, OverflowError):
            return self._error("FIFO_MOVEMENT_COVERAGE_SNAPSHOT_CORRUPT")
        if (
            not coverage.proof.api_read_complete
            or coverage.period_from > (case.dispatch_date or coverage.period_from)
        ):
            return self._error("FIFO_MOVEMENT_COVERAGE_INCOMPLETE")
        return {"error": False, "coverage": coverage, "fingerprint": item["payload_fingerprint"]}

    def _case_context(
        self, *, case_id, identity, expected_case_revision,
        sealed_preview_id=None,
    ):
        if (
            not isinstance(identity, dict)
            or set(identity) != self._IDENTITY_KEYS
            or type(expected_case_revision) is not int
            or expected_case_revision < 1
        ):
            return self._error("FIFO_TRANSITION_EVIDENCE_INPUT_INVALID")
        current = self.transition_service.get_case(case_id=case_id, **identity)
        if current.get("error"):
            return current
        case_payload = current.get("case")
        if sealed_preview_id is None:
            if current.get("case_revision") != expected_case_revision:
                return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        else:
            last_preview = (
                case_payload.get("last_preview")
                if isinstance(case_payload, dict) else None
            )
            if (
                current.get("state") != "READY_TO_CONFIRM"
                or current.get("case_revision") != expected_case_revision + 1
                or not isinstance(last_preview, dict)
                or last_preview.get("preview_id") != sealed_preview_id
            ):
                return self._error("FIFO_TRANSITION_PREVIEW_STALE")
            sealed = self.repository.read_transition_preview(
                case_id=case_id, preview_id=sealed_preview_id, **identity,
            )
            preview = sealed.get("preview") if sealed.get("error") is False else None
            row = sealed.get("sealed_preview") if sealed.get("error") is False else None
            if (
                not isinstance(preview, dict)
                or not isinstance(row, dict)
                or sealed.get("is_current") is not True
                or sealed.get("expired") is True
                or row.get("case_revision") != current.get("case_revision")
                or preview.get("case_revision") != expected_case_revision
                or row.get("preview_fingerprint") != last_preview.get(
                    "preview_fingerprint",
                )
            ):
                return self._error("FIFO_TRANSITION_PREVIEW_STALE")
            historical = self.transition_service.get_case_revision(
                case_id=case_id, **identity,
                case_revision=expected_case_revision,
            )
            if historical.get("error"):
                return historical
            if historical.get("state") not in {"DRAFT", "AWAITING_EVIDENCE"}:
                return self._error("FIFO_TRANSITION_CASE_CORRUPT")
            case_payload = historical.get("case")
        try:
            case = self.transition_service._case_from_payload(case_payload)
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
        if any(getattr(case.metadata.scope, key) != value for key, value in identity.items()):
            return self._error("FIFO_TRANSITION_SCOPE_MISMATCH")
        return {
            "error": False, "case": case,
            "current_case_revision": current.get("case_revision"),
            "basis_case_revision": expected_case_revision,
        }

    def _case_timezone(self, case_id, identity):
        current = self.transition_service.get_case(case_id=case_id, **identity)
        if current.get("error"):
            raise ValueError("FIFO_TRANSITION_CASE_UNAVAILABLE")
        return self.transition_service._case_from_payload(current["case"]).metadata.store_timezone

    @staticmethod
    def _movement_payload(item):
        return {
            "movement_kind": item.movement_kind,
            "movement_fingerprint": item.movement_fingerprint,
            "source_identity_digest": item.source_identity_digest,
            "linked_sale_identity_digest": item.linked_sale_identity_digest,
            "quantity": item.quantity,
            "effective_date": item.effective_date,
        }

    @staticmethod
    def _json(value):
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
