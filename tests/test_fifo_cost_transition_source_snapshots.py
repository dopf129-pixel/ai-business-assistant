from datetime import datetime, timezone
import json

from api.base_ozon_client import OzonClient as BaseOzonClient
from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
from services.fifo_cost_transition_contracts import ScopeIdentity
from services.ozon_account_repository import make_store_tenant_scope
from services.period_profit_operation_diagnostics import current_period_profit_trace
from services.period_profit_operation_diagnostics import PeriodProfitOperationTrace
from services.period_profit_return_evidence_service import PeriodProfitReturnEvidenceService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


SCOPE = ScopeIdentity(
    owner_id="owner-test", store_id="store-test", sku="3921245627",
    product_id="101", offer_id="hook-2",
)
TENANT_SCOPE = make_store_tenant_scope(SCOPE.owner_id, SCOPE.store_id)


class _Ozon:
    def __init__(self):
        self.calls = []
        self.return_requests = []
        self.realization = {}
        self.return_pages = {}

    def _request(self, method, options):
        self.calls.append((method, dict(options)))
        trace = current_period_profit_trace()
        if trace is not None:
            reservation = trace.reserve_ozon_request("synthetic")
            if reservation.get("error"):
                return {"error": True, "code": reservation["code"]}
        observer = options.get("request_attempt_observer")
        if callable(observer):
            observer("synthetic")
        return None

    def get_realization_posting(self, year, month, **options):
        blocked = self._request("realization", options)
        if blocked:
            return blocked
        return self.realization.get((year, month), {"result": {"rows": []}})

    def get_returns(self, *, offer_id, return_schema, since, to, limit, last_id, **options):
        blocked = self._request("returns", options)
        if blocked:
            return blocked
        self.return_requests.append({
            "offer_id": offer_id, "return_schema": return_schema,
            "since": since, "to": to, "limit": limit, "last_id": last_id,
        })
        key = (return_schema, last_id)
        return self.return_pages.get(key, {"items": [], "has_next": False})


def _service(ozon):
    return FifoCostSourceCollectionService(
        ozon_client=ozon,
        utc_clock=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    )


def _identity_context():
    return set_current_tenant_user_id(TENANT_SCOPE)


def test_finance_identity_uses_realization_adapter_and_resumes_across_months():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.realization[(2026, 8)] = {"result": {"rows": [{
            "order": {"posting_number": "private-aug"},
            "item": {"sku": SCOPE.sku, "offer_id": SCOPE.offer_id,
                     "product_id": SCOPE.product_id, "quantity": 100},
        }]}}
        ozon.realization[(2026, 9)] = {"rows": []}
        ozon.realization[(2026, 10)] = {"rows": [{
            "order": {"posting_number": "private-oct"},
            "item": {"sku": SCOPE.sku, "offer_id": SCOPE.offer_id,
                     "product_id": SCOPE.product_id},
        }]}
        service = _service(ozon)

        first = service.collect_finance_identity_snapshot(
            scope=SCOPE, period_from="2026-08-15", period_to="2026-10-04",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", max_pages_per_call=2,
        )
        assert first.status == "PARTIAL"
        assert first.source_status == "PARTIAL"
        assert len(first.finance_identity_snapshots) == 2
        assert first.finance_identity_snapshots[0].rows[0].posting_number == "private-aug"
        assert first.finance_identity_snapshots[1].rows == ()
        assert first.continuation_token

        second = service.collect_finance_identity_snapshot(
            scope=SCOPE, period_from="2026-08-15", period_to="2026-10-04",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", continuation_token=first.continuation_token,
        )
        assert second.status == "COMPLETE"
        assert second.source_status == "COMPLETE"
        assert len(second.finance_identity_snapshots) == 3
        assert len(ozon.calls) == 3
        assert all(call[0] == "realization" for call in ozon.calls)
        assert all(call[1]["max_attempts"] == 1 for call in ozon.calls)
    finally:
        reset_current_tenant_user_id(tenant)


