from datetime import date, datetime, timedelta, timezone

from services.cross_docking_supply_evidence_service import (
    CrossDockingSupplyEvidenceService,
)
from services.cross_docking_unit_rate_source import CrossDockingUnitRateSource
from services.period_profit_operation_diagnostics import PeriodProfitOperationTrace


class _FakeOzonClient:
    def __init__(self):
        self.calls = []
        self.finance_cursor_calls = []
        self.trace = None

    def _observe(self, endpoint, options):
        self.calls.append(endpoint)
        if self.trace is not None:
            self.trace.reserve_ozon_request(endpoint)
        observer = options.get("request_attempt_observer")
        if callable(observer):
            observer(endpoint)

    def get_accrual_types(self, **options):
        self._observe("accrual_types", options)
        return {
            "error": False,
            "accrual_types": [
                {"id": 41, "name": "CrossDocking", "description": "Кросс-докинг"}
            ],
        }

    def get_accruals_by_day_page(self, day, **options):
        self._observe("finance", options)
        self.finance_cursor_calls.append((day, options.get("last_id")))
        if not options.get("last_id"):
            accruals = []
            if day == "2026-08-24":
                accruals = [
                    {
                        "accrual_id": 9001,
                        "non_item_fee": {
                            "type_id": 41,
                            "accrued": {"amount": "-1000.00"},
                        },
                    }
                ]
            return {"error": False, "accruals": accruals, "last_id": "next"}
        return {"error": False, "accruals": [], "last_id": ""}

    def get_supply_orders_list(self, _states, **options):
        self._observe("supply_list", options)
        return {"error": False, "order_ids": [101], "last_id": None}

    def get_supply_orders_details(self, order_ids, **options):
        self._observe("supply_details", options)
        assert list(order_ids) == ["101"]
        return {
            "error": False,
            "orders": [
                {
                    "order_id": 101,
                    "state": "COMPLETED",
                    "state_updated_date": "2026-10-17T05:22:50.401705Z",
                    "supplies": [
                        {
                            "supply_id": 201,
                            "state": "COMPLETED",
                            "is_crossdock": True,
                        }
                    ],
                }
            ],
        }

    def get_supply_act_summary(self, _order_id, **options):
        self._observe("act_summary", options)
        return {
            "error": False,
            "supplies_acts": [
                {
                    "supply_id": 201,
                    "is_agreement_completed": True,
                    "supply_acts": [
                        {
                            "act_id": 301,
                            "act_state": "ACCEPTED",
                            "type": "ACCEPTANCE",
                            "summary": {
                                "fact_quantity": 100,
                                "approved_quantity": 0,
                                "unidentified_quantity": 0,
                            },
                        }
                    ],
                }
            ],
        }

    def get_supply_act_products(self, _supply_id, **options):
        self._observe("act_products", options)
        return {
            "error": False,
            "supply_acts": [
                {
                    "act_id": 301,
                    "type": "ACCEPTANCE",
                    "items": [
                        {
                            "sku_info": {"sku": 3921245627},
                            "declared_quantity": 100,
                            "approved_quantity": 0,
                            "fact_quantity": 100,
                        }
                    ],
                }
            ],
        }


class _FinanceService:
    def __init__(self, client, cached_days=None):
        self.ozon = client
        self.accrual_types = {
            41: {"name": "CrossDocking", "description": "Кросс-докинг"}
        }
        self.cached_days = cached_days or {}

    def get_cached_daily_accruals(self, _date_from, _date_to):
        return dict(self.cached_days)


class _Trace:
    def __init__(self, *, budget, reserved):
        self.ozon_request_budget = budget
        self.ozon_requests_reserved = reserved

    def remaining_seconds(self):
        return 60

    def reserve_ozon_request(self, _endpoint):
        if self.ozon_requests_reserved >= self.ozon_request_budget:
            raise AssertionError("request attempted beyond parent budget")
        self.ozon_requests_reserved += 1


def _source(
    client,
    *,
    max_requests=64,
    cache_clock=lambda: 0,
    cached_days=None,
    clock=None,
):
    finance = _FinanceService(client, cached_days=cached_days)
    return CrossDockingUnitRateSource(
        ozon_client=client,
        finance_service=finance,
        max_requests=max_requests,
        clock=clock or (lambda: datetime(2026, 10, 19, 12, tzinfo=timezone.utc)),
        cache_clock=cache_clock,
    )


