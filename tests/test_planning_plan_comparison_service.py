from copy import deepcopy

from services.planning_plan_comparison_service import PlanningPlanComparisonService
from services.sales_mix_planning_service import SalesMixPlanningService
from services.tax_service import TaxService
from services.unit_price_scenario_service import UnitPriceScenarioService


def _document(revision, *, price="500", quantity=10, period="01.08.2026 - 31.08.2026", store="store-a"):
    scenario = UnitPriceScenarioService(TaxService())
    inputs = {
        "price": price, "cost": "150", "commission_rate": "20",
        "logistics_per_unit": "25", "last_mile_per_unit": "5",
        "acquiring_per_unit": "5", "advertising_rate": "10",
        "discount_points_rate": "20", "tax_mode": "USN_INCOME",
        "tax_rate": "6", "minimum_tax_rate": "1",
    }
    projection = scenario.calculate(inputs)
    item = {
        "row_id": "row-1",
        "identity": {"product_id": "p1", "offer_id": "offer-1", "sku": "sku-1", "product_name": "Test"},
        "inputs": inputs,
        "projection": {"available": projection.get("available"), "calculated": projection.get("calculated")},
    }
    return {"document": {
        "document_id": f"doc-{revision}", "title": f"Plan {revision}",
        "revision": revision, "owner_id": "owner-1", "store_id": store,
        "payload": {
            "plan_kind": "single", "schema_version": 1,
            "calculation_version": scenario.VERSION, "items": [item],
            "sales_mix": {
                "period_label": period, "quantities": {"row-1": quantity},
                "expenses": [{"name": "Packaging", "amount": "100.00"}],
                "confirmed": True,
            },
        },
    }}


def test_comparison_recomputes_only_compatible_historical_sales_mix_and_marks_margin_delta_pp():
    scenario = UnitPriceScenarioService(TaxService())
    service = PlanningPlanComparisonService(SalesMixPlanningService(scenario, scenario.tax_service))
    before = _document(1)
    after = _document(2, price="550", quantity=8)

    result = service.compare(before, after)

    assert result["error"] is False
    assert result["status"] == "COMPARABLE", result.get("reason")
    assert result["historical"] is True
    assert result["external_reads"] == 0
    assert result["input_changes"][0]["changes"]
    assert result["metrics"]["revenue"]["before"] == "5000.00"
    assert result["metrics"]["revenue"]["after"] == "4400.00"
    assert result["metrics"]["margin_percent"]["unit"] == "pp"
    assert result["expense_changes"] == []


def test_comparison_refuses_different_periods_but_keeps_visible_input_differences():
    scenario = UnitPriceScenarioService(TaxService())
    service = PlanningPlanComparisonService(SalesMixPlanningService(scenario, scenario.tax_service))

    result = service.compare(_document(1), _document(2, price="550", period="01.09.2026 - 30.09.2026"))

    assert result["status"] == "INPUTS_ONLY"
    assert result["reason"] == "PERIOD_MISMATCH"
    assert result["input_changes"]
    assert all(metric["status"] == "NOT_COMPARABLE" for metric in result["metrics"].values())


def test_comparison_rejects_cross_store_and_ambiguous_identity():
    scenario = UnitPriceScenarioService(TaxService())
    service = PlanningPlanComparisonService(SalesMixPlanningService(scenario, scenario.tax_service))
    cross_store = service.compare(_document(1), _document(2, store="store-b"))
    assert cross_store["error"] is True
    assert cross_store["code"] == "PLANNING_COMPARISON_SCOPE_MISMATCH"

    duplicate = _document(2)
    duplicate["document"]["payload"]["items"].append(
        deepcopy(duplicate["document"]["payload"]["items"][0])
    )
    result = service.compare(_document(1), duplicate)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "IDENTITY_INVALID_OR_AMBIGUOUS"


def test_calculation_version_mismatch_keeps_input_diff_without_recalculating_history():
    scenario = UnitPriceScenarioService(TaxService())
    service = PlanningPlanComparisonService(SalesMixPlanningService(scenario, scenario.tax_service))
    newer = _document(2, price="550")
    newer["document"]["payload"]["calculation_version"] += 1

    result = service.compare(_document(1), newer)

    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "CALCULATION_VERSION_MISMATCH"
    assert result["input_changes"][0]["changes"][0]["field"] == "price"
    assert result["recalculated_from_saved_inputs"] is False
    assert result["metrics"] == {
        name: {
            "status": "NOT_COMPARABLE", "before": None, "after": None,
            "delta": None, "reason": "CALCULATION_VERSION_MISMATCH",
        }
        for name in service.METRICS
    }
