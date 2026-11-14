from datetime import datetime, timezone

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_batch_rule_contracts import (
    BatchRuleInput,
    BatchStartDayPolicy,
)
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_batch_scan_checkpoint_service import FifoCostBatchScanCheckpointService
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_batch_supply_source import FifoCostBatchSupplySourceService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    SupplyTotalMode,
    TransitionCase,
    TransitionMetadata,
    TransitionState,
    UnknownValue,
    TransitionReasonCode,
)
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


SCOPE = ScopeIdentity(
    owner_id="owner-a", store_id="store-a", product_id="product-101",
    offer_id="hook-2", sku="3921245627",
)
TENANT_SCOPE = make_store_tenant_scope("owner-a", "store-a")
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def test_parent_order_state_allowlist_matches_documented_v3_enum():
    assert set(FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES) == {
        "UNSPECIFIED",
        "DATA_FILLING",
        "READY_TO_SUPPLY",
        "ACCEPTED_AT_SUPPLY_WAREHOUSE",
        "IN_TRANSIT",
        "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "REPORTS_CONFIRMATION_AWAITING",
        "REPORT_REJECTED",
        "COMPLETED",
        "REJECTED_AT_SUPPLY_WAREHOUSE",
        "CANCELLED",
        "OVERDUE",
    }


@pytest.fixture(autouse=True)
def _isolate_request_trace_between_source_tests():
    # Each test models an independent bot request. A parent budget belongs to
    # the request that supplied it, so leaked context from a prior test must
    # not make the next source call start with an exhausted shared budget.
    activate_period_profit_trace(None)
    try:
        yield
    finally:
        activate_period_profit_trace(None)


class _FakeOzon:
    def __init__(self, *, error=False, list_pages=None, details=None, bundle_pages=None):
        self.calls = []
        self.error = error
        self.list_pages = list(list_pages or [{"order_ids": [], "last_id": None}])
        self.details = dict(details or {})
        self.bundle_pages = dict(bundle_pages or {})

    def _count_attempt(self, name, options):
        self.calls.append((name, dict(options)))
        trace = current_period_profit_trace()
        reservation = trace.reserve_ozon_request("synthetic-list")
        if reservation.get("error"):
            return {"error": True, "code": reservation["code"]}
        options["request_attempt_observer"]("synthetic-list")
        if self.error:
            return {"error": True, "code": "SYNTHETIC_FAILURE"}
        return None

    def get_supply_orders_list(self, states, **options):
        error = self._count_attempt("list", options)
        self.calls[-1][1]["states"] = tuple(states)
        if error:
            return error
        if not self.list_pages:
            return {"error": True, "code": "NO_SYNTHETIC_PAGE"}
        page = self.list_pages.pop(0)
        return page(options.get("last_id")) if callable(page) else page

    def get_supply_orders_details(self, order_ids, **options):
        error = self._count_attempt("details", options)
        self.calls[-1][1]["order_ids"] = tuple(order_ids)
        if error:
            return error
        records = []
        for order_id in order_ids:
            record = self.details.get(str(order_id))
            if record is None:
                record = {
                    "order_id": str(order_id), "state": "COMPLETED", "supplies": [],
                }
            records.append(record)
        return {"orders": records}

    def get_supply_order_bundle(self, bundle_ids, **options):
        error = self._count_attempt("bundle", options)
        self.calls[-1][1]["bundle_ids"] = tuple(bundle_ids)
        if error:
            return error
        if len(bundle_ids) != 1:
            return {"error": True, "code": "SYNTHETIC_BUNDLE_BINDING_INVALID"}
        pages = self.bundle_pages.get(bundle_ids[0], {})
        return pages.get(options.get("last_id"), {"error": True, "code": "SYNTHETIC_BUNDLE_PAGE_MISSING"})


