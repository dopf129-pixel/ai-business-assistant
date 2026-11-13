"""Read-only assembly of durable FIFO transition evidence for owner review."""

from __future__ import annotations

from services.fifo_cost_source_normalizer import (
    FifoCostSourceNormalizer,
    FifoSupplyActEvidence,
    FifoSupplyActSnapshot,
)
from services.fifo_cost_supply_acceptance_reconciliation_service import (
    FifoCostSupplyAcceptanceReconciliationService,
)
from services.fifo_cost_report_import_service import FifoCostReportImportService
from services.fifo_cost_stock_management_import_service import (
    FifoCostStockManagementImportService,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SupplyDeclaration,
    SupplyObservation,
    SupplyReferenceKind,
    TransitionMetadata,
    TransitionReasonCode,
    UnknownValue,
    AcceptedQuantityKind,
    EvidencePresence,
    NormalizedSupplyStatus,
    SupplyActEvidence,
)
from services.fifo_cost_transition_opening_proposal_service import (
    FifoCostTransitionOpeningProposalService,
)
from services.fifo_cost_transition_readiness_service import (
    FifoCostTransitionReadinessService,
)
from services.fifo_cost_transition_supply_reconciliation_service import (
    FifoSupplyAcceptanceSnapshot,
    FifoCostTransitionSupplyReconciliationService,
)


