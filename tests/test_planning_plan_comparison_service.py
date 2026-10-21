from copy import deepcopy
import json

from services.analytics_export_service import AnalyticsExportService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.planning_plan_comparison_service import PlanningPlanComparisonService
from services.saved_planning_plan_service import SavedPlanningPlanService
from services.sales_mix_planning_service import SalesMixPlanningService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_saved_planning_plan_runtime_service import TelegramSavedPlanningPlanRuntimeService
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
            "calculation_version": 1, "items": [item],
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


def test_equal_but_unsupported_calculation_versions_do_not_use_current_calculator():
    scenario = UnitPriceScenarioService(TaxService())
    sales_mix = SalesMixPlanningService(scenario, scenario.tax_service)
    calculate_calls = []
    calculate = sales_mix.calculate
    sales_mix.calculate = lambda *args, **kwargs: (
        calculate_calls.append((args, kwargs)) or calculate(*args, **kwargs)
    )
    service = PlanningPlanComparisonService(sales_mix)
    first = _document(1)
    second = _document(2, price="550")
    old_version = scenario.VERSION
    first["document"]["payload"]["calculation_version"] = old_version
    second["document"]["payload"]["calculation_version"] = old_version
    scenario.VERSION = old_version + 1

    result = service.compare(first, second)

    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "CALCULATION_VERSION_UNSUPPORTED"
    assert result["input_changes"][0]["changes"][0]["field"] == "price"
    assert result["recalculated_from_saved_inputs"] is False
    assert result["metrics"]["profit"]["status"] == "NOT_COMPARABLE"
    assert calculate_calls == []


def test_v2_plan_comparison_and_exports_include_frozen_cross_docking_evidence():
    scenario = UnitPriceScenarioService(TaxService())
    service = PlanningPlanComparisonService(SalesMixPlanningService(scenario, scenario.tax_service))
    exporter = AnalyticsExportService()

    def evidence(rate, expense):
        return {
            "evidence_complete": True, "rate_available": True,
            "status": "SKU_SUPPLY_PERIOD_AVERAGE", "reason": None,
            "method": "sku_accrual_cost_per_delivered_crossdock_unit",
            "amount_per_unit": rate, "applicable_to_sku": True,
            "denominator_kind": "DELIVERED_CROSSDOCK_UNITS",
            "expense_total": expense, "expense_by_sku": expense,
            "supplied_units_sku": 100, "supplied_units_store": 100,
            "days_complete": 56, "days_expected": 56,
            "date_from": "2026-08-24", "date_to": "2026-10-18",
            "as_of": "2026-10-19T12:00:00Z", "timezone": "Europe/Moscow",
            "financial_date_basis": "ACCRUAL_DATE",
            "supply_date_basis": "COMPLETED_SINGLE_CROSSDOCK_ORDER_STATE_UPDATED_DATE",
            "model_version": 1,
        }

    first, second = _document(1), _document(2)
    for document, rate, expense in ((first, "12.00", "1200.00"), (second, "14.00", "1400.00")):
        payload = document["document"]["payload"]
        payload["schema_version"] = 2
        payload["calculation_version"] = 2
        item = payload["items"][0]
        item["inputs"]["cross_docking_per_unit"] = rate
        item["sources"] = {"cross_docking": evidence(rate, expense)}
        item["projection"]["cross_docking"] = rate

    comparison = service.compare(first, second)

    assert comparison["status"] == "COMPARABLE"
    row = comparison["input_changes"][0]
    assert any(change["field"] == "cross_docking_per_unit" for change in row["changes"])
    assert row["cross_docking_source_before"]["supplied_units_sku"] == 100
    assert row["cross_docking_source_after"]["expense_total"] == "1400.00"
    exported = exporter.export_plan_comparison({"comparison": comparison}, "json")
    assert exported["error"] is False
    document = json.loads(exported["file_content"].decode("utf-8"))
    assert "cross_docking_source_before" in {column["key"] for column in document["columns"]}
    assert document["rows"][0]["cross_docking_source_after"]["denominator_kind"] == "DELIVERED_CROSSDOCK_UNITS"

    saved_export = exporter.export_saved_plan(first["document"], "json")
    assert saved_export["error"] is False
    saved = json.loads(saved_export["file_content"].decode("utf-8"))
    assert saved["rows"][0]["cross_docking_source"]["method"] == "sku_accrual_cost_per_delivered_crossdock_unit"


