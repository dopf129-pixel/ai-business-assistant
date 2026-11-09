from datetime import datetime, timezone

from cryptography.fernet import Fernet

from services.fifo_cost_cutoff_bridge_service import (
    FifoCutoffMovementCoverage,
    FifoFinanceSaleIdentity,
    FifoFinanceSaleIdentityBatch,
)
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_physical_sales_evidence_service import (
    FifoCostPhysicalSalesEvidenceService,
)
from services.fifo_cost_physical_sales_import_service import (
    FifoCostPhysicalSalesImportService,
)
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    SourceProof,
    StockBucket,
    TransitionMetadata,
    TransitionBridgeEvidenceKind,
    source_fingerprint,
)
from services.fifo_cost_transition_evidence_service import (
    FifoCostTransitionEvidenceService,
)
from services.fifo_cost_transition_review_service import (
    FifoCostTransitionReviewService,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)


IDENTITY = {
    "store_id": "store-fr18",
    "product_id": "product-fr18",
    "offer_id": "offer-fr18",
    "sku": "3921245627",
}
TENANT = make_store_tenant_scope("owner-fr18", IDENTITY["store_id"])
TIMEZONE = "Europe/Moscow"
PERIOD_FROM = "2026-11-05"
PERIOD_TO = "2026-11-08"
CUTOFF = "2026-11-06"


def _services(path, now):
    repository = FifoCostRepository(db_path=path, now_provider=now)
    history = FifoCostHistoryService(repository)
    transition = FifoCostTransitionService(repository, now_provider=now)
    return repository, history, transition


def _current_revision(transition, case_id):
    result = transition.get_case(case_id=case_id, **IDENTITY)
    assert result["error"] is False, result
    return result["case_revision"]


def _create_case(path, now):
    repository, history, transition = _services(path, now)
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition, history, now_provider=now,
    )
    created = runtime.start_new_case(
        101, IDENTITY, "Synthetic FR18", 0, "TOTAL_LANDED",
    )
    assert created["error"] is False, created
    return repository, history, transition, runtime._sessions["101"]["case_id"]


def _api_metadata(scope, completeness, fingerprint):
    return TransitionMetadata(
        scope=scope, source_kind=EvidenceSourceKind.OZON_API,
        completeness=completeness, source_fingerprint=fingerprint,
        store_timezone=TIMEZONE,
    )


