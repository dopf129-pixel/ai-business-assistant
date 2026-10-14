from datetime import datetime
from decimal import Decimal

from services.finance_service import FinanceService
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


def _source(finance, products=None, current=None, cost=None, tax=None):
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
