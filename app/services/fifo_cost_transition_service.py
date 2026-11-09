"""Application lifecycle for owner-reported FIFO transition cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from collections.abc import Mapping

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_cutoff_bridge_service import (
    FifoCostCutoffBridgeService,
    FifoCutoffDescriptor,
)
from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_report_import_service import FifoCostReportImportService
from services.fifo_cost_stock_management_import_service import (
    FifoCostStockManagementImportService,
)
from services.fifo_cost_transition_contracts import (
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    TransitionBridgeEvidence,
    TransitionBridgeEvidenceKind,
    TransitionEvidenceConfirmation,
    TransitionEvidenceConfirmationKind,
    source_fingerprint,
)
from services.fifo_cost_transition_activation_proposal_service import (
    FifoCostTransitionActivationProposalService,
)
from services.fifo_cost_source_normalizer import (
    FifoActiveSupplySnapshot,
    FifoCostSourceNormalizer,
    FifoSupplyActSnapshot,
)
from services.fifo_cost_transition_contracts import (
    AcceptedQuantityKind,
    CostComponents,
    CostInputMode,
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    SupplyDeclaration,
    SupplyActEvidence,
    SupplyObservation,
    SupplyReferenceKind,
    UnknownValue,
    normalize_date_only,
    supply_reference_digest,
    utc_now,
)
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.tenant_cipher_provider import encrypt_tenant_value


class FifoCostTransitionService:
    """Create, revise, cancel, and list durable transition drafts.

    This layer only coordinates typed owner facts and the existing FIFO
    repository. It never chooses a cutoff, creates inventory, or changes
    current cost/profit.
    """

    _EDITABLE_STATES = frozenset({
        TransitionState.DRAFT,
        TransitionState.AWAITING_EVIDENCE,
    })

    def __init__(
        self, repository: FifoCostRepository | None = None, *,
        now_provider=None, cutoff_bridge_service=None,
        activation_proposal_service=None,
    ):
        self.repository = repository or FifoCostRepository()
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.cutoff_bridge_service = cutoff_bridge_service or FifoCostCutoffBridgeService()
        self.activation_proposal_service = (
            activation_proposal_service or FifoCostTransitionActivationProposalService()
        )

    def build_cutoff_bridge(self, **evidence) -> dict:
        """Build a read-only bridge through the production transition service."""
        try:
            result = self.cutoff_bridge_service.build(**evidence)
        except (TypeError, ValueError) as exc:
            code = str(exc) or "FIFO_CUTOFF_BRIDGE_INPUT_INVALID"
            return self._error(code)
        return {"error": False, "result": result}

    def build_activation_proposal(self, **evidence) -> dict:
        """Build a no-write opening/rate proposal through production wiring."""
        try:
            result = self.activation_proposal_service.propose(**evidence)
        except (TypeError, ValueError) as exc:
            code = str(exc) or "FIFO_ACTIVATION_PROPOSAL_INPUT_INVALID"
            return self._error(code)
        return {"error": False, "result": result}

    def record_cutoff_selection(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        cutoff_date, stock_report_fingerprint, expected_case_revision,
        idempotency_key,
    ) -> dict:
        """Persist a candidate store-local cutoff bound to one saved stock report.

        This records owner intent only. The derived bridge-input fingerprint is
        not a completed movement/finance bridge and remains PARTIAL until the
        evidence assembler proves that bridge.
        """
        loaded = self._read_transition_owner_context(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        case = loaded["case"]
        try:
            cutoff = self._normalize_transition_date(cutoff_date)
            if case.dispatch_date is not None and cutoff < case.dispatch_date:
                return self._error("FIFO_CUTOFF_PRECEDES_DISPATCH_DATE")
            report = self._read_saved_transition_report(
                case_id=case_id, identity=loaded["identity"], scope=case.metadata.scope,
                store_timezone=case.metadata.store_timezone,
                file_sha256=stock_report_fingerprint,
            )
            if report is None:
                return self._error("FIFO_CUTOFF_STOCK_EVIDENCE_UNAVAILABLE")
            if (
                report.report_type is not ReportType.STOCK_MANAGEMENT
                or report.metadata.completeness is not EvidenceCompleteness.COMPLETE
                or report.period_provenance is not PeriodProvenance.OWNER_CONFIRMED
                or report.period_from != cutoff or report.period_to != cutoff
            ):
                return self._error("FIFO_CUTOFF_STOCK_EVIDENCE_MISMATCH")
            refs = self._transition_source_reference_manifest(
                case_id=case_id, identity=loaded["identity"], scope=case.metadata.scope,
            )
            identity_fingerprint = self._transition_identity_fingerprint(case.metadata.scope)
            bridge_fingerprint = source_fingerprint({
                "kind": "FIFO_CUTOFF_BRIDGE_INPUT_SELECTION_V1",
                "case_id": case_id,
                "case_revision": expected_case_revision,
                "scope": self._transition_scope_material(case.metadata.scope),
                "descriptor": {
                    "cutoff_date": cutoff,
                    "timezone": case.metadata.store_timezone,
                    "precision": "STORE_LOCAL_DATE",
                    "boundary": "END_OF_LOCAL_DATE",
                },
                "stock_report_fingerprint": report.file_sha256,
                "source_references": refs,
            })
            descriptor_metadata = TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
                completeness=EvidenceCompleteness.COMPLETE,
                source_fingerprint=bridge_fingerprint,
                store_timezone=case.metadata.store_timezone,
            )
            cutoff_descriptor = FifoCutoffDescriptor(
                metadata=descriptor_metadata,
                case_id=case_id,
                case_revision=expected_case_revision,
                cutoff_date=cutoff,
                timezone=case.metadata.store_timezone,
                precision="STORE_LOCAL_DATE",
                boundary="END_OF_LOCAL_DATE",
            )
            descriptor = {
                "cutoff_date": cutoff_descriptor.cutoff_date,
                "timezone": cutoff_descriptor.timezone,
                "precision": cutoff_descriptor.precision,
                "boundary": cutoff_descriptor.boundary,
            }
            metadata = TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
                completeness=EvidenceCompleteness.PARTIAL,
                source_fingerprint=bridge_fingerprint,
                store_timezone=case.metadata.store_timezone,
            )
            evidence = TransitionBridgeEvidence(
                metadata=metadata,
                evidence_kind=TransitionBridgeEvidenceKind.CUTOFF_SELECTION,
                captured_at=self._transition_now(),
                period_from=cutoff,
                period_to=cutoff,
                payload={
                    "cutoff_date": cutoff,
                    "complete_through": cutoff,
                    "bridge_fingerprint": bridge_fingerprint,
                    "selected_event_count": None,
                    "identity_fingerprint": identity_fingerprint,
                },
                sensitive_payload=self._canonical_transition_json({
                    "schema_version": 1,
                    "case_id": case_id,
                    "case_revision": expected_case_revision,
                    "case_basis_fingerprint": self._transition_case_basis_fingerprint(case),
                    "descriptor": descriptor,
                    "stock_report_fingerprint": report.file_sha256,
                    "source_references": refs,
                }),
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            return self._error("FIFO_CUTOFF_SELECTION_INVALID")
        return self.repository.append_transition_bridge_evidence(
            case_id=case_id, evidence=evidence,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def confirm_cutoff_selection(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        evidence_id, expected_evidence_fingerprint, expected_case_revision,
        idempotency_key,
    ) -> dict:
        """Durably confirm an exact cutoff descriptor and its stock semantics."""
        loaded = self._read_confirmable_owner_evidence(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, evidence_id=evidence_id,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            evidence_kind=TransitionBridgeEvidenceKind.CUTOFF_SELECTION,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        payload = loaded["sensitive_payload"]
        descriptor = payload.get("descriptor")
        if (
            not self._owner_evidence_revision_matches(
                payload, expected_case_revision,
            )
            or payload.get("case_basis_fingerprint")
            != self._transition_case_basis_fingerprint(loaded["case"])
            or
            not isinstance(descriptor, dict)
            or descriptor.get("cutoff_date") != loaded["item"]["payload"].get("cutoff_date")
            or descriptor.get("timezone") != loaded["case"].metadata.store_timezone
            or descriptor.get("precision") != "STORE_LOCAL_DATE"
            or descriptor.get("boundary") != "END_OF_LOCAL_DATE"
            or not self._saved_stock_report_matches(
                loaded, payload.get("stock_report_fingerprint"),
                descriptor.get("cutoff_date"),
            )
        ):
            return self._error("FIFO_CUTOFF_SELECTION_STALE")
        confirmation = TransitionEvidenceConfirmation(
            confirmation_kind=TransitionEvidenceConfirmationKind.CUTOFF_SELECTION,
            confirmed_fields={
                "cutoff_date": descriptor["cutoff_date"],
                "bridge_fingerprint": loaded["item"]["payload"]["bridge_fingerprint"],
                "stock_semantics": "AVAILABLE_PLUS_RESERVED_TRANSIT_EXCLUDED",
            },
        )
        return self.repository.confirm_transition_evidence(
            case_id=case_id, metadata=loaded["case"].metadata,
            evidence_id=evidence_id,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            confirmation=confirmation,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def record_opening_composition(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        cutoff_evidence_id, cutoff_evidence_fingerprint,
        stock_report_fingerprint, layers, expected_case_revision,
        idempotency_key,
    ) -> dict:
        """Persist a bounded FIFO opening composition, never as a live anchor."""
        loaded = self._read_transition_owner_context(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        case = loaded["case"]
        cutoff = self._read_confirmed_cutoff_evidence(
            case_id=case_id, identity=loaded["identity"], scope=case.metadata.scope,
        )
        if cutoff.get("error"):
            return cutoff
        if (
            cutoff["item"].get("evidence_id") != cutoff_evidence_id
            or cutoff["item"].get("payload_fingerprint") != cutoff_evidence_fingerprint
            or cutoff["sensitive_payload"].get("stock_report_fingerprint")
            != stock_report_fingerprint
        ):
            return self._error("FIFO_CUTOFF_SELECTION_STALE")
        report = self._read_saved_transition_report(
            case_id=case_id, identity=loaded["identity"], scope=case.metadata.scope,
            store_timezone=case.metadata.store_timezone,
            file_sha256=stock_report_fingerprint,
        )
        if report is None or not self._valid_cutoff_stock_report(
            report, cutoff["descriptor"]["cutoff_date"],
        ):
            return self._error("FIFO_CUTOFF_STOCK_EVIDENCE_MISMATCH")
        normalized_layers, layer_error = FifoCostAnchorService._layers(layers)
        if layer_error:
            return self._error(layer_error)
        quantities = self._opening_zone_totals(normalized_layers)
        fields = report.normalized_fields
        buckets = fields.get("stock_buckets")
        available = buckets.get("available") if isinstance(buckets, Mapping) else None
        reserved = buckets.get("reserved") if isinstance(buckets, Mapping) else None
        fbs_return_units = fields.get("fbs_return_available_units")
        if (
            type(available) is not int or available < 0
            or type(reserved) is not int or reserved < 0
        ):
            return self._error("FIFO_INITIAL_CUTOVER_STOCK_SCOPE_UNPROVEN")
        if (
            type(fbs_return_units) is not int or fbs_return_units != 0
            or fields.get("fbs_return_is_subset_of_available") is not True
        ):
            return self._error("FIFO_INITIAL_CUTOVER_RETURN_BASIS_UNAVAILABLE")
        if any(
            buckets.get(name) not in (0, None)
            for name in ("preparing", "checking")
        ):
            return self._error("FIFO_INITIAL_CUTOVER_STOCK_BUCKET_UNRESOLVED")
        if (
            quantities["ozon_units"] != available + reserved
            or quantities["home_units"] != case.owner_old_home_units
            or quantities["transit_units"] != case.owner_old_transit_units
            or sum(quantities.values()) <= 0
        ):
            return self._error("FIFO_INITIAL_CUTOVER_QUANTITY_MISMATCH")
        costs = [row["unit_cost_rub"] for row in normalized_layers]
        old_cost = self._normalize_transition_money(case.old_unit_cost_rub)
        new_cost = self._normalize_transition_money(case.new_unit_cost_rub)
        if old_cost is None or new_cost is None or any(
            cost not in {old_cost, new_cost} for cost in costs
        ):
            return self._error("FIFO_INITIAL_CUTOVER_COST_MISMATCH")
        new_seen = False
        for cost in costs:
            if cost == new_cost:
                new_seen = True
            elif cost == old_cost and new_seen:
                return self._error("FIFO_INITIAL_CUTOVER_LAYER_ORDER_CONFLICT")
        source_refs = self._transition_source_reference_manifest(
            case_id=case_id, identity=loaded["identity"], scope=case.metadata.scope,
        )
        composition = {
            "schema_version": 1,
            "case_id": case_id,
            "case_revision": expected_case_revision,
            "case_basis_fingerprint": self._transition_case_basis_fingerprint(case),
            "opening_date": cutoff["descriptor"]["cutoff_date"],
            "cutoff_evidence_id": cutoff_evidence_id,
            "cutoff_evidence_fingerprint": cutoff_evidence_fingerprint,
            "stock_report_fingerprint": stock_report_fingerprint,
            "layers": normalized_layers,
            "zone_totals": quantities,
            "ozon_units_include_reserved_confirmed": True,
            "transit_not_in_ozon_confirmed": True,
            "accepted_supply_units_added_to_stock_snapshot": 0,
            "source_references": source_refs,
        }
        identity_fingerprint = self._transition_identity_fingerprint(case.metadata.scope)
        composition_fingerprint = source_fingerprint(composition)
        composition["composition_fingerprint"] = composition_fingerprint
        metadata = TransitionMetadata(
            scope=case.metadata.scope,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.PARTIAL,
            source_fingerprint=composition_fingerprint,
            store_timezone=case.metadata.store_timezone,
        )
        evidence = TransitionBridgeEvidence(
            metadata=metadata,
            evidence_kind=TransitionBridgeEvidenceKind.OPENING_COMPOSITION,
            captured_at=self._transition_now(),
            period_from=composition["opening_date"],
            period_to=composition["opening_date"],
            row_count=len(normalized_layers),
            payload={
                "opening_date": composition["opening_date"],
                "total_units": sum(quantities.values()),
                "component_count": len(normalized_layers),
                "composition_fingerprint": composition_fingerprint,
                "identity_fingerprint": identity_fingerprint,
            },
            sensitive_payload=self._canonical_transition_json(composition),
        )
        return self.repository.append_transition_bridge_evidence(
            case_id=case_id, evidence=evidence,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def confirm_opening_composition(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        evidence_id, expected_evidence_fingerprint, expected_case_revision,
        idempotency_key,
    ) -> dict:
        loaded = self._read_confirmable_owner_evidence(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, evidence_id=evidence_id,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            evidence_kind=TransitionBridgeEvidenceKind.OPENING_COMPOSITION,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        composition = loaded["sensitive_payload"]
        safe = loaded["item"]["payload"]
        cutoff = self._read_confirmed_cutoff_evidence(
            case_id=case_id, identity=loaded["identity"], scope=loaded["case"].metadata.scope,
        )
        if cutoff.get("error") or (
            not self._owner_evidence_revision_matches(
                composition, expected_case_revision,
            )
            or composition.get("case_basis_fingerprint")
            != self._transition_case_basis_fingerprint(loaded["case"])
            or
            composition.get("cutoff_evidence_id") != cutoff["item"].get("evidence_id")
            or composition.get("cutoff_evidence_fingerprint")
            != cutoff["item"].get("payload_fingerprint")
            or composition.get("composition_fingerprint")
            != safe.get("composition_fingerprint")
        ):
            return self._error("FIFO_OPENING_COMPOSITION_STALE")
        confirmation = TransitionEvidenceConfirmation(
            confirmation_kind=TransitionEvidenceConfirmationKind.OPENING_COMPOSITION,
            confirmed_fields={
                "composition_fingerprint": safe["composition_fingerprint"],
                "opening_date": safe["opening_date"],
                "total_units": safe["total_units"],
            },
        )
        return self.repository.confirm_transition_evidence(
            case_id=case_id, metadata=loaded["case"].metadata,
            evidence_id=evidence_id,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            confirmation=confirmation,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def read_confirmed_cutoff_selection(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
    ) -> dict:
        """Read the latest exact confirmed cutoff after process restart."""
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        try:
            case = self._case_from_payload(current["case"])
            identity = {"store_id": store_id, "product_id": product_id,
                        "offer_id": offer_id, "sku": sku}
            loaded = self._read_confirmed_cutoff_evidence(
                case_id=case_id, identity=identity, scope=case.metadata.scope,
            )
            if loaded.get("error"):
                return loaded
            return {
                "error": False,
                "case_revision": current["case_revision"],
                "evidence_id": loaded["item"]["evidence_id"],
                "evidence_fingerprint": loaded["item"]["payload_fingerprint"],
                "descriptor": dict(loaded["descriptor"]),
                "stock_report_fingerprint": loaded["sensitive_payload"]["stock_report_fingerprint"],
                "confirmed": True,
                "preview_only": True,
            }
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_CUTOFF_SELECTION_INVALID")

    def read_confirmed_opening_composition(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
    ) -> dict:
        """Read only the latest composition if its separate owner confirmation survives."""
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        try:
            case = self._case_from_payload(current["case"])
            identity = {"store_id": store_id, "product_id": product_id,
                        "offer_id": offer_id, "sku": sku}
            result = self.repository.read_transition_bridge_evidence(
                case_id=case_id, **identity,
                evidence_kind=TransitionBridgeEvidenceKind.OPENING_COMPOSITION,
                limit=100, include_sensitive_payload=True,
            )
            if result.get("error"):
                return result
            items = result.get("items")
            if not isinstance(items, list) or not items:
                return self._error("FIFO_OPENING_COMPOSITION_NOT_CONFIRMED")
            item = max(items, key=lambda value: value.get("evidence_revision", 0))
            loaded = self._verified_owner_payload(item)
            if loaded.get("error"):
                return loaded
            cutoff = self._read_confirmed_cutoff_evidence(
                case_id=case_id, identity=identity, scope=case.metadata.scope,
            )
            composition = loaded["sensitive_payload"]
            safe = item["payload"]
            expected_fields = {
                "composition_fingerprint": safe.get("composition_fingerprint"),
                "opening_date": safe.get("opening_date"),
                "total_units": safe.get("total_units"),
            }
            confirmed = any(
                value.get("confirmation_kind") == TransitionEvidenceConfirmationKind.OPENING_COMPOSITION.value
                and value.get("confirmed_fields") == expected_fields
                for value in item.get("confirmations", ())
            )
            if (
                cutoff.get("error") or not confirmed
                or composition.get("case_basis_fingerprint")
                != self._transition_case_basis_fingerprint(case)
                or composition.get("cutoff_evidence_id") != cutoff["item"].get("evidence_id")
                or composition.get("cutoff_evidence_fingerprint")
                != cutoff["item"].get("payload_fingerprint")
            ):
                return self._error("FIFO_OPENING_COMPOSITION_NOT_CONFIRMED")
            try:
                current_refs = self._transition_source_reference_manifest(
                    case_id=case_id, identity=identity, scope=case.metadata.scope,
                )
            except ValueError:
                return self._error("FIFO_TRANSITION_EVIDENCE_UNAVAILABLE")
            if composition.get("source_references") != current_refs:
                return self._error("FIFO_OPENING_COMPOSITION_STALE")
            return {
                "error": False,
                "case_revision": current["case_revision"],
                "evidence_id": item["evidence_id"],
                "evidence_fingerprint": item["payload_fingerprint"],
                "composition_fingerprint": safe["composition_fingerprint"],
                "opening_date": safe["opening_date"],
                "total_units": safe["total_units"],
                "layers": composition["layers"],
                "stock_report_fingerprint": composition["stock_report_fingerprint"],
                "cutoff_evidence_id": composition["cutoff_evidence_id"],
                "cutoff_evidence_fingerprint": composition["cutoff_evidence_fingerprint"],
                "source_references": composition["source_references"],
                "confirmed": True,
                "preview_only": True,
            }
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_OPENING_COMPOSITION_INVALID")

    def _read_transition_owner_context(
        self, *, case_id, store_id, product_id, offer_id, sku,
        expected_case_revision,
    ):
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        identity = {
            "store_id": store_id, "product_id": product_id,
            "offer_id": offer_id, "sku": sku,
        }
        current = self.get_case(case_id=case_id, **identity)
        if current.get("error"):
            return current
        if current.get("case_revision") != expected_case_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        try:
            case = self._case_from_payload(current["case"])
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
        if case.state not in self._EDITABLE_STATES:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        if any(
            getattr(case.metadata.scope, name) != value
            for name, value in (
                ("store_id", store_id), ("product_id", product_id),
                ("offer_id", offer_id), ("sku", sku),
            )
        ):
            return self._error("FIFO_TRANSITION_SCOPE_MISMATCH")
        return {"error": False, "case": case, "identity": identity}

    def _read_saved_transition_report(
        self, *, case_id, identity, scope, store_timezone, file_sha256,
    ):
        try:
            result = self.repository.read_transition_evidence(
                case_id=case_id, **identity, kind="REPORT_EVIDENCE", limit=101,
            )
            if result.get("error") or not isinstance(result.get("items"), list):
                return None
            matches = [
                item for item in result["items"]
                if item.get("file_sha256") == file_sha256
            ]
            if len(matches) != 1:
                return None
            item = matches[0]
            payload = item.get("payload")
            if not isinstance(payload, dict):
                return None
            parser = (
                FifoCostStockManagementImportService
                if item.get("report_type") == ReportType.STOCK_MANAGEMENT.value
                else FifoCostReportImportService
            )
            return ReportEvidence(
                metadata=TransitionMetadata(
                    scope=scope,
                    source_kind=EvidenceSourceKind(item["source_kind"]),
                    completeness=EvidenceCompleteness(item["completeness"]),
                    source_fingerprint=parser._source_fingerprint(
                        item["file_sha256"], scope,
                    ),
                    store_timezone=store_timezone,
                ),
                report_type=ReportType(item["report_type"]),
                period_from=item.get("period_from"),
                period_to=item.get("period_to"),
                period_provenance=PeriodProvenance(item["period_provenance"]),
                captured_at=item["captured_at"],
                file_sha256=item["file_sha256"],
                parser_version=item["parser_version"],
                cell_references=tuple(payload["cell_references"]),
                normalized_fields=payload["normalized_fields"],
            )
        except (TypeError, ValueError, KeyError, AttributeError):
            return None

    def _transition_source_reference_manifest(self, *, case_id, identity, scope):
        """Return bounded hashes only; never copy source identifiers into metadata."""
        references = []
        for kind, limit in (
            ("REPORT_EVIDENCE", 101),
            ("SUPPLY_DECLARATION", 501),
            ("SUPPLY_OBSERVATION", 2000),
        ):
            result = self.repository.read_transition_evidence(
                case_id=case_id, **identity, kind=kind, limit=limit,
            )
            if result.get("error") or not isinstance(result.get("items"), list):
                raise ValueError("FIFO_TRANSITION_EVIDENCE_UNAVAILABLE")
            if len(result["items"]) >= limit:
                raise ValueError("FIFO_TRANSITION_EVIDENCE_LIMIT_REACHED")
            for item in result["items"]:
                references.append({
                    "kind": kind,
                    "fingerprint": source_fingerprint(item),
                })
        for kind in (
            TransitionBridgeEvidenceKind.PHYSICAL_SALES_DOCUMENT,
            TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT,
            TransitionBridgeEvidenceKind.MOVEMENT_COVERAGE,
        ):
            result = self.repository.read_transition_bridge_evidence(
                case_id=case_id, **identity, evidence_kind=kind, limit=100,
            )
            if result.get("error") or not isinstance(result.get("items"), list):
                raise ValueError("FIFO_TRANSITION_EVIDENCE_UNAVAILABLE")
            if len(result["items"]) >= 100:
                raise ValueError("FIFO_TRANSITION_EVIDENCE_LIMIT_REACHED")
            for item in result["items"]:
                references.append({
                    "kind": kind.value,
                    "fingerprint": item["payload_fingerprint"],
                })
        references.sort(key=lambda item: (item["kind"], item["fingerprint"]))
        if len(references) > 2_700:
            raise ValueError("FIFO_TRANSITION_EVIDENCE_LIMIT_REACHED")
        return references

    def _read_confirmable_owner_evidence(
        self, *, case_id, store_id, product_id, offer_id, sku, evidence_id,
        expected_evidence_fingerprint, evidence_kind, expected_case_revision,
    ):
        loaded = self._read_transition_owner_context(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
            expected_case_revision=expected_case_revision,
        )
        if loaded.get("error"):
            return loaded
        result = self.repository.read_transition_bridge_evidence(
            case_id=case_id, **loaded["identity"], evidence_kind=evidence_kind,
            evidence_id=evidence_id, limit=1, include_sensitive_payload=True,
        )
        if result.get("error"):
            return result
        items = result.get("items")
        if not isinstance(items, list) or len(items) != 1:
            return self._error("FIFO_TRANSITION_EVIDENCE_MISSING")
        item = items[0]
        if item.get("payload_fingerprint") != expected_evidence_fingerprint:
            return self._error("FIFO_TRANSITION_EVIDENCE_MISMATCH")
        payload = self._verified_owner_payload(item)
        if payload.get("error"):
            return payload
        return {
            **loaded, "item": item,
            "sensitive_payload": payload["sensitive_payload"],
        }

    @staticmethod
    def _verified_owner_payload(item):
        if item.get("sensitive_payload_available") is not True:
            return {"error": True, "code": item.get(
                "blocker", "FIFO_TRANSITION_ENCRYPTION_UNAVAILABLE",
            )}
        try:
            payload = json.loads(item["sensitive_payload"])
        except (KeyError, TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_EVIDENCE_CORRUPT"}
        if not isinstance(payload, dict):
            return {"error": True, "code": "FIFO_TRANSITION_EVIDENCE_CORRUPT"}
        return {"error": False, "sensitive_payload": payload}

    def _read_confirmed_cutoff_evidence(self, *, case_id, identity, scope):
        result = self.repository.read_transition_bridge_evidence(
            case_id=case_id, **identity,
            evidence_kind=TransitionBridgeEvidenceKind.CUTOFF_SELECTION,
            limit=100, include_sensitive_payload=True,
        )
        if result.get("error"):
            return result
        items = result.get("items")
        if not isinstance(items, list) or not items:
            return self._error("FIFO_CUTOFF_SELECTION_NOT_CONFIRMED")
        item = max(items, key=lambda value: value.get("evidence_revision", 0))
        verified = self._verified_owner_payload(item)
        if verified.get("error"):
            return verified
        payload = verified["sensitive_payload"]
        safe = item.get("payload")
        descriptor = payload.get("descriptor")
        if not isinstance(safe, dict) or not isinstance(descriptor, dict):
            return self._error("FIFO_CUTOFF_SELECTION_INVALID")
        expected_fields = {
            "cutoff_date": descriptor.get("cutoff_date"),
            "bridge_fingerprint": safe.get("bridge_fingerprint"),
            "stock_semantics": "AVAILABLE_PLUS_RESERVED_TRANSIT_EXCLUDED",
        }
        if not any(
            confirmation.get("confirmation_kind")
            == TransitionEvidenceConfirmationKind.CUTOFF_SELECTION.value
            and confirmation.get("confirmed_fields") == expected_fields
            for confirmation in item.get("confirmations", ())
        ):
            return self._error("FIFO_CUTOFF_SELECTION_NOT_CONFIRMED")
        current_case_result = self.get_case(case_id=case_id, **identity)
        if current_case_result.get("error"):
            return current_case_result
        try:
            current_case = self._case_from_payload(current_case_result["case"])
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
        if (
            descriptor.get("timezone") != current_case.metadata.store_timezone
            or descriptor.get("precision") != "STORE_LOCAL_DATE"
            or descriptor.get("boundary") != "END_OF_LOCAL_DATE"
            or safe.get("cutoff_date") != descriptor.get("cutoff_date")
            or payload.get("case_id") != case_id
            or payload.get("case_basis_fingerprint")
            != self._transition_case_basis_fingerprint(current_case)
            or not self._saved_stock_report_matches(
                {"case_id": case_id, "identity": identity, "case": current_case},
                payload.get("stock_report_fingerprint"), descriptor.get("cutoff_date"),
            )
        ):
            return self._error("FIFO_CUTOFF_SELECTION_STALE")
        try:
            current_refs = self._transition_source_reference_manifest(
                case_id=case_id, identity=identity, scope=scope,
            )
        except ValueError:
            return self._error("FIFO_TRANSITION_EVIDENCE_UNAVAILABLE")
        if payload.get("source_references") != current_refs:
            return self._error("FIFO_CUTOFF_SELECTION_STALE")
        return {
            "error": False, "item": item, "sensitive_payload": payload,
            "descriptor": descriptor,
        }

    def _saved_stock_report_matches(self, loaded, fingerprint, cutoff_date):
        report = self._read_saved_transition_report(
            case_id=loaded["case_id"] if "case_id" in loaded else loaded["case"].case_id,
            identity=loaded["identity"], scope=loaded["case"].metadata.scope,
            store_timezone=loaded["case"].metadata.store_timezone,
            file_sha256=fingerprint,
        )
        return bool(report and self._valid_cutoff_stock_report(report, cutoff_date))

    @staticmethod
    def _valid_cutoff_stock_report(report, cutoff_date):
        return bool(
            isinstance(report, ReportEvidence)
            and report.report_type is ReportType.STOCK_MANAGEMENT
            and report.metadata.completeness is EvidenceCompleteness.COMPLETE
            and report.period_provenance is PeriodProvenance.OWNER_CONFIRMED
            and report.period_from == cutoff_date
            and report.period_to == cutoff_date
        )

    @staticmethod
    def _opening_zone_totals(layers):
        return {
            name: sum(layer[name] for layer in layers)
            for name in ("ozon_units", "transit_units", "home_units")
        }

    @staticmethod
    def _owner_evidence_revision_matches(payload, expected_case_revision):
        """Reject corrupt persisted revisions without raising during confirmation."""
        if not isinstance(payload, dict):
            return False
        revision = payload.get("case_revision")
        return (
            type(revision) is int
            and revision >= 1
            and type(expected_case_revision) is int
            and revision + 1 == expected_case_revision
        )

    @staticmethod
    def _transition_scope_material(scope):
        return {
            "owner_id": scope.owner_id, "store_id": scope.store_id,
            "product_id": scope.product_id, "offer_id": scope.offer_id,
            "sku": scope.sku,
        }

    @staticmethod
    def _transition_identity_fingerprint(scope):
        return source_fingerprint({
            "store_id": scope.store_id,
            "product_id": scope.product_id,
            "offer_id": scope.offer_id,
            "sku": scope.sku,
            "policy_version": 1,
        })

    @classmethod
    def _transition_case_basis_fingerprint(cls, case):
        return source_fingerprint({
            "case_id": case.case_id,
            "scope": cls._transition_scope_material(case.metadata.scope),
            "dispatch_date": case.dispatch_date,
            "old_unit_cost_rub": (
                None if case.old_unit_cost_rub is None else str(case.old_unit_cost_rub)
            ),
            "new_unit_cost_rub": (
                None if case.new_unit_cost_rub is None else str(case.new_unit_cost_rub)
            ),
            "cost_input_mode": case.cost_input_mode.value,
            "cost_components": (
                None if case.cost_components is None else {
                    "purchase_cost_rub": str(case.cost_components.purchase_cost_rub),
                    "delivery_cost_rub": str(case.cost_components.delivery_cost_rub),
                    "packaging_cost_rub": str(case.cost_components.packaging_cost_rub),
                }
            ),
            "owner_old_home_units": case.owner_old_home_units,
            "owner_old_transit_units": case.owner_old_transit_units,
            "new_home_quantity": case.new_home_quantity,
            "declared_shipped_units": case.declared_shipped_units,
            "store_timezone": case.metadata.store_timezone,
        })

    def _transition_now(self):
        now = utc_now(self._now_provider)
        return now

    @staticmethod
    def _canonical_transition_json(value):
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )

    @staticmethod
    def _normalize_transition_date(value):
        return normalize_date_only(value)

    @staticmethod
    def _normalize_transition_money(value):
        if value is None:
            return None
        normalized = FifoCostAnchorService._money(value)
        return normalized

    def create_case(self, *, case: TransitionCase, idempotency_key: str) -> dict:
        if not isinstance(case, TransitionCase):
            return self._error("FIFO_TRANSITION_CASE_INVALID")
        if case.case_revision != 1 or case.state is not TransitionState.DRAFT:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        return self.repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key=idempotency_key,
        )

    def update_case(
        self, *, case: TransitionCase, expected_revision: int,
        idempotency_key: str,
    ) -> dict:
        if not isinstance(case, TransitionCase):
            return self._error("FIFO_TRANSITION_CASE_INVALID")
        if type(expected_revision) is not int or expected_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if (
            case.case_revision != expected_revision + 1
            or case.state not in self._EDITABLE_STATES
        ):
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        scope = case.metadata.scope
        current = self.repository.read_transition_case(
            case_id=case.case_id,
            store_id=scope.store_id,
            product_id=scope.product_id,
            offer_id=scope.offer_id,
            sku=scope.sku,
        )
        if current.get("error"):
            return current
        if current["case_revision"] == expected_revision + 1:
            # Let repository idempotency resolve a retry of the exact committed
            # payload before treating the now-advanced revision as stale.
            return self.repository.save_transition_case(
                case=case, expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        if current["case_revision"] != expected_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        if current["state"] not in {state.value for state in self._EDITABLE_STATES}:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        return self.repository.save_transition_case(
            case=case, expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def update_owner_inputs(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        expected_revision, updates, idempotency_key, state=None,
    ):
        """CAS-save a narrow set of typed owner-entered transition facts."""
        allowed = {
            "dispatch_date", "old_unit_cost_rub", "new_unit_cost_rub",
            "cost_components", "owner_old_home_units", "owner_old_transit_units",
            "new_home_quantity", "declared_shipped_units",
        }
        if not isinstance(updates, dict) or not updates or set(updates) - allowed:
            return self._error("FIFO_TRANSITION_OWNER_INPUT_INVALID")
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        if current.get("case_revision") != expected_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        try:
            case = self._case_from_payload(current["case"])
            if case.state not in self._EDITABLE_STATES:
                return self._error("FIFO_TRANSITION_CASE_NOT_READY")
            unknown_values = dict(case.unknown_values)
            optional_fields = {
                "dispatch_date", "old_unit_cost_rub", "new_unit_cost_rub",
                "owner_old_home_units", "owner_old_transit_units",
                "new_home_quantity", "declared_shipped_units",
            }
            for name, value in updates.items():
                if name in optional_fields:
                    if value is None:
                        unknown_values[name] = UnknownValue(
                            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                            EvidenceSourceKind.OWNER_INPUT,
                        )
                    else:
                        unknown_values.pop(name, None)
            next_state = case.state if state is None else (
                state if isinstance(state, TransitionState) else TransitionState(str(state))
            )
            if next_state not in self._EDITABLE_STATES:
                return self._error("FIFO_TRANSITION_CASE_NOT_READY")
            fingerprint_payload = {
                "prior": case.metadata.source_fingerprint,
                "revision": expected_revision + 1,
                "updates": {
                    key: (
                        {
                            "purchase_cost_rub": str(value.purchase_cost_rub),
                            "delivery_cost_rub": str(value.delivery_cost_rub),
                            "packaging_cost_rub": str(value.packaging_cost_rub),
                        }
                        if isinstance(value, CostComponents)
                        else None if value is None else str(value)
                    )
                    for key, value in sorted(updates.items())
                },
                "state": next_state.value,
            }
            source_fingerprint = hashlib.sha256(
                json.dumps(
                    fingerprint_payload, sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            metadata = replace(
                case.metadata,
                source_fingerprint=source_fingerprint,
                completeness=EvidenceCompleteness.PARTIAL,
            )
            updated = replace(
                case,
                metadata=metadata,
                case_revision=expected_revision + 1,
                state=next_state,
                updated_at=max(utc_now(self._now_provider), case.updated_at),
                unknown_values=unknown_values,
                **updates,
            )
        except (TypeError, ValueError, KeyError) as exc:
            reason = getattr(exc, "reason_code", None)
            if reason is not None:
                return self._error(reason.value)
            return self._error("FIFO_TRANSITION_OWNER_INPUT_INVALID")
        return self.update_case(
            case=updated,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def cancel_case(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        expected_revision, idempotency_key,
    ) -> dict:
        if type(expected_revision) is not int or expected_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        current_payload = self.repository.read_transition_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current_payload.get("error"):
            return current_payload
        if (
            current_payload["state"] == TransitionState.CANCELLED.value
            and current_payload["case_revision"] == expected_revision + 1
        ):
            try:
                already_cancelled = self._case_from_payload(current_payload["case"])
            except (TypeError, ValueError, KeyError):
                return self._error("FIFO_TRANSITION_CASE_CORRUPT")
            return self.repository.cancel_transition_case(
                case=already_cancelled, expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        if current_payload["case_revision"] != expected_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        if current_payload["state"] not in {state.value for state in self._EDITABLE_STATES}:
            return self._error("FIFO_TRANSITION_CASE_NOT_READY")
        try:
            case = self._case_from_payload(current_payload["case"])
            updated_at = max(utc_now(self._now_provider), case.updated_at)
            cancelled = replace(
                case,
                case_revision=expected_revision + 1,
                state=TransitionState.CANCELLED,
                updated_at=updated_at,
            )
        except (TypeError, ValueError, KeyError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
        return self.repository.cancel_transition_case(
            case=cancelled, expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def get_case(self, *, case_id, store_id, product_id=None, offer_id=None, sku):
        return self.repository.read_transition_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )

    def get_case_revision(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        case_revision,
    ):
        """Read one scoped immutable basis revision for a sealed preview."""
        return self.repository.read_transition_case_revision(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, case_revision=case_revision,
        )

    def list_cases(
        self, *, store_id, sku=None,
        states=("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM"), limit=100,
    ):
        return self.repository.list_transition_cases(
            store_id=store_id, sku=sku, states=states, limit=limit,
        )

    def read_case_history(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        limit=100, before_revision=None,
    ):
        """Read bounded, redacted case revisions for the exact owner/store/SKU."""
        return self.repository.read_transition_case_history(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, limit=limit,
            before_revision=before_revision,
        )

    def declare_supply(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        reference_kind, reference_id, declared_shipped_units,
        dispatch_date=None, expected_case_revision, idempotency_key,
    ) -> dict:
        """Append an owner-declared typed ORDER/SUPPLY link to the exact case.

        The raw lookup reference exists only in this call frame: persistence
        receives a scoped digest and, when the configured tenant cipher is
        available, a Fernet token. A missing cipher does not discard the
        declaration; it explicitly disables future refresh-by-ID.
        """
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        try:
            case = self._case_from_payload(current["case"])
            if case.state not in self._EDITABLE_STATES:
                return self._error("FIFO_TRANSITION_CASE_NOT_READY")
            kind = (
                reference_kind if isinstance(reference_kind, SupplyReferenceKind)
                else SupplyReferenceKind(str(reference_kind).strip().upper())
            )
            normalized_reference = self._normalize_reference_id(reference_id)
            reference_digest = supply_reference_digest(
                owner_id=case.metadata.scope.owner_id,
                store_id=case.metadata.scope.store_id,
                reference_kind=kind,
                reference_id=normalized_reference,
            )
            if reference_digest is None:
                return self._error("FIFO_TRANSITION_REFERENCE_INVALID")
            encrypted_lookup = encrypt_tenant_value(normalized_reference)
            unknown_values = {}
            if declared_shipped_units is None:
                unknown_values["declared_shipped_units"] = UnknownValue(
                    TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                    EvidenceSourceKind.OWNER_INPUT,
                )
            if encrypted_lookup is None:
                unknown_values["lookup_reference"] = UnknownValue(
                    TransitionReasonCode.LOOKUP_REFERENCE_UNAVAILABLE,
                    EvidenceSourceKind.OWNER_INPUT,
                )
            source_fingerprint = hashlib.sha256(
                ("fifo-transition-declaration:v1:" + ":".join((
                    reference_digest,
                    "UNKNOWN" if declared_shipped_units is None
                    else str(declared_shipped_units),
                    str(dispatch_date or ""),
                ))).encode("utf-8")
            ).hexdigest()
            metadata = TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
                completeness=(
                    EvidenceCompleteness.PARTIAL if unknown_values
                    else EvidenceCompleteness.COMPLETE
                ),
                source_fingerprint=source_fingerprint,
                store_timezone=case.metadata.store_timezone,
            )
            declaration_id = "decl_" + hashlib.sha256(
                f"fifo-transition-declaration-id:v1:{case.case_id}:{idempotency_key}".encode()
            ).hexdigest()[:32]
            declaration = SupplyDeclaration(
                metadata=metadata,
                case_id=case.case_id,
                declaration_id=declaration_id,
                revision=1,
                reference_kind=kind,
                reference_digest=reference_digest,
                encrypted_lookup_reference=encrypted_lookup,
                declared_shipped_units=declared_shipped_units,
                dispatch_date=dispatch_date,
                provenance=EvidenceSourceKind.OWNER_INPUT,
                unknown_values=unknown_values,
            )
        except (TypeError, ValueError, KeyError) as exc:
            reason = getattr(exc, "reason_code", None)
            if reason is not None:
                return self._error(reason.value)
            if isinstance(exc, ValueError) and str(exc) == "FIFO_TRANSITION_REFERENCE_INVALID":
                return self._error(str(exc))
            return self._error("FIFO_TRANSITION_DECLARATION_INVALID")
        return self.repository.append_supply_declaration(
            declaration=declaration,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    def get_supply_manifest(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
    ) -> dict:
        """Return safe supply quantities and owner-total remainder, never IDs."""
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        evidence = self.repository.read_transition_evidence(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, kind="SUPPLY_DECLARATION", limit=100,
        )
        if evidence.get("error"):
            return evidence
        latest = {}
        for item in evidence["items"]:
            key = item["declaration_id"]
            if key not in latest or item["evidence_revision"] > latest[key]["evidence_revision"]:
                latest[key] = item
        declarations = sorted(
            latest.values(), key=lambda item: (item.get("recorded_at") or "", item["declaration_id"]),
        )
        known_units = sum(
            item["declared_shipped_units"]
            for item in declarations
            if item["declared_shipped_units"] is not None
        )
        quantities_complete = all(
            item["declared_shipped_units"] is not None for item in declarations
        )
        owner_total = current["case"].get("declared_shipped_units")
        if owner_total is not None and known_units > owner_total:
            return self._error("FIFO_TRANSITION_SUPPLY_TOTAL_CONFLICT")
        undistributed = (
            owner_total - known_units
            if owner_total is not None and quantities_complete else None
        )
        return {
            "error": False,
            "code": "FIFO_TRANSITION_SUPPLY_MANIFEST_FOUND",
            "case_id": current["case_id"],
            "case_revision": current["case_revision"],
            "owner_declared_total": owner_total,
            "known_assigned_units": known_units,
            "assignment_complete": quantities_complete,
            "undistributed_units": undistributed,
            "undistributed_status": "KNOWN" if undistributed is not None else "UNKNOWN",
            "declarations": [
                {
                    "declaration_id": item["declaration_id"],
                    "reference_kind": item["reference_kind"],
                    "declared_shipped_units": item["declared_shipped_units"],
                    "dispatch_date": item["dispatch_date"],
                    "lookup_status": (
                        "AVAILABLE" if item.get("lookup_reference_available")
                        else "LOOKUP_REFERENCE_UNAVAILABLE"
                    ),
                }
                for item in declarations
            ],
        }

    def supply_declaration_matches_reference(
        self, *, case_id, declaration_id, owner_id, store_id,
        product_id=None, offer_id=None, sku, reference_id,
    ) -> bool:
        """Validate a supplied ID against one scoped encrypted declaration.

        The scoped digest is compared internally and never returned in a
        manifest or diagnostic result.
        """
        evidence = self.repository.read_transition_evidence(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku, kind="SUPPLY_DECLARATION", limit=100,
        )
        if evidence.get("error"):
            return False
        latest = {}
        for item in evidence["items"]:
            key = item["declaration_id"]
            if key not in latest or item["evidence_revision"] > latest[key]["evidence_revision"]:
                latest[key] = item
        persisted = latest.get(declaration_id)
        expected_digest = self.reference_digest_for_supply(
            owner_id=owner_id, store_id=store_id, reference_id=reference_id,
        )
        return bool(
            persisted is not None
            and persisted.get("reference_kind") == "SUPPLY"
            and persisted.get("lookup_reference_available")
            and expected_digest is not None
            and persisted.get("reference_digest") == expected_digest
        )

    def record_supply_observation(
        self, *, case_id, store_id, product_id=None, offer_id=None, sku,
        declaration_id, reference_id, snapshot, expected_case_revision,
        idempotency_key, act_snapshot=None,
    ) -> dict:
        """Append a redacted status observation for its exact supply declaration.

        ``reference_id`` is used only in memory to bind the API result back to
        the encrypted owner declaration; neither the ID nor its plaintext
        digest is returned from this method.
        """
        if not isinstance(snapshot, FifoActiveSupplySnapshot):
            return self._error("FIFO_TRANSITION_OBSERVATION_INVALID")
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_TRANSITION_REVISION_INVALID")
        if (
            snapshot.status not in {"PRESENT", "MISSING"}
            or snapshot.presence != snapshot.status
            or snapshot.source_status not in {"COMPLETE", "PARTIAL"}
            or snapshot.store_id != store_id
            or snapshot.source_fingerprint is None
            or (snapshot.presence == "PRESENT" and snapshot.order_ref is None)
            or (
                snapshot.presence == "MISSING"
                and (snapshot.raw_status is not None or snapshot.normalized_status != "UNKNOWN")
            )
            or type(snapshot.scope_complete) is not bool
            or type(snapshot.pagination_complete) is not bool
        ):
            return self._error("FIFO_TRANSITION_OBSERVATION_INVALID")
        if snapshot.presence == "MISSING" and not (
            snapshot.source_status == "COMPLETE"
            and snapshot.scope_complete
            and snapshot.pagination_complete
        ):
            return self._error("FIFO_TRANSITION_OBSERVATION_NOT_COMPLETE")
        current = self.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return current
        if current["case_revision"] != expected_case_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        try:
            case = self._case_from_payload(current["case"])
            if case.state not in self._EDITABLE_STATES:
                return self._error("FIFO_TRANSITION_CASE_NOT_READY")
            normalized_reference = self._normalize_reference_id(reference_id)
            expected_supply_digest = supply_reference_digest(
                owner_id=case.metadata.scope.owner_id,
                store_id=case.metadata.scope.store_id,
                reference_kind=SupplyReferenceKind.SUPPLY,
                reference_id=normalized_reference,
            )
            if expected_supply_digest is None:
                return self._error("FIFO_TRANSITION_REFERENCE_INVALID")
            if snapshot.supply_reference_digest != expected_supply_digest:
                return self._error("FIFO_TRANSITION_SUPPLY_REFERENCE_MISMATCH")
            declarations = self.repository.read_transition_evidence(
                case_id=case_id, store_id=store_id, product_id=product_id,
                offer_id=offer_id, sku=sku,
                kind="SUPPLY_DECLARATION", limit=100,
            )
            if declarations.get("error"):
                return declarations
            matching = [
                item for item in declarations["items"]
                if item.get("declaration_id") == declaration_id
            ]
            if not matching or any(
                item.get("reference_kind") != SupplyReferenceKind.SUPPLY.value
                or item.get("reference_digest") != expected_supply_digest
                for item in matching
            ):
                return self._error("FIFO_TRANSITION_SUPPLY_REFERENCE_MISMATCH")
            if any(item.get("lookup_reference_available") is not True for item in matching):
                return self._error("FIFO_TRANSITION_LOOKUP_REFERENCE_UNAVAILABLE")

            accepted_quantity = None
            accepted_kind = None
            act_reference_digest = None
            act_version_digest = None
            act_captured_at = None
            act_source_fingerprint = None
            act_source_supply_reference_digest = None
            act_order_reference_digest = None
            act_evidence = ()
            source_fingerprint = snapshot.source_fingerprint
            if act_snapshot is not None:
                if not isinstance(act_snapshot, FifoSupplyActSnapshot):
                    return self._error("FIFO_TRANSITION_ACCEPTANCE_INVALID")
                latest_declaration = max(
                    matching, key=lambda item: item.get("evidence_revision", 0),
                )
                declared_units = latest_declaration.get("declared_shipped_units")
                if (
                    snapshot.presence != "PRESENT"
                    or snapshot.normalized_status != "ACCEPTED"
                    or snapshot.source_status != "COMPLETE"
                    or act_snapshot.status not in {"COMPLETE", "CONFIRMED_ZERO"}
                    or act_snapshot.source_status != "COMPLETE"
                    or act_snapshot.store_id != store_id
                    or act_snapshot.supply_ref
                    != FifoCostSourceNormalizer._digest("SUPPLY", normalized_reference)
                    or act_snapshot.order_ref != snapshot.order_ref
                    or act_snapshot.captured_at is None
                    or act_snapshot.source_fingerprint is None
                    or act_snapshot.evidence_fingerprint is None
                    or not isinstance(act_snapshot.units_by_sku, tuple)
                    or len(act_snapshot.units_by_sku) != 1
                    or act_snapshot.units_by_sku[0][0] != str(sku)
                    or not isinstance(act_snapshot.act_evidence, tuple)
                ):
                    return self._error("FIFO_TRANSITION_ACCEPTANCE_INVALID")
                act_payload = {
                    "store_id": act_snapshot.store_id,
                    "order_ref": act_snapshot.order_ref,
                    "supply_ref": act_snapshot.supply_ref,
                    "act_refs": list(sorted(act_snapshot.act_refs)),
                    "act_evidence": [
                        {
                            "act_ref": item.act_ref,
                            "act_type": item.act_type,
                            "act_state": item.act_state,
                            "created_date": item.created_date,
                            "declared_quantity": item.declared_quantity,
                            "approved_quantity": item.approved_quantity,
                            "fact_quantity": item.fact_quantity,
                        }
                        for item in act_snapshot.act_evidence
                    ],
                    "units_by_sku": [list(item) for item in act_snapshot.units_by_sku],
                    "status": act_snapshot.status,
                }
                if (
                    FifoCostSourceNormalizer._fingerprint(act_payload)
                    != act_snapshot.evidence_fingerprint
                    or FifoCostSourceNormalizer._fingerprint({
                        **act_payload, "captured_at": act_snapshot.captured_at,
                    }) != act_snapshot.source_fingerprint
                ):
                    return self._error("FIFO_TRANSITION_ACCEPTANCE_INVALID")
                from services.fifo_cost_supply_acceptance_reconciliation_service import (
                    FifoCostSupplyAcceptanceReconciliationService,
                )

                reconciled = FifoCostSupplyAcceptanceReconciliationService().reconcile(
                    snapshots=(act_snapshot,), target_sku=str(sku),
                    declared_quantity=declared_units,
                )
                if (
                    reconciled.status not in {"COMPLETE", "PARTIALLY_ACCEPTED"}
                    or reconciled.accepted_quantity != act_snapshot.units_by_sku[0][1]
                    or not reconciled.act_reference_digests
                ):
                    return self._error("FIFO_TRANSITION_ACCEPTANCE_INVALID")
                accepted_quantity = reconciled.accepted_quantity
                accepted_kind = AcceptedQuantityKind.DOCUMENT_LINES
                act_reference_digest = FifoCostSourceNormalizer._fingerprint(
                    list(sorted(act_snapshot.act_refs)),
                )
                act_version_digest = act_snapshot.evidence_fingerprint
                act_captured_at = act_snapshot.captured_at
                act_source_fingerprint = act_snapshot.source_fingerprint
                act_source_supply_reference_digest = act_snapshot.supply_ref
                act_order_reference_digest = act_snapshot.order_ref
                act_evidence = tuple(
                    SupplyActEvidence(
                        act_ref=item.act_ref,
                        act_type=item.act_type,
                        act_state=item.act_state,
                        created_date=item.created_date,
                        declared_quantity=item.declared_quantity,
                        approved_quantity=item.approved_quantity,
                        fact_quantity=item.fact_quantity,
                    )
                    for item in act_snapshot.act_evidence
                )
                source_fingerprint = FifoCostSourceNormalizer._fingerprint({
                    "status": snapshot.source_fingerprint,
                    "acts": act_snapshot.source_fingerprint,
                })

            normalized_status = NormalizedSupplyStatus(snapshot.normalized_status)
            presence = EvidencePresence(snapshot.presence)
            completeness = (
                EvidenceCompleteness.COMPLETE
                if snapshot.source_status == "COMPLETE"
                else EvidenceCompleteness.PARTIAL
            )
            metadata = TransitionMetadata(
                scope=case.metadata.scope,
                source_kind=EvidenceSourceKind.OZON_API,
                completeness=completeness,
                source_fingerprint=source_fingerprint,
                store_timezone=case.metadata.store_timezone,
            )
            unknown_reason = (
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING
                if presence is EvidencePresence.MISSING
                else TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE
            )
            unknown_values = {
                "declared_quantity": UnknownValue(
                    unknown_reason, EvidenceSourceKind.OZON_API,
                ),
            }
            if accepted_quantity is None:
                unknown_values["accepted_quantity"] = UnknownValue(
                    unknown_reason, EvidenceSourceKind.OZON_API,
                )
            observation = SupplyObservation(
                metadata=metadata,
                declaration_id=declaration_id,
                captured_at=snapshot.captured_at,
                source_as_of=None,
                raw_status=snapshot.raw_status,
                normalized_status=normalized_status,
                declared_quantity=None,
                accepted_quantity=accepted_quantity,
                accepted_quantity_kind=accepted_kind,
                act_reference_digest=act_reference_digest,
                act_version_digest=act_version_digest,
                scope_complete=snapshot.scope_complete,
                pagination_complete=snapshot.pagination_complete,
                presence=presence,
                unknown_values=unknown_values,
                act_captured_at=act_captured_at,
                act_source_fingerprint=act_source_fingerprint,
                act_source_supply_reference_digest=act_source_supply_reference_digest,
                act_order_reference_digest=act_order_reference_digest,
                act_evidence=act_evidence,
            )
        except (TypeError, ValueError, KeyError) as exc:
            reason = getattr(exc, "reason_code", None)
            if reason is not None:
                return self._error(reason.value)
            return self._error("FIFO_TRANSITION_OBSERVATION_INVALID")
        return self.repository.append_supply_observation(
            case_id=case_id, observation=observation,
            expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _normalize_reference_id(value) -> str:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("FIFO_TRANSITION_REFERENCE_INVALID")
        raw = str(value).strip()
        if not re.fullmatch(r"[0-9]{1,40}", raw):
            raise ValueError("FIFO_TRANSITION_REFERENCE_INVALID")
        return str(int(raw))

    @classmethod
    def reference_digest_for_supply(cls, *, owner_id, store_id, reference_id):
        try:
            normalized_reference = cls._normalize_reference_id(reference_id)
        except (TypeError, ValueError):
            return None
        return supply_reference_digest(
            owner_id=owner_id,
            store_id=store_id,
            reference_kind=SupplyReferenceKind.SUPPLY,
            reference_id=normalized_reference,
        )

    @staticmethod
    def _case_from_payload(payload: dict) -> TransitionCase:
        metadata_payload = payload["metadata"]
        scope_payload = metadata_payload["scope"]
        owner_id, scoped_store = split_store_tenant_scope(
            str(get_current_tenant_user_id() or "").strip(),
        )
        if scoped_store != scope_payload["store_id"]:
            raise ValueError("FIFO_TRANSITION_SCOPE_MISMATCH")
        metadata = TransitionMetadata(
            scope=ScopeIdentity(
                owner_id=owner_id,
                store_id=scope_payload["store_id"],
                product_id=scope_payload.get("product_id"),
                offer_id=scope_payload.get("offer_id"),
                sku=scope_payload["sku"],
            ),
            source_kind=EvidenceSourceKind(metadata_payload["source_kind"]),
            completeness=EvidenceCompleteness(metadata_payload["completeness"]),
            source_fingerprint=metadata_payload["source_fingerprint"],
            schema_version=metadata_payload["schema_version"],
            store_timezone=metadata_payload["store_timezone"],
        )
        component_payload = payload.get("cost_components")
        components = (
            CostComponents(
                purchase_cost_rub=Decimal(component_payload["purchase_cost_rub"]),
                delivery_cost_rub=Decimal(component_payload["delivery_cost_rub"]),
                packaging_cost_rub=Decimal(component_payload["packaging_cost_rub"]),
            )
            if isinstance(component_payload, dict) else None
        )
        unknown_values = {
            name: UnknownValue(
                reason_code=TransitionReasonCode(value["reason_code"]),
                source_kind=EvidenceSourceKind(value["source_kind"]),
            )
            for name, value in payload.get("unknown_values", {}).items()
        }
        return TransitionCase(
            metadata=metadata,
            case_id=payload["case_id"],
            case_revision=payload["case_revision"],
            state=TransitionState(payload["state"]),
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            dispatch_date=payload.get("dispatch_date"),
            old_unit_cost_rub=(
                None if payload.get("old_unit_cost_rub") is None
                else Decimal(payload["old_unit_cost_rub"])
            ),
            new_unit_cost_rub=(
                None if payload.get("new_unit_cost_rub") is None
                else Decimal(payload["new_unit_cost_rub"])
            ),
            cost_input_mode=CostInputMode(payload["cost_input_mode"]),
            cost_components=components,
            owner_old_home_units=payload.get("owner_old_home_units"),
            owner_old_transit_units=payload.get("owner_old_transit_units"),
            new_home_quantity=payload.get("new_home_quantity"),
            declared_shipped_units=payload.get("declared_shipped_units"),
            opening_evidence_ref=payload.get("opening_evidence_ref"),
            source_watermark=payload.get("source_watermark"),
            reason_codes=tuple(
                TransitionReasonCode(value)
                for value in payload.get("reason_codes", ())
            ),
            supersedes_case_id=payload.get("supersedes_case_id"),
            unknown_values=unknown_values,
        )

    @staticmethod
    def _error(code: str) -> dict:
        return {"error": True, "code": code}
