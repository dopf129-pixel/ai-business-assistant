from dataclasses import replace
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionState,
    UnknownValue,
    TransitionReasonCode,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_transition_supply_refresh_service import (
    FifoCostTransitionSupplyRefreshService,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.period_profit_operation_diagnostics import PeriodProfitOperationTrace
from services.period_profit_operation_diagnostics import current_period_profit_trace
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


STORE = "store-a"
OWNER = "owner-a"
SKU = "3921245627"
IDENTITY = {"product_id": "101", "offer_id": "hook-2", "sku": SKU}
TENANT_SCOPE = make_store_tenant_scope(OWNER, STORE)


class _Ozon:
    def __init__(self):
        self.calls = []
        self.list_pages = []
        self.details = {}
        self.summary = None
        self.products = None
        self.on_request = None

    def _request(self, name, options):
        self.calls.append(name)
        trace = current_period_profit_trace()
        if trace is not None:
            reservation = trace.reserve_ozon_request("synthetic")
            if reservation.get("error"):
                return {"error": True, "code": reservation["code"]}
        observer = options.get("request_attempt_observer")
        if callable(observer):
            observer("synthetic")
        if callable(self.on_request):
            self.on_request(name)
        return None

    def get_supply_orders_list(self, _states, **options):
        error = self._request("list", options)
        if error:
            return error
        if not self.list_pages:
            return {"error": True, "code": "OZON_HTTP_ERROR"}
        response = self.list_pages.pop(0)
        return response(options.get("last_id")) if callable(response) else response

    def get_supply_orders_details(self, order_ids, **options):
        error = self._request("details", options)
        if error:
            return error
        return {"orders": [self.details[str(order_id)] for order_id in order_ids]}

    def get_supply_act_summary(self, _order_id, **options):
        error = self._request("summary", options)
        return error or self.summary

    def get_supply_act_products(self, _supply_id, **options):
        error = self._request("products", options)
        return error or self.products


def _case():
    metadata = TransitionMetadata(
        scope=ScopeIdentity(
            owner_id=OWNER, store_id=STORE, product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=SKU,
        ),
        source_kind=EvidenceSourceKind.OWNER_INPUT,
        completeness=EvidenceCompleteness.PARTIAL,
        source_fingerprint="a" * 64,
    )
    return TransitionCase(
        metadata=metadata, case_id="case_fl11_0001", case_revision=1,
        state=TransitionState.DRAFT, created_at="2026-11-08T10:00:00Z",
        updated_at="2026-11-08T10:00:00Z", dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00", new_unit_cost_rub="14.65",
        cost_input_mode=CostInputMode.TOTAL_LANDED, cost_components=None,
        owner_old_home_units=0, owner_old_transit_units=0,
        new_home_quantity=None, declared_shipped_units=148,
        unknown_values={"new_home_quantity": UnknownValue(
            TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
            EvidenceSourceKind.OWNER_INPUT,
        )},
    )


def _setup(tmp_path, monkeypatch, ozon, *, monotonic_clock=lambda: 0.0):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    tenant = set_current_tenant_user_id(TENANT_SCOPE)
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-transition-refresh.sqlite",
        now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )
    transition = FifoCostTransitionService(
        repository,
        now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )
    assert transition.create_case(
        case=_case(), idempotency_key="fl11-create-case",
    )["error"] is False
    declared = transition.declare_supply(
        case_id="case_fl11_0001", store_id=STORE,
        product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
        sku=SKU, reference_kind="SUPPLY", reference_id="2001",
        declared_shipped_units=148, dispatch_date="2026-11-05",
        expected_case_revision=1, idempotency_key="fl11-declare-supply",
    )
    assert declared["error"] is False, declared
    source = FifoCostSourceCollectionService(
        ozon_client=ozon,
        monotonic_clock=monotonic_clock,
        utc_clock=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )
    refresh = FifoCostTransitionSupplyRefreshService(
        transition_service=transition,
        source_collection=source,
        monotonic_clock=monotonic_clock,
    )
    return tenant, repository, transition, source, refresh