def test_expense_add_remove_rename_and_amount_changes_export_to_csv_and_json():
    scenario = UnitPriceScenarioService(TaxService())
    service = PlanningPlanComparisonService(SalesMixPlanningService(scenario, scenario.tax_service))
    exporter = AnalyticsExportService()
    variants = [
        ([{"name": "Packaging", "amount": "100.00"}],
         [{"name": "Packaging", "amount": "150.00"}],
         [{"name": "Packaging", "before": "100.00", "after": "150.00", "delta": "50.00"}]),
        ([{"name": "Packaging", "amount": "100.00"}], [],
         [{"name": "Packaging", "before": "100.00", "after": "0.00", "delta": "-100.00"}]),
        ([], [{"name": "New expense", "amount": "10.00"}],
         [{"name": "New expense", "before": "0.00", "after": "10.00", "delta": "10.00"}]),
        ([{"name": "Packaging", "amount": "100.00"}],
         [{"name": "Packing", "amount": "100.00"}],
         [
             {"name": "Packaging", "before": "100.00", "after": "0.00", "delta": "-100.00"},
             {"name": "Packing", "before": "0.00", "after": "100.00", "delta": "100.00"},
         ]),
    ]

    for index, (before_expenses, after_expenses, expected) in enumerate(variants):
        first = _document(1)
        second = _document(2)
        first["document"]["payload"]["sales_mix"]["expenses"] = before_expenses
        second["document"]["payload"]["sales_mix"]["expenses"] = after_expenses
        comparison = service.compare(first, second)
        assert comparison["error"] is False
        assert comparison["status"] == "COMPARABLE"
        assert comparison["expense_changes"] == expected

        for file_format in ("csv", "json"):
            exported = exporter.export_plan_comparison(
                {"comparison": comparison}, file_format,
            )
            assert exported["error"] is False, (index, file_format, exported)
            content = exported["file_content"].decode("utf-8")
            assert "expense_changes" in content
            if file_format == "json":
                document = json.loads(content)
                assert document["metadata"]["expense_changes"] == expected


def test_plan_comparison_screen_shows_expense_changes_instead_of_false_empty_state(tmp_path):
    scenario = UnitPriceScenarioService(TaxService())
    sales_mix = SalesMixPlanningService(scenario, scenario.tax_service)
    service = PlanningPlanComparisonService(sales_mix)
    first = _document(1)
    second = _document(2)
    first["document"]["payload"]["sales_mix"]["expenses"] = [
        {"name": "Packaging", "amount": "100.00"},
    ]
    second["document"]["payload"]["sales_mix"]["expenses"] = [
        {"name": "Packaging", "amount": "100.00"},
        {"name": "New expense", "amount": "10.00"},
    ]
    comparison = service.compare(first, second)
    runtime = TelegramSavedPlanningPlanRuntimeService(
        SavedPlanningPlanService(
            PlanningWorkspaceRepository(db_path=tmp_path / "expense-render.sqlite"), scenario,
        ), None, None, AssistantKeyboardService(), sales_mix_planning_service=sales_mix,
        plan_comparison_service=service,
    )
    tenant = set_current_tenant_user_id("owner-1::ozon::store-a")
    try:
        scope = runtime._scope("owner-1")
        generation = runtime.comparison_snapshot_store.begin_generation(
            "owner-1", "store-a", "plan_comparison",
        )["generation"]
        stored = runtime.comparison_snapshot_store.put_snapshot(
            "owner-1", "store-a", "plan_comparison", generation, 2,
            {"status": "HISTORICAL_ASSUMPTIONS"}, comparison["scope"],
            [{"row_id": "comparison", "comparison": comparison}],
        )
        screen = runtime._render_plan_comparison_snapshot(scope, stored["snapshot"])
    finally:
        reset_current_tenant_user_id(tenant)

    assert "Расход «New expense»: 0.00 → 10.00 ₽" in screen["message"]
    assert "Введённые параметры не изменились." not in screen["message"]