def _case():
    return TransitionCase(
        metadata=TransitionMetadata(
            scope=SCOPE,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.PARTIAL,
            source_fingerprint="a" * 64,
            store_timezone="Europe/Moscow",
        ),
        case_id="case_batch_src_01", case_revision=1,
        state=TransitionState.AWAITING_EVIDENCE,
        created_at="2026-11-14T10:00:00Z",
        updated_at="2026-11-14T10:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00", new_unit_cost_rub="14.65",
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None, owner_old_home_units=0,
        owner_old_transit_units=0, new_home_quantity=None,
        declared_shipped_units=None, supply_total_mode=SupplyTotalMode.LEGACY_OWNER_TOTAL,
        unknown_values={
            "new_home_quantity": UnknownValue(
                TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                EvidenceSourceKind.OWNER_INPUT,
            ),
            "declared_shipped_units": UnknownValue(
                TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _setup(
    tmp_path, monkeypatch, *, ozon_error=False, list_pages=None, details=None,
    bundle_pages=None, durable_source=False,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-batch-source.sqlite",
        now_provider=lambda: NOW,
    )
    tenant_token = set_current_tenant_user_id(TENANT_SCOPE)
    saved = repository.save_transition_case(
        case=_case(), expected_revision=0, idempotency_key="create-batch-src-01",
    )
    assert saved["error"] is False, saved
    rule_service = FifoCostBatchRuleService(
        repository, now_provider=lambda: NOW,
    )
    preview_result = rule_service.preview_rule(
        SCOPE, "case_batch_src_01", 1,
        BatchRuleInput("2026-11-05", BatchStartDayPolicy.ALL_OWNER_CONFIRMED),
    )
    assert preview_result["error"] is False, preview_result
    preview = preview_result["preview"]
    confirmed = rule_service.confirm_rule(
        SCOPE, "case_batch_src_01", 1, preview.preview_id,
        preview.preview_fingerprint, "confirm-batch-src-01",
    )
    assert confirmed["error"] is False, confirmed
    ozon = _FakeOzon(
        error=ozon_error, list_pages=list_pages, details=details,
        bundle_pages=bundle_pages,
    )
    source = FifoCostBatchSupplySourceService(
        rule_service=rule_service, ozon_client=ozon,
        scan_checkpoint_service=(
            FifoCostBatchScanCheckpointService(repository, now_provider=lambda: NOW)
            if durable_source else None
        ),
        utc_clock=lambda: NOW,
    )
    return repository, rule_service, source, ozon, tenant_token, confirmed


def test_collect_uses_one_allowlisted_bounded_page_and_returns_partial_only(
    tmp_path, monkeypatch,
):
    repo, _rules, source, ozon, tenant_token, confirmed = _setup(tmp_path, monkeypatch)
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "PARTIAL"
        assert result.source_status == "PARTIAL"
        assert result.read_only is True
        assert result.actual_http_attempts == 1
        assert result.http_attempt_cap == 10
        assert result.continuation_token is None
        assert result.issue_codes == ("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED",)
        assert result.pagination_complete is True
        assert result.details_complete is True
        assert result.orders_observed == 0
        assert result.supplies_observed == 0
        assert len(ozon.calls) == 1
        method, options = ozon.calls[0]
        assert method == "list"
        states = options["states"]
        assert states
        assert options["limit"] == 100
        assert options["max_attempts"] == 1
        assert 0 < options["timeout"] <= 8
        assert 0 < options["total_timeout"] <= 8
        assert "raw-id-must-not-escape" not in repr(result)
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations",
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_scans",
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_durable_bundle_scan_stores_only_planned_quantity_and_unknown_dispatch_date(
    tmp_path, monkeypatch,
):
    supply_id = "2000070135564"
    order_id = "3000000000001"
    bundle_id = "bundle id+/=%"
    details = {
        order_id: {
            "order_id": order_id,
            "state": "COMPLETED",
            "supplies": [{
                "supply_id": supply_id, "bundle_id": bundle_id,
                "state": "COMPLETED", "is_crossdock": True,
            }],
        },
    }
    bundle_page = {
        "items": [{
            "sku": int(SCOPE.sku), "quantity": 200,
            "product_id": int(SCOPE.product_id.removeprefix("product-")),
            "offer_id": SCOPE.offer_id, "name": "private name",
            "barcode": "private barcode",
        }],
        "total_count": 1, "has_next": False, "last_id": "",
    }
    repository, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch, durable_source=True,
        list_pages=[{"order_ids": [order_id], "last_id": None}],
        details=details, bundle_pages={bundle_id: {None: bundle_page}},
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )

        assert result.status == "COMPLETE"
        assert result.source_status == "PARTIAL"
        assert result.candidates_observed == 1
        assert result.sku_composition_complete is True
        assert result.continuation_token is None
        assert result.actual_http_attempts == 3
        assert supply_id not in repr(result)
        assert order_id not in repr(result)
        assert bundle_id not in repr(result)
        assert len(ozon.calls) == 3

        connection = repository.get_connection()
        try:
            observation = connection.execute(
                "SELECT planned_declared_quantity, shipped_composition_quantity, "
                "accepted_quantity, dispatch_local_date, dispatch_time_status, "
                "quantity_coverage, membership, encrypted_lookup_payload "
                "FROM fifo_cost_batch_supply_observations",
            ).fetchone()
            assert observation[0:7] == (
                200, None, None, None, "UNKNOWN", "PARTIAL", "NEEDS_CONFIRMATION",
            )
            assert bytes(observation[7]).startswith(b"gAAAA")
            scan = connection.execute(
                "SELECT sku_composition_complete, historical_window_proven, "
                "membership_complete, quantity_complete, physical_receipt_timing_complete "
                "FROM fifo_cost_batch_supply_scans",
            ).fetchone()
            assert tuple(scan) == (1, 0, 0, 0, 0)
            candidates = FifoCostBatchSupplyStore.read_scan_candidate_page(
                connection, scope=SCOPE, case_id="case_batch_src_01",
                tenant_fingerprint=repository._tenant_scope(SCOPE.store_id)["tenant_fingerprint"],
                scan_id=result.scan_id,
            )
            assert candidates["total"] == 1
            assert candidates["candidate_set_fingerprint"] == candidates[
                "stored_candidate_set_fingerprint"
            ]
            assert candidates["items"][0]["planned_declared_quantity"] == 200
            assert "encrypted_lookup_payload" not in candidates["items"][0]
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_b23_later_refresh_adds_supply_without_new_cost_or_manual_total(
    tmp_path, monkeypatch,
):
    from services.fifo_cost_transition_service import FifoCostTransitionService

    order_ids = ("3000000000001", "3000000000002")
    supply_ids = ("2000070135564", "2000070135565")
    bundle_ids = ("bundle-first", "bundle-later")
    details = {
        order_id: {
            "order_id": order_id,
            "state": "COMPLETED",
            "supplies": [{
                "supply_id": supply_id,
                "bundle_id": bundle_id,
                "state": "COMPLETED",
                "is_crossdock": True,
            }],
        }
        for order_id, supply_id, bundle_id in zip(order_ids, supply_ids, bundle_ids)
    }
    bundle_pages = {
        bundle_id: {None: {
            "items": [{
                "sku": int(SCOPE.sku), "quantity": quantity,
                "product_id": int(SCOPE.product_id.removeprefix("product-")),
                "offer_id": SCOPE.offer_id,
            }],
            "total_count": 1, "has_next": False, "last_id": "",
        }}
        for bundle_id, quantity in zip(bundle_ids, (6_982, 100))
    }
    repository, _rules, source, _ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch, durable_source=True,
        list_pages=[
            {"order_ids": [order_ids[0]], "last_id": None},
            {"order_ids": [order_ids[1]], "last_id": None},
        ],
        details=details, bundle_pages=bundle_pages,
    )
    try:
        first = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        later = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert first.status == later.status == "COMPLETE"
        assert first.scan_id != later.scan_id
        assert first.candidates_observed == later.candidates_observed == 1

        connection = repository.get_connection()
        try:
            rows = connection.execute(
                "SELECT planned_declared_quantity, shipped_composition_quantity, "
                "dispatch_local_date FROM fifo_cost_batch_supply_observations "
                "ORDER BY planned_declared_quantity",
            ).fetchall()
            assert [tuple(row) for row in rows] == [
                (100, None, None), (6_982, None, None),
            ]
            rule_rows = FifoCostBatchSupplyStore.read_rule_revisions(
                connection, scope=SCOPE, case_id="case_batch_src_01",
                tenant_fingerprint=repository._tenant_scope(SCOPE.store_id)[
                    "tenant_fingerprint"
                ],
            )
            assert [row["new_unit_cost_rub"] for row in rule_rows] == ["14.65"]
            for table in ("fifo_cost_events", "fifo_cost_layers", "fifo_cost_allocations"):
                assert connection.execute(
                    f"SELECT COUNT(*) FROM {table}",
                ).fetchone()[0] == 0
        finally:
            connection.close()
        case_result = repository.read_transition_case(
            case_id="case_batch_src_01", **{
                "store_id": SCOPE.store_id,
                "product_id": SCOPE.product_id,
                "offer_id": SCOPE.offer_id,
                "sku": SCOPE.sku,
            },
        )
        assert case_result["error"] is False
        case = FifoCostTransitionService._case_from_payload(case_result["case"])
        assert case.supply_total_mode is SupplyTotalMode.AUTO_FROM_SUPPLIES
        assert case.declared_shipped_units is None
        assert str(case.new_unit_cost_rub) == "14.65"
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_telegram_bundle_review_confirms_exact_set_without_fifo_writes_or_identity_leaks(
    tmp_path, monkeypatch,
):
    from services.fifo_cost_history_service import FifoCostHistoryService
    from services.fifo_cost_transition_service import FifoCostTransitionService
    from services.telegram_fifo_cost_batch_rule_service import TelegramFifoCostBatchRuleService
    from services.telegram_fifo_cost_transition_runtime_service import (
        TelegramFifoCostTransitionRuntimeService,
    )

    order_id = "3000000000001"
    supply_id = "2000070135564"
    bundle_id = "private-bundle-id+/="
    private_name = "must-not-leak-private-product-name"
    private_barcode = "must-not-leak-private-barcode"
    details = {
        order_id: {
            "order_id": order_id, "state": "COMPLETED",
            "supplies": [{
                "supply_id": supply_id, "bundle_id": bundle_id,
                "state": "COMPLETED", "is_crossdock": True,
            }],
        },
    }
    bundle_page = {
        "items": [{
            "sku": int(SCOPE.sku), "quantity": 500,
            "product_id": int(SCOPE.product_id.removeprefix("product-")),
            "offer_id": SCOPE.offer_id, "name": private_name,
            "barcode": private_barcode,
        }],
        "total_count": 1, "has_next": False, "last_id": "",
    }
    repository, _rules, source, _ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch, durable_source=True,
        list_pages=[{"order_ids": [order_id], "last_id": None}],
        details=details, bundle_pages={bundle_id: {None: bundle_page}},
    )
    try:
        transitions = FifoCostTransitionService(repository, now_provider=lambda: NOW)
        telegram_rules = TelegramFifoCostBatchRuleService(
            _rules, repository, supply_source_service=source,
            scan_checkpoint_service=source.scan_checkpoint_service,
            supply_store=FifoCostBatchSupplyStore,
        )
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, FifoCostHistoryService(repository),
            now_provider=lambda: NOW, batch_rule_telegram_service=telegram_rules,
        )
        runtime_identity = {
            "store_id": SCOPE.store_id, "product_id": SCOPE.product_id,
            "offer_id": SCOPE.offer_id, "sku": SCOPE.sku,
        }
        resumed = runtime.resume_case(
            101, identity=runtime_identity, display_name=private_name,
            case_id="case_batch_src_01",
            expected_case_revision=confirmed["case_revision"],
        )
        assert resumed["error"] is False, resumed
        card = runtime._show_summary("101")
        refresh = next(
            item["callback"] for item in card["keyboard"]["buttons"]
            if item["text"] == "Обновить поставки"
        )
        refreshed = runtime.handle_callback(101, refresh)
        assert "Точных строк выбранного SKU" in refreshed["message"]
        assert "заявленное количество" in refreshed["message"]
        review_callback = next(
            item["callback"] for item in refreshed["keyboard"]["buttons"]
            if item["text"] == "Проверить состав SKU"
        )
        review_page = runtime.handle_callback(101, review_callback)
        assert "500 шт. заявлено" in review_page["message"]
        assert "дата отправки неизвестна" in review_page["message"]
        row_callback = next(
            item["callback"] for item in review_page["keyboard"]["buttons"]
            if item["text"] == "⬜ Строка 1"
        )
        assert all(value not in row_callback for value in (
            order_id, supply_id, bundle_id, private_name, private_barcode,
        ))
        selected_page = runtime.handle_callback(101, row_callback)
        include_callback = next(
            item["callback"] for item in selected_page["keyboard"]["buttons"]
            if item["text"].startswith("Выбранные — новая партия")
        )
        preview = runtime.handle_callback(101, include_callback)
        assert "дата и количество отгрузки не подтверждены Ozon" in preview["message"]
        assert "FIFO и прибыль не изменятся" in preview["message"]
        confirm_callback = next(
            item["callback"] for item in preview["keyboard"]["buttons"]
            if item["text"] == "Подтвердить выбор"
        )
        saved = runtime.handle_callback(101, confirm_callback)
        assert "Решение владельца сохранено" in saved["message"]
        assert "не доказательство отправки или приёмки Ozon" in saved["message"]
        transcript = "\n".join((
            refreshed["message"], review_page["message"], preview["message"],
            saved["message"], row_callback, include_callback, confirm_callback,
        ))
        assert all(value not in transcript for value in (
            order_id, supply_id, bundle_id, private_name, private_barcode,
        ))

        connection = repository.get_connection()
        try:
            decision = connection.execute(
                "SELECT decision, source FROM fifo_cost_batch_membership_decisions",
            ).fetchone()
            assert tuple(decision) == ("INCLUDED", "OWNER_SELECTED_SET")
            for table in ("fifo_cost_events", "fifo_cost_layers", "fifo_cost_allocations"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_durable_source_fails_closed_when_existing_scan_refs_cannot_be_read(
    tmp_path, monkeypatch,
):
    repository, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch, durable_source=True,
    )

    class _UnreadableCheckpointRepository:
        def __getattr__(self, name):
            return getattr(repository, name)

        def get_connection(self):
            raise OSError("synthetic read failure")

    monkeypatch.setattr(
        source.scan_checkpoint_service, "repository",
        _UnreadableCheckpointRepository(),
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "UNAVAILABLE"
        assert result.issue_codes == ("FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE",)
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
        assert current_period_profit_trace() is None
        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_scans",
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations",
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_durable_bundle_scan_resumes_pagination_after_service_restart(
    tmp_path, monkeypatch,
):
    supply_id = "2000070135564"
    order_id = "3000000000001"
    bundle_id = "bundle-123"
    details = {
        order_id: {
            "order_id": order_id, "state": "COMPLETED",
            "supplies": [{
                "supply_id": supply_id, "bundle_id": bundle_id,
                "state": "COMPLETED", "is_crossdock": True,
            }],
        },
    }
    pages = {}
    for index in range(8):
        pages[None if index == 0 else f"cursor-{index}"] = {
            "items": [{"sku": index + 1, "quantity": 1} for _ in range(100)],
            "total_count": 801, "has_next": True,
            "last_id": f"cursor-{index + 1}",
        }
    pages["cursor-8"] = {
        "items": [{
            "sku": int(SCOPE.sku), "quantity": 500,
            "product_id": int(SCOPE.product_id.removeprefix("product-")),
            "offer_id": SCOPE.offer_id,
        }],
        "total_count": 801, "has_next": False, "last_id": "",
    }
    repository, rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch, durable_source=True,
        list_pages=[{"order_ids": [order_id], "last_id": None}],
        details=details, bundle_pages={bundle_id: pages},
    )
    try:
        assert current_period_profit_trace() is None
        first = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert first.status == "PARTIAL"
        assert first.actual_http_attempts == 10
        assert first.candidates_observed == 0
        assert first.continuation_token is not None
        assert first.scan_revision == 1

        restarted_service = FifoCostBatchSupplySourceService(
            rule_service=rules, ozon_client=ozon,
            scan_checkpoint_service=FifoCostBatchScanCheckpointService(
                repository, now_provider=lambda: NOW,
            ),
            utc_clock=lambda: NOW,
        )
        second = restarted_service.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], continuation_token=first.continuation_token,
        )

        assert second.status == "COMPLETE", (
            second.status, second.actual_http_attempts, second.issue_codes,
            second.continuation_token, second.scan_revision,
        )
        assert second.scan_id == first.scan_id
        assert second.scan_revision == 2
        assert second.actual_http_attempts == 1
        assert second.candidates_observed == 1
        assert second.continuation_token is None
        assert ozon.calls[-1][1]["last_id"] == "cursor-8"
        connection = repository.get_connection()
        try:
            observation = connection.execute(
                "SELECT planned_declared_quantity, shipped_composition_quantity, "
                "dispatch_local_date FROM fifo_cost_batch_supply_observations",
            ).fetchone()
            assert tuple(observation) == (500, None, None)
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_production_fifo_workflow_uses_one_shared_batch_graph_and_fake_ozon(
    tmp_path, monkeypatch,
):
    """The existing production workflow owns the complete source/read graph."""
    import app.telegram_assistant_factory as factory_module

    from services.fifo_cost_history_service import FifoCostHistoryService
    from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
    from services.fifo_cost_transition_service import FifoCostTransitionService

    repo, _rules, _standalone_source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
    )
    try:
        transition = FifoCostTransitionService(repo, now_provider=lambda: NOW)
        history = FifoCostHistoryService(repo)
        source_collection = FifoCostSourceCollectionService(
            ozon_client=ozon, utc_clock=lambda: NOW,
        )
        workflow = factory_module.create_fifo_cost_transition_workflow(
            repository=repo,
            history_service=history,
            transition_service=transition,
            source_collection_service=source_collection,
            tax_service=object(),
            tax_configuration_service=object(),
            period_profit_service=object(),
            now_provider=lambda: NOW,
        )

        batch_source = workflow["batch_supply_source_service"]
        assert batch_source.ozon_client is ozon
        assert batch_source.rule_service is workflow["batch_rule_service"]
        assert workflow["batch_scan_checkpoint_service"].repository is repo
        assert workflow["batch_rule_telegram_service"].supply_source_service is batch_source
        assert workflow["batch_rule_telegram_service"].scan_checkpoint_service is workflow[
            "batch_scan_checkpoint_service"
        ]
        assert workflow["batch_rule_telegram_service"].supply_store is workflow[
            "batch_supply_store"
        ]
        assert workflow["batch_rule_telegram_service"].supply_deduplicator is workflow[
            "batch_supply_deduplicator"
        ]
        assert workflow["batch_rule_telegram_service"].manifest_builder is workflow[
            "batch_manifest_builder"
        ]

        result = batch_source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "COMPLETE"
        assert result.source_status == "PARTIAL"
        assert result.actual_http_attempts == 1
        assert len(ozon.calls) == 1
        assert ozon.calls[0][0] == "list"
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations",
            ).fetchone()[0] == 0
            scan = connection.execute(
                "SELECT status, list_pagination_complete, historical_window_proven, "
                "membership_complete, quantity_complete "
                "FROM fifo_cost_batch_supply_scans",
            ).fetchone()
            assert tuple(scan) == ("PUBLISHED", 1, 0, 0, 0)
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_bundle_source_requires_exact_nested_bundle_reference_before_http(
    tmp_path, monkeypatch,
):
    repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
    )
    try:
        result = source.get_supply_composition(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], "a" * 64,
        )

        assert result.status == "UNKNOWN"
        assert result.source_status == "NOT_VERIFIED"
        assert result.read_only is True
        assert result.actual_http_attempts == 0
        assert result.case_revision == confirmed["case_revision"]
        assert result.rule_revision == confirmed["rule_revision"]
        assert result.planned_quantity is None
        assert result.shipped_quantity is None
        assert result.issue_codes == ("FIFO_BATCH_BUNDLE_REFERENCE_UNAVAILABLE",)
        assert ozon.calls == []
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations",
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_scans",
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_bundle_source_reads_only_exact_target_sku_as_declared_quantity(
    tmp_path, monkeypatch,
):
    target_page = {
        "items": [{
            "sku": int(SCOPE.sku), "quantity": 200,
            "product_id": int(SCOPE.product_id.removeprefix("product-")),
            "offer_id": SCOPE.offer_id, "name": "private title",
            "barcode": "private barcode",
        }],
        "total_count": 1, "has_next": False, "last_id": "",
    }
    repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        bundle_pages={"bundle-123": {None: target_page}},
    )
    try:
        result = source.get_supply_composition(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], "a" * 64, bundle_id="bundle-123",
        )

        assert result.status == "COMPLETE"
        assert result.source_status == "DOCUMENTED_BUNDLE_COMPOSITION"
        assert result.planned_quantity == 200
        assert result.shipped_quantity is None
        assert result.actual_http_attempts == 1
        assert ozon.calls[0][0] == "bundle"
        assert ozon.calls[0][1]["bundle_ids"] == ("bundle-123",)
        assert ozon.calls[0][1]["max_attempts"] == 1
        assert 0 < ozon.calls[0][1]["timeout"] <= 8
        assert "private title" not in repr(result)
        assert "private barcode" not in repr(result)
        assert "bundle-123" not in repr(result)
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_batch_supply_observations",
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_bundle_source_paginates_and_rejects_cursor_or_duplicate_mapping_conflicts(
    tmp_path, monkeypatch,
):
    first = {
        "items": [{"sku": 1, "quantity": 4, "product_id": 1, "offer_id": "other"}],
        "total_count": 2, "has_next": True, "last_id": "cursor-a",
    }
    terminal = {
        "items": [{
            "sku": int(SCOPE.sku), "quantity": 5,
            "product_id": int(SCOPE.product_id.removeprefix("product-")),
            "offer_id": SCOPE.offer_id,
        }],
        "total_count": 2, "has_next": False, "last_id": "",
    }
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        bundle_pages={"bundle-123": {None: first, "cursor-a": terminal}},
    )
    try:
        result = source.get_supply_composition(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], "a" * 64, bundle_id="bundle-123",
        )
        assert result.status == "COMPLETE"
        assert result.planned_quantity == 5
        assert result.shipped_quantity is None
        assert result.actual_http_attempts == 2
        assert [call[1].get("last_id") for call in ozon.calls] == [None, "cursor-a"]
    finally:
        reset_current_tenant_user_id(tenant_token)

    duplicate_page = {
        "items": [
            {
                "sku": int(SCOPE.sku), "quantity": 5,
                "product_id": int(SCOPE.product_id.removeprefix("product-")),
                "offer_id": SCOPE.offer_id,
            },
            {
                "sku": int(SCOPE.sku), "quantity": 6,
                "product_id": int(SCOPE.product_id.removeprefix("product-")),
                "offer_id": SCOPE.offer_id,
            },
        ],
        "total_count": 2, "has_next": False, "last_id": "",
    }
    _repo, _rules, source, _ozon, tenant_token, confirmed = _setup(
        tmp_path / "duplicate", monkeypatch,
        bundle_pages={"bundle-123": {None: duplicate_page}},
    )
    try:
        result = source.get_supply_composition(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], "a" * 64, bundle_id="bundle-123",
        )
        assert result.status == "UNKNOWN"
        assert result.planned_quantity is None
        assert result.issue_codes == ("FIFO_BATCH_BUNDLE_DUPLICATE_SKU_MAPPING",)
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_bundle_source_rejects_invalid_supply_reference_before_any_http(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
    )
    try:
        result = source.get_supply_composition(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], "not-a-digest",
        )

        assert result.status == "CONFLICT"
        assert result.issue_codes == (
            "FIFO_BATCH_BUNDLE_SUPPLY_REFERENCE_INVALID",
        )
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_stale_case_revision_is_rejected_before_any_http_attempt(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(tmp_path, monkeypatch)
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"] - 1,
            confirmed["rule_revision"],
        )
        assert result.status == "CONFLICT"
        assert result.issue_codes == ("FIFO_BATCH_CASE_REVISION_CONFLICT",)
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_wrong_active_rule_revision_is_rejected_before_any_http_attempt(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(tmp_path, monkeypatch)
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"] + 1,
        )
        assert result.status == "CONFLICT"
        assert result.issue_codes == ("FIFO_BATCH_RULE_REVISION_CONFLICT",)
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_wrong_owner_scope_is_rejected_before_any_http_attempt(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(tmp_path, monkeypatch)
    try:
        foreign_scope = ScopeIdentity(
            owner_id="other-owner", store_id=SCOPE.store_id,
            product_id=SCOPE.product_id, offer_id=SCOPE.offer_id, sku=SCOPE.sku,
        )
        result = source.collect_supplies(
            foreign_scope, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "CONFLICT"
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_parent_operation_budget_is_shared_and_prevents_source_request(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(tmp_path, monkeypatch)
    try:
        parent = PeriodProfitOperationTrace(
            operation="parent", time_budget_seconds=20, ozon_request_budget=1,
        )
        assert parent.reserve_ozon_request("already-used")["error"] is False
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], operation_trace=parent,
        )
        assert result.status == "PARTIAL"
        assert "FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED" in result.issue_codes
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
        assert parent.public_summary()["http_attempts"] == 1
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_list_details_collect_all_nested_supplies_without_state_filtering(
    tmp_path, monkeypatch,
):
    details = {
        "101": {
            "order_id": 101, "state": "IN_TRANSIT",
            "supplies": [
                {"supply_id": 901, "state": "IN_TRANSIT", "is_crossdock": True},
                {"supply_id": 902, "state": "ACCEPTED_AT_SUPPLY_WAREHOUSE", "is_crossdock": False},
            ],
        },
        "102": {
            "order_id": 102, "state": "COMPLETED",
            "supplies": [
                {"supply_id": 903, "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE", "is_crossdock": True},
                {"supply_id": 902, "state": "ACCEPTED_AT_SUPPLY_WAREHOUSE", "is_crossdock": False},
            ],
        },
    }
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        list_pages=[{"order_ids": [101, 102], "last_id": None}],
        details=details,
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "PARTIAL"
        assert result.orders_observed == 2
        assert result.supplies_observed == 3
        assert result.pagination_complete is True
        assert result.details_complete is True
        assert result.actual_http_attempts == 2
        assert [call[0] for call in ozon.calls] == ["list", "details"]
        assert len(ozon.calls[1][1]["order_ids"]) <= 50
        assert ozon.calls[1][1]["max_attempts"] == 1
        assert 0 < ozon.calls[1][1]["timeout"] <= 8
        assert "901" not in repr(result)
        assert "FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED" in result.issue_codes
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_unrecognized_raw_state_is_reported_unsupported_without_defaulting(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, _ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        list_pages=[{"order_ids": [4101], "last_id": None}],
        details={
            "4101": {
                "order_id": 4101, "state": "FUTURE_ORDER_STATE",
                "supplies": [{
                    "supply_id": 4201, "state": "FUTURE_SUPPLY_STATE",
                    "is_crossdock": False,
                }],
            },
        },
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "PARTIAL"
        assert result.orders_observed == 1
        assert result.supplies_observed == 1
        assert "FIFO_BATCH_SUPPLY_ORDER_STATE_UNSUPPORTED" in result.issue_codes
        assert "FIFO_BATCH_SUPPLY_STATE_UNSUPPORTED" in result.issue_codes
        assert "FUTURE_ORDER_STATE" not in repr(result)
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_full_page_uses_details_batches_of_50_and_resumes_opaquely(
    tmp_path, monkeypatch,
):
    order_ids = list(range(1000, 1100))
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        list_pages=[
            {"order_ids": order_ids, "last_id": "cursor-1"},
            {"order_ids": [], "last_id": None},
        ],
    )
    try:
        parent = PeriodProfitOperationTrace(
            operation="parent", time_budget_seconds=20, ozon_request_budget=3,
        )
        first = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], operation_trace=parent,
        )
        assert first.status == "PARTIAL"
        assert first.actual_http_attempts == 3
        assert first.orders_observed == 100
        assert first.pagination_complete is False
        assert first.details_complete is False
        assert first.continuation_token is not None
        detail_calls = [call for call in ozon.calls if call[0] == "details"]
        assert [len(call[1]["order_ids"]) for call in detail_calls] == [50, 50]
        assert parent.public_summary()["http_attempts"] == 3

        second = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], continuation_token=first.continuation_token,
        )
        assert second.status == "PARTIAL"
        assert second.actual_http_attempts == 1
        assert second.orders_observed == 100
        assert second.pagination_complete is True
        assert second.details_complete is True
        assert second.continuation_token is None
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_full_page_without_cursor_never_claims_complete_coverage(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        list_pages=[{"order_ids": list(range(2000, 2100)), "last_id": None}],
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "PARTIAL"
        assert result.pagination_complete is False
        assert result.details_complete is False
        assert "FIFO_BATCH_SUPPLY_CURSOR_PROOF_MISSING" in result.issue_codes
        assert result.continuation_token is None
        assert result.actual_http_attempts == 3
        assert result.orders_observed == 100
        assert len([call for call in ozon.calls if call[0] == "details"]) == 2
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_repeated_cursor_fails_closed_after_deduplicating_seen_orders(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        list_pages=[
            {"order_ids": [3001], "last_id": "cursor-1"},
            {"order_ids": [3002], "last_id": "cursor-1"},
        ],
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "CONFLICT"
        assert result.pagination_complete is False
        assert result.orders_observed == 1
        assert result.actual_http_attempts == 3
        assert result.issue_codes == ("FIFO_BATCH_SUPPLY_CURSOR_NOT_ADVANCING",)
        assert len(ozon.calls) == 3
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_overlapping_pages_deduplicate_orders_and_remain_partial(
    tmp_path, monkeypatch,
):
    details = {
        str(order_id): {
            "order_id": order_id, "state": "COMPLETED",
            "supplies": [{
                "supply_id": 7000 + order_id, "state": "COMPLETED",
                "is_crossdock": False,
            }],
        }
        for order_id in (5001, 5002, 5003)
    }
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch,
        list_pages=[
            {"order_ids": [5001, 5002], "last_id": "cursor-a"},
            {"order_ids": [5002, 5003], "last_id": None},
        ],
        details=details,
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "PARTIAL"
        assert result.orders_observed == 3
        assert result.supplies_observed == 3
        assert result.pagination_complete is True
        assert result.details_complete is True
        assert "FIFO_BATCH_SUPPLY_LIST_MUTATED_DURING_SCAN" in result.issue_codes
        detail_ids = [
            order_id for _kind, options in ozon.calls if _kind == "details"
            for order_id in options["order_ids"]
        ]
        assert detail_ids == ["5001", "5002", "5003"]
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_unavailable_list_does_not_leak_client_error_or_raw_payload(
    tmp_path, monkeypatch,
):
    repo, _rules, source, ozon, tenant_token, confirmed = _setup(
        tmp_path, monkeypatch, ozon_error=True,
    )
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"],
        )
        assert result.status == "PARTIAL"
        assert "FIFO_BATCH_SUPPLY_LIST_UNAVAILABLE" in result.issue_codes
        assert result.actual_http_attempts == 1
        assert "SYNTHETIC_FAILURE" not in repr(result)
        assert len(ozon.calls) == 1
        connection = repo.get_connection()
        try:
            for table in (
                "fifo_cost_batch_supply_observations",
                "fifo_cost_batch_supply_scans",
                "fifo_cost_batch_scan_observations",
                "fifo_cost_events",
                "fifo_cost_layers",
                "fifo_cost_allocations",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_malformed_continuation_is_rejected_without_network(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(tmp_path, monkeypatch)
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], continuation_token="resume-me",
        )
        assert result.status == "CONFLICT"
        assert result.issue_codes == ("FIFO_BATCH_SUPPLY_CONTINUATION_INVALID",)
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_invalid_parent_trace_is_rejected_before_any_http_attempt(
    tmp_path, monkeypatch,
):
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(tmp_path, monkeypatch)
    try:
        result = source.collect_supplies(
            SCOPE, "case_batch_src_01", confirmed["case_revision"],
            confirmed["rule_revision"], operation_trace=object(),
        )
        assert result.status == "INVALID"
        assert result.issue_codes == ("FIFO_BATCH_OPERATION_TRACE_INVALID",)
        assert result.actual_http_attempts == 0
        assert ozon.calls == []
    finally:
        reset_current_tenant_user_id(tenant_token)