def _receiving_order():
    return {
        "order_id": 11,
        "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "supplies": [{
            "supply_id": 2001,
            "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
            "is_crossdock": True,
        }],
    }


def _accepted_order():
    return {
        "order_id": 11,
        "state": "COMPLETED",
        "supplies": [{"supply_id": 2001, "state": "COMPLETED", "is_crossdock": True}],
    }


def _accepted_act(quantity=100):
    return (
        {"supplies_acts": [{
            "supply_id": 2001,
            "is_agreement_completed": True,
            "supply_acts": [{
                "type": "ACCEPTANCE", "act_state": "ACCEPTED", "act_id": 3001,
                "summary": {"fact_quantity": quantity, "unidentified_quantity": 0},
            }],
        }]},
        {"supply_acts": [{
            "type": "ACCEPTANCE", "act_id": 3001,
            "items": [{
                "sku_info": {"sku": int(SKU)}, "fact_quantity": quantity,
                "unidentified_quantity": 0,
            }],
        }]},
    )


def _refresh(refresh, **overrides):
    args = {
        "case_id": "case_fl11_0001", "declaration_id": "decl_" + "0" * 32,
        "reference_id": "2001", "store_id": STORE,
        "product_id": IDENTITY["product_id"], "offer_id": IDENTITY["offer_id"],
        "sku": SKU, "expected_case_revision": 2,
    }
    args.update(overrides)
    manifest = refresh.transition_service.get_supply_manifest(
        case_id=args["case_id"], store_id=args["store_id"],
        product_id=args["product_id"], offer_id=args["offer_id"], sku=args["sku"],
    )
    if args["declaration_id"] == "decl_" + "0" * 32:
        args["declaration_id"] = manifest["declarations"][0]["declaration_id"]
    return refresh.refresh(**args)


def test_refresh_shares_one_budget_across_status_details_and_accepted_acts(
    tmp_path, monkeypatch,
):
    client = _Ozon()
    client.list_pages = [
        {"order_ids": [11], "last_id": None},
        {"order_ids": [11], "last_id": None},
    ]
    client.details["11"] = _accepted_order()
    client.summary, client.products = _accepted_act(100)
    tenant, repository, transition, source, refresh = _setup(tmp_path, monkeypatch, client)
    try:
        result = _refresh(refresh)

        assert result.status == "COMPLETE"
        assert result.source_status == "COMPLETE"
        assert result.actual_http_attempts == 6
        assert result.http_attempt_cap == 10
        assert result.act_snapshot.units_by_sku == ((SKU, 100),)
        assert result.case_revision == 3
        assert client.calls == ["list", "details", "list", "details", "summary", "products"]
        observations = repository.read_transition_evidence(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=SKU, kind="SUPPLY_OBSERVATION",
        )
        assert len(observations["items"]) == 1
        assert observations["items"][0]["normalized_status"] == "ACCEPTED"
        assert repository.read_cost_history_snapshot(
            store_id=STORE, product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"], sku=SKU,
        )["code"] == "FIFO_HISTORY_NOT_INITIALIZED"
    finally:
        reset_current_tenant_user_id(tenant)


def test_tighter_parent_http_budget_is_shared_with_act_lookup(
    tmp_path, monkeypatch,
):
    client = _Ozon()
    client.list_pages = [
        {"order_ids": [11], "last_id": None},
        {"order_ids": [11], "last_id": None},
    ]
    client.details["11"] = _accepted_order()
    client.summary, client.products = _accepted_act(100)
    tenant, _repository, _transition, _source, refresh = _setup(tmp_path, monkeypatch, client)
    parent = PeriodProfitOperationTrace(
        operation="test_parent", time_budget_seconds=20, ozon_request_budget=3,
    )
    try:
        result = _refresh(refresh, operation_trace=parent)
        assert result.status == "PARTIAL"
        assert result.actual_http_attempts == 3
        assert parent.ozon_requests_reserved == 3
        assert result.http_attempt_cap == 10
        assert result.continuation_token
    finally:
        reset_current_tenant_user_id(tenant)


