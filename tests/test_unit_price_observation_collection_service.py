from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.period_profit_finance_service import PeriodProfitFinanceService
from services.unit_price_observation_collection_service import (
    UnitPriceObservationCollectionService,
)


OBSERVATION = {
    "status": "ACTIVE",
    "store_id": "store-a",
    "product_id": "product-1",
    "offer_id": "offer-1",
    "sku": "3921245627",
    "sale_schema": "FBO",
    "seller_price_cents": 10_000,
    "window_timezone": "Europe/Moscow",
    "effective_from": "2026-10-10T12:00:00+03:00",
}


class Repository:
    def __init__(self, observation=None):
        self.observation = dict(observation or OBSERVATION)
        self.calls = 0

    def get_unit_price_observation(self, observation_id):
        self.calls += 1
        if observation_id != "observation-1":
            return {"error": True, "code": "PLANNING_OBSERVATION_NOT_FOUND"}
        return {"error": False, "observation": dict(self.observation), "result": None}


class Finance:
    def __init__(self, *, per_day_attempts=1, fail_on=None):
        self.per_day_attempts = per_day_attempts
        self.fail_on = fail_on
        self.days = []
        self.session_started = 0
        self.cached_days = {}
        self.prepared = []

    def prepare_read_session(self, date_from, date_to):
        self.prepared.append((date_from, date_to))

    def begin_read_session(self):
        self.session_started += 1

    def get_daily_finance(self, day, *, sku):
        self.days.append((day, sku))
        trace = current_period_profit_trace()
        for _ in range(self.per_day_attempts):
            reserved = trace.reserve_ozon_request("fake-finance")
            if reserved["error"]:
                return {"error": True, "code": reserved["code"]}
        if day == self.fail_on:
            return {"error": True, "code": "OZON_RATE_LIMITED"}
        self.cached_days[day] = {
            "accruals": [{
                "accrued_category": "POSTING",
                "future_api_flag": True,
                "posting": {"products": [{
                    "sku": sku,
                    "future_product_metadata": "raw-secret-product-name",
                }]},
            }],
            "last_id": "",
            "pages_loaded": 1,
        }
        return {
            "error": False,
            "date": day,
            "sku": sku,
            "operations": 2,
            "sales_count": 99,
            "gross_sales": Decimal("100.00"),
            "discount_points": Decimal("20.00"),
            "net_accrual": Decimal("40.00"),
            "commission": Decimal("-10.00"),
            "logistics": Decimal("-15.00"),
            "acquiring": Decimal("-2.00"),
            "other_fees": Decimal("-33.00"),
            "fee_components_included": True,
            "accrual_type_breakdown": {
                "1": {"name": "Эквайринг", "amount": -2.0},
                "777": {"name": "Новая услуга Ozon", "amount": -1.0},
            },
            "future_field": 3,
        }

    def get_cached_daily_accruals(self, date_from, date_to):
        if date_from != date_to:
            return {}
        return {date_from: self.cached_days[date_from]} if date_from in self.cached_days else {}


class Advertising:
    def __init__(self, *, attempts=1, configured=True):
        self.attempts = attempts
        self.configured = configured
        self.calls = []

    def load(self, date_from, date_to, accepted_skus):
        self.calls.append((date_from, date_to, set(accepted_skus)))
        trace = current_period_profit_trace()
        for _ in range(self.attempts):
            reserved = trace.reserve_ozon_request("fake-performance")
            if reserved["error"]:
                return {"error": True, "code": reserved["code"]}
        if not self.configured:
            return {
                "error": False,
                "configured": False,
                "complete": False,
                "status": "PERIOD_PROFIT_SKU_ADVERTISING_NOT_CONFIGURED",
            }
        return {
            "error": False,
            "configured": True,
            "complete": True,
            "expense": Decimal("12.50"),
            "matched_row_count": 3,
        }


class ReturnsBuyoutSource:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def get(self, sku, since, to):
        self.calls.append((sku, since, to))
        trace = current_period_profit_trace()
        for _ in range(2):
            reserved = trace.reserve_ozon_request("fake-returns-buyout")
            if reserved["error"]:
                return {"error": True, "code": reserved["code"]}
        return self.facts