def test_plan_comparison_detail_pages_expose_every_change_and_added_sku_without_external_reads(tmp_path):
    scenario = UnitPriceScenarioService(TaxService())
    sales_mix = SalesMixPlanningService(scenario, scenario.tax_service)
    service = PlanningPlanComparisonService(sales_mix)
    first = _document(1)
    second = _document(2)
    first_payload = first["document"]["payload"]
    second_payload = second["document"]["payload"]
    first_payload["plan_kind"] = second_payload["plan_kind"] = "batch"
    first_items = []
    second_items = []
    for index in range(1, 4):
        left = deepcopy(first_payload["items"][0])
        left["row_id"] = f"row-{index}"
        left["identity"].update(
            product_id=f"product-{index}", offer_id=f"offer-{index}",
            sku=f"sku-{index}", product_name=f"Product {index}",
        )
        right = deepcopy(left)
        for field, _label in service.INPUT_FIELDS:
            before = right["inputs"].get(field)
            right["inputs"][field] = (
                "USN_REVENUE" if field == "tax_mode" and before != "USN_REVENUE"
                else "USN_INCOME" if field == "tax_mode"
                else str(before) + "1"
            )
        first_items.append(left)
        second_items.append(right)
    added = deepcopy(second_items[-1])
    added["row_id"] = "row-added"
    added["identity"].update(
        product_id="product-z", offer_id="offer-z", sku="sku-z",
        product_name="🧪" * 500,
    )
    second_items.append(added)
    first_payload["items"] = first_items
    second_payload["items"] = second_items
    first_payload["sales_mix"]["quantities"] = {f"row-{i}": 10 for i in range(1, 4)}
    second_payload["sales_mix"]["quantities"] = {f"row-{i}": 10 for i in range(1, 4)}
    comparison = service.compare(first, second)
    assert comparison["scope"]["row_count"] == 4

    runtime = TelegramSavedPlanningPlanRuntimeService(
        SavedPlanningPlanService(
            PlanningWorkspaceRepository(db_path=tmp_path / "comparison-pages.sqlite"), scenario,
        ), None, None, AssistantKeyboardService(), sales_mix_planning_service=sales_mix,
        plan_comparison_service=service,
    )
    tenant = set_current_tenant_user_id("owner-1::ozon::store-a")
    try:
        scope = runtime._scope("owner-1")
        generation = runtime.comparison_snapshot_store.begin_generation(
            "owner-1", "store-a", "plan_comparison",
        )["generation"]
        stored = runtime.comparison_snapshot_store.put_snapshot(
            "owner-1", "store-a", "plan_comparison", generation, 2,
            {"status": "HISTORICAL_ASSUMPTIONS"}, comparison["scope"],
            [{"row_id": "comparison", "comparison": comparison}],
        )
        screen = runtime._render_plan_comparison_snapshot(scope, stored["snapshot"])
        all_pages = [screen["message"]]
        callback_values = []
        while True:
            callback_values.extend(
                button["callback"] for button in screen["keyboard"]["buttons"]
                if isinstance(button.get("callback"), str)
            )
            next_button = next((
                button for button in screen["keyboard"]["buttons"]
                if button["text"] in {"Подробнее", "Следующая страница →"}
            ), None)
            if next_button is None:
                break
            screen = runtime.handle_callback(next_button["callback"], user_id="owner-1")
            all_pages.append(screen["message"])
    finally:
        reset_current_tenant_user_id(tenant)

    assert len(all_pages) == 5
    assert "SKU sku-z: добавлен во втором варианте" in all_pages[0]
    assert all("Изменения " in page for page in all_pages)
    assert all(len(page.encode("utf-16-le")) // 2 <= 3500 for page in all_pages)
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callback_values)
    assert all(label in "\n".join(all_pages) for _field, label in service.INPUT_FIELDS)
    assert "Введённые параметры не изменились." not in "\n".join(all_pages)
    assert comparison["external_reads"] == 0