def test_429_never_writes_status_observation_or_exceeds_shared_budget(tmp_path, monkeypatch):
    client = _Ozon()
    client.list_pages = [{"error": True, "code": "OZON_HTTP_429"}]
    tenant, repository, _transition, _source, refresh = _setup(tmp_path, monkeypatch, client)
    try:
        result = _refresh(refresh)
        assert result.status == "PARTIAL"
        assert result.actual_http_attempts == 1
        assert result.actual_http_attempts <= result.http_attempt_cap
        assert "OZON_HTTP_429" in result.issue_codes
        observations = repository.read_transition_evidence(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=SKU, kind="SUPPLY_OBSERVATION",
        )
        assert observations["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_broken_active_page_is_conflict_and_never_persisted(tmp_path, monkeypatch):
    client = _Ozon()
    client.list_pages = [{"order_ids": "not-a-list", "last_id": None}]
    tenant, repository, _transition, _source, refresh = _setup(tmp_path, monkeypatch, client)
    try:
        result = _refresh(refresh)
        assert result.status == "CONFLICT"
        assert "FIFO_ACTIVE_SUPPLY_LIST_INVALID" in result.issue_codes
        assert result.actual_http_attempts == 1
        assert result.continuation_token is None
        observations = repository.read_transition_evidence(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=SKU, kind="SUPPLY_OBSERVATION",
        )
        assert observations["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_timeout_never_writes_status_observation_or_exceeds_shared_budget(
    tmp_path, monkeypatch,
):
    clock = [0.0]
    client = _Ozon()
    client.list_pages = [{"order_ids": [11], "last_id": None}]
    tenant, repository, _transition, _source, refresh = _setup(
        tmp_path, monkeypatch, client, monotonic_clock=lambda: clock[0],
    )
    client.on_request = lambda _name: clock.__setitem__(0, clock[0] + 30.0)
    try:
        result = _refresh(refresh)
        assert result.status == "PARTIAL"
        assert result.actual_http_attempts == 1
        assert result.actual_http_attempts <= result.http_attempt_cap
        assert result.continuation_token
        observations = repository.read_transition_evidence(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=SKU, kind="SUPPLY_OBSERVATION",
        )
        assert observations["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_matched_active_supply_survives_budget_checkpoint_and_completes_on_resume(
    tmp_path, monkeypatch,
):
    client = _Ozon()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [], "last_id": None},
    ]
    client.details["11"] = _receiving_order()
    tenant, repository, _transition, _source, refresh = _setup(tmp_path, monkeypatch, client)
    limited_parent = PeriodProfitOperationTrace(
        operation="test_parent", time_budget_seconds=20, ozon_request_budget=2,
    )
    try:
        partial = _refresh(refresh, operation_trace=limited_parent)
        assert partial.status == "PARTIAL"
        assert partial.continuation_token
        assert partial.actual_http_attempts == 2
        assert client.calls == ["list", "details", "list"]
        assert repository.read_transition_evidence(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=SKU, kind="SUPPLY_OBSERVATION",
        )["items"] == []

        resumed = _refresh(refresh, continuation_token=partial.continuation_token)
        assert resumed.status == "COMPLETE"
        assert resumed.status_snapshot.normalized_status == "RECEIVING"
        assert resumed.status_snapshot.pagination_complete is True
        assert resumed.case_revision == 3
        assert client.calls == ["list", "details", "list", "list"]
    finally:
        reset_current_tenant_user_id(tenant)