class FakeOzonFinanceTransport:
    """Fake the existing client boundary while retaining trace reservations."""

    def __init__(self):
        self.calls = []

    def get_accruals_by_day(self, day):
        trace = current_period_profit_trace()
        reservation = trace.reserve_ozon_request("fake-ozon-finance")
        if reservation["error"]:
            return {"error": True, "code": reservation["code"]}
        self.calls.append(day)
        return {
            "error": False,
            "last_id": "",
            "pages_loaded": 1,
            "accruals": [{
                "accrual_id": 7001,
                "unit_number": "private-posting-id",
                "accrued_category": "POSTING",
                "total_amount": {"amount": "40.00", "currency": "RUB"},
                "posting": {"products": [{
                    "sku": OBSERVATION["sku"],
                    "commission": {
                        "sale_amount": {"amount": "100.00", "currency": "RUB"},
                        "sale_commission": {"amount": "-10.00", "currency": "RUB"},
                        "bonus": {"amount": "20.00", "currency": "RUB"},
                    },
                    "delivery": {"services": []},
                    "future_product_metadata": "private-product-title",
                }]},
                "item_fees": {"fees": [{
                    "sku": OBSERVATION["sku"],
                    "fees": [{
                        "type_id": 777,
                        "accrued": {"amount": "-3.00", "currency": "RUB"},
                    }],
                }]},
                "future_api_flag": True,
            }],
        }


def _service(*, repository=None, finance=None, advertising=None, returns_buyout_source=None):
    return UnitPriceObservationCollectionService(
        repository or Repository(),
        finance or Finance(),
        advertising,
        clock=lambda: datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
        returns_buyout_source=returns_buyout_source,
    )


def test_collects_only_selected_completed_window_and_preserves_schema_diagnostics():
    finance = Finance(per_day_attempts=2)
    advertising = Advertising(attempts=3)
    repo = Repository()
    result = _service(repository=repo, finance=finance, advertising=advertising).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )

    assert result["error"] is False
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["identity"]["sku"] == OBSERVATION["sku"]
    assert result["seller_price_cents"] == 10_000
    assert result["metrics"]["gross_seller_revenue"] == "300.00"
    assert result["metrics"]["discount_points"] == "60.00"
    assert result["metrics"]["finance_net"] == "120.00"
    assert result["metrics"]["cpc_spend"] == "12.50"
    assert result["metrics"]["successful_sale_units"] is None
    assert result["metrics"]["ordered_units"] is None
    assert result["metrics"]["sample_days"] == 3
    assert result["metrics"]["source_row_count"] == 6
    assert result["completeness"]["price_history"] == "PRICE_HISTORY_UNCONFIRMED"
    assert result["completeness"]["successful_units"] == "UNKNOWN"
    finance_source = next(item for item in result["sources"] if item["name"] == "FINANCE")
    assert finance_source["status"] == "COMPLETE"
    assert finance_source["unknown_fields"] == [
        {"name": "accruals[].future_api_flag", "type": "bool"},
        {"name": "accruals[].posting.products[].future_product_metadata", "type": "string"},
        {"name": "future_field", "type": "int"},
    ]
    assert finance_source["unsupported_types"] == ["Новая услуга Ozon"]
    assert "raw-secret-product-name" not in repr(result)
    assert result["diagnostics"]["http_attempts"] == 9
    assert result["diagnostics"]["collection_http_attempts"] == 9
    assert result["diagnostics"]["collection_http_attempt_limit"] == 64
    assert len(finance.days) == 3
    assert finance.prepared == [("2026-10-20", "2026-10-22")]
    assert all(sku == OBSERVATION["sku"] for _, sku in finance.days)
    assert advertising.calls == [("2026-10-20", "2026-10-22", {OBSERVATION["sku"]})]
    assert repo.calls == 1


def test_unconfigured_performance_is_not_reported_as_zero_spend():
    result = _service(
        finance=Finance(), advertising=Advertising(configured=False),
    ).collect_window("observation-1", date_from="2026-10-20", date_to="2026-10-22")
    assert result["metrics"]["cpc_spend"] is None
    assert result["metrics"]["advertising_status"] == "NOT_REQUESTED"
    assert next(item for item in result["sources"] if item["name"] == "PERFORMANCE")["reason"] == "PERFORMANCE_CREDENTIALS_NOT_CONFIGURED"
    assert any("does not mean zero advertising" in item for item in result["warnings"])