def test_finance_identity_batches_rehydrate_from_durable_snapshot_after_restart(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(TENANT)
    now = lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    database = tmp_path / "finance-evidence.sqlite"
    try:
        _repository, _history, transition, case_id = _create_case(database, now)
        case_result = transition.get_case(case_id=case_id, **IDENTITY)
        case = transition._case_from_payload(case_result["case"])
        scope = case.metadata.scope
        proof = SourceProof(
            metadata=_api_metadata(scope, EvidenceCompleteness.COMPLETE, "a" * 64),
            scope_complete=True, pagination_complete=True,
            source_as_of="2026-11-09T12:00:00Z",
        )
        batch = FifoFinanceSaleIdentityBatch(
            metadata=_api_metadata(scope, EvidenceCompleteness.COMPLETE, "b" * 64),
            source_fingerprint="b" * 64,
            period_from=PERIOD_FROM, period_to=PERIOD_TO,
            source_as_of=proof.source_as_of, proof=proof,
            rows=(FifoFinanceSaleIdentity(
                posting_number="synthetic-posting-1", finance_sku=IDENTITY["sku"],
                offer_id=IDENTITY["offer_id"], product_id=IDENTITY["product_id"],
            ),),
        )
        evidence = FifoCostTransitionEvidenceService(transition)
        recorded = evidence.record_finance_identity_batches(
            case_id=case_id, identity=IDENTITY, batches=(batch,),
            requested_period_from=PERIOD_FROM, requested_period_to=PERIOD_TO,
            source_complete=True,
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-finance-snapshot-1",
        )
        assert recorded["error"] is False, recorded

        restarted_repository, _history, restarted_transition = _services(database, now)
        restored = FifoCostTransitionEvidenceService(restarted_transition).load(
            case_id=case_id, identity=IDENTITY,
            expected_case_revision=_current_revision(restarted_transition, case_id),
        )
        assert restored["error"] is False, restored
        assert restored["bundle"].finance_batch.rows == batch.rows
        assert restored["bundle"].finance_batch.period_from == PERIOD_FROM
        assert "FINANCE_IDENTITY_COVERAGE_INCOMPLETE" not in restored["missing_requirements"]
        stored = restarted_repository.read_transition_bridge_evidence(
            case_id=case_id, **IDENTITY,
            evidence_kind=TransitionBridgeEvidenceKind.FINANCE_IDENTITY_SNAPSHOT,
            limit=1,
        )
        assert stored["error"] is False, stored
        assert "synthetic-posting-1" not in repr(stored)
    finally:
        reset_current_tenant_user_id(tenant)


def test_incomplete_movement_snapshot_stays_a_concrete_blocker_after_restart(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(TENANT)
    now = lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    database = tmp_path / "movement-evidence.sqlite"
    try:
        repository, history, transition, case_id = _create_case(database, now)
        case_result = transition.get_case(case_id=case_id, **IDENTITY)
        case = transition._case_from_payload(case_result["case"])
        scope = case.metadata.scope
        proof = SourceProof(
            metadata=_api_metadata(scope, EvidenceCompleteness.PARTIAL, "c" * 64),
            scope_complete=True, pagination_complete=False,
            source_as_of="2026-11-09T12:00:00Z",
        )
        coverage = FifoCutoffMovementCoverage(
            scope=scope, period_from=PERIOD_FROM, complete_through=PERIOD_TO,
            source_fingerprint="c" * 64, proof=proof, movements=(), page_count=2,
        )
        evidence = FifoCostTransitionEvidenceService(transition)
        recorded = evidence.record_movement_coverage(
            case_id=case_id, identity=IDENTITY, coverage=coverage,
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-movement-snapshot-1",
        )
        assert recorded["error"] is False, recorded
        confirmed = evidence.confirm_movement_coverage(
            case_id=case_id, identity=IDENTITY,
            evidence_id=recorded["evidence_id"],
            expected_evidence_fingerprint=recorded["payload_fingerprint"],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-movement-confirm-1",
        )
        assert confirmed["error"] is False, confirmed

        _restarted_repository, restarted_history, restarted_transition = _services(database, now)
        review = FifoCostTransitionReviewService(
            restarted_transition, restarted_history,
        )
        result = review.assess(case_id=case_id, identity=IDENTITY)
        assert result["error"] is False, result
        assert result["preview_only"] is True
        assert result["ready_to_apply"] is False
        assert result["cutoff_bridge_status"] == "MISSING_EVIDENCE"
        assert "MOVEMENT_COVERAGE_INCOMPLETE" in result["cutoff_bridge_missing_requirements"]
        assert result["case_revision"] == _current_revision(restarted_transition, case_id)
    finally:
        reset_current_tenant_user_id(tenant)


def test_complete_saved_sources_rebuild_the_actual_cutoff_bridge_after_restart(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(TENANT)
    now = lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    database = tmp_path / "ready-bridge.sqlite"
    try:
        repository, history, transition, case_id = _create_case(database, now)
        updated = transition.update_owner_inputs(
            case_id=case_id, **IDENTITY, expected_revision=1,
            updates={
                "dispatch_date": PERIOD_FROM,
                "old_unit_cost_rub": "21.00",
                "new_unit_cost_rub": "14.65",
                "owner_old_home_units": 3,
                "owner_old_transit_units": 0,
                "new_home_quantity": 0,
                "declared_shipped_units": 0,
            },
            idempotency_key="fr18-owner-facts-1",
        )
        assert updated["error"] is False, updated
        current = transition.get_case(case_id=case_id, **IDENTITY)
        case = transition._case_from_payload(current["case"])
        scope = case.metadata.scope
        buckets = {bucket.value: 0 for bucket in StockBucket}
        buckets.update({"available": 100, "supplier_transit": 0})
        report = ReportEvidence(
            metadata=TransitionMetadata(
                scope=scope, source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.COMPLETE,
                source_fingerprint="d" * 64, store_timezone=TIMEZONE,
            ),
            report_type=ReportType.STOCK_MANAGEMENT,
            period_from=CUTOFF, period_to=CUTOFF,
            period_provenance=PeriodProvenance.OWNER_CONFIRMED,
            captured_at="2026-11-09T12:00:00Z", file_sha256="e" * 64,
            parser_version="fifo-stock-management-v1", cell_references=("A1",),
            normalized_fields={
                "stock_buckets": buckets,
                "fbs_return_available_units": 0,
                "fbs_return_is_subset_of_available": True,
            },
        )
        saved_report = repository.append_report_evidence(
            case_id=case_id, report=report,
            expected_case_revision=current["case_revision"],
            idempotency_key="fr18-stock-report-1",
        )
        assert saved_report["error"] is False, saved_report
        cutoff = transition.record_cutoff_selection(
            case_id=case_id, **IDENTITY, cutoff_date=CUTOFF,
            stock_report_fingerprint=report.file_sha256,
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-cutoff-selection-1",
        )
        assert cutoff["error"] is False, cutoff
        confirmed_cutoff = transition.confirm_cutoff_selection(
            case_id=case_id, **IDENTITY, evidence_id=cutoff["evidence_id"],
            expected_evidence_fingerprint=cutoff["payload_fingerprint"],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-cutoff-confirm-1",
        )
        assert confirmed_cutoff["error"] is False, confirmed_cutoff
        opening = transition.record_opening_composition(
            case_id=case_id, **IDENTITY,
            cutoff_evidence_id=cutoff["evidence_id"],
            cutoff_evidence_fingerprint=cutoff["payload_fingerprint"],
            stock_report_fingerprint=report.file_sha256,
            layers=[
                {"sequence": 1, "unit_cost_rub": "21.00", "ozon_units": 0,
                 "transit_units": 0, "home_units": 3},
                {"sequence": 2, "unit_cost_rub": "14.65", "ozon_units": 100,
                 "transit_units": 0, "home_units": 0},
            ],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-opening-composition-1",
        )
        assert opening["error"] is False, opening
        confirmed_opening = transition.confirm_opening_composition(
            case_id=case_id, **IDENTITY, evidence_id=opening["evidence_id"],
            expected_evidence_fingerprint=opening["payload_fingerprint"],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-opening-confirm-1",
        )
        assert confirmed_opening["error"] is False, confirmed_opening

        finance_source = source_fingerprint("fr18-finance-source")
        finance_proof = SourceProof(
            metadata=_api_metadata(scope, EvidenceCompleteness.COMPLETE, finance_source),
            scope_complete=True, pagination_complete=True,
            source_as_of="2026-11-09T12:00:00Z",
        )
        finance_batch_source = source_fingerprint("fr18-finance-batch")
        finance_batch = FifoFinanceSaleIdentityBatch(
            metadata=_api_metadata(scope, EvidenceCompleteness.COMPLETE, finance_batch_source),
            source_fingerprint=finance_batch_source,
            period_from=PERIOD_FROM, period_to=PERIOD_TO,
            source_as_of=finance_proof.source_as_of, proof=finance_proof,
            rows=(FifoFinanceSaleIdentity(
                posting_number="synthetic-posting-1", finance_sku=IDENTITY["sku"],
                offer_id=IDENTITY["offer_id"], product_id=IDENTITY["product_id"],
            ),),
        )
        evidence = FifoCostTransitionEvidenceService(transition)
        finance_saved = evidence.record_finance_identity_batches(
            case_id=case_id, identity=IDENTITY, batches=(finance_batch,),
            requested_period_from=PERIOD_FROM, requested_period_to=PERIOD_TO,
            source_complete=True,
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-finance-batch-1",
        )
        assert finance_saved["error"] is False, finance_saved

        raw_csv = (
            FifoCostPhysicalSalesImportService.TEMPLATE_HEADER + "\n"
            f"synthetic-posting-1;{IDENTITY['sku']};1;2026-11-07;synthetic-row-1\n"
        ).encode("utf-8")
        physical_importer = FifoCostPhysicalSalesImportService()
        parsed = physical_importer.parse_csv(
            filename="physical-sales.csv", payload=raw_csv, scope=scope,
        )
        assert parsed.document is not None, parsed.issue_codes
        physical = FifoCostPhysicalSalesEvidenceService()
        physical_preview = physical.preview_document(
            document=parsed.document, period_from=PERIOD_FROM,
            period_to=PERIOD_TO, timezone_name=TIMEZONE,
        )
        physical_saved = physical.save_document(
            repository=repository, case_id=case_id, scope=scope,
            filename="physical-sales.csv", payload=raw_csv,
            document=parsed.document, period_from=PERIOD_FROM,
            period_to=PERIOD_TO, timezone_name=TIMEZONE,
            captured_at="2026-11-09T12:00:00Z",
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-physical-document-1",
        )
        assert physical_saved["error"] is False, physical_saved
        physical_confirmed = physical.confirm_document(
            repository=repository, case_id=case_id, scope=scope,
            evidence_id=physical_saved["evidence_id"],
            expected_evidence_fingerprint=physical_saved["payload_fingerprint"],
            expected_case_revision=_current_revision(transition, case_id),
            expected_document_fingerprint=physical_preview["document_fingerprint"],
            expected_rows_fingerprint=physical_preview["rows_fingerprint"],
            expected_identity_fingerprint=physical_preview["identity_fingerprint"],
            expected_row_count=physical_preview["row_count"],
            period_from=PERIOD_FROM, period_to=PERIOD_TO,
            timezone_name=TIMEZONE, semantics="PHYSICAL_OUTFLOW",
            idempotency_key="fr18-physical-confirm-1",
        )
        assert physical_confirmed["error"] is False, physical_confirmed

        movement_source = source_fingerprint("fr18-movement-source")
        movement_proof = SourceProof(
            metadata=_api_metadata(scope, EvidenceCompleteness.COMPLETE, movement_source),
            scope_complete=True, pagination_complete=True,
            source_as_of="2026-11-09T12:00:00Z",
        )
        movement_coverage = FifoCutoffMovementCoverage(
            scope=scope, period_from=PERIOD_FROM, complete_through=PERIOD_TO,
            source_fingerprint=movement_source, proof=movement_proof,
            movements=(), page_count=1,
        )
        movement_saved = evidence.record_movement_coverage(
            case_id=case_id, identity=IDENTITY, coverage=movement_coverage,
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-movement-coverage-1",
        )
        assert movement_saved["error"] is False, movement_saved
        movement_confirmed = evidence.confirm_movement_coverage(
            case_id=case_id, identity=IDENTITY,
            evidence_id=movement_saved["evidence_id"],
            expected_evidence_fingerprint=movement_saved["payload_fingerprint"],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-movement-confirm-1",
        )
        assert movement_confirmed["error"] is False, movement_confirmed

        # Source evidence is finalized before the owner re-confirms the exact
        # cutoff and opening composition that reference it.
        final_cutoff = transition.record_cutoff_selection(
            case_id=case_id, **IDENTITY, cutoff_date=CUTOFF,
            stock_report_fingerprint=report.file_sha256,
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-cutoff-selection-final",
        )
        assert final_cutoff["error"] is False, final_cutoff
        final_cutoff_confirmation = transition.confirm_cutoff_selection(
            case_id=case_id, **IDENTITY,
            evidence_id=final_cutoff["evidence_id"],
            expected_evidence_fingerprint=final_cutoff["payload_fingerprint"],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-cutoff-confirm-final",
        )
        assert final_cutoff_confirmation["error"] is False, final_cutoff_confirmation
        final_opening = transition.record_opening_composition(
            case_id=case_id, **IDENTITY,
            cutoff_evidence_id=final_cutoff["evidence_id"],
            cutoff_evidence_fingerprint=final_cutoff["payload_fingerprint"],
            stock_report_fingerprint=report.file_sha256,
            layers=[
                {"sequence": 1, "unit_cost_rub": "21.00", "ozon_units": 0,
                 "transit_units": 0, "home_units": 3},
                {"sequence": 2, "unit_cost_rub": "14.65", "ozon_units": 100,
                 "transit_units": 0, "home_units": 0},
            ],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-opening-composition-final",
        )
        assert final_opening["error"] is False, final_opening
        final_opening_confirmation = transition.confirm_opening_composition(
            case_id=case_id, **IDENTITY,
            evidence_id=final_opening["evidence_id"],
            expected_evidence_fingerprint=final_opening["payload_fingerprint"],
            expected_case_revision=_current_revision(transition, case_id),
            idempotency_key="fr18-opening-confirm-final",
        )
        assert final_opening_confirmation["error"] is False, final_opening_confirmation

        restarted_repository, restarted_history, restarted_transition = _services(database, now)
        restarted_evidence = FifoCostTransitionEvidenceService(restarted_transition)
        bundle = restarted_evidence.load(
            case_id=case_id, identity=IDENTITY,
            expected_case_revision=_current_revision(restarted_transition, case_id),
        )
        assert bundle["error"] is False, bundle
        assert bundle["missing_requirements"] == ()
        review = FifoCostTransitionReviewService(
            restarted_transition, restarted_history,
            evidence_service=restarted_evidence,
        )
        reviewed = review.assess(case_id=case_id, identity=IDENTITY)
        assert reviewed["error"] is False, reviewed
        assert reviewed["cutoff_bridge_status"] == "READY"
        assert reviewed["cutoff_bridge_missing_requirements"] == ()
        assert reviewed["ready_to_apply"] is False
        assert reviewed["preview_only"] is True
    finally:
        reset_current_tenant_user_id(tenant)