def test_duplicate_supply_id_across_pages_conflicts_without_observation(tmp_path, monkeypatch):
    client = _Ozon()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [12], "last_id": None},
    ]
    duplicate_supply = {
        "supply_id": 2001,
        "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "is_crossdock": True,
    }
    client.details["11"] = {
        "order_id": 11, "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "supplies": [duplicate_supply],
    }
    client.details["12"] = {
        "order_id": 12, "state": "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
        "supplies": [duplicate_supply],
    }
    tenant, repository, _transition, _source, refresh = _setup(tmp_path, monkeypatch, client)
    try:
        result = _refresh(refresh)
        assert result.status == "CONFLICT"
        assert "FIFO_ACTIVE_SUPPLY_ID_AMBIGUOUS" in result.issue_codes
        assert result.actual_http_attempts == 4
        assert result.continuation_token is None
        observations = repository.read_transition_evidence(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=SKU, kind="SUPPLY_OBSERVATION",
        )
        assert observations["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_partial_checkpoint_is_case_revision_bound_and_restart_fails_closed(
    tmp_path, monkeypatch,
):
    client = _Ozon()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [12], "last_id": "cursor-B"},
    ]
    client.details["11"] = {
        "order_id": 11, "state": "COMPLETED", "supplies": [],
    }
    client.details["12"] = {
        "order_id": 12, "state": "COMPLETED", "supplies": [],
    }
    tenant, repository, transition, source, refresh = _setup(
        tmp_path, monkeypatch, client,
    )
    try:
        partial = _refresh(refresh)
        assert partial.status == "PARTIAL"
        assert partial.continuation_token
        assert partial.case_revision == 2
        calls_before = list(client.calls)

        restarted = FifoCostTransitionSupplyRefreshService(
            transition_service=transition,
            source_collection=source,
        )
        stale = _refresh(
            restarted, continuation_token=partial.continuation_token,
        )
        assert stale.status == "CONFLICT"
        assert stale.issue_codes == ("FIFO_TRANSITION_CHECKPOINT_STALE",)
        assert client.calls == calls_before

        declaration_id = transition.get_supply_manifest(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"], sku=SKU,
        )["declarations"][0]["declaration_id"]

        current_case_payload = transition.get_case(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"], sku=SKU,
        )
        current_case = transition._case_from_payload(current_case_payload["case"])
        revised_case = replace(
            current_case, case_revision=3, new_home_quantity=0,
            unknown_values={}, updated_at="2026-11-08T13:00:00Z",
        )
        updated = transition.update_case(
            case=revised_case, expected_revision=2,
            idempotency_key="fl11-revision-change",
        )
        assert updated["error"] is False, updated
        revision_mismatch = _refresh(
            refresh, continuation_token=partial.continuation_token,
            expected_case_revision=3,
        )
        assert revision_mismatch.status == "CONFLICT"
        assert revision_mismatch.issue_codes == ("FIFO_TRANSITION_CHECKPOINT_SCOPE_MISMATCH",)
        assert client.calls == calls_before

        wrong_store = _refresh(
            refresh, continuation_token=partial.continuation_token,
            store_id="store-other", declaration_id=declaration_id,
        )
        assert wrong_store.status == "CONFLICT"
        assert client.calls == calls_before
        assert repository.read_transition_case(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"], sku=SKU,
        )["case_revision"] == 3
    finally:
        reset_current_tenant_user_id(tenant)


def test_repeated_cursor_is_conflict_and_never_persisted_as_complete(tmp_path, monkeypatch):
    client = _Ozon()
    client.list_pages = [
        {"order_ids": [11], "last_id": "cursor-A"},
        {"order_ids": [12], "last_id": "cursor-A"},
    ]
    client.details["11"] = {"order_id": 11, "state": "COMPLETED", "supplies": []}
    client.details["12"] = {"order_id": 12, "state": "COMPLETED", "supplies": []}
    tenant, repository, _transition, _source, refresh = _setup(tmp_path, monkeypatch, client)
    try:
        result = _refresh(refresh)
        assert result.status == "CONFLICT"
        assert "FIFO_ACTIVE_SUPPLY_CURSOR_NOT_ADVANCING" in result.issue_codes
        observations = repository.read_transition_evidence(
            case_id="case_fl11_0001", store_id=STORE,
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=SKU, kind="SUPPLY_OBSERVATION",
        )
        assert observations["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)