def test_cold_window_over_64_attempts_resumes_before_publishing_rate(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone.utc),
    )
    client = _FakeOzonClient()
    source = _source(client)

    first = source.get_rate(sku="3921245627", tenant_scope="user:store-a")

    assert first["status"] == "UNAVAILABLE"
    assert first["cross_docking_per_unit"] is None
    assert first["http_attempts"] == 64
    assert first["finance_checkpointed"] is True
    assert "supply_list" not in client.calls

    second = source.get_rate(sku="3921245627", tenant_scope="user:store-a")

    assert second["status"] == "STORE_CROSSDOCK_SUPPLY_ESTIMATE"
    assert second["cross_docking_per_unit"] == "10.00"
    assert second["supplied_units_sku"] == 100
    assert second["supplied_units_store"] == 100
    assert second["days_expected"] == 56
    assert second["days_complete"] == 56
    assert second["date_from"] == "2026-08-24"
    assert second["date_to"] == "2026-10-18"
    assert len(client.calls) == 116

    before_cache_hit = len(client.calls)
    cached = source.get_rate(sku="3921245627", tenant_scope="user:store-a")
    assert cached["cross_docking_per_unit"] == "10.00"
    assert len(client.calls) == before_cache_hit
    other_sku = source.get_rate(sku="archived-sku", tenant_scope="user:store-a")
    assert other_sku["status"] == "UNAVAILABLE"
    assert other_sku["reason"] == "SKU_NOT_IN_CROSSDOCK_WINDOW"
    assert other_sku["cross_docking_per_unit"] is None
    assert other_sku["applicable_to_sku"] is False
    assert len(client.calls) == before_cache_hit


def test_tenant_scope_isolated_and_force_refresh_resets_window_checkpoint(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone.utc),
    )
    client = _FakeOzonClient()
    source = _source(client, max_requests=5)

    first_store = source.get_rate(sku="3921245627", tenant_scope="user:store-a")
    assert first_store["http_attempts"] == 5
    assert first_store["finance_checkpointed"] is True

    second_store = source.get_rate(sku="3921245627", tenant_scope="user:store-b")
    assert second_store["http_attempts"] == 5
    assert second_store["finance_checkpointed"] is True
    assert len(client.calls) == 10

    refreshed = source.get_rate(
        sku="3921245627",
        tenant_scope="user:store-a",
        force_refresh=True,
    )
    assert refreshed["http_attempts"] == 5
    assert refreshed["cross_docking_per_unit"] is None
    assert len(client.calls) == 15


def test_force_refresh_resets_shared_window_once_per_parent_operation(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone.utc),
    )
    client = _FakeOzonClient()
    source = _source(client, max_requests=5)
    operation = PeriodProfitOperationTrace(
        operation="unit_price_batch_plan",
        time_budget_seconds=120,
        ozon_request_budget=128,
    )
    client.trace = operation
    first_row_trace = PeriodProfitOperationTrace(parent=operation)
    second_row_trace = PeriodProfitOperationTrace(parent=operation)

    first = source.get_rate(
        sku="3921245627",
        tenant_scope="user:store-a",
        operation_trace=first_row_trace,
        force_refresh=True,
    )
    first_window_calls = list(client.finance_cursor_calls)
    second = source.get_rate(
        sku="another-sku",
        tenant_scope="user:store-a",
        operation_trace=second_row_trace,
        force_refresh=True,
    )

    assert first["finance_checkpointed"] is True
    assert second["finance_checkpointed"] is True
    assert operation.ozon_requests_reserved == 10
    assert len(client.finance_cursor_calls) == 10
    assert client.finance_cursor_calls[5] != first_window_calls[0]


def test_source_creation_is_lazy_and_missing_identity_never_calls_ozon():
    client = _FakeOzonClient()
    source = _source(client)

    result = source.get_rate(sku="", tenant_scope="user:store-a")

    assert result["reason"] == "CROSSDOCK_IDENTITY_REQUIRED"
    assert client.calls == []


