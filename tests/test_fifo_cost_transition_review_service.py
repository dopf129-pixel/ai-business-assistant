from datetime import datetime, timezone

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_report_import_service import FifoCostReportImportService
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SupplyReferenceKind,
    TransitionMetadata,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_transition_review_service import FifoCostTransitionReviewService
from services.ozon_account_repository import make_store_tenant_scope
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-a",
    "offer_id": "hook-2",
    "sku": "3921245627",
}


def _services(tmp_path):
    now = lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(
        db_path=tmp_path / "transition-review.sqlite", now_provider=now,
    )
    history = FifoCostHistoryService(repository)
    transition = FifoCostTransitionService(repository, now_provider=now)
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition, history, now_provider=now,
    )
    review = FifoCostTransitionReviewService(transition, history)
    return repository, history, transition, runtime, review


def _create_case(runtime):
    result = runtime.start_new_case(101, IDENTITY, "Крючки", 0, "TOTAL_LANDED")
    assert result["error"] is False, result
    return runtime._sessions["101"]["case_id"]


def test_readiness_rebuild_is_scoped_read_only_and_never_marks_ready(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("101", "store-a"))
    try:
        repository, _history, transition, runtime, review = _services(tmp_path)
        case_id = _create_case(runtime)
        before = transition.get_case(case_id=case_id, **IDENTITY)

        result = review.assess(case_id=case_id, identity=IDENTITY)

        after = transition.get_case(case_id=case_id, **IDENTITY)
        assert result["error"] is False, result
        assert result["ready_to_apply"] is False
        assert result["preview_only"] is True
        assert result["case_revision"] == before["case_revision"] == after["case_revision"]
        assert after["state"] == "DRAFT"
        assert result["readiness"].ready_to_apply is False
        assert result["readiness"].status in {"AWAITING_EVIDENCE", "CONFLICT"}
        assert "OWNER_CUTOFF_DATE_REQUIRED" in result["proposal"].requirements
        assert result["fifo_queue_initialized"] is False
        assert result["fifo_layers"] == ()

        hidden = repository.read_transition_evidence(
            case_id=case_id, **IDENTITY, kind="SUPPLY_DECLARATION",
        )
        assert hidden["error"] is False
        assert all("encrypted_lookup_reference" not in item for item in hidden["items"])
    finally:
        reset_current_tenant_user_id(tenant)


def test_review_only_exposes_layers_with_proven_remaining_units():
    confirmed = FifoCostTransitionReviewService._confirmed_fifo_layers({
        "error": False,
        "remaining_status": "AT_CONFIRMED_SNAPSHOT",
        "layers": [
            {
                "remaining_units": 3, "unit_cost_rub": "21.00",
                "effective_date": "2026-01-01", "recorded_location_label": "дома",
                "provenance_label": "подтверждено владельцем", "layer_id": "secret",
            },
            {"remaining_units": None, "unit_cost_rub": "14.65"},
            {"remaining_units": 0, "unit_cost_rub": "14.65"},
        ],
    })
    assert confirmed == ({
        "remaining_units": 3, "unit_cost_rub": "21.00",
        "effective_date": "2026-01-01", "location": "дома",
        "provenance": "подтверждено владельцем",
    },)
    assert FifoCostTransitionReviewService._confirmed_fifo_layers({
        "error": False,
        "remaining_status": "REPLAY_REQUIRED",
        "layers": [{"remaining_units": 3, "unit_cost_rub": "21.00"}],
    }) == ()


def test_review_reconstructs_typed_supply_and_report_evidence(tmp_path):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("101", "store-a"))
    try:
        repository, _history, transition, runtime, review = _services(tmp_path)
        case_id = _create_case(runtime)
        created = transition.declare_supply(
            case_id=case_id, **IDENTITY,
            reference_kind=SupplyReferenceKind.SUPPLY,
            reference_id="700003", declared_shipped_units=148,
            dispatch_date="2026-11-05", expected_case_revision=1,
            idempotency_key="review-supply-1",
        )
        assert created["error"] is False, created
        current = transition.get_case(case_id=case_id, **IDENTITY)
        scope = ScopeIdentity(
            owner_id="101", store_id=IDENTITY["store_id"],
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
        )
        file_digest = "a" * 64
        report = ReportEvidence(
            metadata=TransitionMetadata(
                scope=scope,
                source_kind=EvidenceSourceKind.OWNER_IMPORTED,
                completeness=EvidenceCompleteness.PARTIAL,
                source_fingerprint=FifoCostReportImportService._source_fingerprint(
                    file_digest, scope,
                ),
            ),
            report_type=ReportType.STOCK_MANAGEMENT,
            period_from="2026-11-07", period_to="2026-11-07",
            period_provenance=PeriodProvenance.FILENAME_CANDIDATE,
            captured_at="2026-11-08T12:00:00Z",
            file_sha256=file_digest, parser_version="fifo-stock-management-v1",
            cell_references=("M5",), normalized_fields={
                "stock_buckets": {"available": 1191, "supplier_transit": 6234},
                "fbs_return_available_units": 9,
                "fbs_return_is_subset_of_available": True,
            },
        )
        saved = repository.append_report_evidence(
            case_id=case_id, report=report,
            expected_case_revision=current["case_revision"],
            idempotency_key="review-report-1",
        )
        assert saved["error"] is False, saved

        result = review.assess(case_id=case_id, identity=IDENTITY)

        assert result["error"] is False, result
        assert result["reports_read"] == 1
        assert len(result["supply_reconciliation"].declarations) == 1
        assert result["supply_reconciliation"].declarations[0].declared_quantity == 148
        assert len(result["proposal"].stock_snapshots) == 1
        assert result["proposal"].stock_snapshots[0].period_provenance is PeriodProvenance.FILENAME_CANDIDATE
        assert result["readiness"].ready_to_apply is False
        assert result["case_revision"] == saved["case_revision"]
    finally:
        reset_current_tenant_user_id(tenant)
