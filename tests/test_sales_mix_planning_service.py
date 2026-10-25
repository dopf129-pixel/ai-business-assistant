from copy import deepcopy

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
    assert len(tax.calls) == 1


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
    assert tax.calls == []


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
    assert tax.calls == []


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
