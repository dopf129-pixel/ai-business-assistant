from datetime import datetime
from decimal import Decimal

import pytest

from services.finance_service import FinanceService
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.unit_price_scenario_source import UnitPriceScenarioSource


def _accrual(posting_number, sku="sku-1", sale="100", bonus="20"):
    commission = {"sale_amount": {"amount": sale}}
    if bonus is not None:
        commission["bonus"] = {"amount": bonus}
    return {
        "accrued_category": "POSTING",
        "unit_number": posting_number,
        "posting": {
            "products": [{"sku": sku, "commission": commission}]
        },
    }


class _Finance(FinanceService):
    def __init__(self, by_date):
        self.by_date = by_date
        self._daily_accrual_cache = {}

    def _get_accruals_by_day(self, accrual_date):
        return self.by_date[str(accrual_date)]


class _ProductService:
    def __init__(self, products):
        self.products = products

    def load_products(self):
        return self.products


class _CurrentSource:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "seller_price": 500,
            "commission_rate": 15,
        }
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


class _CostService:
    def get_cost(self, product_id):
        return (product_id, "hook", "sku-1", 120.0, "RUB", "2026-10-01")


class _TaxConfiguration:
    def get_policy(self):
        return {
            "error": False,
            "configured": True,
            "policy": {
                "mode": "USN_INCOME",
                "tax_rate": 6.0,
                "minimum_tax_rate": 1.0,
            },
        }


def _complete_response(accruals):
    return {
        "error": False,
        "last_id": "",
        "pages_loaded": 1,
        "accruals": accruals,
    }


def test_finance_evidence_distinguishes_explicit_zero_from_missing_bonus():
    finance = _Finance({
        "2026-10-13": _complete_response([
            _accrual("posting-zero", sale="100", bonus="0"),
            _accrual("posting-missing", sale="50", bonus=None),
        ])
    })

    result = finance.get_daily_discount_points_evidence(
        "2026-10-13", "sku-1"
    )

    assert result["complete"] is False
    assert result["record_count"] == 1
    assert result["records"][0]["discount_points"] == "0"


def test_finance_evidence_requires_complete_pagination_and_exact_sku():
    finance = _Finance({
        "2026-10-13": {
            "error": False,
            "accruals": [_accrual("posting-1")],
        },
        "2026-10-12": _complete_response([
            _accrual("posting-other", sku="other"),
        ]),
    })

    partial = finance.get_daily_discount_points_evidence(
        "2026-10-13", "sku-1"
    )
    other_sku = finance.get_daily_discount_points_evidence(
        "2026-10-12", "sku-1"
    )

    assert partial["complete"] is False
    assert other_sku["complete"] is True
    assert other_sku["records"] == []


@pytest.mark.parametrize(
    "unresolved_sku",
    [None, "", "   ", "<missing-field>"],
)
def test_finance_evidence_marks_unresolved_posting_sku_incomplete(unresolved_sku):
    row = _accrual(
        "unresolved-posting",
        sku=None if unresolved_sku == "<missing-field>" else unresolved_sku,
        sale="900",
        bonus="0",
    )
    if unresolved_sku == "<missing-field>":
        del row["posting"]["products"][0]["sku"]
    finance = _Finance({"2026-10-13": _complete_response([row])})

    result = finance.get_daily_discount_points_evidence(
        "2026-10-13", "sku-1"
    )

    assert result["complete"] is False
    assert result["malformed_record_count"] == 1
    assert result["records"] == []


def test_finance_evidence_ignores_known_other_sku_even_when_bonus_is_missing():
    finance = _Finance({
        "2026-10-13": _complete_response([
            _accrual("other-product", sku="other-sku", bonus=None),
        ]),
    })

    result = finance.get_daily_discount_points_evidence(
        "2026-10-13", "sku-1"
    )

    assert result["complete"] is True
    assert result["records"] == []


def test_finance_evidence_deduplicates_identical_rows_and_rejects_conflict():
    finance = _Finance({
        "2026-10-13": _complete_response([
            _accrual("posting-1", sale="100", bonus="20"),
            _accrual("posting-1", sale="100", bonus="20"),
            _accrual("posting-1", sale="110", bonus="20"),
        ])
    })

    result = finance.get_daily_discount_points_evidence(
        "2026-10-13", "sku-1"
    )

    assert result["complete"] is False
    assert result["record_count"] == 1
    assert result["conflicting_duplicate_count"] == 1