def test_uses_existing_finance_adapter_with_fake_transport_and_no_raw_values():
    finance = PeriodProfitFinanceService()
    transport = FakeOzonFinanceTransport()
    finance.ozon = transport
    finance.accrual_types = {
        777: {"name": "Synthetic fee", "description": "Synthetic unsupported fee"},
    }
    advertising = Advertising(attempts=1)
    result = _service(finance=finance, advertising=advertising).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    source = next(item for item in result["sources"] if item["name"] == "FINANCE")
    assert result["metrics"]["gross_seller_revenue"] == "300.00"
    assert result["metrics"]["discount_points"] == "60.00"
    assert result["metrics"]["finance_net"] == "120.00"
    assert source["status"] == "COMPLETE"
    assert source["unsupported_types"] == ["Synthetic fee"]
    assert {item["name"] for item in source["unknown_fields"]} >= {
        "accruals[].future_api_flag",
        "accruals[].posting.products[].future_product_metadata",
    }
    serialized = repr(result)
    assert "private-posting-id" not in serialized
    assert "private-product-title" not in serialized
    assert result["metrics"]["successful_sale_units"] is None
    assert result["metrics"]["price_evidence_status"] == "PRICE_HISTORY_UNCONFIRMED"
    assert len(transport.calls) == 3
    assert result["diagnostics"]["http_attempts"] == 4


def test_complete_same_sku_buyout_facts_supply_model_units_and_safe_rate():
    facts = {
        "error": False, "sku": "private-offer-id", "since": "2026-10-20",
        "to": "2026-10-22", "posting_count": 4, "total_units": 4,
        "delivered_units": 3, "cancelled_units": 1,
        "ambiguous_cancelled_units": 0, "customer_non_buyout_units": 1,
        "customer_return_units": 0, "customer_cancelled_units": 0,
        "delivery_failure_units": 0, "unknown_return_units": 0,
        "postings_complete": True, "returns_available": True,
        "returns_complete": True, "postings": [
            {"posting_number": "private-posting-1", "status": "delivered", "quantity": 1},
            {"posting_number": "private-posting-2", "status": "delivered", "quantity": 1},
            {"posting_number": "private-posting-3", "status": "delivered", "quantity": 1},
            {"posting_number": "private-posting-4", "status": "cancelled", "quantity": 1},
        ],
        "return_events": [{"return_id": "private-return-id"}],
    }
    source = ReturnsBuyoutSource(facts)
    result = _service(returns_buyout_source=source).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )

    returns_source = next(item for item in result["sources"] if item["name"] == "RETURNS")
    performance_source = next(
        item for item in result["sources"] if item["name"] == "PERFORMANCE"
    )
    assert returns_source["status"] == "COMPLETE"
    assert returns_source["complete"] is True
    assert returns_source["source_date_basis"] == "FBO_POSTING_AND_RETURN_CHANGE_WINDOW"
    assert performance_source["timezone"] == "Europe/Moscow"
    assert result["metrics"]["ordered_units"] == 4
    assert result["metrics"]["delivered_units"] == 3
    assert result["metrics"]["successful_sale_units"] == 3
    assert result["metrics"]["successful_unit_denominator"] == 3
    assert result["metrics"]["buyout_rate_percent"] == 75.0
    assert result["metrics"]["buyout_sample_size"] == 4
    assert result["completeness"]["successful_units"] == "CONFIRMED"
    assert result["completeness"]["returns"] == "CONFIRMED"
    assert source.calls == [(
        "offer-1", "2026-10-19T21:00:00.000000Z",
        "2026-10-22T20:59:59.999999Z",
    )]
    serialized = repr(result)
    assert "private-offer-id" not in serialized
    assert "private-posting-1" not in serialized
    assert "private-return-id" not in serialized
    assert result["diagnostics"]["collection_http_attempts"] == 5


