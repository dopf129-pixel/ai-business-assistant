from copy import deepcopy
from decimal import Decimal

from services.sales_mix_planning_service import SalesMixPlanningService
from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService


class _CountingTaxService(TaxService):
    def __init__(self):
        self.calls = []

    def calculate(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return super().calculate(**kwargs)


def _item(sku, inputs, row_id=None):
    return {
        "row_id": row_id or sku,
        "identity": {
            "product_id": "product-" + sku,
            "offer_id": "offer-" + sku,
            "sku": sku,
            "product_name": "Тест " + sku,
        },
        "inputs": inputs,
    }


def _sample_inputs(**updates):
    result = {
        "price": "500", "cost": "150", "commission_rate": "20",
        "advertising_rate": "10", "discount_points_rate": "20",
        "logistics_per_unit": "25", "last_mile_per_unit": "5",
        "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
        "tax_rate": "6", "minimum_tax_rate": "1",
    }
    result.update(updates)
    return result


def _extended_expense_contract(reference, amount, units=100):
    return {
        "schema_version": 1,
        "calculation_mode": "WINDOW_COST_ALLOCATION",
        "expense_snapshot_ref": reference * 64,
        "quantity_evidence_ref": ("f" if reference != "f" else "e") * 64,
        "expense_policy_revision": "unit-economics-v1",
        "included_component_keys": ["EXTRA_SERVICE"],
        "excluded_component_statuses": {},
        "numerator_and_denominator_basis": {
            "numerator": "WINDOW_EXPENSE_RUB", "denominator": "SOLD_UNITS_WINDOW",
        },
        "source_completeness": "COMPLETE",
        "assumed_inputs": [],
        "scope": {
            "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
            "from_date": "2026-01-01", "to_date": "2026-02-25",
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "UTC",
        },
        "denominator_units": units,
        "components": [{
            "component_key": "EXTRA_SERVICE", "numerator_rub": amount,
            "ownership": "ADDITIONAL",
        }],
    }


def _service():
    tax = _CountingTaxService()
    scenario = UnitPriceScenarioService(tax)
    return SalesMixPlanningService(scenario, tax), tax


def test_task_15_2_aggregates_rounded_unit_components_and_calls_tax_once():
    service, tax = _service()
    item_a = _item("SKU-A", _sample_inputs())
    item_b = _item("SKU-B", _sample_inputs(
        price="1000", cost="400", commission_rate="20", advertising_rate="10",
        discount_points_rate="20", logistics_per_unit="50", last_mile_per_unit="10",
        acquiring_per_unit="10",
    ))
    result = service.calculate(
        [item_a, item_b], quantities={"SKU-A": 10, "SKU-B": 5},
        period_label="2026-08-01 — 2026-08-31",
        expenses=[{"name": "Прочие расходы", "amount": "360"}], expenses_confirmed=True,
    )

    assert result["status"] == "COMPLETE"
    assert result["total_quantity"] == 15
    assert result["components"]["revenue"] == "10000.00"
    assert result["components"]["cost_of_goods"] == "3500.00"
    assert result["components"]["discount_points"] == "2000.00"
    assert result["components"]["commission"] == "2000.00"
    assert result["components"]["advertising"] == "1000.00"
    assert result["components"]["fees"] == "700.00"
    assert result["components"]["profit_before_tax"] == "2800.00"
    assert result["fixed_expense_total"] == "360.00"
    assert result["profit_before_tax_after_fixed_expenses"] == "2440.00"
    assert result["tax"] == "480.00"
    assert result["profit"] == "1960.00"
    assert result["margin_percent"] == "19.60"
    assert result["rows"][0]["price_per_unit"] == "500.00"
    assert result["rows"][0]["components"]["cost_of_goods"] == "1500.00"
    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["revenue_basis"] == "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS"
    assert len(tax.calls) == 1


def test_typed_period_advertising_is_excluded_from_pre_ad_profit_and_legacy_expense_is_unknown():
    service, _tax = _service()
    item = _item("SKU-A", _sample_inputs(
        price="500", cost="100", commission_rate="15", advertising_rate="8",
        discount_points_rate="20", logistics_per_unit="40", last_mile_per_unit="10",
        acquiring_per_unit="5", tax_mode="USN_INCOME", tax_rate="6",
        minimum_tax_rate="1",
    ))

    result = service.calculate(
        [item], quantities={"SKU-A": 10}, period_label="2026-08-01 — 2026-08-31",
        expenses=[
            {"category": "ADVERTISING", "name": "CPC", "amount": "100.00"},
            {"category": "OTHER", "name": "Упаковка", "amount": "200.00"},
            # The pre-category contract remains accepted but cannot be assumed non-ad.
            {"name": "Реклама", "amount": "50.00"},
        ],
        expenses_confirmed=True,
    )

    scope = result["pre_ad_margin"]["expense_scope"]
    assert result["fixed_expense_total"] == "350.00"
    assert result["profit_before_tax_after_fixed_expenses"] == "1950.00"
    assert result["profit"] == "1710.00"
    assert result["pre_ad_margin"]["profit_before_tax_rub"] == "2500.00"
    assert result["pre_ad_margin"]["profit_rub"] == "2260.00"
    assert scope["status"] == "PARTIAL"
    assert scope["known_non_ad_expenses_rub"]["FIXED_PLANNING_EXPENSES"] == "200.00"
    assert scope["fixed_planning_expenses_rub"] == "200.00"
    assert scope["fixed_planning_advertising_expenses_rub"] == "100.00"
    assert "UNCLASSIFIED_FIXED_PLANNING_EXPENSES" in scope["unknown_non_ad_expense_keys"]


def test_extended_expenses_are_applied_per_sku_once_and_tax_is_aggregated_once():
    service, tax = _service()
    item_a = _item("SKU-A", _sample_inputs())
    item_a["extended_scenario"] = _extended_expense_contract("a", "500.00")
    item_b = _item("SKU-B", _sample_inputs(price="1000", cost="400"))
    item_b["extended_scenario"] = _extended_expense_contract("b", "250.00")
    quantities = {"SKU-A": 10, "SKU-B": 4}
    common = {
        "quantities": quantities,
        "period_label": "2026-08-01 — 2026-08-31",
        "expenses": [],
        "expenses_confirmed": True,
    }

    baseline = service.calculate([_item("SKU-A", _sample_inputs()),
                                  _item("SKU-B", _sample_inputs(price="1000", cost="400"))],
                                 **common)
    tax.calls.clear()
    result = service.calculate([item_a, item_b], **common)

    rows = {row["row_id"]: row for row in result["rows"]}
    assert result["status"] == "COMPLETE"
    assert rows["SKU-A"]["components"]["additional_unit_expenses"] == "50.00"
    assert rows["SKU-B"]["components"]["additional_unit_expenses"] == "10.00"
    assert result["components"]["additional_unit_expenses"] == "60.00"
    assert Decimal(baseline["profit_before_tax_after_fixed_expenses"]) - Decimal(
        result["profit_before_tax_after_fixed_expenses"]
    ) == Decimal("60.00")
    assert len(tax.calls) == 1
    assert tax.calls[0]["gross_profit"] == float(
        Decimal(baseline["profit_before_tax_after_fixed_expenses"]) - Decimal("60.00")
    )


def test_mix_pre_ad_tax_bridge_uses_one_aggregate_tax_call_and_preserves_after_ad_result():
    service, tax = _service()
    item = _item("SKU-A", _sample_inputs(
        price="100", cost="30", commission_rate="14", logistics_per_unit="10",
        last_mile_per_unit="3", acquiring_per_unit="2", fees="3",
        advertising_rate="12", discount_points_rate="0",
        tax_mode="USN_INCOME_MINUS_EXPENSES", tax_rate="15", minimum_tax_rate="1",
    ))
    item["extended_scenario"] = _extended_expense_contract("a", "300.00")

    result = service.calculate(
        [item], quantities={"SKU-A": 1}, period_label="2026-08-01 — 2026-08-01",
        expenses=[], expenses_confirmed=True,
    )

    assert result["profit_before_tax_after_fixed_expenses"] == "26.00"
    assert result["tax"] == "3.90"
    assert result["profit"] == "22.10"
    assert result["margin_percent"] == "22.10"
    assert {
        key: value for key, value in result["pre_ad_margin"].items()
        if key != "expense_scope"
    } == {
        "schema_version": 1,
        "status": "AVAILABLE",
        "basis": "WEIGHTED_AGGREGATE_NO_AD_AFTER_TAX",
        "tax_basis": "AGGREGATE_NO_AD_SCENARIO",
        "revenue_basis": "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS",
        "unit_basis": "AGGREGATE_REVENUE_WEIGHTED",
        "revenue_rub": "100.00",
        "profit_before_tax_rub": "38.00",
        "tax_rub": "5.70",
        "profit_rub": "32.30",
        "margin_percent": "32.30",
        "reason": None,
    }
    expense_scope = result["pre_ad_margin"]["expense_scope"]
    assert expense_scope["status"] == "PARTIAL"
    assert expense_scope["known_non_ad_expenses_rub"] == {
        "ACQUIRING": "2.00",
        "COGS": "30.00",
        "CONFIRMED_ADDITIONAL_EXPENSES": "3.00",
        "LAST_MILE": "3.00",
        "LOGISTICS": "10.00",
        "OZON_COMMISSION": "14.00",
    }
    assert "EXTRA_SERVICE" in expense_scope["included_expense_keys"]
    assert {"CROSS_DOCKING", "PLACEMENT", "STORAGE"}.issubset(
        expense_scope["unknown_non_ad_expense_keys"]
    )
    assert expense_scope["excluded_expense_keys"] == ["ADVERTISING", "FIXED_STORE_OVERHEAD"]
    assert expense_scope["fixed_planning_expenses_rub"] == "0.00"
    assert len(tax.calls) == 1
    assert tax.calls[0]["gross_profit"] == 26.0
    assert tax.calls[0]["comparison_gross_profit"] == 38.0


def test_mix_pre_ad_margin_uses_revenue_weighting_not_mean_of_sku_percentages():
    service, tax = _service()
    item_a = _item("SKU-A", _sample_inputs(
        price="100", cost="80", commission_rate="0", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    ))
    item_b = _item("SKU-B", _sample_inputs(
        price="300", cost="210", commission_rate="0", logistics_per_unit="0",
        last_mile_per_unit="0", acquiring_per_unit="0", advertising_rate="0",
        discount_points_rate="0", tax_mode="NONE", tax_rate=None,
        minimum_tax_rate=None,
    ))

    result = service.calculate(
        [item_a, item_b], quantities={"SKU-A": 1, "SKU-B": 1},
        period_label="2026-08-01 — 2026-08-01", expenses=[], expenses_confirmed=True,
    )

    assert [row["components"]["pre_ad_profit_before_tax"] for row in result["rows"]] == ["20.00", "90.00"]
    assert result["pre_ad_margin"]["profit_rub"] == "110.00"
    assert result["pre_ad_margin"]["margin_percent"] == "27.50"
    assert result["pre_ad_margin"]["margin_percent"] != "25.00"
    assert len(tax.calls) == 1


def test_mix_margin_percentages_do_not_render_negative_zero():
    service, _tax = _service()
    item = _item("SKU-NEAR-ZERO", _sample_inputs(
        price="1000", cost="940.01", commission_rate="0", advertising_rate="0",
        discount_points_rate="0", logistics_per_unit="0", last_mile_per_unit="0",
        acquiring_per_unit="0", tax_mode="USN_INCOME", tax_rate="6",
        minimum_tax_rate="1",
    ))

    result = service.calculate(
        [item], quantities={"SKU-NEAR-ZERO": 1},
        period_label="01.08.2026 - 31.08.2026", expenses=[], expenses_confirmed=True,
    )

    assert result["profit"] == "-0.01"
    assert result["pre_ad_margin"]["profit_rub"] == "-0.01"
    assert result["margin_percent"] == "0.00"
    assert result["pre_ad_margin"]["margin_percent"] == "0.00"


def test_mix_keeps_pre_ad_tax_margin_available_with_unknown_advertising_and_exposes_scope():
    service, tax = _service()
    item = _item("SKU-A", _sample_inputs(advertising_rate=None))

    result = service.calculate(
        [item], quantities={"SKU-A": 2},
        period_label="2026-08-01 — 2026-08-31",
        expenses=[], expenses_confirmed=True,
    )

    assert result["coverage_complete"] is False
    assert result["after_ad_status"] == "INCOMPLETE_ADVERTISING"
    assert result["total_quantity"] == 2
    assert result["included_rows"] == 1
    assert result["components"]["revenue"] == "1000.00"
    assert result["components"]["advertising"] is None
    assert result["components"]["profit_before_tax"] is None
    assert result["profit_before_tax_after_fixed_expenses"] is None
    assert result["tax"] is None and result["profit"] is None
    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["revenue_rub"] == "1000.00"
    assert result["pre_ad_margin"]["profit_before_tax_rub"] == "430.00"
    assert result["pre_ad_margin"]["tax_rub"] == "48.00"
    assert result["pre_ad_margin"]["profit_rub"] == "382.00"
    assert result["pre_ad_margin"]["margin_percent"] == "38.20"
    assert result["rows"][0]["components"]["advertising"] is None
    assert result["rows"][0]["profit_before_tax_contribution"] is None
    scope = result["pre_ad_margin"]["expense_scope"]
    assert scope["status"] == "PARTIAL"
    assert "CROSS_DOCKING" in scope["unknown_non_ad_expense_keys"]
    assert "STORAGE" in scope["unknown_non_ad_expense_keys"]
    assert scope["known_non_ad_expenses_rub"]["COGS"] == "300.00"
    assert len(tax.calls) == 1
    assert tax.calls[0]["gross_profit"] == 430.0


def test_unknown_advertising_does_not_hide_confirmed_cross_docking_in_mix():
    service, _tax = _service()
    item = _item("SKU-A", _sample_inputs(
        advertising_rate=None, cross_docking_per_unit="12.00",
    ))
    item["sources"] = {"cross_docking": {
        "evidence_complete": True,
        "rate_available": True,
        "applicable_to_sku": True,
        "method": "sku_accrual_cost_per_delivered_crossdock_unit",
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "amount_per_unit": "12.00",
    }}

    result = service.calculate(
        [item], quantities={"SKU-A": 2},
        period_label="2026-08-01 - 2026-08-31",
        expenses=[], expenses_confirmed=True, include_cross_docking=True,
    )

    assert result["after_ad_status"] == "INCOMPLETE_ADVERTISING"
    assert result["components"]["cross_docking"] == "24.00"
    assert result["cross_docking_status"] == "CONFIRMED"


def test_mix_does_not_promote_one_skus_confirmed_zero_storage_to_global_zero():
    service, _tax = _service()
    item_zero = _item("SKU-ZERO", _sample_inputs())
    item_positive = _item("SKU-PAID", _sample_inputs())
    item_zero["extended_scenario"] = _extended_expense_contract("a", "0.00")
    item_zero["extended_scenario"]["included_component_keys"] = ["FINANCE_PAID_STORAGE"]
    item_zero["extended_scenario"]["components"] = [{
        "component_key": "FINANCE_PAID_STORAGE",
        "numerator_rub": "0.00",
        "ownership": "ADDITIONAL",
    }]
    item_positive["extended_scenario"] = _extended_expense_contract("b", "100.00")
    item_positive["extended_scenario"]["included_component_keys"] = ["FINANCE_PAID_STORAGE"]
    item_positive["extended_scenario"]["components"] = [{
        "component_key": "FINANCE_PAID_STORAGE",
        "numerator_rub": "100.00",
        "ownership": "ADDITIONAL",
    }]

    mixed = service.calculate(
        [item_zero, item_positive],
        quantities={"SKU-ZERO": 10, "SKU-PAID": 10},
        period_label="2026-08-01 - 2026-08-31",
        expenses=[], expenses_confirmed=True,
    )
    item_zero_second = _item("SKU-ZERO-2", _sample_inputs())
    item_zero_second["extended_scenario"] = _extended_expense_contract("c", "0.00")
    item_zero_second["extended_scenario"]["included_component_keys"] = ["FINANCE_PAID_STORAGE"]
    item_zero_second["extended_scenario"]["components"] = [{
        "component_key": "FINANCE_PAID_STORAGE",
        "numerator_rub": "0.00",
        "ownership": "ADDITIONAL",
    }]
    all_zero = service.calculate(
        [item_zero, item_zero_second],
        quantities={"SKU-ZERO": 10, "SKU-ZERO-2": 10},
        period_label="2026-08-01 - 2026-08-31",
        expenses=[], expenses_confirmed=True,
    )

    mixed_scope = mixed["pre_ad_margin"]["expense_scope"]
    assert mixed["error"] is False
    assert "STORAGE" not in mixed_scope["confirmed_zero_expense_keys"]
    assert "STORAGE" not in mixed_scope["known_non_ad_expenses_rub"]
    assert mixed_scope["known_non_ad_expenses_rub"]["CONFIRMED_ADDITIONAL_EXPENSES"] == "10.00"
    zero_scope = all_zero["pre_ad_margin"]["expense_scope"]
    assert "STORAGE" in zero_scope["confirmed_zero_expense_keys"]
    assert zero_scope["known_non_ad_expenses_rub"]["STORAGE"] == "0.00"


def test_pre_ad_expense_ledger_reconciles_canonical_unit_rounding_across_quantity():
    service, _tax = _service()
    item = _item("SKU-HALF-CENT", _sample_inputs(cost="150.005"))

    result = service.calculate(
        [item], quantities={"SKU-HALF-CENT": 100},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
    )

    projection = result["pre_ad_margin"]
    known = projection["expense_scope"]["known_non_ad_expenses_rub"]
    known_total = sum((Decimal(value) for value in known.values()), Decimal("0.00"))
    assert projection["revenue_rub"] == "50000.00"
    assert projection["profit_before_tax_rub"] == "21500.00"
    assert known["COGS"] == "15001.00"
    assert known["ROUNDING_ADJUSTMENT"] == "-1.00"
    assert Decimal(projection["revenue_rub"]) - known_total == Decimal(
        projection["profit_before_tax_rub"]
    )


def test_mixed_storage_inclusion_and_exclusion_is_partial_not_globally_excluded():
    service, _tax = _service()
    excluded_item = _item("SKU-EXCLUDED", _sample_inputs())
    excluded_item["extended_scenario"] = _extended_expense_contract("a", "0.00")
    excluded_item["extended_scenario"]["excluded_component_statuses"] = {
        "STORAGE": "EXCLUDED",
    }
    included_item = _item("SKU-INCLUDED", _sample_inputs())
    included_item["extended_scenario"] = _extended_expense_contract("b", "100.00")
    included_item["extended_scenario"]["included_component_keys"] = [
        "FINANCE_PAID_STORAGE",
    ]
    included_item["extended_scenario"]["components"] = [{
        "component_key": "FINANCE_PAID_STORAGE",
        "numerator_rub": "100.00",
        "ownership": "ADDITIONAL",
    }]

    result = service.calculate(
        [excluded_item, included_item], quantities={"SKU-EXCLUDED": 1, "SKU-INCLUDED": 1},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
    )

    scope = result["pre_ad_margin"]["expense_scope"]
    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert scope["status"] == "PARTIAL"
    assert "STORAGE" in scope["included_expense_keys"]
    assert "STORAGE" in scope["unknown_non_ad_expense_keys"]
    assert "STORAGE" not in scope["excluded_expense_keys"]
    assert "STORAGE" not in scope["excluded_expense_reasons"]


def test_sales_mix_keeps_known_base_logistics_when_extended_source_excludes_it():
    service, _tax = _service()
    item = _item("SKU-LOGISTICS", _sample_inputs())
    item["extended_scenario"] = _extended_expense_contract("a", "0.00")
    item["extended_scenario"]["excluded_component_statuses"] = {
        "LOGISTICS": "EXCLUDED",
    }

    result = service.calculate(
        [item], quantities={"SKU-LOGISTICS": 10},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
    )

    assert result["error"] is False
    scope = result["pre_ad_margin"]["expense_scope"]
    assert scope["known_non_ad_expenses_rub"]["LOGISTICS"] == "250.00"
    assert "LOGISTICS" in scope["included_expense_keys"]
    assert "LOGISTICS" not in scope["unknown_non_ad_expense_keys"]
    assert "LOGISTICS" not in scope["excluded_expense_keys"]


def test_v2_cross_docking_uses_planned_quantity_after_historical_supply_rate():
    service, tax = _service()
    inputs = _sample_inputs(cross_docking_per_unit="12.00")
    item = _item("SKU-A", inputs)
    item["sources"] = {"cross_docking": {
        "evidence_complete": True,
        "rate_available": True,
        "applicable_to_sku": True,
        "method": "sku_accrual_cost_per_delivered_crossdock_unit",
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "amount_per_unit": "12.00",
        "expense_total": "1200.00",
        "expense_by_sku": "1200.00",
        "supplied_units_sku": 100,
        "supplied_units_store": 100,
        "date_from": "2026-08-24", "date_to": "2026-10-18",
        "days_complete": 56, "days_expected": 56,
    }}

    result = service.calculate(
        [item], quantities={"SKU-A": 100},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
        include_cross_docking=True,
    )

    assert result["coverage_complete"] is True
    assert result["components"]["cross_docking"] == "1200.00"
    assert result["components"]["profit_before_tax"] == "15300.00"
    assert result["rows"][0]["components"]["cross_docking"] == "1200.00"
    assert result["profit"] == "12900.00"
    assert tax.calls[0]["gross_profit"] == 15300.0


def test_v2_sales_mix_marks_unconfirmed_cross_docking_partial_instead_of_zero():
    service, tax = _service()
    item = _item("SKU-A", _sample_inputs(cross_docking_per_unit=None))
    item["sources"] = {"cross_docking": {"evidence_complete": False}}

    result = service.calculate(
        [item], quantities={"SKU-A": 10},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
        include_cross_docking=True,
    )

    assert result["status"] == "PARTIAL"
    assert result["components"]["cross_docking"] is None
    assert result["profit"] is None
    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["expense_scope"]["status"] == "PARTIAL"
    assert "CROSS_DOCKING" in result["pre_ad_margin"]["expense_scope"]["unknown_non_ad_expense_keys"]
    assert len(tax.calls) == 1
    assert tax.calls[0]["gross_profit"] == 2150.0


def test_v2_complete_window_without_sku_rate_does_not_become_zero_expense():
    service, tax = _service()
    item = _item("SKU-A", _sample_inputs(cross_docking_per_unit=None))
    item["sources"] = {"cross_docking": {
        "evidence_complete": True,
        "rate_available": False,
        "applicable_to_sku": False,
        "method": None,
        "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
        "amount_per_unit": None,
    }}

    result = service.calculate(
        [item], quantities={"SKU-A": 10},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
        include_cross_docking=True,
    )

    assert result["coverage_complete"] is False
    assert result["cross_docking_status"] == "PARTIAL_OR_UNAVAILABLE"
    assert result["components"]["cross_docking"] is None
    assert result["profit"] is None
    assert result["pre_ad_margin"]["status"] == "AVAILABLE"
    assert result["pre_ad_margin"]["expense_scope"]["status"] == "PARTIAL"
    assert "CROSS_DOCKING" in result["pre_ad_margin"]["expense_scope"]["unknown_non_ad_expense_keys"]
    assert len(tax.calls) == 1
    assert tax.calls[0]["gross_profit"] == 2150.0


def test_aggregate_minimum_tax_does_not_sum_standalone_taxes():
    service, tax = _service()
    first = _item("A", _sample_inputs(
        price="500", cost="300", commission_rate="0", advertising_rate="0",
        discount_points_rate="0", logistics_per_unit="0", last_mile_per_unit="0",
        acquiring_per_unit="0", tax_mode="USN_INCOME_MINUS_EXPENSES", tax_rate="15",
        minimum_tax_rate="1",
    ))
    second = _item("B", _sample_inputs(
        price="500", cost="600", commission_rate="0", advertising_rate="0",
        discount_points_rate="0", logistics_per_unit="0", last_mile_per_unit="0",
        acquiring_per_unit="0", tax_mode="USN_INCOME_MINUS_EXPENSES", tax_rate="15",
        minimum_tax_rate="1",
    ))

    result = service.calculate(
        [first, second], quantities={"A": 1, "B": 1},
        period_label="01.08.2026 - 31.08.2026", expenses=[], expenses_confirmed=True,
    )

    assert result["components"]["profit_before_tax"] == "100.00"
    assert result["tax"] == "15.00"
    assert result["profit"] == "85.00"
    assert len(tax.calls) == 1
    assert tax.calls[0]["gross_profit"] == 100.0


def test_unknown_quantity_and_missing_inputs_produce_subtotal_but_no_group_profit():
    service, tax = _service()
    known = _item("KNOWN", _sample_inputs())
    unknown = _item("UNKNOWN", _sample_inputs())
    incomplete = _item("INCOMPLETE", _sample_inputs(cost=None))

    result = service.calculate(
        [known, unknown, incomplete],
        quantities={"KNOWN": 2, "UNKNOWN": None, "INCOMPLETE": 3},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
    )

    assert result["status"] == "PARTIAL"
    assert result["coverage_complete"] is False
    assert result["components"]["revenue"] == "1000.00"
    assert result["profit_before_tax_after_fixed_expenses"] == "330.00"
    assert result["tax"] is None and result["profit"] is None and result["margin_percent"] is None
    assert {item["reason"] for item in result["excluded_rows"]} == {
        "QUANTITY_UNKNOWN", "UNIT_INPUTS_INCOMPLETE",
    }
    assert tax.calls == []


def test_explicit_zero_contributes_zero_without_demanding_unit_cost_or_fees():
    service, tax = _service()
    item = _item("ZERO", _sample_inputs(
        cost=None, logistics_per_unit=None, last_mile_per_unit=None,
        acquiring_per_unit=None, tax_mode="USN_INCOME", tax_rate="6",
    ))

    result = service.calculate(
        [item], quantities={"ZERO": 0}, period_label="2026-08-01 - 2026-08-31",
        expenses=[], expenses_confirmed=True,
    )

    assert result["status"] == "COMPLETE"
    assert result["components"]["revenue"] == "0.00"
    assert result["margin_percent"] is None
    assert result["margin_status"] == "UNDEFINED_ZERO_REVENUE"
    assert result["tax"] == "0.00"
    assert len(tax.calls) == 1


def test_three_sku_mix_keeps_cost_commission_and_ads_separate_with_zero_and_missing_cost():
    service, tax = _service()
    first = _item("SKU-A", _sample_inputs(
        price="500", cost="100", commission_rate="10", advertising_rate="2",
    ))
    zero_sales = _item("SKU-B", _sample_inputs(
        price="1200", cost="300", commission_rate="30", advertising_rate="15",
    ))
    missing_cost = _item("SKU-C", _sample_inputs(
        price="250", cost=None, commission_rate="12", advertising_rate="5",
    ))

    result = service.calculate(
        [first, zero_sales, missing_cost],
        quantities={"SKU-A": 2, "SKU-B": 0, "SKU-C": 1},
        period_label="2026-08-01 - 2026-08-31",
        expenses=[], expenses_confirmed=True,
    )

    assert result["status"] == "PARTIAL"
    assert result["total_quantity"] == 2
    assert result["components"]["cost_of_goods"] == "200.00"
    assert result["components"]["commission"] == "100.00"
    assert result["components"]["advertising"] == "20.00"
    rows = {row["row_id"]: row for row in result["rows"]}
    assert rows["SKU-A"]["components"]["cost_of_goods"] == "200.00"
    assert rows["SKU-A"]["components"]["commission"] == "100.00"
    assert rows["SKU-A"]["components"]["advertising"] == "20.00"
    assert rows["SKU-B"]["quantity"] == 0
    assert rows["SKU-B"]["components"]["cost_of_goods"] == "0.00"
    assert {row["row_id"] for row in result["excluded_rows"]} == {"SKU-C"}
    assert result["profit"] is None and result["tax"] is None
    assert tax.calls == []


def test_mixed_tax_policy_and_unconfirmed_empty_expenses_fail_closed():
    service, tax = _service()
    first = _item("A", _sample_inputs())
    second = _item("B", _sample_inputs(tax_rate="5"))

    mixed = service.calculate(
        [first, second], quantities={"A": 1, "B": 1},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
    )
    unconfirmed = service.calculate(
        [first], quantities={"A": 1}, period_label="2026-08-01 - 2026-08-31",
        expenses=[], expenses_confirmed=False,
    )

    assert mixed["tax_status"] == "MIXED_TAX_POLICIES"
    assert mixed["tax"] is None and mixed["profit"] is None
    assert unconfirmed["code"] == "FIXED_EXPENSES_NOT_CONFIRMED"
    assert tax.calls == []


def test_invalid_period_quantity_and_duplicate_identity_are_rejected():
    service, _tax = _service()
    item = _item("A", _sample_inputs())
    common = {"quantities": {"A": 1}, "expenses": [], "expenses_confirmed": True}

    assert service.calculate([item], period_label="2026-02-30 - 2026-03-01", **common)["code"] == "INVALID_PERIOD"
    assert service.calculate([item], period_label="2026-08-01 - 2026-08-31", quantities={"A": 1.0}, expenses=[], expenses_confirmed=True)["code"] == "INVALID_QUANTITY"
    duplicate = _item("A", _sample_inputs(), row_id="OTHER")
    assert service.calculate([item, duplicate], quantities={"A": 1, "OTHER": 1}, period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True)["code"] == "DUPLICATE_PRODUCT_IDENTITY"


def test_sales_mix_limits_accept_boundaries_and_reject_values_above_them():
    service, tax = _service()
    item = _item("A", _sample_inputs())
    at_boundary = service.calculate(
        [item], quantities={"A": 100_000},
        period_label="2025-10-19 - 2026-10-18", expenses=[], expenses_confirmed=True,
    )
    too_many_units = service.calculate(
        [item], quantities={"A": 100_001},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
    )
    too_long_period = service.calculate(
        [item], quantities={"A": 1},
        period_label="2025-10-18 - 2026-10-19", expenses=[], expenses_confirmed=True,
    )
    too_many_expenses = service.calculate(
        [item], quantities={"A": 1}, period_label="2026-08-01 - 2026-08-31",
        expenses=[{"name": f"expense-{n}", "amount": "0"} for n in range(21)],
        expenses_confirmed=True,
    )
    expense_total_overflow = service.calculate(
        [item], quantities={"A": 1}, period_label="2026-08-01 - 2026-08-31",
        expenses=[
            {"name": "one", "amount": "600000000"},
            {"name": "two", "amount": "600000000"},
        ], expenses_confirmed=True,
    )

    assert at_boundary["error"] is False and at_boundary["total_quantity"] == 100_000
    assert too_many_units["code"] == "INVALID_QUANTITY"
    assert too_long_period["code"] == "INVALID_PERIOD"
    assert too_many_expenses["code"] == "INVALID_FIXED_EXPENSES"
    assert expense_total_overflow["code"] == "FIXED_EXPENSE_TOTAL_LIMIT_EXCEEDED"
    assert len(tax.calls) == 1


def test_aggregate_money_guard_runs_before_float_tax_service_for_single_and_multiple_skus():
    service, tax = _service()
    first = _item("A", _sample_inputs(
        price="6000000", cost="0", commission_rate="0", advertising_rate="0",
        discount_points_rate="0", logistics_per_unit="0", last_mile_per_unit="0",
        acquiring_per_unit="0",
    ))
    second = _item("B", _sample_inputs(
        price="6000000", cost="0", commission_rate="0", advertising_rate="0",
        discount_points_rate="0", logistics_per_unit="0", last_mile_per_unit="0",
        acquiring_per_unit="0",
    ))
    single_overflow = service.calculate(
        [_item("SINGLE", _sample_inputs(
            price="999999999.99", cost="0", commission_rate="0", advertising_rate="0",
            discount_points_rate="0", logistics_per_unit="0", last_mile_per_unit="0",
            acquiring_per_unit="0",
        ))],
        quantities={"SINGLE": 100_000}, period_label="2026-08-01 - 2026-08-31",
        expenses=[], expenses_confirmed=True,
    )
    multiple_overflow = service.calculate(
        [first, second], quantities={"A": 100_000, "B": 100_000},
        period_label="2026-08-01 - 2026-08-31", expenses=[], expenses_confirmed=True,
    )

    assert single_overflow["code"] == "AGGREGATE_AMOUNT_LIMIT_EXCEEDED"
    assert multiple_overflow["code"] == "AGGREGATE_AMOUNT_LIMIT_EXCEEDED"
    assert tax.calls == []