def test_added_and_removed_skus_remain_visible_in_plan_comparison_screen_and_exports(tmp_path):
    scenario = UnitPriceScenarioService(TaxService())
    sales_mix = SalesMixPlanningService(scenario, scenario.tax_service)
    service = PlanningPlanComparisonService(sales_mix)
    exporter = AnalyticsExportService()

    first = _document(1)
    second = _document(2)
    first_doc = first["document"]
    second_doc = second["document"]
    first_doc["payload"]["plan_kind"] = "batch"
    second_doc["payload"]["plan_kind"] = "batch"
    removed = deepcopy(first_doc["payload"]["items"][0])
    removed["row_id"] = "row-2"
    removed["identity"].update(
        product_id="p2", offer_id="offer-2", sku="sku-2", product_name="Removed SKU",
    )
    added = deepcopy(second_doc["payload"]["items"][0])
    added["row_id"] = "row-3"
    added["identity"].update(
        product_id="p3", offer_id="offer-3", sku="sku-3", product_name="Added SKU",
    )
    first_doc["payload"]["items"].append(removed)
    second_doc["payload"]["items"].append(added)
    first_doc["payload"]["sales_mix"]["quantities"] = {"row-1": 10, "row-2": 7}
    second_doc["payload"]["sales_mix"]["quantities"] = {"row-1": 10, "row-3": 5}

    comparison = service.compare(first, second)
    assert comparison["status"] == "NOT_COMPARABLE"
    assert comparison["reason"] == "PRODUCT_SCOPE_MISMATCH"
    assert comparison["scope"]["row_count"] == 3
    assert comparison["scope"]["first_only"] == 1
    assert comparison["scope"]["second_only"] == 1
    assert all(value["status"] == "NOT_COMPARABLE" for value in comparison["metrics"].values())
    changed_rows = {
        (row["identity"]["sku"], row["scope_status"])
        for row in comparison["input_changes"] if row.get("scope_status")
    }
    assert changed_rows == {("sku-2", "REMOVED_FROM_SECOND"), ("sku-3", "ADDED_IN_SECOND")}

    tenant = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        plan_service = SavedPlanningPlanService(
            PlanningWorkspaceRepository(db_path=tmp_path / "comparison-render.sqlite"), scenario,
        )
        runtime = TelegramSavedPlanningPlanRuntimeService(
            plan_service, None, None, AssistantKeyboardService(),
            sales_mix_planning_service=sales_mix,
            plan_comparison_service=service,
        )
        scope = runtime._scope("user-1")
        screen = runtime._render_plan_comparison_snapshot(scope, {
            "snapshot_id": "snapshot", "generation": "generation", "version": 1,
            "rows": [{"row_id": "comparison", "comparison": comparison}],
        })
    finally:
        reset_current_tenant_user_id(tenant)
    assert "SKU sku-2: есть только в первом варианте" in screen["message"]
    assert "SKU sku-3: добавлен во втором варианте" in screen["message"]
    assert "Введённые параметры не изменились" not in screen["message"]

    for file_format in ("csv", "json"):
        exported = exporter.export_plan_comparison({"comparison": comparison}, file_format)
        assert exported["error"] is False
        content = exported["file_content"].decode("utf-8")
        assert "sku-2" in content and "sku-3" in content
        if file_format == "json":
            rows = json.loads(content)["rows"]
            assert exported["row_count"] == 3
            assert {row["scope_status"] for row in rows} == {
                "COMMON", "REMOVED_FROM_SECOND", "ADDED_IN_SECOND",
            }
            assert {row["sku"] for row in rows} == {"sku-1", "sku-2", "sku-3"}