def test_ambiguous_or_unfinalized_buyout_cohort_never_becomes_model_units():
    facts = {
        "error": False, "posting_count": 2, "total_units": 2,
        "delivered_units": 1, "cancelled_units": 1,
        "ambiguous_cancelled_units": 1, "customer_non_buyout_units": 0,
        "customer_return_units": 0, "customer_cancelled_units": 0,
        "delivery_failure_units": 0, "unknown_return_units": 1,
        "postings_complete": True, "returns_available": True,
        "returns_complete": True, "postings": [
            {"posting_number": "private-posting-1", "status": "delivered", "quantity": 1},
            {"posting_number": "private-posting-2", "status": "cancelled", "quantity": 1},
        ], "return_events": [],
    }
    result = _service(returns_buyout_source=ReturnsBuyoutSource(facts)).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    returns_source = next(item for item in result["sources"] if item["name"] == "RETURNS")
    assert returns_source["status"] == "PARTIAL"
    assert result["metrics"]["successful_sale_units"] is None
    assert result["metrics"]["buyout_rate_percent"] is None

    facts["ambiguous_cancelled_units"] = 0
    facts["postings"][0]["status"] = "awaiting_deliver"
    result = _service(returns_buyout_source=ReturnsBuyoutSource(facts)).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    assert result["metrics"]["successful_sale_units"] is None
    assert result["metrics"]["buyout_rate_percent"] is None


def test_collector_reads_repository_nested_identity_and_rejects_scope_conflict():
    stored = {
        "status": "ACTIVE", "store_id": "store-a",
        "sku": "3921245627",
        "identity": {
            "product_id": "product-1", "offer_id": "offer-1",
            "sku": "3921245627", "sale_schema": "FBO",
        },
        "seller_price_cents": 10_000,
        "window_timezone": "Europe/Moscow",
        "effective_from": "2026-10-10T12:00:00+03:00",
    }
    result = _service(repository=Repository(stored)).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    assert result["error"] is False
    assert result["identity"] == {
        "store_id": "store-a", "product_id": "product-1",
        "offer_id": "offer-1", "sku": "3921245627", "sale_schema": "FBO",
    }

    stored["identity"]["sku"] = "another-sku"
    conflict = _service(repository=Repository(stored)).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    assert conflict["error"] is True
    assert conflict["code"] == "PLANNING_OBSERVATION_IDENTITY_INVALID"
    assert result["completeness"]["successful_units"] == "UNKNOWN"


def test_finance_failure_does_not_zero_fill_unread_days_or_claim_complete_source():
    finance = Finance(fail_on="2026-10-21")
    result = _service(finance=finance).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    source = next(item for item in result["sources"] if item["name"] == "FINANCE")
    assert result["status"] == "INSUFFICIENT_DATA"
    assert source["status"] == "PARTIAL"
    assert source["row_count"] == 2
    assert source["reason"] == "OZON_RATE_LIMITED"
    assert result["metrics"]["gross_seller_revenue"] == "100.00"
    assert result["metrics"]["sample_days"] == 1
    assert "FINANCE_WINDOW_PARTIAL" in " ".join(result["warnings"])
    assert len(finance.days) == 2


def test_shared_http_attempt_budget_includes_finance_retries_and_optional_performance():
    finance = Finance(per_day_attempts=64)
    advertising = Advertising(attempts=1)
    result = _service(finance=finance, advertising=advertising).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    assert result["diagnostics"]["http_attempts"] == 64
    assert result["diagnostics"]["http_attempt_cap"] == 64
    assert len(finance.days) == 1
    assert advertising.calls == []
    assert result["sources"][0]["status"] == "PARTIAL"
    assert result["sources"][0]["reason"] == "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED"


def test_collector_respects_a_tighter_parent_operation_budget():
    parent = PeriodProfitOperationTrace(
        "outer_operation", time_budget_seconds=60, ozon_request_budget=3,
    )
    finance = Finance()
    advertising = Advertising()
    token = activate_period_profit_trace(parent)
    try:
        result = _service(finance=finance, advertising=advertising).collect_window(
            "observation-1", date_from="2026-10-20", date_to="2026-10-22",
        )
    finally:
        reset_period_profit_trace(token)
    assert result["diagnostics"]["http_attempts"] == 3
    assert result["diagnostics"]["collection_http_attempts"] == 3
    assert result["diagnostics"]["http_attempt_cap"] == 3
    assert result["diagnostics"]["collection_http_attempt_limit"] == 64
    assert len(finance.days) == 3
    assert advertising.calls == []