def test_finance_complete_zero_is_distinct_from_unavailable():
    tenant = _identity_context()
    try:
        result = _service(_Ozon()).collect_finance_identity_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow",
        )
        assert result.status == "COMPLETE"
        assert result.source_status == "COMPLETE"
        assert result.finance_identity_snapshots[0].rows == ()
        assert result.actual_http_attempts == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_unpublished_finance_month_is_not_treated_as_complete_zero_before_day_six():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        service = FifoCostSourceCollectionService(
            ozon_client=ozon,
            utc_clock=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        )
        result = service.collect_finance_identity_snapshot(
            scope=SCOPE, period_from="2026-10-01", period_to="2026-10-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow",
        )
        assert result.status == "UNAVAILABLE"
        assert result.finance_identity_snapshots == ()
        assert result.actual_http_attempts == 0
        assert result.issue_codes == ("FIFO_FINANCE_REALIZATION_MONTH_NOT_PUBLISHED",)
        assert ozon.calls == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_completed_finance_report_month_can_prove_zero_after_publication_day():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        service = FifoCostSourceCollectionService(
            ozon_client=ozon,
            utc_clock=lambda: datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc),
        )
        result = service.collect_finance_identity_snapshot(
            scope=SCOPE, period_from="2026-10-01", period_to="2026-10-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow",
        )
        assert result.status == "COMPLETE"
        assert result.finance_identity_snapshots[0].period_from == "2026-10-01"
        assert result.finance_identity_snapshots[0].period_to == "2026-10-31"
        assert result.finance_identity_snapshots[0].rows == ()
        assert result.actual_http_attempts == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_finance_source_fails_closed_on_unpaged_flag_and_preserves_http_budget():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.realization[(2026, 8)] = {
            "rows": [], "has_next": True, "next_page_token": "opaque-next",
        }
        parent = PeriodProfitOperationTrace(
            operation="shared-source-step", time_budget_seconds=20,
            ozon_request_budget=1,
        )
        result = _service(ozon).collect_finance_identity_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", operation_trace=parent,
        )
        assert result.status == "CONFLICT"
        assert "FIFO_FINANCE_PAGINATION_UNSUPPORTED" in result.issue_codes
        assert result.finance_identity_snapshots == ()

        captured = {}
        client = object.__new__(BaseOzonClient)
        client._post = lambda endpoint, payload, **options: captured.update(
            endpoint=endpoint, payload=payload, options=options,
        ) or {"rows": []}
        client.get_realization_posting(
            2026, 8, timeout=3, max_attempts=1, total_timeout=4,
            request_attempt_observer=lambda *_: None,
        )
        assert captured["endpoint"] == "/v1/finance/realization/posting"
        assert captured["payload"] == {"year": 2026, "month": 8}
        assert captured["options"]["max_attempts"] == 1
        assert captured["options"]["total_timeout"] == 4
        assert callable(captured["options"]["request_attempt_observer"])
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_status_snapshot_paginates_and_does_not_claim_physical_movement_coverage():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"returns": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }], "has_next": True}
        ozon.return_pages[("FBO", 10)] = {"items": [{
            "return_id": 20, "posting_number": "private-posting-20", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-08-11T10:00:00Z",
                       "status": {"sys_name": "ReceivedBySeller"}},
        }], "has_next": False}
        service = _service(ozon)

        first = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO", max_pages_per_call=1,
        )
        assert first.status == "PARTIAL"
        assert first.return_snapshot.page_count == 1
        assert first.return_snapshot.record_count == 1
        assert first.continuation_token

        second = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
            continuation_token=first.continuation_token,
        )
        snapshot = second.return_snapshot
        assert second.status == "COMPLETE"
        assert snapshot.record_count == 2
        assert snapshot.filter_basis == "VISUAL_STATUS_CHANGE_MOMENT_UTC"
        assert snapshot.filter_timezone == "UTC"
        assert snapshot.movement_coverage_complete is False
        assert snapshot.records[0]["posting_number"] == "private-posting-10"
        assert snapshot.to_payload()["records"][0]["return_id"] == "10"
        assert all(call["offer_id"] == SCOPE.offer_id for call in ozon.return_requests)
        assert all(call["return_schema"] == "FBO" for call in ozon.return_requests)
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_empty_complete_and_rate_limited_are_not_conflated():
    tenant = _identity_context()
    try:
        empty = _service(_Ozon()).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        assert empty.status == "COMPLETE"
        assert empty.return_snapshot.record_count == 0

        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"error": True, "code": "OZON_RATE_LIMITED"}
        unavailable = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        assert unavailable.status == "UNAVAILABLE"
        assert unavailable.return_snapshot is None
        assert "OZON_RATE_LIMITED" in unavailable.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_repeated_return_page_is_conflict_not_complete_coverage():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        page = {"items": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }], "has_next": True}
        ozon.return_pages[("FBO", 0)] = page
        ozon.return_pages[("FBO", 10)] = page
        first = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO", max_pages_per_call=2,
        )
        assert first.status == "CONFLICT"
        assert first.return_snapshot is None
        assert "FIFO_RETURNS_DUPLICATE_ID" in first.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_returns_without_explicit_pagination_flag_are_missing_evidence():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"items": []}
        result = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        assert result.status == "CONFLICT"
        assert result.return_snapshot is None
        assert "FIFO_RETURNS_PAGINATION_FLAG_MISSING" in result.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_status_timestamp_outside_requested_utc_period_is_rejected():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"items": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-09-01T00:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }], "has_next": False}
        result = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        assert result.status == "CONFLICT"
        assert result.return_snapshot is None
        assert "FIFO_RETURNS_STATUS_MOMENT_OUTSIDE_PERIOD" in result.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_source_page_cannot_exceed_requested_page_size():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {
            "items": [{}] * (PeriodProfitReturnEvidenceService.PAGE_SIZE + 1),
            "has_next": False,
        }
        result = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        assert result.status == "CONFLICT"
        assert result.return_snapshot is None
        assert "FIFO_RETURNS_PAGE_SIZE_EXCEEDED" in result.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_snapshot_allowlists_fields_and_hides_exact_ids_from_repr():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"items": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "return_reason_name": "damaged",
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon",
                                  "display_name": "private-display-value"}},
        }], "has_next": False}
        result = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        snapshot = result.return_snapshot
        assert result.status == "COMPLETE"
        record = snapshot.to_payload()["records"][0]
        assert set(record) == {
            "id", "return_id", "posting_number", "offer_id", "sku", "quantity",
            "type", "schema", "visual_status_sys_name",
            "visual_status_change_moment", "source", "return_reason_name",
            "visual_status",
        }
        assert "private-display-value" not in repr(snapshot)
        assert "private-posting-10" not in repr(snapshot)
        assert SCOPE.offer_id not in repr(snapshot)
        assert len(json.dumps(snapshot.to_payload(), ensure_ascii=False)) < 4096
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_snapshot_rejects_oversized_semantic_source_field():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"items": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "return_reason_name": "x" * 257,
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }], "has_next": False}
        result = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        assert result.status == "CONFLICT"
        assert result.return_snapshot is None
        assert "FIFO_RETURNS_OPTIONAL_FIELD_INVALID" in result.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_snapshot_rejects_same_offer_row_for_different_sku():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"items": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": "9999999999", "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }], "has_next": False}
        result = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
        )
        assert result.status == "CONFLICT"
        assert result.return_snapshot is None
        assert "FIFO_RETURNS_IDENTITY_SCOPE_MISMATCH" in result.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_byte_quota_preserves_prior_page_as_partial_without_continuation():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        first_record = {
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }
        second_record = dict(first_record, id=20, posting_number="private-posting-20")
        ozon.return_pages[("FBO", 0)] = {"items": [first_record], "has_next": True}
        ozon.return_pages[("FBO", 10)] = {"items": [second_record], "has_next": False}
        service = _service(ozon)
        normalized, _, error = service._parse_return_page(
            ozon.return_pages[("FBO", 0)], scope=SCOPE, return_schema="FBO",
            period_from="2026-08-01", period_to="2026-08-31",
        )
        assert error is None
        first_bytes = len(json.dumps(
            [item["record"] for item in normalized], sort_keys=True,
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        service.MAX_RETURN_SNAPSHOT_BYTES = first_bytes + max(1, first_bytes // 2)
        first = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO", max_pages_per_call=1,
        )
        assert first.status == "PARTIAL"
        assert first.continuation_token
        second = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
            continuation_token=first.continuation_token,
        )
        assert second.status == "PARTIAL"
        assert second.return_snapshot.record_count == 1
        assert second.continuation_token is None
        assert "FIFO_RETURNS_SOURCE_BYTE_LIMIT" in second.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_collection_honors_parent_http_budget_and_keeps_continuation():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"items": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }], "has_next": True}
        parent = PeriodProfitOperationTrace(
            operation="shared-return-refresh", time_budget_seconds=20,
            ozon_request_budget=1,
        )
        result = _service(ozon).collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
            operation_trace=parent,
        )
        assert result.status == "PARTIAL"
        assert result.actual_http_attempts == 1
        assert result.return_snapshot.record_count == 1
        assert result.continuation_token
        assert "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED" in result.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)


