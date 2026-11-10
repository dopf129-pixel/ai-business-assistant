"""Production-assembly regressions for the FIFO transition positive path."""

from datetime import datetime, timezone
from importlib.util import find_spec

import pytest
from cryptography.fernet import Fernet
from openpyxl import load_workbook
from io import BytesIO

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
    "product_id": "101",
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


@pytest.mark.parametrize(
    "supplier_receiving_units", [None, 148],
    ids=["unknown-remains-blocked", "explicit-owner-confirmation"],
)
def test_fr27_production_workflow_requires_exact_owner_cutoff_receiving_bucket(
    tmp_path, monkeypatch, supplier_receiving_units,
):
    """Exercise the actual production graph using only synthetic source bytes."""
    from services.fifo_cost_cutoff_bridge_service import FifoCutoffMovementCoverage
    from services.fifo_current_unit_cost_adapter import FifoCurrentUnitCostAdapter
    from services.fifo_cost_history_service import FifoCostHistoryService
    from services.fifo_cost_period_profit_source_service import (
        FifoCostPeriodProfitSourceService,
    )
    from services.fifo_cost_physical_sales_import_service import (
        FifoCostPhysicalSalesImportService,
    )
    from services.fifo_cost_report_import_service import FifoCostReportImportService
    from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
    from services.fifo_cost_stock_management_import_service import (
        FifoCostStockManagementImportService,
    )
    from services.fifo_cost_transition_contracts import (
        EvidenceCompleteness,
        EvidenceSourceKind,
        ReportType,
        ScopeIdentity,
        SourceProof,
        TransitionState,
        source_fingerprint,
    )
    from services.fifo_cost_transition_service import FifoCostTransitionService
    from services.ozon_account_repository import make_store_tenant_scope
    from services.tax_configuration_service import TaxConfigurationService
    from services.tax_service import TaxService
    from services.telegram_fifo_cost_history_service import TelegramFifoCostHistoryService
    from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
    from test_fifo_cost_report_import_service import _turnover_payload
    from test_fifo_cost_stock_management_import_service import (
        _DETAIL_COLUMNS, _MASTER_COLUMNS, _stock_payload,
    )

    import app.telegram_assistant_factory as factory_module

    now = lambda: datetime(2026, 12, 16, 12, tzinfo=timezone.utc)
    tenant_scope = make_store_tenant_scope("owner-fr27", IDENTITY["store_id"])
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(tenant_scope)

    def current_case(transition, case_id):
        result = transition.get_case(case_id=case_id, **IDENTITY)
        assert result["error"] is False, result
        return result

    def latest_revision(transition, case_id):
        return current_case(transition, case_id)["case_revision"]

    def click_button(result, predicate):
        assert result.get("error") is False, result
        buttons = result.get("keyboard", {}).get("buttons", [])
        button = next((item for item in buttons if predicate(item["text"])), None)
        assert button is not None, result
        return button["callback"]

    class SyntheticOzon:
        def __init__(self):
            self.observed_methods = []

        def _observe(self, method, options):
            self.observed_methods.append(method)
            from services.period_profit_operation_diagnostics import current_period_profit_trace

            trace = current_period_profit_trace()
            if trace is not None:
                reserved = trace.reserve_ozon_request("synthetic-fr27")
                if reserved.get("error"):
                    return {"error": True, "code": reserved["code"]}
            observer = options.get("request_attempt_observer")
            if callable(observer):
                observer("synthetic-fr27")
            return None

        def get_supply_orders_list(self, _states, **options):
            return self._observe("supply-list", options) or {
                "order_ids": [7001], "last_id": None,
            }

        def get_supply_orders_details(self, order_ids, **options):
            error = self._observe("supply-details", options)
            if error:
                return error
            return {"orders": [{
                "order_id": _order_id,
                "state": "COMPLETED",
                "supplies": [{
                    "supply_id": 2001,
                    "state": "COMPLETED",
                    "is_crossdock": True,
                }],
            } for _order_id in order_ids]}

        def get_supply_act_summary(self, _order_id, **options):
            error = self._observe("supply-act-summary", options)
            if error:
                return error
            return {"supplies_acts": [{
                "supply_id": 2001,
                "is_agreement_completed": True,
                "supply_acts": [{
                    "type": "ACCEPTANCE", "act_state": "ACCEPTED",
                    "act_id": 3001, "created_date": "2026-11-06",
                    "summary": {"fact_quantity": 101, "unidentified_quantity": 0},
                }],
            }]}

        def get_supply_act_products(self, _supply_id, **options):
            error = self._observe("supply-act-products", options)
            if error:
                return error
            return {"supply_acts": [{
                "act_id": 3001,
                "type": "ACCEPTANCE",
                "items": [{
                    "sku_info": {"sku": int(IDENTITY["sku"])},
                    "fact_quantity": 101,
                    "unidentified_quantity": 0,
                }],
            }]}

        def get_realization_posting(self, _year, _month, **options):
            error = self._observe("realization", options)
            if error:
                return error
            return {"rows": [{
                "order": {"posting_number": "synthetic-pre-cutoff"},
                "item": {
                    "sku": IDENTITY["sku"], "offer_id": IDENTITY["offer_id"],
                    "product_id": IDENTITY["product_id"],
                },
            }, {
                "order": {"posting_number": "synthetic-mr01-sale"},
                "item": {
                    "sku": IDENTITY["sku"], "offer_id": IDENTITY["offer_id"],
                    "product_id": IDENTITY["product_id"],
                },
            }]}

    class ParserWorker:
        def __init__(self):
            self.reports = {}

        def parse(self, *, report_type, filename, payload, scope):
            if report_type is ReportType.STOCK_MANAGEMENT:
                parsed = FifoCostStockManagementImportService(
                    utc_clock=now,
                ).parse_stock_management_workbook(
                    payload=payload, filename=filename, scope=scope,
                )
            else:
                parsed = FifoCostReportImportService(
                    utc_clock=now,
                ).parse_turnover_workbook(
                    payload=payload, filename=filename, scope=scope,
                )
            self.reports[report_type] = parsed.report_evidence
            return parsed

        def parse_physical_sales(self, *, filename, payload, scope):
            return FifoCostPhysicalSalesImportService().parse_csv(
                filename=filename, payload=payload, scope=scope,
            )

    class DailyFinanceCache:
        def get_cached_daily_accruals(self, date_from, date_to):
            from datetime import date, timedelta

            day, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
            result = {}
            while day <= end:
                result[day.isoformat()] = {
                    "error": False, "accruals": [], "last_id": "", "pages_loaded": 1,
                }
                day += timedelta(days=1)
            return result

    source_client = SyntheticOzon()
    source_collection = FifoCostSourceCollectionService(
        ozon_client=source_client,
        utc_clock=now,
    )
    repository = FifoCostRepository(
        db_path=tmp_path / "fr27-production.sqlite", now_provider=now,
    )
    history = FifoCostHistoryService(repository)
    transition = FifoCostTransitionService(repository, now_provider=now)
    tax_configuration = TaxConfigurationService(file_path=tmp_path / "tax-policy.json")
    assert tax_configuration.save_policy("NONE")["error"] is False
    period_profit_reader = object()
    workflow = factory_module.create_fifo_cost_transition_workflow(
        repository=repository,
        history_service=history,
        transition_service=transition,
        source_collection_service=source_collection,
        tax_service=TaxService(),
        period_profit_service=period_profit_reader,
        tax_configuration_service=tax_configuration,
        now_provider=now,
    )
    parser_worker = ParserWorker()
    workflow["report_import_service"].worker = parser_worker
    workflow["physical_sales_import_service"].worker = parser_worker
    runtime = workflow["runtime_service"]

    try:
        created = runtime.start_new_case(101, IDENTITY, "Synthetic", 0, "TOTAL_LANDED")
        assert created.get("error") is False, created
        listed = transition.list_cases(store_id=IDENTITY["store_id"], sku=IDENTITY["sku"])
        case_id = listed["cases"][0]["case_id"]
        saved_inputs = transition.update_owner_inputs(
            case_id=case_id, **IDENTITY,
            expected_revision=latest_revision(transition, case_id),
            updates={
                "old_unit_cost_rub": "21.00",
                "new_unit_cost_rub": "14.65",
                "dispatch_date": "2026-11-05",
                "owner_old_home_units": 3,
                "owner_old_transit_units": 0,
                "new_home_quantity": 0,
                "declared_shipped_units": 101,
            },
            state=TransitionState.AWAITING_EVIDENCE,
            idempotency_key="fr27-owner-inputs-0001",
        )
        assert saved_inputs.get("error") is False, saved_inputs

        declared = transition.declare_supply(
            case_id=case_id, **IDENTITY,
            reference_kind="SUPPLY", reference_id="2001",
            declared_shipped_units=101, dispatch_date="2026-11-05",
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-supply-declaration-0001",
        )
        assert declared.get("error") is False, declared
        manifest = transition.get_supply_manifest(case_id=case_id, **IDENTITY)
        assert manifest.get("error") is False, manifest
        supply_refresh = workflow["supply_refresh_service"].refresh(
            case_id=case_id,
            declaration_id=manifest["declarations"][0]["declaration_id"],
            reference_id="2001", **IDENTITY,
            expected_case_revision=latest_revision(transition, case_id),
        )
        assert supply_refresh.status == "COMPLETE", supply_refresh
        assert supply_refresh.source_status == "COMPLETE"
        assert supply_refresh.act_snapshot.units_by_sku == ((IDENTITY["sku"], 101),)
        assert {"supply-list", "supply-details", "supply-act-summary", "supply-act-products"} <= set(
            source_client.observed_methods
        )

        scope = ScopeIdentity(
            owner_id="owner-fr27", store_id=IDENTITY["store_id"],
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
        )

        def import_report(report_type, filename, payload):
            importer = workflow["report_import_service"]
            selection = importer.create_selection_callback(
                user_id="owner-fr27", case_id=case_id, scope=scope,
                report_type=report_type,
            )
            assert selection.get("error") is False, selection
            assert importer.handle_callback("owner-fr27", selection["callback"])["error"] is False
            preview = importer.handle_document("owner-fr27", payload, filename)
            assert preview.get("code") == "FIFO_REPORT_PREVIEW_READY", preview
            confirm = click_button(
                preview, lambda text: "Подтвердить период" in text,
            )
            saved = importer.handle_callback("owner-fr27", confirm)
            assert saved.get("error") is False, saved
            return saved

        def make_stock_payload():
            def mutate(workbook):
                products = workbook["Товары"]
                warehouse = workbook["Товар-склад"]
                for row, available in ((5, 100), (6, 0)):
                    products[f"L{row}"] = available
                    for column in _MASTER_COLUMNS.values():
                        products[f"{column}{row}"] = 0
                    products[f"M{row}"] = available
                    warehouse[f"J{row}"] = available
                    for column in _DETAIL_COLUMNS.values():
                        warehouse[f"{column}{row}"] = 0
                    warehouse[f"K{row}"] = available
            return _stock_payload(mutate=mutate, include_removed=True)

        stock_saved = import_report(
            ReportType.STOCK_MANAGEMENT,
            "stock_06.11.2026_21-16.xlsx", make_stock_payload(),
        )
        turnover_payload = _turnover_payload(
            second_sku=False,
            mutate=lambda sheet: [
                setattr(sheet.cell(4, column), "value", 0)
                for column in range(1, 41)
            ] + [
                setattr(sheet["A4"], "value", int(IDENTITY["sku"])),
                setattr(sheet["L4"], "value", 101),
                setattr(sheet["T4"], "value", 1),
                setattr(sheet["AB4"], "value", 100),
                setattr(sheet["AK4"], "value", 101),
                setattr(sheet["AL4"], "value", 1),
                setattr(sheet["AM4"], "value", 100),
                setattr(sheet["AN4"], "value", 0),
            ],
        )
        turnover_saved = import_report(
            ReportType.TURNOVER,
            "turnover_05112026-06112026.xlsx", turnover_payload,
        )
        assert stock_saved["code"] == "FIFO_TRANSITION_EVIDENCE_SAVED", stock_saved
        assert turnover_saved["error"] is False

        physical_importer = workflow["physical_sales_import_service"]
        case_revision = latest_revision(transition, case_id)
        selection = physical_importer.start_selection(
            user_id="owner-fr27", case_id=case_id, scope=scope,
            expected_case_revision=case_revision,
        )
        assert selection.get("code") == "FIFO_PHYSICAL_SALES_UPLOAD_SELECTED", selection
        physical_csv = (
            FifoCostPhysicalSalesImportService.TEMPLATE_HEADER + "\n"
            f"synthetic-pre-cutoff;{IDENTITY['sku']};1;2026-11-05;row-pre-cutoff\n"
            f"synthetic-mr01-sale;{IDENTITY['sku']};5;2026-11-08;row-mr01-sale\n"
        ).encode("utf-8")
        physical_preview = physical_importer.handle_document(
            user_id="owner-fr27", content=physical_csv,
            filename="physical-sales-fr27.csv", expected_case_id=case_id,
            expected_scope=scope, expected_case_revision=case_revision,
        )
        assert physical_preview.get("code") == "FIFO_PHYSICAL_SALES_PREVIEW_READY", physical_preview
        save_physical = click_button(
            physical_preview, lambda text: "Сохранить документ" in text,
        )
        physical_saved = physical_importer.handle_callback(
            user_id="owner-fr27", callback=save_physical,
            expected_case_id=case_id, expected_scope=scope,
            expected_case_revision=case_revision,
        )
        assert physical_saved.get("error") is False, physical_saved
        physical_revision = latest_revision(transition, case_id)
        confirm_physical = click_button(
            physical_saved, lambda text: "Подтвердить" in text,
        )
        physical_confirmed = physical_importer.handle_callback(
            user_id="owner-fr27", callback=confirm_physical,
            expected_case_id=case_id, expected_scope=scope,
            expected_case_revision=physical_revision,
        )
        assert physical_confirmed.get("code") == "FIFO_PHYSICAL_SALES_CONFIRMED", physical_confirmed

        case_revision = latest_revision(transition, case_id)
        case_payload = current_case(transition, case_id)["case"]
        typed_case = transition._case_from_payload(case_payload)
        finance = source_collection.collect_finance_identity_snapshot(
            scope=typed_case.metadata.scope,
            period_from="2026-11-05", period_to="2026-11-08",
            transition_case_id=case_id,
            transition_case_revision=case_revision,
            store_timezone="Europe/Moscow",
        )
        assert finance.status == "COMPLETE", finance
        batches = finance.finance_identity_snapshots
        assert len(batches) == 1 and len(batches[0].rows) == 2
        finance_saved = workflow["evidence_service"].record_finance_identity_batches(
            case_id=case_id, identity=IDENTITY, batches=batches,
            requested_period_from="2026-11-05", requested_period_to="2026-11-08",
            source_complete=True,
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-finance-identity-0001",
        )
        assert finance_saved.get("error") is False, finance_saved

        movement_source = source_fingerprint("fr27-complete-empty-movements")
        movement_metadata = typed_case.metadata.__class__(
            scope=typed_case.metadata.scope,
            source_kind=EvidenceSourceKind.OZON_API,
            completeness=EvidenceCompleteness.COMPLETE,
            source_fingerprint=movement_source,
            store_timezone="Europe/Moscow",
        )
        movement_coverage = FifoCutoffMovementCoverage(
            scope=typed_case.metadata.scope,
            period_from="2026-11-05", complete_through="2026-11-08",
            source_fingerprint=movement_source,
            proof=SourceProof(
                metadata=movement_metadata, scope_complete=True,
                pagination_complete=True,
                source_as_of="2026-11-16T12:00:00Z",
            ),
            movements=(), page_count=1,
        )
        movement_saved = workflow["evidence_service"].record_movement_coverage(
            case_id=case_id, identity=IDENTITY, coverage=movement_coverage,
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-movement-coverage-0001",
        )
        assert movement_saved.get("error") is False, movement_saved
        movement_confirmed = workflow["evidence_service"].confirm_movement_coverage(
            case_id=case_id, identity=IDENTITY,
            evidence_id=movement_saved["evidence_id"],
            expected_evidence_fingerprint=movement_saved["payload_fingerprint"],
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-movement-confirm-0001",
        )
        assert movement_confirmed.get("error") is False, movement_confirmed

        cutoff = transition.record_cutoff_selection(
            case_id=case_id, **IDENTITY, cutoff_date="2026-11-06",
            stock_report_fingerprint=parser_worker.reports[
                ReportType.STOCK_MANAGEMENT
            ].file_sha256,
            supplier_receiving_units=supplier_receiving_units,
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-cutoff-selection-0001",
        )
        assert cutoff.get("error") is False, cutoff
        confirmed_cutoff = transition.confirm_cutoff_selection(
            case_id=case_id, **IDENTITY,
            evidence_id=cutoff["evidence_id"],
            expected_evidence_fingerprint=cutoff["payload_fingerprint"],
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-cutoff-confirm-0001",
        )
        assert confirmed_cutoff.get("error") is False, confirmed_cutoff
        opening = transition.record_opening_composition(
            case_id=case_id, **IDENTITY,
            cutoff_evidence_id=cutoff["evidence_id"],
            cutoff_evidence_fingerprint=cutoff["payload_fingerprint"],
            stock_report_fingerprint=parser_worker.reports[
                ReportType.STOCK_MANAGEMENT
            ].file_sha256,
            layers=[
                {"sequence": 1, "unit_cost_rub": "21.00", "ozon_units": 0,
                 "transit_units": 0, "home_units": 3},
                {"sequence": 2, "unit_cost_rub": "14.65", "ozon_units": 100,
                 "transit_units": 0, "home_units": 0},
            ],
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-opening-composition-0001",
        )
        assert opening.get("error") is False, opening
        confirmed_opening = transition.confirm_opening_composition(
            case_id=case_id, **IDENTITY,
            evidence_id=opening["evidence_id"],
            expected_evidence_fingerprint=opening["payload_fingerprint"],
            expected_case_revision=latest_revision(transition, case_id),
            idempotency_key="fr27-opening-confirm-0001",
        )
        assert confirmed_opening.get("error") is False, confirmed_opening

        case_revision = latest_revision(transition, case_id)
        review = workflow["review_service"].assess(
            case_id=case_id, identity=IDENTITY,
        )
        assert review.get("error") is False, review
        bridge_missing = review.get("cutoff_bridge_missing_requirements", ())
        assert review["proposal"].stock_snapshots[0].stock_buckets["defective"] == 0
        assert review["proposal"].stock_snapshots[0].stock_buckets["seller_withdrawal"] == 0
        assert review["proposal"].stock_snapshots[0].stock_buckets["supplier_receiving"] is None
        assert current_case(transition, case_id)["state"] == TransitionState.AWAITING_EVIDENCE
        if supplier_receiving_units is None:
            assert review["cutoff_bridge_status"] == "SOURCE_BLOCKED"
            assert "CUTOFF_BRIDGE:STOCK_BUCKET_UNKNOWN" in bridge_missing
            assert "OWNER_SUPPLIER_RECEIVING_CONFIRMATION_REQUIRED" in bridge_missing
            assert review["ready_to_apply"] is False
        else:
            assert review["cutoff_bridge_status"] == "READY"
            assert "CUTOFF_BRIDGE:STOCK_BUCKET_UNKNOWN" not in bridge_missing
            assert "OWNER_SUPPLIER_RECEIVING_CONFIRMATION_REQUIRED" not in bridge_missing
            opening = transition.read_confirmed_opening_composition(
                case_id=case_id, **IDENTITY,
            )
            assert opening.get("error") is False, opening
            opening_units = sum(
                layer["ozon_units"] + layer["transit_units"] + layer["home_units"]
                for layer in opening["layers"]
            )
            assert opening_units == 103
            bundle = workflow["evidence_service"].load(
                case_id=case_id, identity=IDENTITY,
                expected_case_revision=case_revision,
            )
            assert bundle.get("error") is False, bundle
            bridge = workflow["evidence_service"].build_cutoff_bridge(
                bundle=bundle["bundle"], proposal=review["proposal"],
            )
            assert bridge.get("error") is False, bridge
            assert bridge["result"].confirmed_stock_buckets["supplier_receiving"] == 148
            initial_cutover = {
                "schema_version": 1,
                "case_id": case_id,
                "case_revision": case_revision,
                "cutoff_date": "2026-11-06",
                "stock_report_fingerprint": parser_worker.reports[
                    ReportType.STOCK_MANAGEMENT
                ].file_sha256,
                "layers": [dict(layer) for layer in opening["layers"]],
                "ozon_units_include_reserved_confirmed": True,
                "transit_not_in_ozon_confirmed": True,
            }
            repository_identity = repository._normalize_identity(
                IDENTITY["store_id"], IDENTITY["product_id"],
                IDENTITY["offer_id"], IDENTITY["sku"], 1,
            )
            connection = repository.get_connection()
            try:
                assert repository._owner_supplier_receiving_confirmation_matches(
                    connection,
                    bridge=bridge["result"],
                    identity=repository_identity,
                    stock_report_fingerprint=parser_worker.reports[
                        ReportType.STOCK_MANAGEMENT
                    ].file_sha256,
                    expected_units=148,
                ) is True
                normalized_cutover = repository._normalize_transition_initial_cutover(
                    connection,
                    initial_cutover,
                    bridge["result"],
                    current_case(transition, case_id)["case"],
                    recorded_at="2026-12-16T12:00:00+00:00",
                    identity=repository_identity,
                )
            finally:
                connection.close()
            assert isinstance(normalized_cutover, dict), normalized_cutover
            assert sum(
                layer["ozon_units"] + layer["transit_units"] + layer["home_units"]
                for layer in normalized_cutover["layers"]
            ) == 103
            receiving_as_accepted_stock = {
                **initial_cutover,
                "layers": [dict(layer) for layer in initial_cutover["layers"]],
            }
            receiving_as_accepted_stock["layers"][1]["ozon_units"] += 148
            connection = repository.get_connection()
            try:
                rejected_cutover = repository._normalize_transition_initial_cutover(
                    connection,
                    receiving_as_accepted_stock,
                    bridge["result"],
                    current_case(transition, case_id)["case"],
                    recorded_at="2026-12-16T12:00:00+00:00",
                    identity=repository_identity,
                )
            finally:
                connection.close()
            assert rejected_cutover == "FIFO_INITIAL_CUTOVER_STOCK_SCOPE_UNPROVEN"
    finally:
        reset_current_tenant_user_id(tenant)

