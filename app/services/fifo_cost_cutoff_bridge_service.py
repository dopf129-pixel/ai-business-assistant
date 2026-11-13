"""Proof-bound bridge between a physical inventory cutoff and finance sales.

This module is intentionally read-only.  The realization adapter contributes
sale identity only; physical dates and quantities must come from an exact,
separately owner-confirmed document.  No finance/accrual date is promoted to
physical timing here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
import re
from types import MappingProxyType
from typing import Mapping

from services.fifo_cost_sale_evidence_normalizer import FifoCostSaleEvidenceNormalizer
from services.fifo_cost_transition_opening_proposal_service import (
    FifoCostTransitionOpeningProposal,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SourceProof,
    StockBucket,
    TransitionCase,
    TransitionMetadata,
    TransitionState,
    normalize_date_only,
    normalize_digest,
    normalize_quantity,
    normalize_store_timezone,
    normalize_utc_timestamp,
    source_fingerprint,
)


_OWNER_DOCUMENT_KIND = "OWNER_DOCUMENTED_PHYSICAL_SALES_V1"
_OWNER_CONFIRMED_FIELDS = frozenset({
    "posting_number", "finance_sku", "quantity", "physical_effective_date",
})
_STOCK_SOURCE_BUCKET_KEYS = frozenset({
    *(bucket.value for bucket in StockBucket),
    "marking_pending_withdrawal", "marking_pending_documents", "expiring",
    "defective_supply", "defective_stock", "unidentified_supply_surplus",
    "seller_withdrawal_preparing", "seller_withdrawal_ready", "seller_return_transit",
})
_ROW_REF_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
_MAX_IDENTITY_ROWS = 100_000
_MAX_OWNER_ROWS = 100_000
_MAX_MOVEMENTS = 100_000


@dataclass(frozen=True, slots=True)
class FifoFinanceSaleIdentity:
    """Transient identity extracted from an exact realization posting row."""

    posting_number: str = field(repr=False)
    finance_sku: str
    offer_id: str | None
    product_id: str | None

    def __post_init__(self):
        for name in ("posting_number", "finance_sku"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
                raise ValueError("FIFO_CUTOFF_BRIDGE_IDENTITY_INVALID")
            object.__setattr__(self, name, value.strip())
        for name in ("offer_id", "product_id"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
                    raise ValueError("FIFO_CUTOFF_BRIDGE_IDENTITY_INVALID")
                object.__setattr__(self, name, value.strip())
        if self.offer_id is None and self.product_id is None:
            raise ValueError("FIFO_CUTOFF_BRIDGE_IDENTITY_INVALID")


@dataclass(frozen=True, slots=True)
class FifoFinanceSaleIdentityBatch:
    metadata: TransitionMetadata
    source_fingerprint: str
    period_from: str
    period_to: str
    source_as_of: str | None
    proof: SourceProof
    rows: tuple[FifoFinanceSaleIdentity, ...]

    def __post_init__(self):
        object.__setattr__(self, "source_fingerprint", normalize_digest(self.source_fingerprint))
        if (
            not isinstance(self.metadata, TransitionMetadata)
            or self.metadata.source_kind is not EvidenceSourceKind.OZON_API
            or self.metadata.completeness is not EvidenceCompleteness.COMPLETE
            or self.metadata.source_fingerprint != self.source_fingerprint
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_INVALID")
        start = normalize_date_only(self.period_from)
        end = normalize_date_only(self.period_to)
        if end < start:
            raise ValueError("FIFO_CUTOFF_BRIDGE_PERIOD_INVALID")
        object.__setattr__(self, "period_from", start)
        object.__setattr__(self, "period_to", end)
        if self.source_as_of is not None:
            object.__setattr__(self, "source_as_of", normalize_utc_timestamp(self.source_as_of))
        if not isinstance(self.proof, SourceProof):
            raise ValueError("FIFO_CUTOFF_BRIDGE_COVERAGE_INVALID")
        if self.proof.metadata.scope != self.metadata.scope:
            raise ValueError("FIFO_CUTOFF_BRIDGE_SCOPE_MISMATCH")
        if self.proof.metadata.source_kind is not EvidenceSourceKind.OZON_API:
            raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_INVALID")
        if self.proof.source_as_of != self.source_as_of:
            raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_AS_OF_MISMATCH")
        rows = tuple(self.rows)
        if len(rows) > _MAX_IDENTITY_ROWS or any(
            not isinstance(row, FifoFinanceSaleIdentity) for row in rows
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_ROWS_INVALID")
        object.__setattr__(self, "rows", rows)

    @property
    def metadata_scope(self):
        return self.metadata.scope


class FifoCutoffBridgeSourceAdapter:
    """Allowlisted, non-financial parsing for realization identity rows."""

    def parse_realization_postings(
        self, *, response, scope: ScopeIdentity, proof: SourceProof,
        period_from, period_to, source_as_of=None,
        confirmed_finance_sku_mappings=None,
    ) -> FifoFinanceSaleIdentityBatch:
        if not isinstance(scope, ScopeIdentity) or not isinstance(proof, SourceProof):
            raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_INVALID")
        if proof.metadata.scope != scope or proof.metadata.source_kind is not EvidenceSourceKind.OZON_API:
            raise ValueError("FIFO_CUTOFF_BRIDGE_SCOPE_MISMATCH")
        if not isinstance(response, Mapping) or response.get("error") is True:
            raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_UNAVAILABLE")
        rows = response.get("rows")
        if rows is None and isinstance(response.get("result"), Mapping):
            rows = response["result"].get("rows")
        if not isinstance(rows, list) or len(rows) > _MAX_IDENTITY_ROWS:
            raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_FORMAT_INVALID")

        if confirmed_finance_sku_mappings is None:
            confirmed_finance_sku_mappings = {}
        if not isinstance(confirmed_finance_sku_mappings, Mapping):
            raise ValueError("FIFO_CUTOFF_BRIDGE_SKU_MAPPING_INVALID")
        identities = []
        alias_material = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_FORMAT_INVALID")
            order, item = row.get("order"), row.get("item")
            if not isinstance(order, Mapping) or not isinstance(item, Mapping):
                raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_FORMAT_INVALID")
            finance_sku = self._safe_source_text(item.get("sku"))
            if finance_sku is None:
                raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_FORMAT_INVALID")
            posting_number = self._safe_source_text(order.get("posting_number"))
            offer_id = self._safe_source_text(item.get("offer_id"))
            product_id = self._safe_source_text(item.get("product_id"))
            if posting_number is None or (offer_id is None and product_id is None):
                raise ValueError("FIFO_CUTOFF_BRIDGE_SOURCE_FORMAT_INVALID")
            matches_scope = (
                offer_id == scope.offer_id if scope.offer_id is not None
                else product_id == scope.product_id
            )
            if not matches_scope:
                continue
            if scope.product_id is not None and product_id not in (None, scope.product_id):
                raise ValueError("FIFO_CUTOFF_BRIDGE_PRODUCT_IDENTITY_CONFLICT")
            if finance_sku != scope.sku:
                mapping = confirmed_finance_sku_mappings.get(finance_sku)
                if not self._mapping_confirms_scope(mapping, finance_sku, scope):
                    # Do not silently discard a posting that otherwise belongs
                    # to this exact product. A complete API page is not proof
                    # that the selected SKU's historical aliases were covered.
                    raise ValueError("FIFO_CUTOFF_BRIDGE_FINANCE_SKU_ALIAS_UNCONFIRMED")
                alias_material[finance_sku] = {
                    key: mapping.get(key)
                    for key in ("mapping_id", "source", "confirmed_at")
                    if isinstance(mapping.get(key), (str, int))
                }
            identities.append(FifoFinanceSaleIdentity(
                posting_number=posting_number,
                finance_sku=finance_sku,
                offer_id=offer_id,
                product_id=product_id,
            ))

        if not proof.api_read_complete:
            raise ValueError("FIFO_CUTOFF_BRIDGE_COVERAGE_INCOMPLETE")
        batch_fingerprint = source_fingerprint({
            "source": proof.metadata.source_fingerprint,
            "period_from": period_from,
            "period_to": period_to,
            "confirmed_finance_sku_mappings": alias_material,
            "rows": [
                self._identity_material(row)
                for row in sorted(identities, key=lambda item: (
                    item.posting_number, item.finance_sku,
                    item.offer_id or "", item.product_id or "",
                ))
            ],
        })
        return FifoFinanceSaleIdentityBatch(
            metadata=TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OZON_API,
                completeness=EvidenceCompleteness.COMPLETE,
                source_fingerprint=batch_fingerprint,
                store_timezone=proof.metadata.store_timezone,
            ),
            source_fingerprint=batch_fingerprint,
            period_from=period_from,
            period_to=period_to,
            source_as_of=source_as_of,
            proof=proof,
            rows=tuple(identities),
        )

    @staticmethod
    def _mapping_confirms_scope(mapping, finance_sku, scope):
        if not isinstance(mapping, Mapping) or (
            mapping.get("mapping_confirmed") is not True
            or mapping.get("seller_confirmed") is not True
            or str(mapping.get("finance_sku") or "").strip() != finance_sku
            or str(mapping.get("current_sku") or "").strip() != scope.sku
        ):
            return False
        if scope.product_id is not None and str(
            mapping.get("current_product_id") or ""
        ).strip() != scope.product_id:
            return False
        if scope.offer_id is not None and mapping.get("current_offer_id") not in (
            None, scope.offer_id,
        ):
            return False
        return True

    @staticmethod
    def _identity_material(row):
        return {
            "posting_number": row.posting_number,
            "finance_sku": row.finance_sku,
            "offer_id": row.offer_id,
            "product_id": row.product_id,
        }

    @staticmethod
    def _safe_source_text(value):
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        if not text or len(text) > 256 or any(ord(ch) < 32 for ch in text):
            return None
        return text


@dataclass(frozen=True, slots=True)
class FifoDocumentedPhysicalSaleRow:
    posting_number: str = field(repr=False)
    finance_sku: str
    quantity: int
    physical_effective_date: str
    row_reference: str

    def __post_init__(self):
        for name in ("posting_number", "finance_sku"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
                raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_ROW_INVALID")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(self, "quantity", normalize_quantity(self.quantity))
        if self.quantity < 1:
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_ROW_INVALID")
        object.__setattr__(self, "physical_effective_date", normalize_date_only(self.physical_effective_date))
        if not isinstance(self.row_reference, str) or not _ROW_REF_RE.fullmatch(self.row_reference):
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_ROW_INVALID")


@dataclass(frozen=True, slots=True)
class FifoDocumentedPhysicalSaleDocument:
    metadata: TransitionMetadata
    case_id: str
    document_kind: str
    document_fingerprint: str
    parser_version: str
    period_from: str
    period_to: str
    rows: tuple[FifoDocumentedPhysicalSaleRow, ...]

    def __post_init__(self):
        document_fingerprint = normalize_digest(self.document_fingerprint)
        object.__setattr__(self, "document_fingerprint", document_fingerprint)
        if (
            not isinstance(self.metadata, TransitionMetadata)
            or self.metadata.source_kind is not EvidenceSourceKind.OWNER_IMPORTED
            or self.metadata.completeness is not EvidenceCompleteness.COMPLETE
            or self.metadata.source_fingerprint != document_fingerprint
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_INVALID")
        if self.document_kind != _OWNER_DOCUMENT_KIND:
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_UNSUPPORTED")
        if not isinstance(self.case_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", self.case_id):
            raise ValueError("FIFO_CUTOFF_BRIDGE_CASE_INVALID")
        if self.parser_version != "fifo-owner-physical-sales-v1":
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_UNSUPPORTED")
        start = normalize_date_only(self.period_from)
        end = normalize_date_only(self.period_to)
        if end < start:
            raise ValueError("FIFO_CUTOFF_BRIDGE_PERIOD_INVALID")
        object.__setattr__(self, "period_from", start)
        object.__setattr__(self, "period_to", end)
        rows = tuple(self.rows)
        if not rows or len(rows) > _MAX_OWNER_ROWS or any(
            not isinstance(row, FifoDocumentedPhysicalSaleRow) for row in rows
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_ROWS_INVALID")
        refs = [row.row_reference for row in rows]
        if len(refs) != len(set(refs)):
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_DUPLICATE_ROW")
        object.__setattr__(self, "rows", rows)

    @property
    def scope(self):
        return self.metadata.scope


class FifoCutoffBridgeDocumentParser:
    """Parse only the explicit, owner-documented exact-sale schema."""

    _TOP_LEVEL_KEYS = frozenset({
        "document_kind", "document_fingerprint", "parser_version",
        "period_from", "period_to", "rows",
    })
    _ROW_KEYS = frozenset({
        "posting_number", "finance_sku", "quantity", "physical_effective_date",
        "row_reference",
    })

    def parse(self, *, payload, scope, case_id) -> FifoDocumentedPhysicalSaleDocument:
        if not isinstance(payload, Mapping) or set(payload) != self._TOP_LEVEL_KEYS:
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_FORMAT_INVALID")
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list) or len(raw_rows) > _MAX_OWNER_ROWS:
            raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_FORMAT_INVALID")
        rows = []
        for row in raw_rows:
            if not isinstance(row, Mapping) or set(row) != self._ROW_KEYS:
                raise ValueError("FIFO_CUTOFF_BRIDGE_DOCUMENT_FORMAT_INVALID")
            rows.append(FifoDocumentedPhysicalSaleRow(**row))
        return FifoDocumentedPhysicalSaleDocument(
            metadata=TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.COMPLETE,
                source_fingerprint=payload["document_fingerprint"],
            ),
            case_id=case_id,
            document_kind=payload["document_kind"],
            document_fingerprint=payload["document_fingerprint"],
            parser_version=payload["parser_version"],
            period_from=payload["period_from"],
            period_to=payload["period_to"],
            rows=tuple(rows),
        )


@dataclass(frozen=True, slots=True)
class FifoPhysicalSaleDocumentConfirmation:
    metadata: TransitionMetadata
    owner_id: str
    case_id: str
    document_fingerprint: str
    confirmed_row_references: tuple[str, ...]
    confirmed_fields: frozenset[str]
    physical_date_semantics: str
    physical_date_timezone: str
    physical_date_precision: str
    confirmed_at: str

    def __post_init__(self):
        document_fingerprint = normalize_digest(self.document_fingerprint)
        object.__setattr__(self, "document_fingerprint", document_fingerprint)
        if (
            not isinstance(self.metadata, TransitionMetadata)
            or self.metadata.source_kind is not EvidenceSourceKind.OWNER_INPUT
            or self.metadata.completeness is not EvidenceCompleteness.COMPLETE
            or self.metadata.scope.owner_id != self.owner_id
            or not isinstance(self.case_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", self.case_id)
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_CONFIRMATION_INVALID")
        object.__setattr__(self, "confirmed_at", normalize_utc_timestamp(self.confirmed_at))
        refs = tuple(self.confirmed_row_references)
        if any(not isinstance(ref, str) or not _ROW_REF_RE.fullmatch(ref) for ref in refs):
            raise ValueError("FIFO_CUTOFF_BRIDGE_CONFIRMATION_INVALID")
        if len(refs) != len(set(refs)):
            raise ValueError("FIFO_CUTOFF_BRIDGE_CONFIRMATION_INVALID")
        object.__setattr__(self, "confirmed_row_references", refs)
        fields = frozenset(self.confirmed_fields)
        if fields != _OWNER_CONFIRMED_FIELDS:
            raise ValueError("FIFO_CUTOFF_BRIDGE_CONFIRMATION_INVALID")
        object.__setattr__(self, "confirmed_fields", fields)
        if self.physical_date_semantics != "PHYSICAL_OUTFLOW":
            raise ValueError("FIFO_CUTOFF_BRIDGE_CONFIRMATION_INVALID")
        object.__setattr__(
            self, "physical_date_timezone", normalize_store_timezone(self.physical_date_timezone),
        )
        if self.physical_date_precision != "STORE_LOCAL_DATE":
            raise ValueError("FIFO_CUTOFF_BRIDGE_CONFIRMATION_INVALID")

    @property
    def scope(self):
        return self.metadata.scope


@dataclass(frozen=True, slots=True)
class FifoCutoffMovementReference:
    movement_kind: str
    movement_fingerprint: str
    source_identity_digest: str | None
    linked_sale_identity_digest: str | None
    quantity: int
    effective_date: str

    def __post_init__(self):
        if self.movement_kind not in {"RETURN", "SELLER_WITHDRAWAL", "DAMAGE", "TRANSFER"}:
            raise ValueError("FIFO_CUTOFF_BRIDGE_MOVEMENT_INVALID")
        object.__setattr__(self, "movement_fingerprint", normalize_digest(self.movement_fingerprint))
        if self.source_identity_digest is not None:
            object.__setattr__(self, "source_identity_digest", normalize_digest(self.source_identity_digest))
        if self.linked_sale_identity_digest is not None:
            object.__setattr__(self, "linked_sale_identity_digest", normalize_digest(self.linked_sale_identity_digest))
        object.__setattr__(self, "quantity", normalize_quantity(self.quantity))
        if self.quantity < 1:
            raise ValueError("FIFO_CUTOFF_BRIDGE_MOVEMENT_INVALID")
        object.__setattr__(self, "effective_date", normalize_date_only(self.effective_date))


@dataclass(frozen=True, slots=True)
class FifoCutoffMovementCoverage:
    scope: ScopeIdentity
    period_from: str
    complete_through: str
    source_fingerprint: str
    proof: SourceProof
    movements: tuple[FifoCutoffMovementReference, ...] = ()

    def __post_init__(self):
        start = normalize_date_only(self.period_from)
        end = normalize_date_only(self.complete_through)
        if end < start:
            raise ValueError("FIFO_CUTOFF_BRIDGE_PERIOD_INVALID")
        object.__setattr__(self, "period_from", start)
        object.__setattr__(self, "complete_through", end)
        object.__setattr__(self, "source_fingerprint", normalize_digest(self.source_fingerprint))
        if not isinstance(self.proof, SourceProof) or self.proof.metadata.scope != self.scope:
            raise ValueError("FIFO_CUTOFF_BRIDGE_COVERAGE_INVALID")
        if self.source_fingerprint != self.proof.metadata.source_fingerprint:
            raise ValueError("FIFO_CUTOFF_BRIDGE_COVERAGE_INVALID")
        movements = tuple(self.movements)
        if len(movements) > _MAX_MOVEMENTS or any(
            not isinstance(item, FifoCutoffMovementReference) for item in movements
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_MOVEMENTS_INVALID")
        object.__setattr__(self, "movements", movements)

    @property
    def metadata(self):
        return self.proof.metadata


@dataclass(frozen=True, slots=True)
class FifoCutoffBridgeEvent:
    source_identity_digest: str
    quantity: int
    physical_effective_date: str
    finance_source_fingerprint: str
    document_fingerprint: str
    document_row_reference: str

    def __post_init__(self):
        object.__setattr__(self, "source_identity_digest", normalize_digest(self.source_identity_digest))
        object.__setattr__(self, "quantity", normalize_quantity(self.quantity))
        if self.quantity < 1:
            raise ValueError("FIFO_CUTOFF_BRIDGE_EVENT_INVALID")
        object.__setattr__(self, "physical_effective_date", normalize_date_only(self.physical_effective_date))
        object.__setattr__(self, "finance_source_fingerprint", normalize_digest(self.finance_source_fingerprint))
        object.__setattr__(self, "document_fingerprint", normalize_digest(self.document_fingerprint))
        if not isinstance(self.document_row_reference, str) or not _ROW_REF_RE.fullmatch(self.document_row_reference):
            raise ValueError("FIFO_CUTOFF_BRIDGE_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class FifoCutoffDescriptor:
    metadata: TransitionMetadata
    case_id: str
    case_revision: int
    cutoff_date: str | None
    timezone: str
    precision: str
    boundary: str

    def __post_init__(self):
        if (
            not isinstance(self.metadata, TransitionMetadata)
            or self.metadata.source_kind is not EvidenceSourceKind.OWNER_INPUT
            or not isinstance(self.case_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", self.case_id)
            or type(self.case_revision) is not int
            or self.case_revision < 1
        ):
            raise ValueError("FIFO_CUTOFF_DESCRIPTOR_INVALID")
        if self.cutoff_date is not None:
            object.__setattr__(self, "cutoff_date", normalize_date_only(self.cutoff_date))
        object.__setattr__(self, "timezone", normalize_store_timezone(self.timezone))
        if self.precision != "STORE_LOCAL_DATE" or self.boundary != "END_OF_LOCAL_DATE":
            raise ValueError("FIFO_CUTOFF_DESCRIPTOR_INVALID")
        if (self.cutoff_date is None) == (
            self.metadata.completeness is EvidenceCompleteness.COMPLETE
        ):
            raise ValueError("FIFO_CUTOFF_DESCRIPTOR_INVALID")


@dataclass(frozen=True, slots=True)
class FifoCutoffBridgeResult:
    status: str
    scope: ScopeIdentity
    case_id: str
    case_revision: int
    cutoff_descriptor: FifoCutoffDescriptor
    complete_through: str | None
    confirmed_stock_buckets: Mapping[str, int | None]
    pre_cutoff_outflows: tuple[FifoCutoffBridgeEvent, ...]
    post_cutoff_events: tuple[FifoCutoffBridgeEvent, ...]
    finance_to_sale_identity_mappings: tuple[tuple[str, str], ...]
    linked_returns_non_sale_movements: tuple[object, ...]
    source_set_fingerprint: str
    unresolved_issues: tuple[str, ...]
    provenance_by_basis: Mapping[str, tuple[str, ...]]
    ready_for_fifo_event: bool
    preview_only: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.cutoff_descriptor, FifoCutoffDescriptor)
            or self.cutoff_descriptor.metadata.scope != self.scope
            or self.cutoff_descriptor.case_id != self.case_id
            or self.cutoff_descriptor.case_revision != self.case_revision
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_RESULT_INVALID")
        object.__setattr__(self, "confirmed_stock_buckets", MappingProxyType(dict(self.confirmed_stock_buckets)))
        object.__setattr__(self, "provenance_by_basis", MappingProxyType({
            key: tuple(value) for key, value in self.provenance_by_basis.items()
        }))
        object.__setattr__(self, "unresolved_issues", tuple(sorted(set(self.unresolved_issues))))
        if self.status not in {"READY", "SOURCE_BLOCKED"}:
            raise ValueError("FIFO_CUTOFF_BRIDGE_RESULT_INVALID")
        if self.complete_through is not None:
            object.__setattr__(self, "complete_through", normalize_date_only(self.complete_through))
        if self.ready_for_fifo_event != (self.status == "READY"):
            raise ValueError("FIFO_CUTOFF_BRIDGE_RESULT_INVALID")
        if self.ready_for_fifo_event and (
            self.unresolved_issues or self.complete_through is None
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_RESULT_INVALID")
        if not self.ready_for_fifo_event and self.complete_through is not None:
            raise ValueError("FIFO_CUTOFF_BRIDGE_RESULT_INVALID")
        if not self.preview_only:
            raise ValueError("FIFO_CUTOFF_BRIDGE_RESULT_INVALID")

    @property
    def cutoff_date(self):
        return self.cutoff_descriptor.cutoff_date

    @property
    def cutoff_timezone(self):
        return self.cutoff_descriptor.timezone

    @property
    def cutoff_precision(self):
        return self.cutoff_descriptor.precision

    @property
    def cutoff_boundary(self):
        return self.cutoff_descriptor.boundary


class FifoCostCutoffBridgeService:
    """Validate cutoff, exact sale identity, physical dates, and source coverage."""

    MAX_EVENTS = 100_000

    def __init__(self, *, source_adapter=None, document_parser=None, sale_normalizer=None):
        self.source_adapter = source_adapter or FifoCutoffBridgeSourceAdapter()
        self.document_parser = document_parser or FifoCutoffBridgeDocumentParser()
        self.sale_normalizer = sale_normalizer or FifoCostSaleEvidenceNormalizer()

    def build(
        self, *, case: TransitionCase, proposal, stock_evidence: ReportEvidence,
        finance_batch: FifoFinanceSaleIdentityBatch,
        physical_sale_document: FifoDocumentedPhysicalSaleDocument,
        owner_confirmation: FifoPhysicalSaleDocumentConfirmation,
        movement_coverage: FifoCutoffMovementCoverage,
        requested_complete_through: str,
    ) -> FifoCutoffBridgeResult:
        if not isinstance(case, TransitionCase) or case.state not in {
            TransitionState.DRAFT, TransitionState.AWAITING_EVIDENCE,
        }:
            raise ValueError("FIFO_CUTOFF_BRIDGE_CASE_INVALID")
        scope = case.metadata.scope
        if (
            not isinstance(stock_evidence, ReportEvidence)
            or not isinstance(finance_batch, FifoFinanceSaleIdentityBatch)
            or not isinstance(physical_sale_document, FifoDocumentedPhysicalSaleDocument)
            or not isinstance(owner_confirmation, FifoPhysicalSaleDocumentConfirmation)
            or not isinstance(movement_coverage, FifoCutoffMovementCoverage)
            or not isinstance(proposal, FifoCostTransitionOpeningProposal)
        ):
            raise ValueError("FIFO_CUTOFF_BRIDGE_INPUT_INVALID")
        if case.dispatch_date is None:
            raise ValueError("FIFO_CUTOFF_BRIDGE_DISPATCH_DATE_REQUIRED")
        issues: set[str] = set()
        cutoff = getattr(proposal, "confirmed_cutoff_date", None)
        if (
            getattr(proposal, "scope", None) != scope
            or getattr(proposal, "case_id", None) != case.case_id
            or getattr(proposal, "case_revision", None) != case.case_revision
            or cutoff is None
        ):
            issues.add("OWNER_CONFIRMED_CUTOFF_OR_CASE_PROPOSAL_MISSING")
            cutoff = None
        else:
            cutoff = normalize_date_only(cutoff)
            if case.dispatch_date is not None and cutoff < case.dispatch_date:
                issues.add("CUTOFF_PRECEDES_DISPATCH_DATE")
        timezone_name = normalize_store_timezone(case.metadata.store_timezone)
        cutoff_descriptor = FifoCutoffDescriptor(
            metadata=TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
                completeness=(
                    EvidenceCompleteness.COMPLETE if cutoff is not None
                    else EvidenceCompleteness.PARTIAL
                ),
                source_fingerprint=source_fingerprint({
                    "case_id": case.case_id,
                    "case_revision": case.case_revision,
                    "cutoff_date": cutoff,
                }),
                store_timezone=timezone_name,
            ),
            case_id=case.case_id,
            case_revision=case.case_revision,
            cutoff_date=cutoff,
            timezone=timezone_name,
            precision="STORE_LOCAL_DATE",
            boundary="END_OF_LOCAL_DATE",
        )

        stock_buckets = self._validate_stock_evidence(
            stock_evidence=stock_evidence, scope=scope, cutoff=cutoff,
            proposal=proposal, issues=issues,
        )
        self._validate_finance_batch(
            batch=finance_batch, scope=scope, case=case,
            complete_through=requested_complete_through, issues=issues,
        )
        doc_rows = self._validate_document(
            document=physical_sale_document, confirmation=owner_confirmation,
            scope=scope, case=case, issues=issues,
        )
        post_cutoff_movements = self._validate_movements(
            movements=movement_coverage, scope=scope, case=case,
            requested_complete_through=requested_complete_through, issues=issues,
            cutoff=cutoff,
        )

        normalized_finance = {}
        finance_identity_by_posting = {}
        for row in finance_batch.rows:
            normalized = self.sale_normalizer.build_identity_digest(
                store_id=scope.store_id,
                posting_number=row.posting_number,
                finance_sku=row.finance_sku,
                identity={
                    "offer_id": row.offer_id,
                    "product_id": row.product_id,
                    "mapping_confirmed": True,
                },
            )
            if normalized.get("error"):
                issues.add("FINANCE_SALE_IDENTITY_INVALID")
                continue
            digest = normalized["source_identity_digest"]
            existing = normalized_finance.get(digest)
            if existing is not None and existing != row:
                issues.add("FINANCE_SALE_IDENTITY_CONFLICT")
            normalized_finance[digest] = row
            posting_key = (row.posting_number, row.finance_sku)
            posting_existing = finance_identity_by_posting.get(posting_key)
            if posting_existing is not None and posting_existing != row:
                issues.add("FINANCE_SALE_IDENTITY_CONFLICT")
            else:
                finance_identity_by_posting[posting_key] = row

        normalized_docs = {}
        for row in doc_rows:
            finance_row = finance_identity_by_posting.get((row.posting_number, row.finance_sku))
            if finance_row is None:
                issues.add("DOCUMENT_TO_FINANCE_IDENTITY_MISMATCH")
                continue
            digest_result = self.sale_normalizer.build_identity_digest(
                store_id=scope.store_id,
                posting_number=finance_row.posting_number,
                finance_sku=finance_row.finance_sku,
                identity={
                    "offer_id": finance_row.offer_id,
                    "product_id": finance_row.product_id,
                    "mapping_confirmed": True,
                },
            )
            if digest_result.get("error"):
                issues.add("FINANCE_SALE_IDENTITY_INVALID")
                continue
            digest = digest_result["source_identity_digest"]
            if digest in normalized_docs:
                issues.add("DOCUMENT_TO_FINANCE_IDENTITY_DUPLICATE")
                continue
            normalized_docs[digest] = (finance_row, row)

        # A return can restore cost only from a sale event that this exact
        # cutoff bridge will persist. A pre-cutoff sale is already reflected in
        # the stock snapshot and has no reconstructible FIFO allocation here;
        # an unlinked or same-day return also lacks a proven causal basis.
        bridged_post_cutoff_sale_dates = {
            digest: document_row.physical_effective_date
            for digest, (_finance_row, document_row) in normalized_docs.items()
            if cutoff is not None and document_row.physical_effective_date > cutoff
        }
        returned_units_by_sale = {}
        movement_digests = set()
        movement_fingerprints = set()
        for movement in post_cutoff_movements:
            if (
                movement.source_identity_digest in movement_digests
                or movement.movement_fingerprint in movement_fingerprints
            ):
                issues.add("FIFO_MOVEMENT_IDENTITY_DUPLICATE")
                continue
            movement_digests.add(movement.source_identity_digest)
            movement_fingerprints.add(movement.movement_fingerprint)
            if movement.movement_kind != "RETURN":
                continue
            sale_date = bridged_post_cutoff_sale_dates.get(
                movement.linked_sale_identity_digest,
            )
            if sale_date is None:
                issues.add("FIFO_RETURN_ORIGIN_SALE_NOT_IN_CUTOFF_BRIDGE")
                continue
            if sale_date >= movement.effective_date:
                issues.add("FIFO_RETURN_EVENT_ORDER_UNRESOLVED")
                continue
            sale_row = normalized_docs[movement.linked_sale_identity_digest][1]
            returned_units_by_sale[movement.linked_sale_identity_digest] = (
                returned_units_by_sale.get(movement.linked_sale_identity_digest, 0)
                + movement.quantity
            )
            if returned_units_by_sale[movement.linked_sale_identity_digest] > sale_row.quantity:
                issues.add("FIFO_RETURN_QUANTITY_EXCEEDS_ORIGIN_SALE")

        if set(normalized_docs) != set(normalized_finance):
            issues.add("FINANCE_DOCUMENT_IDENTITY_COVERAGE_MISMATCH")

        requested_end = normalize_date_only(requested_complete_through)
        if (
            physical_sale_document.period_to < requested_end
            or physical_sale_document.period_from > (case.dispatch_date or physical_sale_document.period_from)
        ):
            issues.add("PHYSICAL_SALE_DOCUMENT_COVERAGE_GAP")
        if any(
            row.physical_effective_date < physical_sale_document.period_from
            or row.physical_effective_date > physical_sale_document.period_to
            or row.physical_effective_date > requested_end
            for row in doc_rows
        ):
            issues.add("PHYSICAL_SALE_DOCUMENT_DATE_OUTSIDE_COVERAGE")

        if cutoff and requested_end < cutoff:
            issues.add("COVERAGE_END_BEFORE_CUTOFF")
        pre_events = []
        post_events = []
        mappings = []
        if not issues:
            for digest, (finance_row, document_row) in sorted(normalized_docs.items()):
                normalized = self.sale_normalizer.normalize_sale(
                    store_id=scope.store_id,
                    posting_number=finance_row.posting_number,
                    finance_sku=finance_row.finance_sku,
                    identity={
                        "offer_id": finance_row.offer_id,
                        "product_id": finance_row.product_id,
                        "mapping_confirmed": True,
                    },
                    quantity=document_row.quantity,
                    sale_authority="OZON_REALIZATION_REPORT",
                    sale_authority_confirmed=True,
                    physical_effective_date=document_row.physical_effective_date,
                    effective_date_semantics_confirmed=True,
                    inventory_cutoff_bridge_confirmed=True,
                )
                if normalized.get("error") or not normalized.get("allocation_eligible"):
                    issues.add("PHYSICAL_SALE_EVENT_NOT_ELIGIBLE")
                    break
                event = FifoCutoffBridgeEvent(
                    source_identity_digest=digest,
                    quantity=document_row.quantity,
                    physical_effective_date=document_row.physical_effective_date,
                    finance_source_fingerprint=finance_batch.source_fingerprint,
                    document_fingerprint=physical_sale_document.document_fingerprint,
                    document_row_reference=document_row.row_reference,
                )
                if document_row.physical_effective_date <= cutoff:
                    pre_events.append(event)
                else:
                    post_events.append(event)
                mappings.append((digest, finance_batch.source_fingerprint))

        if len(pre_events) + len(post_events) > self.MAX_EVENTS:
            issues.add("EVENT_LIMIT_EXCEEDED")
            pre_events.clear()
            post_events.clear()
            mappings.clear()

        complete_through = requested_end if not issues else None
        source_set_fp = source_fingerprint({
            "scope": {
                "owner_id": scope.owner_id,
                "store_id": scope.store_id,
                "sku": scope.sku,
                "product_id": scope.product_id,
                "offer_id": scope.offer_id,
            },
            "case_id": case.case_id,
            "case_revision": case.case_revision,
            "cutoff": cutoff,
            "timezone": timezone_name,
            "stock": stock_evidence.file_sha256 if isinstance(stock_evidence, ReportEvidence) else None,
            "finance": finance_batch.source_fingerprint,
            "document": physical_sale_document.document_fingerprint,
            "confirmation_at": owner_confirmation.confirmed_at,
            "movement": movement_coverage.source_fingerprint,
            "events": [(e.source_identity_digest, e.quantity, e.physical_effective_date) for e in (*pre_events, *post_events)],
            "complete_through": complete_through,
        })
        ready = not issues
        return FifoCutoffBridgeResult(
            status="READY" if ready else "SOURCE_BLOCKED",
            scope=scope,
            case_id=case.case_id,
            case_revision=case.case_revision,
            cutoff_descriptor=cutoff_descriptor,
            complete_through=complete_through,
            confirmed_stock_buckets=stock_buckets,
            pre_cutoff_outflows=tuple(pre_events),
            post_cutoff_events=tuple(post_events),
            finance_to_sale_identity_mappings=tuple(mappings),
            linked_returns_non_sale_movements=post_cutoff_movements,
            source_set_fingerprint=source_set_fp,
            unresolved_issues=tuple(issues),
            provenance_by_basis=MappingProxyType({
                "cutoff": ("OWNER_CONFIRMED_CASE_PROPOSAL",),
                "stock_scope": (stock_evidence.file_sha256,) if isinstance(stock_evidence, ReportEvidence) else (),
                "finance_sale_identities": (finance_batch.source_fingerprint,),
                "physical_sale_date_and_quantity": (physical_sale_document.document_fingerprint,),
                "owner_confirmation": (owner_confirmation.document_fingerprint,),
                "returns_and_non_sale_coverage": (movement_coverage.source_fingerprint,),
            }),
            ready_for_fifo_event=ready,
        )

    @staticmethod
    def _validate_stock_evidence(*, stock_evidence, scope, cutoff, proposal, issues):
        if (
            not isinstance(stock_evidence, ReportEvidence)
            or stock_evidence.report_type is not ReportType.STOCK_MANAGEMENT
            or stock_evidence.metadata.scope != scope
            or stock_evidence.metadata.source_kind is not EvidenceSourceKind.OWNER_IMPORTED
            or stock_evidence.period_provenance is not PeriodProvenance.OWNER_CONFIRMED
            or stock_evidence.period_from != cutoff
            or stock_evidence.period_to != cutoff
        ):
            issues.add("STOCK_SCOPE_OR_CUTOFF_UNPROVEN")
            return MappingProxyType({})
        if getattr(proposal, "stock_snapshots", None) is None or not any(
            snapshot.report_fingerprint == stock_evidence.file_sha256
            for snapshot in proposal.stock_snapshots
        ):
            issues.add("STOCK_NOT_BOUND_TO_OPENING_PROPOSAL")
        if stock_evidence.metadata.completeness is not EvidenceCompleteness.COMPLETE:
            issues.add("STOCK_REPORT_PARTIAL")
        buckets = stock_evidence.normalized_fields.get("stock_buckets")
        if not isinstance(buckets, Mapping):
            issues.add("STOCK_BUCKETS_MISSING")
            return MappingProxyType({})
        expected = {bucket.value for bucket in StockBucket}
        if set(buckets) - _STOCK_SOURCE_BUCKET_KEYS:
            issues.add("STOCK_BUCKETS_INCOMPLETE")
        safe_buckets = {}
        for name in sorted(expected):
            value = buckets.get(name)
            if value is None:
                issues.add("STOCK_BUCKET_UNKNOWN")
                safe_buckets[name] = None
            else:
                try:
                    safe_buckets[name] = normalize_quantity(value)
                except ValueError:
                    issues.add("STOCK_BUCKET_INVALID")
        return MappingProxyType(safe_buckets)

    @staticmethod
    def _validate_finance_batch(*, batch, scope, case, complete_through, issues):
        if not isinstance(batch, FifoFinanceSaleIdentityBatch) or batch.metadata_scope != scope:
            issues.add("FINANCE_IDENTITY_SCOPE_UNPROVEN")
            return
        if not batch.proof.api_read_complete:
            issues.add("FINANCE_IDENTITY_COVERAGE_INCOMPLETE")
        if batch.period_from > (case.dispatch_date or batch.period_from):
            issues.add("FINANCE_IDENTITY_START_GAP")
        requested = normalize_date_only(complete_through)
        if batch.period_to < requested:
            issues.add("FINANCE_IDENTITY_END_GAP")
        if batch.metadata_scope.sku != case.metadata.scope.sku:
            issues.add("FINANCE_IDENTITY_SCOPE_MISMATCH")

    @staticmethod
    def _validate_document(*, document, confirmation, scope, case, issues):
        if (
            not isinstance(document, FifoDocumentedPhysicalSaleDocument)
            or document.scope != scope
            or document.case_id != case.case_id
        ):
            issues.add("PHYSICAL_SALE_DOCUMENT_SCOPE_UNPROVEN")
            return ()
        if (
            not isinstance(confirmation, FifoPhysicalSaleDocumentConfirmation)
            or confirmation.owner_id != scope.owner_id
            or confirmation.scope != scope
            or confirmation.case_id != case.case_id
            or confirmation.document_fingerprint != document.document_fingerprint
            or set(confirmation.confirmed_row_references) != {
                row.row_reference for row in document.rows
            }
            or confirmation.confirmed_fields != _OWNER_CONFIRMED_FIELDS
            or confirmation.physical_date_semantics != "PHYSICAL_OUTFLOW"
            or confirmation.physical_date_timezone != case.metadata.store_timezone
            or confirmation.physical_date_precision != "STORE_LOCAL_DATE"
        ):
            issues.add("OWNER_PHYSICAL_DATE_CONFIRMATION_REQUIRED")
            return ()
        if document.period_from > (case.dispatch_date or document.period_from):
            issues.add("PHYSICAL_SALE_DOCUMENT_START_GAP")
        return document.rows

    @staticmethod
    def _validate_movements(
        *, movements, scope, case, requested_complete_through, issues, cutoff,
    ):
        requested = normalize_date_only(requested_complete_through)
        if (
            not isinstance(movements, FifoCutoffMovementCoverage)
            or movements.scope != scope
            or not movements.proof.api_read_complete
            or movements.period_from > (case.dispatch_date or movements.period_from)
            or movements.complete_through < requested
        ):
            issues.add("RETURN_NONSALE_COVERAGE_INCOMPLETE")
            return ()
        supported = []
        for movement in movements.movements:
            if movement.effective_date < movements.period_from or movement.effective_date > requested:
                issues.add("RETURN_NONSALE_EVENT_OUTSIDE_COVERAGE")
                continue
            if cutoff is not None and movement.effective_date <= cutoff:
                # The confirmed stock snapshot already contains pre-cutoff
                # movements. Replaying them again would double-apply quantity.
                continue
            if movement.movement_kind == "TRANSFER":
                issues.add("INVENTORY_TRANSFER_NORMALIZATION_UNAVAILABLE")
                continue
            if movement.movement_kind == "RETURN":
                if (
                    movement.source_identity_digest is None
                    or movement.linked_sale_identity_digest is None
                ):
                    issues.add("FIFO_RETURN_IDENTITY_UNCONFIRMED")
                    continue
            elif movement.movement_kind in {"SELLER_WITHDRAWAL", "DAMAGE"}:
                if (
                    movement.source_identity_digest is None
                    or movement.linked_sale_identity_digest is not None
                ):
                    issues.add("FIFO_MOVEMENT_IDENTITY_UNCONFIRMED")
                    continue
            else:
                issues.add("FIFO_MOVEMENT_KIND_UNSUPPORTED")
                continue
            supported.append(movement)
        return tuple(supported)
