import json

from services.analytics_export_service import AnalyticsExportService
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.product_overview_service import ProductOverviewService
from services.scoped_transient_snapshot_store import ScopedTransientSnapshotStore
from services.tax_service import TaxService
from services.telegram_unit_price_batch_plan_runtime_service import (
    TelegramUnitPriceBatchPlanRuntimeService,
)
from services.telegram_unit_price_sensitivity_runtime_service import (
    TelegramUnitPriceSensitivityRuntimeService,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from services.unit_price_batch_plan_service import UnitPriceBatchPlanService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_sensitivity_service import UnitPriceSensitivityService
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService


class _OverviewQuery:
    def __init__(self):
        self.calls = 0
        self.rows = []

    def query_catalog_group(self, offset=0, limit=20):
        self.calls += 1
        rows = self.rows[offset:offset + limit]
        return {
            "error": False,
            "rows": rows,
            "selection_scope": {
                "mode": "FIRST_SORTED_CATALOG_GROUP",
                "sort_by": "offer_id_then_catalog_sku",
                "selected_count": len(rows),
                "catalog_identity_count": len(self.rows),
                "offset": offset,
                "has_previous_group": False,
                "has_next_group": False,
                "limit": limit,
            },
        }


class _PlanSource:
    def __init__(self):
        self.catalog_calls = 0
        self.snapshot_calls = []
        self.product_service = self

    def load_products(self):
        self.catalog_calls += 1
        return [
            {"product_id": "101", "offer_id": "offer-1", "sku": "sku-1", "scheme": "FBO"},
            {"product_id": "102", "offer_id": "offer-2", "sku": "sku-2", "scheme": "FBO"},
        ]

    def load_snapshot(
        self, sku, user_id, operation_trace=None,
        catalog_product=None, force_refresh=False,
    ):
        self.snapshot_calls.append((sku, user_id, force_refresh))
        reserved = operation_trace.reserve_ozon_request("acceptance_fake_snapshot")
        if reserved.get("error"):
            return reserved
        product = catalog_product or {}
        inputs = {
            "price": "500",
            "commission_rate": "15",
            "advertising_rate": "5",
            "discount_points_rate": "20",
            "logistics_per_unit": "40",
            "last_mile_per_unit": "10",
            "acquiring_per_unit": "5",
            "tax_mode": "USN_INCOME",
            "tax_rate": "6",
            "minimum_tax_rate": "1",
        }
        if sku == "sku-2":
            inputs["cost"] = "100"
        return {
            "error": False,
            "identity": {
                "user_id": user_id,
                "store_id": "store-1",
                "tenant_scope": "owner-1::ozon::store-1",
                "product_id": str(product["product_id"]),
                "offer_id": str(product["offer_id"]),
                "sku": sku,
            },
            "product": {"scheme": "FBO"},
            "suggested_inputs": inputs,
            "input_provenance": {"advertising_rate": "source", "cost": "missing"},
            "source_periods": {"seller_price_as_of": "2026-10-17T00:00:00Z"},
            "source_completeness": {"scheme": "FBO", "commission": {"complete": True}},
            "cache": {"status": "miss", "age_seconds": 1, "ttl_seconds": 600},
        }


def _overview_row(index, incomplete=False):
    offer_id = f"offer-{index}"
    sku = f"sku-{index}"
    missing_data = ["cost"] if incomplete else []
    return {
        "selector": offer_id,
        "identity": {
            "product_id": str(100 + index),
            "offer_id": offer_id,
            "catalog_sku": sku,
        },
        "status": "INCOMPLETE" if incomplete else "READY",
        "decision": {
            "error": False,
            "decision_type": "INSUFFICIENT_DATA" if incomplete else "INVESTIGATE_LOW_PROFIT",
            "priority": "NONE" if incomplete else "HIGH",
            "confidence": "LOW" if incomplete else "HIGH",
            "reasons": ["ECONOMICS_INCOMPLETE"] if incomplete else ["NEGATIVE_UNIT_PROFIT"],
            "missing_data": missing_data,
            "sales_velocity": 3.0,
            "sales_trend": "STABLE",
            "current_stock": 7,
            "days_of_stock": 2.3,
            "decision_profit_per_unit": None if incomplete else -4.5,
            "decision_margin_percent": None if incomplete else -2.0,
            "sales_observed_at": "2026-10-17T10:00:00Z",
            "sales_period_from": "2026-10-01",
            "sales_period_to": "2026-10-16",
            "stock_observed_at": "2026-10-17T10:00:00Z",
            "unit_economics_observed_at": "2026-10-17T10:00:00Z",
            "unit_economics_cache": {"status": "hit", "age_seconds": 1, "ttl_seconds": 600},
        },
    }


def _button(result, text):
    return next(item["callback"] for item in result["keyboard"]["buttons"] if item["text"] == text)


def _button_prefix(result, prefix):
    return next(item["callback"] for item in result["keyboard"]["buttons"] if item["callback"].startswith(prefix))


def test_overview_to_batch_edit_sensitivity_and_exports_stays_on_one_source_snapshot():
    query = _OverviewQuery()
    query.rows = [_overview_row(1, incomplete=True), _overview_row(2)]
    overview = ProductOverviewService(query, ScopedTransientSnapshotStore())
    keyboard = AssistantKeyboardService()
    source = _PlanSource()
    scenario = UnitPriceScenarioService(TaxService())
    batch_service = UnitPriceBatchPlanService(
        source,
        scenario,
        UnitPriceTargetPlanningService(scenario),
        tenant_scope_provider=lambda: "owner-1::ozon::store-1",
    )
    exports = AnalyticsExportService()
    batch_runtime = TelegramUnitPriceBatchPlanRuntimeService(
        batch_service,
        overview,
        keyboard,
        clock=lambda: 100,
        tenant_scope_provider=lambda: "owner-1::ozon::store-1",
        analytics_export_service=exports,
    )
    sensitivity = TelegramUnitPriceSensitivityRuntimeService(
        UnitPriceSensitivityService(scenario),
        single_price_runtime_service=None,
        batch_plan_runtime_service=batch_runtime,
        keyboard_service=keyboard,
        clock=lambda: 100,
        tenant_scope_provider=lambda: "owner-1::ozon::store-1",
        analytics_export_service=exports,
    )
    batch_runtime.sensitivity_runtime_service = sensitivity
    handler = AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=keyboard,
        product_overview_service=overview,
        unit_price_batch_plan_runtime_service=batch_runtime,
        unit_price_sensitivity_runtime_service=sensitivity,
        analytics_export_service=exports,
    )

    tenant = set_current_tenant_user_id("owner-1::ozon::store-1")
    try:
        first_overview = handler.handle("product_overview", user_id="owner-1")
        incomplete = handler.handle(
            _button(first_overview, "Пробелы данных"), user_id="owner-1"
        )
        assert "offer-1" in incomplete["message"]
        assert "offer-2" not in incomplete["message"]
        first_detail = handler.handle(
            _button_prefix(incomplete, "pov:d:"), user_id="owner-1"
        )
        first_added = handler.handle(
            _button(first_detail, "Добавить в план цен"), user_id="owner-1"
        )

        all_rows = handler.handle(
            _button(first_added, "К обзору"), user_id="owner-1"
        )
        second_detail = handler.handle(
            next(
                item["callback"] for item in all_rows["keyboard"]["buttons"]
                if item["callback"].startswith("pov:d:") and "offer-2" in item["text"]
            ),
            user_id="owner-1",
        )
        second_added = handler.handle(
            _button(second_detail, "Добавить в план цен"), user_id="owner-1"
        )
        assert "Выбрано товаров: 2" in second_added["message"]
        target_prompt = handler.handle("pov:bp", user_id="owner-1")
        assert target_prompt["status"] == "UNIT_PRICE_BATCH_TARGET_INPUT_REQUIRED"
        batch = handler.handle_text("20", user_id="owner-1")
        assert batch["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
        assert "нужно указать" in batch["message"].lower()

        row_menu = handler.handle(
            next(
                item["callback"] for item in batch["keyboard"]["buttons"]
                if item["text"].startswith("Изменить · offer-1")
            ),
            user_id="owner-1",
        )
        cost_prompt = handler.handle(
            _button(row_menu, "Себестоимость ₽/шт."), user_id="owner-1"
        )
        assert cost_prompt["status"] == "UNIT_PRICE_BATCH_INPUT_REQUIRED"
        edited = handler.handle_text("200", user_id="owner-1")
        assert edited["status"] == "UNIT_PRICE_BATCH_PLAN_READY"
        batch_json = handler.handle(
            _button(edited, "⬇️ JSON"), user_id="owner-1"
        )
        batch_document = json.loads(batch_json["file_content"].decode("utf-8"))
        assert batch_document["export_kind"] == "unit_price_batch"
        edited_input_rows = [
            row for row in batch_document["rows"]
            if row.get("sku") == "sku-1"
        ]
        assert edited_input_rows
        assert edited_input_rows[0]["manual_assumptions"]["cost"]["value"] == "200"

        sensitivity_prompt = handler.handle(
            next(
                item["callback"] for item in edited["keyboard"]["buttons"]
                if item["text"].startswith("Чувствительность · offer-1")
            ),
            user_id="owner-1",
        )
        values_prompt = handler.handle(
            _button(sensitivity_prompt, "Ось · Цена продавца"),
            user_id="owner-1",
        )
        sensitivity_report = handler.handle_text("500;550;600", user_id="owner-1")
        assert sensitivity_report["status"] == "UNIT_PRICE_SENSITIVITY_READY"
        sensitivity_csv = handler.handle(
            _button(sensitivity_report, "⬇️ CSV"), user_id="owner-1"
        )
        sensitivity_json = handler.handle(
            _button(sensitivity_report, "⬇️ JSON"), user_id="owner-1"
        )
        sensitivity_document = json.loads(
            sensitivity_json["file_content"].decode("utf-8")
        )

        assert values_prompt["status"] == "UNIT_PRICE_SENSITIVITY_VALUES_REQUIRED"
        assert sensitivity_csv["document_kind"] == "analytics_export"
        assert sensitivity_csv["mime_type"] == "text/csv"
        assert sensitivity_document["export_kind"] == "unit_price_sensitivity"
        assert len(sensitivity_document["rows"]) == 3
        assert query.calls == 1
        assert source.catalog_calls == 1
        assert len(source.snapshot_calls) == 2
        for result in (batch_json, sensitivity_csv, sensitivity_json):
            assert result["read_only"] is True
            assert result["executed"] is False
    finally:
        reset_current_tenant_user_id(tenant)