def test_return_continuation_is_case_revision_bound_and_single_use():
    tenant = _identity_context()
    try:
        ozon = _Ozon()
        ozon.return_pages[("FBO", 0)] = {"items": [{
            "id": 10, "posting_number": "private-posting-10", "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku, "quantity": 1, "type": "ClientReturn",
            "visual": {"change_moment": "2026-08-10T10:00:00Z",
                       "status": {"sys_name": "ReturnedToOzon"}},
        }], "has_next": True}
        ozon.return_pages[("FBO", 10)] = {"items": [], "has_next": False}
        service = _service(ozon)
        first = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO", max_pages_per_call=1,
        )
        assert first.continuation_token

        wrong_scope = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=5,
            store_timezone="Europe/Moscow", return_schema="FBO",
            continuation_token=first.continuation_token,
        )
        assert wrong_scope.status == "CONFLICT"
        assert "FIFO_SOURCE_CONTINUATION_SCOPE_MISMATCH" in wrong_scope.issue_codes

        resumed = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
            continuation_token=first.continuation_token,
        )
        assert resumed.status == "COMPLETE"
        assert resumed.return_snapshot.page_count == 2

        replayed = service.collect_return_status_snapshot(
            scope=SCOPE, period_from="2026-08-01", period_to="2026-08-31",
            transition_case_id="case_1", transition_case_revision=4,
            store_timezone="Europe/Moscow", return_schema="FBO",
            continuation_token=first.continuation_token,
        )
        assert replayed.status == "CONFLICT"
        assert "FIFO_SOURCE_CONTINUATION_STALE" in replayed.issue_codes
    finally:
        reset_current_tenant_user_id(tenant)
