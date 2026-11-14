from datetime import datetime, timezone

from cryptography.fernet import Fernet

from services.fifo_cost_batch_rule_contracts import (
    BatchRuleInput,
    BatchStartDayPolicy,
)
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_batch_supply_source import FifoCostBatchSupplySourceService
from services.fifo_cost_repository import FifoCostRepository
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


class _FakeOzon:
    def __init__(self, *, error=False, list_pages=None, details=None):
        self.calls = []
        self.error = error
        self.list_pages = list(list_pages or [{"order_ids": [], "last_id": None}])
        self.details = dict(details or {})

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


def _setup(tmp_path, monkeypatch, *, ozon_error=False, list_pages=None, details=None):
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
    ozon = _FakeOzon(error=ozon_error, list_pages=list_pages, details=details)
    source = FifoCostBatchSupplySourceService(
        rule_service=rule_service, ozon_client=ozon,
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
    _repo, _rules, source, ozon, tenant_token, confirmed = _setup(
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
