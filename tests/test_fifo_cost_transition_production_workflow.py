"""Production-assembly regressions for the FIFO transition positive path."""

from datetime import datetime, timezone
from importlib.util import find_spec

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_review_service import FifoCostTransitionReviewService
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-a",
    "offer_id": "hook-2",
    "sku": "3921245627",
}
TENANT = make_store_tenant_scope("owner-a", "store-a")


def test_readiness_assessment_reloads_saved_evidence_before_cutoff_bridge_review(tmp_path):
    now = lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(
        db_path=tmp_path / "saved-evidence-review.sqlite", now_provider=now,
    )
    history = FifoCostHistoryService(repository)
    transition = FifoCostTransitionService(repository, now_provider=now)
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition, history, now_provider=now,
    )
    tenant = set_current_tenant_user_id(TENANT)
    try:
        created = runtime.start_new_case(101, IDENTITY, "Товар", 0, "TOTAL_LANDED")
        assert created["error"] is False, created
        case_id = runtime._sessions["101"]["case_id"]

        class SavedEvidenceReader:
            def __init__(self):
                self.calls = []
                self.opening_requirements = []

            def load(
                self, *, case_id, identity, expected_case_revision,
                require_opening_composition=True, sealed_preview_id=None,
            ):
                self.calls.append((case_id, dict(identity), expected_case_revision))
                self.opening_requirements.append(require_opening_composition)
                return {"error": True, "code": "FIFO_TRANSITION_EVIDENCE_MISSING"}

        saved_evidence = SavedEvidenceReader()
        review = FifoCostTransitionReviewService(
            transition, history, evidence_service=saved_evidence,
        )
        result = review.assess(case_id=case_id, identity=IDENTITY)

        assert len(saved_evidence.calls) == 1
        assert saved_evidence.calls[0][0] == case_id
        assert saved_evidence.calls[0][1] == IDENTITY
        assert result["ready_to_apply"] is False
        assert transition.get_case(case_id=case_id, **IDENTITY)["case_revision"] == (
            saved_evidence.calls[0][2]
        )

        history.get_sku_history = lambda **_identity: {
            "error": False, "queue_initialized": True,
            "remaining_status": "COMPLETE", "layers": [],
        }
        existing_result = review.assess(
            case_id=case_id, identity=IDENTITY,
            for_transition_prepare=True,
        )
        assert existing_result["error"] is False, existing_result
        assert saved_evidence.opening_requirements[-1] is False
        assert existing_result["opening_composition_required"] is False
        assert "FIFO_ALREADY_INITIALIZED" not in existing_result["proposal"].issue_codes
        assert existing_result["ready_to_apply"] is False
        assert transition.get_case(case_id=case_id, **IDENTITY)["case_revision"] == (
            saved_evidence.calls[-1][2]
        )
    finally:
        reset_current_tenant_user_id(tenant)


def test_production_workflow_builder_wires_durable_evidence_review_apply_and_runtime(tmp_path):
    import app.telegram_assistant_factory as factory_module

    builder = getattr(factory_module, "create_fifo_cost_transition_workflow", None)
    assert callable(builder), (
        "Production-path blocker reproduced: Telegram factory has no shared transition workflow"
    )
    assert find_spec("services.fifo_cost_transition_apply_service") is not None
    assert find_spec("services.fifo_cost_transition_evidence_service") is not None
    import services.fifo_cost_transition_apply_service as apply_module
    import services.fifo_cost_transition_evidence_service as evidence_module
    assert getattr(apply_module, "FifoCostTransitionApplyService", None) is not None
    assert getattr(evidence_module, "FifoCostTransitionEvidenceService", None) is not None

    now = lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(
        db_path=tmp_path / "production-workflow.sqlite", now_provider=now,
    )
    history = FifoCostHistoryService(repository)
    transition = FifoCostTransitionService(repository, now_provider=now)
    source_collection = object()
    tax_service = object()
    period_profit_service = object()
    invalidations = []
    workflow = builder(
        repository=repository,
        history_service=history,
        transition_service=transition,
        source_collection_service=source_collection,
        tax_service=tax_service,
        period_profit_service=period_profit_service,
        cache_invalidator=lambda identity: invalidations.append(identity),
        now_provider=now,
    )

    assert workflow["runtime_service"].apply_service is workflow["apply_service"]
    assert workflow["runtime_service"].cache_invalidator is None
    assert workflow["review_service"].evidence_service is workflow["evidence_service"]
    assert workflow["review_service"].transition_service is transition
    assert workflow["evidence_service"].repository is repository
    assert workflow["apply_service"].repository is repository
    assert workflow["apply_service"].review_service is workflow["review_service"]
    assert workflow["period_summary_collection_service"].impact_service is (
        workflow["impact_service"]
    )
    assert workflow["source_collection_service"] is source_collection
    assert workflow["tax_service"] is tax_service
    assert workflow["period_profit_service"] is period_profit_service
    workflow["apply_service"].cache_invalidator(
        identity=IDENTITY, case_id="case-a", case_revision=5,
        fifo_revision=4, allocation_revision=6,
    )
    assert invalidations == [IDENTITY]


def test_durable_physical_sale_document_is_available_to_production_workflow(tmp_path):
    import app.telegram_assistant_factory as factory_module

    builder = getattr(factory_module, "create_fifo_cost_transition_workflow", None)
    assert callable(builder), (
        "Physical-document blocker reproduced: production assembly cannot expose its durable import flow"
    )

    now = lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    repository = FifoCostRepository(
        db_path=tmp_path / "physical-document-workflow.sqlite", now_provider=now,
    )
    history = FifoCostHistoryService(repository)
    transition = FifoCostTransitionService(repository, now_provider=now)
    workflow = builder(
        repository=repository,
        history_service=history,
        transition_service=transition,
        source_collection_service=object(),
        tax_service=object(),
        period_profit_service=object(),
        now_provider=now,
    )
    importer = workflow["physical_sales_import_service"]
    assert callable(getattr(importer, "start_selection", None))
    assert callable(getattr(importer, "handle_document", None))
    assert callable(getattr(importer, "handle_callback", None))

