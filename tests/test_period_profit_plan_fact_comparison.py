from copy import deepcopy

from period_profit_plan_fact_comparison import PeriodProfitPlanFactComparisonService
from services.sales_mix_planning_service import SalesMixPlanningService
from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService


def _inputs(**updates):
    values = {
        "price": "500", "cost": "150", "commission_rate": "20",
        "advertising_rate": "10", "discount_points_rate": "20",
        "logistics_per_unit": "25", "last_mile_per_unit": "5",
        "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
        "tax_rate": "6", "minimum_tax_rate": "1",
    }
    values.update(updates)
    return values


def _document(*, quantity=10, period="2026-08-01 — 2026-08-31", calculation_version=1,
              cross_docking_per_unit=None):
    item = {
        "row_id": "row-1",
        "identity": {
            "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
            "product_name": "Fixture item",
        },
        "inputs": _inputs(),
    }
    if calculation_version == 2:
        item["inputs"]["cross_docking_per_unit"] = cross_docking_per_unit
        item["sources"] = {"cross_docking": {
            "evidence_complete": True,
            "rate_available": cross_docking_per_unit is not None,
            "applicable_to_sku": cross_docking_per_unit is not None,
            "method": (
                "sku_accrual_cost_per_delivered_crossdock_unit"
                if cross_docking_per_unit is not None else None
            ),
            "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
            "amount_per_unit": cross_docking_per_unit,
        }}
    return {"document": {
        "document_id": "doc-1", "owner_id": "user-1", "store_id": "store-a",
        "revision": 3, "current_revision": 3, "title": "Plan",
        "payload": {
            "plan_kind": "single", "calculation_version": calculation_version,
            **({"schema_version": 2} if calculation_version == 2 else {}),
            "items": [item],
            "sales_mix": {
                "period_label": period, "quantities": {"row-1": quantity},
                "expenses": [], "confirmed": True,
            },
        },
    }}


def _actual(*, revenue=4160, quantity=8):
    row = {
        "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
        "revenue": revenue, "discount_points": 900, "units_sold": quantity,
        "commission": -500, "logistics": -250, "acquiring": -40,
        "other_fees": -15, "product_cost": 1200, "tax": 210, "profit": 1945,
    }
    return {
        "error": False, "status": "PERIOD_PROFIT_QUERY_READY",
        "period_profit_final_application_complete": True,
        "request": {"date_from": "2026-08-01", "date_to": "2026-08-31"},
        "summary": {
            "error": False, "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": "2026-08-01", "date_to": "2026-08-31",
            "products": [row], "product_count": 1,
            "sale_quantity_reconciled": True,
            "sale_quantity_source": "OZON_REALIZATION_POSTING_OR_FBO_LIST_OR_EXACT_POSTING_DETAIL",
            "profit_scope": "SELECTED_SKU",
            "advertising_included": False,
            "return_cogs_profit_applied": False,
        },
    }


def _service():
    scenario = UnitPriceScenarioService(TaxService())
    mix = SalesMixPlanningService(scenario, scenario.tax_service)
    return PeriodProfitPlanFactComparisonService(mix)


def test_plan_fact_reconciles_the_exact_quantity_and_gross_revenue_bridge():
    result = _service().compare(
        _document(), _actual(), tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )

    assert result["error"] is False
    assert result["status"] == "COMPARABLE"
    assert result["plan"]["quantity"] == 10
    assert result["actual"]["quantity"] == 8
    assert result["plan"]["revenue"] == "5000.00"
    assert result["actual"]["revenue"] == "4160.00"
    bridge = result["revenue_comparison"]
    assert bridge["delta"] == "-840.00"
    assert bridge["quantity_effect"] == "-1000.00"
    assert bridge["actual_average_revenue_effect"] == "160.00"
    assert bridge["bridge_reconciled"] is True
    assert result["actual"]["profit_status"] == "NOT_COMPARABLE"
    assert result["rows"][0]["actual_components"]["commission"] == "-500.00"


def test_zero_fact_quantity_keeps_average_undefined_and_bridge_arithmetic_valid():
    result = _service().compare(
        _document(), _actual(revenue=0, quantity=0),
        tenant_scope="user-1::ozon::store-a", generated_at_utc="2026-10-19T14:00:00Z",
    )

    assert result["error"] is False
    assert result["rows"][0]["actual_average_revenue_per_unit"] is None
    assert result["rows"][0]["quantity_effect"] == "-5000.00"
    assert result["rows"][0]["actual_average_revenue_effect"] == "0.00"
    assert result["revenue_comparison"]["delta"] == "-5000.00"
    assert result["revenue_comparison"]["bridge_reconciled"] is True


def test_unknown_plan_quantity_stays_null_and_suppresses_group_bridge():
    document = _document(quantity=None)
    result = _service().compare(
        document, _actual(), tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )

    assert result["error"] is False
    assert result["status"] == "PARTIAL"
    assert result["plan"]["quantity"] is None
    assert result["plan"]["revenue"] is None
    assert result["rows"][0]["plan_quantity"] is None
    assert result["revenue_comparison"]["delta"] is None
    assert result["revenue_comparison"]["bridge_reconciled"] is False


def test_duplicate_actual_identity_and_period_mismatch_fail_closed():
    duplicated = deepcopy(_actual())
    duplicated["summary"]["products"].append(deepcopy(duplicated["summary"]["products"][0]))
    assert _service().compare(
        _document(), duplicated, tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )["code"] == "PLAN_FACT_ACTUAL_IDENTITY_AMBIGUOUS"

    wrong_period = _actual()
    wrong_period["request"]["date_to"] = "2026-08-30"
    assert _service().compare(
        _document(), wrong_period, tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )["code"] == "PLAN_FACT_PERIOD_MISMATCH"


def test_scope_and_identity_mismatch_do_not_compare_other_store_or_sku():
    assert _service().compare(
        _document(), _actual(), tenant_scope="user-1::ozon::store-b",
        generated_at_utc="2026-10-19T14:00:00Z",
    )["code"] == "PLAN_FACT_SCOPE_MISMATCH"

    other = _actual()
    other["summary"]["products"][0]["sku"] = "different-sku"
    assert _service().compare(
        _document(), other, tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )["code"] == "PLAN_FACT_ACTUAL_SCOPE_MISMATCH"


def test_v2_plan_fact_keeps_actual_bridge_unchanged_and_uses_only_planned_rate():
    legacy = _service().compare(
        _document(), _actual(), tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )
    current = _service().compare(
        _document(calculation_version=2, cross_docking_per_unit="12.00"), _actual(),
        tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )

    assert current["error"] is False
    assert current["plan"]["quantity"] == legacy["plan"]["quantity"]
    assert current["plan"]["revenue"] == legacy["plan"]["revenue"]
    assert current["plan"]["profit"] == "1290.00"
    assert current["plan"]["profit"] == f"{float(legacy['plan']['profit']) - 120:.2f}"
    assert current["actual"] == legacy["actual"]
    assert current["revenue_comparison"] == legacy["revenue_comparison"]


def test_v2_plan_fact_does_not_claim_complete_plan_profit_without_rate():
    result = _service().compare(
        _document(calculation_version=2), _actual(),
        tenant_scope="user-1::ozon::store-a",
        generated_at_utc="2026-10-19T14:00:00Z",
    )

    assert result["error"] is False
    assert result["plan"]["profit"] is None
    assert result["plan"]["revenue"] == "5000.00"
    assert result["actual"]["revenue"] == "4160.00"
    assert result["revenue_comparison"]["delta"] == "-840.00"