def test_cancelled_parent_operation_makes_no_source_attempts_and_stays_incomplete():
    finance = Finance()
    advertising = Advertising()
    parent = PeriodProfitOperationTrace(
        "cancelled_owner_operation", time_budget_seconds=60,
        ozon_request_budget=10, clock=lambda: 100.0,
    )
    parent.cancel()
    token = activate_period_profit_trace(parent)
    try:
        result = _service(finance=finance, advertising=advertising).collect_window(
            "observation-1", date_from="2026-10-20", date_to="2026-10-22",
        )
    finally:
        reset_period_profit_trace(token)

    finance_source = next(item for item in result["sources"] if item["name"] == "FINANCE")
    performance_source = next(item for item in result["sources"] if item["name"] == "PERFORMANCE")
    assert result["status"] == "SOURCE_UNAVAILABLE"
    assert finance_source["status"] == performance_source["status"] == "SOURCE_UNAVAILABLE"
    assert finance_source["reason"] == performance_source["reason"] == "OZON_OPERATION_CANCELLED"
    assert result["diagnostics"]["http_attempts"] == 0
    assert result["diagnostics"]["collection_http_attempts"] == 0
    assert finance.days == []
    assert advertising.calls == []


def test_time_budget_expiry_stops_remaining_days_and_optional_performance():
    now = {"seconds": 100.0}

    class _SlowFirstDayFinance(Finance):
        def get_daily_finance(self, day, *, sku):
            result = super().get_daily_finance(day, sku=sku)
            now["seconds"] = 161.0
            return result

    finance = _SlowFirstDayFinance()
    advertising = Advertising()
    parent = PeriodProfitOperationTrace(
        "slow_owner_operation", time_budget_seconds=60,
        ozon_request_budget=10, clock=lambda: now["seconds"],
    )
    token = activate_period_profit_trace(parent)
    try:
        result = _service(finance=finance, advertising=advertising).collect_window(
            "observation-1", date_from="2026-10-20", date_to="2026-10-22",
        )
    finally:
        reset_period_profit_trace(token)

    finance_source = next(item for item in result["sources"] if item["name"] == "FINANCE")
    performance_source = next(item for item in result["sources"] if item["name"] == "PERFORMANCE")
    assert result["status"] == "INSUFFICIENT_DATA"
    assert finance_source["status"] == "PARTIAL"
    assert finance_source["reason"] == "OZON_OPERATION_TIME_BUDGET_EXHAUSTED"
    assert performance_source["status"] == "SOURCE_UNAVAILABLE"
    assert performance_source["reason"] == "OZON_OPERATION_TIME_BUDGET_EXHAUSTED"
    assert result["metrics"]["sample_days"] == 1
    assert result["diagnostics"]["http_attempts"] == 1
    assert len(finance.days) == 1
    assert advertising.calls == []


@pytest.mark.parametrize("date_from,date_to", [
    ("2026-10-24", "2026-10-27"),  # includes local today
    ("2026-10-20", "2026-10-21"),  # too short
    ("2026-09-01", "2026-10-27"),  # too long and incomplete
    ("2026-10-01", "2026-10-03"),  # predates confirmed effective date
])
def test_rejects_incomplete_or_out_of_scope_windows(date_from, date_to):
    finance = Finance()
    result = _service(finance=finance).collect_window(
        "observation-1", date_from=date_from, date_to=date_to,
    )
    assert result["error"] is True
    assert result["code"] == "UNIT_PRICE_OBSERVATION_WINDOW_NOT_COMPLETED"
    assert finance.days == []


def test_rejects_archived_observation_before_calling_sources():
    repository = Repository(dict(OBSERVATION, status="ARCHIVED"))
    finance = Finance()
    result = _service(repository=repository, finance=finance).collect_window(
        "observation-1", date_from="2026-10-20", date_to="2026-10-22",
    )
    assert result["code"] == "PLANNING_OBSERVATION_ARCHIVED"
    assert finance.days == []