def test_source_reserves_only_remaining_parent_http_attempts(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    client = _FakeOzonClient()
    trace = _Trace(budget=64, reserved=62)
    client.trace = trace
    source = _source(client)

    result = source.get_rate(
        sku="3921245627",
        tenant_scope="user:store-a",
        operation_trace=trace,
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["cross_docking_per_unit"] is None
    assert result["http_attempts"] == 2
    assert trace.ozon_requests_reserved == 64
    assert client.calls == ["finance", "finance"]


def test_accrual_type_dictionary_load_is_bounded_and_cached_for_resume(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone.utc),
    )
    client = _FakeOzonClient()
    source = _source(client)
    source.finance_service.accrual_types = {}

    first = source.get_rate(sku="3921245627", tenant_scope="user:store-a")

    assert first["status"] == "UNAVAILABLE"
    assert first["http_attempts"] == 64
    assert client.calls.count("accrual_types") == 1
    assert source.finance_service.accrual_types[41]["name"] == "CrossDocking"

    second = source.get_rate(sku="3921245627", tenant_scope="user:store-a")

    assert second["status"] == "STORE_CROSSDOCK_SUPPLY_ESTIMATE"
    assert client.calls.count("accrual_types") == 1


def test_existing_28_day_finance_cache_is_reused_for_the_window_overlap(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone.utc),
    )
    first_cached_day = date(2026, 9, 21)
    last_cached_day = date(2026, 10, 18)
    cached_days = {}
    current = first_cached_day
    while current <= last_cached_day:
        cached_days[current.isoformat()] = {
            "error": False,
            "accruals": [],
            "last_id": "",
            "pages_loaded": 1,
        }
        current += timedelta(days=1)
    client = _FakeOzonClient()
    source = _source(client, cached_days=cached_days)

    result = source.get_rate(sku="3921245627", tenant_scope="user:store-a")

    assert result["cross_docking_per_unit"] == "10.00"
    assert result["days_complete"] == 56
    assert len(client.calls) == 60
    assert client.calls.count("finance") == 56
    assert client.calls[-4:] == [
        "supply_list",
        "supply_details",
        "act_summary",
        "act_products",
    ]


def test_incomplete_checkpoint_expires_after_ttl_and_restarts_from_fresh_window(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone.utc),
    )
    cache_now = [0]
    client = _FakeOzonClient()
    source = _source(
        client,
        max_requests=5,
        cache_clock=lambda: cache_now[0],
    )

    first = source.get_rate(sku="3921245627", tenant_scope="user:store-a")
    assert first["finance_checkpointed"] is True
    first_attempt_count = len(client.finance_cursor_calls)
    assert first_attempt_count == 5

    cache_now[0] = source.CACHE_TTL_SECONDS + 1
    expired = source.get_rate(sku="3921245627", tenant_scope="user:store-a")

    assert expired["status"] == "UNAVAILABLE"
    assert len(client.finance_cursor_calls) == first_attempt_count + 5
    assert client.finance_cursor_calls[first_attempt_count] == ("2026-08-24", "")


def test_date_rollover_uses_new_key_and_does_not_reuse_prior_window_checkpoint(monkeypatch):
    monkeypatch.setattr(
        "services.cross_docking_unit_rate_source.ZoneInfo",
        lambda _name: timezone.utc,
    )
    monkeypatch.setattr(
        CrossDockingSupplyEvidenceService,
        "resolve_timezone",
        classmethod(lambda cls: timezone.utc),
    )
    now = [datetime(2026, 10, 19, 12, tzinfo=timezone.utc)]
    client = _FakeOzonClient()
    source = _source(client, max_requests=5, clock=lambda: now[0])

    first = source.get_rate(sku="3921245627", tenant_scope="user:store-a")
    assert first["date_from"] == "2026-08-24"
    first_attempt_count = len(client.finance_cursor_calls)

    now[0] = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    next_window = source.get_rate(sku="3921245627", tenant_scope="user:store-a")

    assert next_window["date_from"] == "2026-08-25"
    assert next_window["date_to"] == "2026-10-19"
    assert client.finance_cursor_calls[first_attempt_count] == ("2026-08-25", "")