class _SnapshotFinance:
    def __init__(self, date_rows):
        self.date_rows = date_rows
        self.prepared = None
        self.begun = 0
        self.calls = []

    def prepare_read_session(self, start, end):
        self.prepared = (start, end)

    def begin_read_session(self):
        self.begun += 1

    def get_daily_discount_points_evidence(self, day, sku):
        self.calls.append((day, sku))
        return self.date_rows.get(day, {
            "error": False,
            "complete": True,
            "records": [],
        })


def _source(
    finance,
    products=None,
    current=None,
    cost=None,
    tax=None,
    cross_docking_source=None,
):
    return UnitPriceScenarioSource(
        product_service=_ProductService(products or [{
            "product_id": "p1",
            "offer_id": "hook",
            "sku": "sku-1",
            "name": "Hook",
        }]),
        current_economics_source=current or _CurrentSource(),
        finance_service=finance,
        cost_service=cost or _CostService(),
        tax_configuration_service=tax or _TaxConfiguration(),
        clock=lambda: datetime(2026, 10, 14, 12),
        cross_docking_source=cross_docking_source,
    )


def test_weighted_points_share_uses_full_28_days_and_exact_sku():
    rows = {
        "2026-09-16": {
            "error": False,
            "complete": True,
            "records": [{
                "posting_number": "p-small",
                "sku": "sku-1",
                "sale_amount": "1000",
                "discount_points": "500",
            }],
        },
        "2026-09-17": {
            "error": False,
            "complete": True,
            "records": [{
                "posting_number": "p-large",
                "sku": "sku-1",
                "sale_amount": "9000",
                "discount_points": "900",
            }],
        },
    }
    finance = _SnapshotFinance(rows)
    source = _source(finance)
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = source.load_snapshot("sku-1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is False
    assert result["suggested_inputs"]["discount_points_rate"] == "14"
    assert result["source_periods"]["discount_points"] == {
        "from": "2026-09-16",
        "to": "2026-10-13",
        "calendar_days": 28,
    }
    assert finance.prepared == ("2026-09-16", "2026-10-13")
    assert len(finance.calls) == 28
    assert result["identity"]["store_id"] == "store-1"


def test_grouped_snapshot_inherits_parent_attempt_budget_through_child_trace():
    class _TracingCurrentSource(_CurrentSource):
        def __init__(self):
            super().__init__()
            self.trace = None

        def get(self, **kwargs):
            self.trace = current_period_profit_trace()
            reservation = self.trace.reserve_ozon_request("/synthetic-source")
            if reservation.get("error") is True:
                return reservation
            return super().get(**kwargs)

    current = _TracingCurrentSource()
    source = _source(_SnapshotFinance({}), current=current)
    parent = PeriodProfitOperationTrace(
        "price_batch", time_budget_seconds=30, ozon_request_budget=5
    )
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    trace_token = activate_period_profit_trace(parent)
    try:
        result = source.load_snapshot(
            "sku-1", user_id="user-1", operation_trace=parent
        )
    finally:
        assert current_period_profit_trace() is parent
        reset_period_profit_trace(trace_token)
        reset_current_tenant_user_id(token)

    assert result["error"] is False
    assert current.trace is not None
    assert current.trace.parent is parent
    assert current.trace.ozon_requests_reserved == 1
    assert parent.ozon_requests_reserved == 1


def test_batch_snapshot_uses_exact_catalog_product_without_reloading_catalog():
    products = _ProductService([{
        "product_id": "p1",
        "offer_id": "hook",
        "sku": "sku-1",
        "name": "Hook",
    }])
    products.calls = 0
    original_load = products.load_products

    def counted_load():
        products.calls += 1
        return original_load()

    products.load_products = counted_load
    source = UnitPriceScenarioSource(
        product_service=products,
        current_economics_source=_CurrentSource(),
        finance_service=_SnapshotFinance({}),
        cost_service=_CostService(),
        tax_configuration_service=_TaxConfiguration(),
        clock=lambda: datetime(2026, 10, 14, 12),
    )
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = source.load_snapshot(
            "sku-1",
            user_id="user-1",
            catalog_product={
                "product_id": "p1",
                "offer_id": "hook",
                "sku": "sku-1",
                "name": "Hook",
            },
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is False
    assert products.calls == 0
    assert result["identity"]["product_id"] == "p1"
    assert result["identity"]["offer_id"] == "hook"


def test_batch_exact_identity_cache_preserves_age_and_separates_identity_aliases():
    cache_now = [100.0]
    current = _CurrentSource()
    source = UnitPriceScenarioSource(
        product_service=_ProductService([]),
        current_economics_source=current,
        finance_service=_SnapshotFinance({}),
        cost_service=_CostService(),
        tax_configuration_service=_TaxConfiguration(),
        clock=lambda: datetime(2026, 10, 14, 12),
        cache_clock=lambda: cache_now[0],
    )
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        first_product = {
            "product_id": "p1", "offer_id": "hook", "sku": "sku-1"
        }
        first = source.load_snapshot(
            "sku-1", "user-1", catalog_product=first_product
        )
        cache_now[0] += 25
        cached = source.load_snapshot(
            "sku-1", "user-1", catalog_product=first_product
        )
        alias = source.load_snapshot(
            "sku-1",
            "user-1",
            catalog_product={
                "product_id": "p2", "offer_id": "hook-alias", "sku": "sku-1"
            },
        )
    finally:
        reset_current_tenant_user_id(token)

    assert first["cache"]["status"] == "miss"
    assert cached["cache"]["status"] == "hit"
    assert cached["cache"]["age_seconds"] == 25
    assert alias["identity"]["product_id"] == "p2"
    assert alias["identity"]["offer_id"] == "hook-alias"
    assert current.calls and len(current.calls) == 2


def test_inflight_wait_is_clamped_to_parent_remaining_time():
    class _Clock:
        now = 10.0

        def __call__(self):
            return self.now

    class _Pending:
        def __init__(self, clock):
            self.clock = clock
            self.timeout = None

        def wait(self, timeout=None):
            self.timeout = timeout
            self.clock.now = 15
            return False

    clock = _Clock()
    parent = PeriodProfitOperationTrace(
        "price_batch", time_budget_seconds=5, ozon_request_budget=5, clock=clock
    )
    source = _source(_SnapshotFinance({}))
    tenant = "user-1::ozon::store-1"
    pending = _Pending(clock)
    key = (tenant, "user-1", "sku-1")
    source._inflight[key] = pending
    token = set_current_tenant_user_id(tenant)
    try:
        result = source.load_snapshot(
            "sku-1", user_id="user-1", operation_trace=parent
        )
    finally:
        reset_current_tenant_user_id(token)
        source._inflight.pop(key, None)

    assert pending.timeout == 5
    assert result["error"] is True
    assert result["code"] == "OZON_OPERATION_TIME_BUDGET_EXHAUSTED"


def test_late_source_result_is_not_cached_after_parent_cancellation():
    class _CancellingCurrentSource(_CurrentSource):
        def get(self, **kwargs):
            current_period_profit_trace().parent.cancel()
            return super().get(**kwargs)

    source = _source(
        _SnapshotFinance({}),
        current=_CancellingCurrentSource(),
    )
    parent = PeriodProfitOperationTrace(
        "price_batch", time_budget_seconds=30, ozon_request_budget=5
    )
    tenant = "user-1::ozon::store-1"
    token = set_current_tenant_user_id(tenant)
    try:
        result = source.load_snapshot(
            "sku-1", user_id="user-1", operation_trace=parent
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is True
    assert result["code"] == "OZON_OPERATION_CANCELLED"
    assert parent.is_cancelled() is True
    assert source._cache == {}


def test_incomplete_day_or_missing_bonus_keeps_auto_rate_unknown():
    rows = {
        "2026-10-13": {
            "error": False,
            "complete": False,
            "records": [{
                "posting_number": "p1",
                "sku": "sku-1",
                "sale_amount": "100",
                "discount_points": "20",
            }],
        }
    }
    source = _source(_SnapshotFinance(rows))
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = source.load_snapshot("sku-1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is False
    assert result["suggested_inputs"]["discount_points_rate"] is None
    assert result["source_completeness"]["discount_points"]["complete"] is False


def test_store_scope_is_validated_before_any_product_or_network_read():
    current = _CurrentSource()
    products = _ProductService([{"product_id": "p1", "offer_id": "hook", "sku": "sku-1"}])
    source = UnitPriceScenarioSource(
        product_service=products,
        current_economics_source=current,
        finance_service=_SnapshotFinance({}),
        cost_service=_CostService(),
        tax_configuration_service=_TaxConfiguration(),
    )
    token = set_current_tenant_user_id("user-other::ozon::store-1")
    try:
        result = source.load_snapshot("sku-1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is True
    assert result["code"] == "UNIT_PRICE_SCENARIO_TENANT_MISMATCH"
    assert current.calls == []


def test_snapshot_cache_isolated_by_tenant_and_returns_deep_copies():
    current = _CurrentSource()
    source = _source(_SnapshotFinance({}), current=current)
    first_token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        first = source.load_snapshot("sku-1", user_id="user-1")
        first["suggested_inputs"]["cost"] = 999
        again = source.load_snapshot("sku-1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(first_token)
    second_token = set_current_tenant_user_id("user-1::ozon::store-2")
    try:
        second = source.load_snapshot("sku-1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(second_token)

    assert again["suggested_inputs"]["cost"] == 120.0
    assert again["cache"]["status"] == "hit"
    assert second["cache"]["status"] == "miss"
    assert len(current.calls) == 2


def test_incomplete_cross_docking_snapshot_is_not_cached_so_next_request_resumes():
    class _ResumableCrossDockingSource:
        def __init__(self):
            self.calls = []

        def get_rate(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {
                    "error": False,
                    "status": "UNAVAILABLE",
                    "cross_docking_per_unit": None,
                    "reason": "REQUEST_BUDGET_EXHAUSTED",
                    "evidence_complete": False,
                    "read_only": True,
                    "executed": False,
                }
            return {
                "error": False,
                "status": "SKU_SUPPLY_PERIOD_AVERAGE",
                "cross_docking_per_unit": "10.00",
                "applicable_to_sku": True,
                "method": "sku_accrual_cost_per_delivered_crossdock_unit",
                "reason": None,
                "evidence_complete": True,
                "read_only": True,
                "executed": False,
            }

    cross_docking = _ResumableCrossDockingSource()
    source = _source(
        _SnapshotFinance({}),
        cross_docking_source=cross_docking,
    )
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        first = source.load_snapshot("sku-1", user_id="user-1")
        assert source._cache == {}
        second = source.load_snapshot("sku-1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert first["cross_docking"]["evidence_complete"] is False
    assert first["suggested_inputs"]["cross_docking_per_unit"] is None
    assert "cross_docking_per_unit" not in first["missing_inputs"]
    assert second["cross_docking"]["cross_docking_per_unit"] == "10.00"
    assert second["suggested_inputs"]["cross_docking_per_unit"] == 10.0
    assert second["input_provenance"]["cross_docking_per_unit"] == "ozon_cross_docking_sku_average"
    assert second["cache"]["status"] == "miss"
    assert len(cross_docking.calls) == 2


def test_scenario_snapshot_loads_cross_docking_once_with_exact_sku_and_source_provenance():
    class _FastCurrentSource(_CurrentSource):
        def __init__(self):
            super().__init__()
            self.fast_calls = []

        def get(self, **_kwargs):
            raise AssertionError("fast path must avoid the current unit-economics X lookup")

        def get_price_and_commission_facts(self, **kwargs):
            self.fast_calls.append(kwargs)
            return dict(self.result)

    class _CrossDockingSource:
        def __init__(self):
            self.calls = []

        def get_rate(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "error": False,
                "status": "SKU_SUPPLY_PERIOD_AVERAGE",
                "evidence_complete": True,
                "applicable_to_sku": True,
                "method": "sku_accrual_cost_per_delivered_crossdock_unit",
                "cross_docking_per_unit": "12.50",
                "expense_total": "1250.00",
                "expense_by_sku": "1250.00",
                "supplied_units_sku": 100,
                "supplied_units_store": 100,
                "days_complete": 56,
                "days_expected": 56,
                "date_from": "2026-08-24",
                "date_to": "2026-10-18",
                "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
                "read_only": True,
                "executed": False,
            }

    current = _FastCurrentSource()
    cross_docking = _CrossDockingSource()
    source = _source(
        _SnapshotFinance({}),
        current=current,
        cross_docking_source=cross_docking,
    )
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        result = source.load_snapshot("sku-1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)

    assert result["error"] is False
    assert result["suggested_inputs"]["cross_docking_per_unit"] == 12.5
    assert result["input_provenance"]["cross_docking_per_unit"] == "ozon_cross_docking_sku_average"
    assert result["source_completeness"]["cross_docking"]["complete"] is True
    assert result["source_completeness"]["cross_docking"]["supplied_units_sku"] == 100
    assert "cross_docking_per_unit" not in result["missing_inputs"]
    assert current.fast_calls == [{
        "sku": "hook",
        "product_id": "p1",
        "finance_sku": "sku-1",
    }]
    assert cross_docking.calls[0]["sku"] == "sku-1"
    assert cross_docking.calls[0]["tenant_scope"] == "user-1::ozon::store-1"