class FifoCostTransitionReviewService:
    """Rebuild a fail-closed readiness view from exact case-scoped evidence.

    This service reads only saved transition evidence. It performs no Ozon or
    Telegram calls, writes no case revision, and never authorizes application.
    """

    MAX_DECLARATIONS = 500
    MAX_OBSERVATIONS = 2_000
    MAX_REPORTS = 100

    def __init__(
        self, transition_service, history_service, *,
        supply_reconciliation_service=None,
        opening_proposal_service=None,
        readiness_service=None,
        acceptance_reconciliation_service=None,
    ):
        self.transition_service = transition_service
        self.history_service = history_service
        self.repository = transition_service.repository
        self.supply_reconciliation_service = (
            supply_reconciliation_service
            or FifoCostTransitionSupplyReconciliationService()
        )
        self.opening_proposal_service = (
            opening_proposal_service or FifoCostTransitionOpeningProposalService()
        )
        self.readiness_service = readiness_service or FifoCostTransitionReadinessService()
        self.acceptance_reconciliation_service = (
            acceptance_reconciliation_service
            or FifoCostSupplyAcceptanceReconciliationService()
        )

    def assess(
        self, *, case_id, identity, owner_confirmed_cutoff_date=None,
    ):
        case_result = self.transition_service.get_case(
            case_id=case_id, **identity,
        )
        if not isinstance(case_result, dict) or case_result.get("error") is not False:
            return self._error("FIFO_TRANSITION_CASE_UNAVAILABLE")
        if case_result.get("state") not in {"DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM"}:
            return self._error("FIFO_TRANSITION_CASE_NOT_REVIEWABLE")
        try:
            case = self.transition_service._case_from_payload(case_result["case"])
            scope = case.metadata.scope
            if any(getattr(scope, key) != identity.get(key) for key in (
                "store_id", "product_id", "offer_id", "sku",
            )):
                return self._error("FIFO_TRANSITION_SCOPE_MISMATCH")
            declarations = self._read_declarations(case_id, identity, scope)
            observations = self._read_observations(case_id, identity, scope)
            acceptance_snapshots = self._build_acceptance_snapshots(
                observations, declarations, scope,
            )
            reports = self._read_reports(case_id, identity, scope)
            history = self.history_service.get_sku_history(**identity)
            if not isinstance(history, dict) or history.get("error") is not False:
                return self._error("FIFO_TRANSITION_FIFO_STATE_UNAVAILABLE")
            stock_reports = tuple(
                report for report in reports
                if report.report_type is ReportType.STOCK_MANAGEMENT
            )
            turnover_reports = tuple(
                report for report in reports
                if report.report_type is ReportType.TURNOVER
            )
            reconciliation = self.supply_reconciliation_service.reconcile(
                scope=scope, case_id=case.case_id,
                owner_declared_total=case.declared_shipped_units,
                declarations=declarations,
                observations=observations,
                acceptance_snapshots=acceptance_snapshots,
                stock_reports=stock_reports,
            )
            proposal = self.opening_proposal_service.propose(
                case=case,
                fifo_initialized=history.get("queue_initialized") is not False,
                owner_confirmed_cutoff_date=owner_confirmed_cutoff_date,
                stock_reports=stock_reports,
                turnover_reports=turnover_reports,
                supply_reconciliation=reconciliation,
            )
            readiness = self.readiness_service.assess(
                case=case,
                proposal=proposal,
                supply_reconciliation=reconciliation,
                cutoff_bridge=None,
            )
        except (TypeError, ValueError, KeyError, AttributeError):
            return self._error("FIFO_TRANSITION_EVIDENCE_INVALID")
        return {
            "error": False,
            "code": "FIFO_TRANSITION_READINESS_ASSESSED",
            "case_id": case.case_id,
            "case_revision": case.case_revision,
            "case_state": case.state.value,
            "proposal": proposal,
            "readiness": readiness,
            "supply_reconciliation": reconciliation,
            "fifo_layers": self._confirmed_fifo_layers(history),
            "fifo_queue_initialized": history.get("queue_initialized") is True,
            "fifo_remaining_status": history.get("remaining_status"),
            "reports_read": len(reports),
            "ready_to_apply": readiness.ready_to_apply is True,
            "preview_only": True,
        }

    @staticmethod
    def _confirmed_fifo_layers(history):
        """Return only layers whose remaining quantities are currently proven."""
        if not isinstance(history, dict) or history.get("error") is not False:
            return ()
        if history.get("remaining_status") == "REPLAY_REQUIRED":
            return ()
        result = []
        for item in history.get("layers", ()):
            if not isinstance(item, dict):
                continue
            units = item.get("remaining_units")
            if type(units) is not int or units <= 0:
                continue
            result.append({
                "remaining_units": units,
                "unit_cost_rub": item.get("unit_cost_rub"),
                "effective_date": item.get("effective_date"),
                "location": item.get("recorded_location_label"),
                "provenance": item.get("provenance_label"),
            })
        return tuple(result)

    def _read_declarations(self, case_id, identity, scope):
        result = self.repository.read_transition_evidence(
            case_id=case_id, **identity, kind="SUPPLY_DECLARATION",
            limit=self.MAX_DECLARATIONS + 1,
            include_encrypted_lookup_reference=True,
        )
        items = self._items(result, maximum=self.MAX_DECLARATIONS)
        declarations = []
        for item in items:
            payload = item["payload"]
            declarations.append(SupplyDeclaration(
                metadata=self._metadata(payload["metadata"], scope),
                case_id=payload["case_id"],
                declaration_id=payload["declaration_id"],
                revision=payload["revision"],
                reference_kind=SupplyReferenceKind(payload["reference_kind"]),
                reference_digest=payload["reference_digest"],
                encrypted_lookup_reference=item.get("encrypted_lookup_reference"),
                declared_shipped_units=payload.get("declared_shipped_units"),
                dispatch_date=payload.get("dispatch_date"),
                provenance=EvidenceSourceKind(payload["provenance"]),
                unknown_values=self._unknown_values(payload.get("unknown_values")),
            ))
        return tuple(declarations)

    def _read_observations(self, case_id, identity, scope):
        result = self.repository.read_transition_evidence(
            case_id=case_id, **identity, kind="SUPPLY_OBSERVATION",
            limit=self.MAX_OBSERVATIONS,
        )
        items = self._items(result, maximum=self.MAX_OBSERVATIONS - 1)
        observations = []
        for item in items:
            payload = item["payload"]
            observations.append(SupplyObservation(
                metadata=self._metadata(payload["metadata"], scope),
                declaration_id=payload["declaration_id"],
                captured_at=payload["captured_at"],
                source_as_of=payload.get("source_as_of"),
                raw_status=payload.get("raw_status"),
                normalized_status=NormalizedSupplyStatus(payload["normalized_status"]),
                declared_quantity=payload.get("declared_quantity"),
                accepted_quantity=payload.get("accepted_quantity"),
                accepted_quantity_kind=(
                    AcceptedQuantityKind(payload["accepted_quantity_kind"])
                    if payload.get("accepted_quantity_kind") else None
                ),
                act_reference_digest=payload.get("act_reference_digest"),
                act_version_digest=payload.get("act_version_digest"),
                scope_complete=payload["scope_complete"],
                pagination_complete=payload["pagination_complete"],
                presence=EvidencePresence(payload["presence"]),
                unknown_values=self._unknown_values(payload.get("unknown_values")),
                act_captured_at=payload.get("act_captured_at"),
                act_source_fingerprint=payload.get("act_source_fingerprint"),
                act_source_supply_reference_digest=payload.get(
                    "act_source_supply_reference_digest",
                ),
                act_order_reference_digest=payload.get("act_order_reference_digest"),
                act_evidence=tuple(
                    SupplyActEvidence(**item)
                    for item in payload.get("act_evidence", ())
                ),
            ))
        return tuple(observations)

    def _build_acceptance_snapshots(self, observations, declarations, scope):
        """Rebuild acceptance from immutable, allowlisted act evidence only."""
        declarations_by_id = {}
        for declaration in declarations:
            previous = declarations_by_id.get(declaration.declaration_id)
            if previous is None or declaration.revision > previous.revision:
                declarations_by_id[declaration.declaration_id] = declaration
        observations_by_id = {}
        for observation in observations:
            if observation.act_evidence:
                observations_by_id.setdefault(observation.declaration_id, []).append(observation)
        result = []
        for declaration_id, rows in sorted(observations_by_id.items()):
            declaration = declarations_by_id.get(declaration_id)
            if declaration is None:
                raise ValueError("FIFO_TRANSITION_ACCEPTANCE_BINDING_INVALID")
            rows.sort(key=lambda item: (item.act_captured_at or "", item.captured_at))
            act_snapshots = []
            for observation in rows:
                act_evidence = tuple(FifoSupplyActEvidence(
                    act_ref=item.act_ref,
                    act_type=item.act_type,
                    act_state=item.act_state,
                    created_date=item.created_date,
                    declared_quantity=item.declared_quantity,
                    approved_quantity=item.approved_quantity,
                    fact_quantity=item.fact_quantity,
                ) for item in observation.act_evidence)
                references = tuple(sorted(item.act_ref for item in act_evidence))
                quantity = observation.accepted_quantity
                status = "CONFIRMED_ZERO" if quantity == 0 else "COMPLETE"
                payload = {
                    "store_id": scope.store_id,
                    "order_ref": observation.act_order_reference_digest,
                    "supply_ref": observation.act_source_supply_reference_digest,
                    "act_refs": list(references),
                    "act_evidence": [{
                        "act_ref": item.act_ref,
                        "act_type": item.act_type,
                        "act_state": item.act_state,
                        "created_date": item.created_date,
                        "declared_quantity": item.declared_quantity,
                        "approved_quantity": item.approved_quantity,
                        "fact_quantity": item.fact_quantity,
                    } for item in act_evidence],
                    "units_by_sku": [[scope.sku, quantity]],
                    "status": status,
                }
                expected_act_reference_digest = FifoCostSourceNormalizer._fingerprint(
                    list(references),
                )
                if (
                    observation.accepted_quantity_kind is not AcceptedQuantityKind.DOCUMENT_LINES
                    or observation.act_reference_digest != expected_act_reference_digest
                    or observation.act_version_digest
                    != FifoCostSourceNormalizer._fingerprint(payload)
                    or observation.act_source_fingerprint
                    != FifoCostSourceNormalizer._fingerprint({
                        **payload, "captured_at": observation.act_captured_at,
                    })
                ):
                    raise ValueError("FIFO_TRANSITION_ACCEPTANCE_FINGERPRINT_INVALID")
                act_snapshots.append(FifoSupplyActSnapshot(
                    status=status,
                    source_status="COMPLETE",
                    store_id=scope.store_id,
                    supply_ref=observation.act_source_supply_reference_digest,
                    act_refs=references,
                    units_by_sku=((scope.sku, quantity),),
                    captured_at=observation.act_captured_at,
                    effective_at=None,
                    source_fingerprint=observation.act_source_fingerprint,
                    issue_codes=(),
                    order_ref=observation.act_order_reference_digest,
                    act_evidence=act_evidence,
                    evidence_fingerprint=observation.act_version_digest,
                ))
            latest_status = max(
                (item for item in observations if item.declaration_id == declaration_id),
                key=lambda item: (item.captured_at, item.metadata.source_fingerprint),
            ).normalized_status
            reconciliation = self.acceptance_reconciliation_service.reconcile(
                snapshots=tuple(act_snapshots),
                target_sku=scope.sku,
                declared_quantity=declaration.declared_shipped_units,
                final_state_confirmed=latest_status in {
                    NormalizedSupplyStatus.ACCEPTED,
                    NormalizedSupplyStatus.CANCELLED,
                },
            )
            latest = max(rows, key=lambda item: (item.act_captured_at, item.captured_at))
            result.append(FifoSupplyAcceptanceSnapshot(
                metadata=latest.metadata,
                declaration_id=declaration.declaration_id,
                declaration_reference_digest=declaration.reference_digest,
                captured_at=latest.act_captured_at,
                source_as_of=latest.source_as_of,
                reconciliation=reconciliation,
            ))
        return tuple(result)

    def _read_reports(self, case_id, identity, scope):
        result = self.repository.read_transition_evidence(
            case_id=case_id, **identity, kind="REPORT_EVIDENCE",
            limit=self.MAX_REPORTS + 1,
        )
        items = self._items(result, maximum=self.MAX_REPORTS)
        reports = []
        for item in items:
            payload = item["payload"]
            report_type = ReportType(item["report_type"])
            parser = (
                FifoCostStockManagementImportService
                if report_type is ReportType.STOCK_MANAGEMENT
                else FifoCostReportImportService
            )
            metadata = TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind(item["source_kind"]),
                completeness=EvidenceCompleteness(item["completeness"]),
                source_fingerprint=parser._source_fingerprint(
                    item["file_sha256"], scope,
                ),
            )
            reports.append(ReportEvidence(
                metadata=metadata,
                report_type=report_type,
                period_from=item.get("period_from"),
                period_to=item.get("period_to"),
                period_provenance=PeriodProvenance(item["period_provenance"]),
                captured_at=item["captured_at"],
                file_sha256=item["file_sha256"],
                parser_version=item["parser_version"],
                cell_references=tuple(payload["cell_references"]),
                normalized_fields=payload["normalized_fields"],
            ))
        return tuple(reports)

    @staticmethod
    def _metadata(payload, scope):
        scope_payload = payload["scope"]
        if any(scope_payload.get(key) != getattr(scope, key) for key in (
            "store_id", "product_id", "offer_id", "sku",
        )):
            raise ValueError("FIFO_TRANSITION_SCOPE_MISMATCH")
        return TransitionMetadata(
            scope=scope,
            source_kind=EvidenceSourceKind(payload["source_kind"]),
            completeness=EvidenceCompleteness(payload["completeness"]),
            source_fingerprint=payload["source_fingerprint"],
            schema_version=payload.get("schema_version", 1),
            store_timezone=payload.get("store_timezone", "Europe/Moscow"),
        )

    @staticmethod
    def _unknown_values(payload):
        return {
            key: UnknownValue(
                TransitionReasonCode(value["reason_code"]),
                EvidenceSourceKind(value["source_kind"]),
            )
            for key, value in (payload or {}).items()
        }

    @staticmethod
    def _items(result, *, maximum):
        if not isinstance(result, dict) or result.get("error") is not False:
            raise ValueError("FIFO_TRANSITION_EVIDENCE_UNAVAILABLE")
        items = result.get("items")
        if not isinstance(items, list) or len(items) > maximum:
            raise ValueError("FIFO_TRANSITION_EVIDENCE_LIMIT_REACHED")
        return items

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "preview_only": True}
