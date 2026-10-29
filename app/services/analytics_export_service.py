"""Map finalized owner-visible snapshots into explicit export schemas."""

from copy import deepcopy
from datetime import date
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter

from services.analytics_export_serializer import AnalyticsExportSerializer
from services.period_profit_diagnostic_view_service import (
    PeriodProfitDiagnosticViewService,
)
from services.planning_cross_docking_adapter import PlanningCrossDockingAdapter
from services.unit_economics_experiment_snapshot_view_service import (
    UnitEconomicsExperimentSnapshotViewService,
)


class AnalyticsExportService:
    MAX_TARIFF_EXPORT_ROWS = 400
    SCENARIO_AMOUNT_FIELDS = (
        ("revenue", "revenue", "money"),
        ("discount_points", "discount_points", "money"),
        ("taxable_revenue", "taxable_revenue", "money"),
        ("commission", "commission", "money"),
        ("advertising", "advertising", "money"),
        ("fees", "fees", "money"),
        ("profit_before_tax", "profit_before_tax", "money"),
        ("tax", "tax", "money"),
        ("effective_tax_rate", "effective_tax_rate", "decimal"),
        ("profit", "profit", "money"),
        ("margin_percent", "margin_percent", "decimal"),
    )

    def __init__(self, serializer=None):
        self.serializer = serializer or AnalyticsExportSerializer()

    def export_period_profit(self, snapshot, file_format):
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        columns = self._period_columns()
        rows = []
        metrics = snapshot.get("comparison_metrics") or {}
        for name, metric in metrics.items():
            if not isinstance(metric, dict):
                continue
            rows.append(self._period_row(
                "comparison_metric", name,
                current_value=metric.get("current_value"),
                current_status=metric.get("current_status"),
                previous_value=metric.get("previous_value"),
                previous_status=metric.get("previous_status"),
                delta=metric.get("delta"),
                unit=metric.get("unit"),
                semantic="period_metric_delta",
            ))
        bridge = snapshot.get("profit_bridge") or {}
        for basis_name in ("B", "E"):
            basis = bridge.get(basis_name)
            if not isinstance(basis, dict):
                continue
            rows.append(self._period_row(
                "profit_bridge", f"{basis_name}.authoritative_delta",
                value=basis.get("authoritative_delta"),
                status=basis.get("status"), unit="RUB",
                semantic="authoritative_total",
            ))
            contributions = basis.get("contributions") or {}
            for key, value in contributions.items():
                rows.append(self._period_row(
                    "profit_bridge", f"{basis_name}.{key}", value=value,
                    status=basis.get("status"), unit="RUB",
                    semantic=self._bridge_semantic(key),
                ))
            detail = basis.get("net_accrual_detail") or {}
            for key, value in detail.items():
                if key == "status":
                    continue
                rows.append(self._period_row(
                    "profit_bridge", f"{basis_name}.net_accrual_detail.{key}",
                    value=value, status=detail.get("status"), unit="RUB",
                    semantic="reconciliation_component",
                ))

        sku = snapshot.get("sku_contribution") or {}
        if isinstance(sku, dict):
            for key in (
                "store_profit_delta", "matched_sku_profit_delta", "store_minus_sku_delta",
            ):
                if key in sku:
                    rows.append(self._period_row(
                        "sku_reconciliation", key, value=sku.get(key),
                        status=sku.get("reconciliation_status"), unit="RUB",
                        semantic="reconciliation_total_or_residual",
                    ))
            for key in (
                "matched_sku_count", "unmatched_current_count",
                "unmatched_previous_count", "ambiguous_identity_count", "invalid_row_count",
            ):
                if key in sku:
                    rows.append(self._period_row(
                        "sku_coverage", key, count=sku.get(key),
                        status=sku.get("coverage_status"), unit="rows",
                        semantic="coverage_count",
                    ))
            for list_name in ("top_growth", "top_decline"):
                entries = sku.get(list_name) or []
                for row in entries:
                    if not isinstance(row, dict):
                        continue
                    rows.append(self._period_row(
                        "top_sku_reference", list_name,
                        sku=row.get("sku"), value=row.get("delta"),
                        status=row.get("status"), unit="RUB",
                        semantic="top_k_reference_not_additive",
                    ))

        top_lists = sku if isinstance(sku, dict) else {}
        metadata = {
            "periods": deepcopy(snapshot.get("periods") or {}),
            "comparison_basis": snapshot.get("comparison_basis"),
            "comparison_status": snapshot.get("comparison_status"),
            "comparison_reason_code": snapshot.get("comparison_reason_code"),
            "coverage_status": snapshot.get("coverage_status"),
            "snapshot_generated_at": snapshot.get("generated_at"),
            "completeness": self._period_completeness_metadata(
                snapshot.get("completeness")
            ),
            "profit_bridge_semantics": {
                "authoritative_delta": "total",
                "contributions": "additive_components_with_rounding_adjustment",
                "net_accrual_detail": "decomposition_not_additional_to_net_accrual",
            },
            "sku_contribution": {
                "status": top_lists.get("status"),
                "coverage_status": top_lists.get("coverage_status"),
                "basis": top_lists.get("basis"),
                "reconciliation_status": top_lists.get("reconciliation_status"),
                "top_k_limit": 5,
                "top_growth_rows": len(top_lists.get("top_growth") or []),
                "top_decline_rows": len(top_lists.get("top_decline") or []),
                "unmatched_rows_are_zero": top_lists.get("unmatched_rows_are_zero"),
                "matched_sku_count": top_lists.get("matched_sku_count"),
                "unmatched_current_count": top_lists.get("unmatched_current_count"),
                "unmatched_previous_count": top_lists.get("unmatched_previous_count"),
                "ambiguous_identity_count": top_lists.get("ambiguous_identity_count"),
                "invalid_row_count": top_lists.get("invalid_row_count"),
            },
            "row_count": len(rows),
        }
        return self.serializer.serialize("period_profit", file_format, columns, rows, metadata)

    @staticmethod
    def _period_completeness_metadata(value):
        if not isinstance(value, dict):
            return None
        allowed_statuses = PeriodProfitDiagnosticViewService.ALLOWED_STATUS_CODES
        allowed_keys = PeriodProfitDiagnosticViewService.STATUS_KEYS
        raw_statuses = value.get("source_completeness")
        statuses = {}
        if isinstance(raw_statuses, dict):
            statuses = {
                key: status
                for key, status in raw_statuses.items()
                if key in allowed_keys
                and isinstance(status, str)
                and status in allowed_statuses
            }
        raw_reasons = value.get("reason_codes")
        reasons = list(dict.fromkeys(
            code for code in raw_reasons
            if isinstance(code, str)
            and code in PeriodProfitDiagnosticViewService.REASON_LABELS
        )) if isinstance(raw_reasons, (list, tuple)) else []
        date_from = value.get("date_from")
        date_to = value.get("date_to")
        if not (
            AnalyticsExportService._is_iso_date(date_from)
            and AnalyticsExportService._is_iso_date(date_to)
            and date_from <= date_to
        ):
            date_from = None
            date_to = None
        status = value.get("status")
        if not isinstance(status, str) or status not in {
            "CONFIRMED", "PARTIAL", "UNKNOWN", "UNAVAILABLE"
        }:
            status = "UNKNOWN"
        return {
            "date_from": date_from,
            "date_to": date_to,
            "status": status,
            "source_completeness": statuses,
            "reason_codes": reasons,
        }

    @staticmethod
    def _is_iso_date(value):
        if not isinstance(value, str) or len(value) != 10:
            return False
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False

    def export_product_overview(self, snapshot_result, file_format):
        if not isinstance(snapshot_result, dict) or snapshot_result.get("error") is True:
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        columns = [
            self._column("selector", "Запрошенный товар", "text"),
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU каталога", "text"),
            self._column("status", "Полнота", "status"),
            self._column("error", "Причина недоступности", "status"),
            self._column("decision_type", "Тип решения", "status"),
            self._column("priority", "Приоритет", "status"),
            self._column("confidence", "Уверенность", "status"),
            self._column("reasons", "Причины решения", "text"),
            self._column("missing_data", "Недостающие данные", "text"),
            self._column("sales_velocity", "Скорость продаж", "decimal", "шт./день"),
            self._column("sales_trend", "Тренд продаж", "text"),
            self._column("current_stock", "Остаток", "decimal", "шт."),
            self._column("days_of_stock", "Дни запаса", "decimal", "дн."),
            self._column("stock_priority", "Приоритет остатка", "status"),
            self._column("decision_profit_per_unit", "Расчётная прибыль с единицы", "money", "RUB/шт.", "model_estimate"),
            self._column("decision_margin_percent", "Расчётная маржа", "decimal", "%", "model_estimate"),
            self._column("source_freshness", "Свежесть источников", "json"),
        ]
        rows = []
        for row in snapshot_result.get("rows") or []:
            if not isinstance(row, dict):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            identity = row.get("identity") or {}
            decision = row.get("decision") or {}
            metrics = row.get("metrics") or {}
            values = {key: (metrics.get(key) or {}).get("value") for key in (
                "sales_velocity", "sales_trend", "current_stock", "days_of_stock",
                "stock_priority", "decision_profit_per_unit", "decision_margin_percent",
            )}
            rows.append({
                "selector": row.get("selector"),
                "product_id": identity.get("product_id"),
                "offer_id": identity.get("offer_id"),
                "sku": identity.get("catalog_sku"),
                "status": row.get("status"),
                "error": row.get("error"),
                "decision_type": decision.get("decision_type"),
                "priority": decision.get("priority"),
                "confidence": decision.get("confidence"),
                "reasons": "; ".join(str(item) for item in decision.get("reasons") or []),
                "missing_data": "; ".join(str(item) for item in row.get("missing_data") or []),
                **values,
                "source_freshness": deepcopy(row.get("source_freshness") or {}),
            })
        pagination = snapshot_result.get("pagination") or {}
        coverage = deepcopy(snapshot_result.get("coverage") or {})
        selection_scope = coverage.get("selection_scope") or {}
        metadata = {
            "snapshot_kind": "product_overview",
            "snapshot_captured_at": (snapshot_result.get("source_freshness") or {}).get("captured_at"),
            "active_filter": pagination.get("filter"),
            "active_sort": pagination.get("sort_by"),
            "sort_direction": pagination.get("direction"),
            "exported_scope": "all_rows_in_selected_snapshot_scope_after_active_filter",
            "coverage": coverage,
            "selection_scope": selection_scope,
            "snapshot_scope_rows": pagination.get("scope_rows"),
            "filtered_row_count": pagination.get("total_rows"),
            "exported_row_count": len(rows),
        }
        return self.serializer.serialize("product_overview", file_format, columns, rows, metadata)

    def export_unit_price_batch(self, batch, file_format, active_sort="selection"):
        if not isinstance(batch, dict) or batch.get("kind") != "UNIT_PRICE_BATCH_PLAN":
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        columns, rows = self._plan_columns_and_rows(batch.get("rows") or [])
        if isinstance(rows, dict):
            return rows
        metadata = {
            "plan_status": "PLANNED",
            "sale_basis": "one_successful_sale",
            "fulfillment_estimate": "FBO",
            "target_margin_percent": batch.get("target_margin_percent"),
            "selected_row_count": batch.get("rows_selected"),
            "attempted_row_count": batch.get("rows_attempted"),
            "completed_row_count": batch.get("rows_completed"),
            "evaluation_count": batch.get("evaluation_count"),
            "evaluation_limit": batch.get("evaluation_limit"),
            "active_sort": active_sort,
            "exported_scope": "all_rows_in_exact_batch_snapshot",
            "source_freshness_status": batch.get("source_freshness_status"),
            "source_stale_row_count": batch.get("source_stale_row_count"),
            "freshness_checked_at_export": batch.get("freshness_checked_at_export") is True,
            "source_warning": "Plan is not a forecast of demand or total store profit.",
        }
        return self.serializer.serialize("unit_price_batch", file_format, columns, rows, metadata)

    def export_unit_price_sensitivity(self, result, context, file_format, freshness=None):
        if not isinstance(result, dict) or result.get("kind") != "UNIT_PRICE_SENSITIVITY":
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        freshness = deepcopy(freshness) if isinstance(freshness, dict) else {
            "freshness_status": "UNCHECKED",
            "reason": "NOT_CHECKED_AT_EXPORT",
            "source_age_seconds_at_check": None,
            "source_ttl_seconds": None,
            "freshness_checked": False,
            "transfer_allowed": False,
        }
        freshness_status = freshness.get("freshness_status") or "UNCHECKED"
        freshness_reason = freshness.get("reason")
        fresh = freshness_status == "CURRENT" and freshness.get("transfer_allowed") is True
        origin = (context or {}).get("origin") or {}
        identity = (context or {}).get("identity") or {}
        columns = [
            self._column("sku", "SKU каталога", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("cell_number", "Номер ячейки", "integer"),
            self._column("coordinates", "Параметры ячейки", "json"),
            self._column("status", "Статус", "status"),
            self._column("snapshot_status", "Статус расчёта в исходном снимке", "status"),
            self._column("source_freshness_status", "Свежесть исходного плана", "status"),
            self._column("source_staleness_reason", "Причина устаревания", "status"),
            self._column("transfer_allowed", "Перенос сценария разрешён", "boolean"),
            self._column("inputs", "Допущения", "json"),
            self._column("provenance", "Источники допущений", "json"),
            self._column("commission_rate", "Комиссия Ozon", "decimal", "%"),
            self._column("commission_origin", "Источник ставки комиссии", "status"),
            self._column("tariff_status", "Статус тарифа для цены", "status"),
            self._column("tariff_reason", "Причина недоступности тарифа", "status"),
            *[self._column("calc_" + key, label, kind, unit)
              for key, label, kind, unit in self._calculation_columns()],
            self._column("target_reached", "Цель достигнута", "boolean"),
        ]
        rows = []
        for index, cell in enumerate(result.get("cells") or [], start=1):
            scenario = cell.get("scenario") or {}
            calculated = scenario.get("calculated") or {}
            row_status = cell.get("status")
            if row_status == "AVAILABLE" and not fresh:
                row_status = (
                    "SOURCE_STALE"
                    if freshness_status == "STALE"
                    else "SOURCE_FRESHNESS_UNCHECKED"
                )
            tariff = cell.get("tariff_resolution") or {}
            inputs = cell.get("inputs") or {}
            rows.append({
                "sku": identity.get("catalog_sku") or identity.get("sku"),
                "offer_id": identity.get("offer_id"),
                "cell_number": index,
                "coordinates": deepcopy(cell.get("coordinates") or {}),
                "status": row_status,
                "snapshot_status": cell.get("status"),
                "source_freshness_status": freshness_status,
                "source_staleness_reason": freshness_reason,
                "transfer_allowed": fresh and cell.get("status") == "AVAILABLE",
                "inputs": deepcopy(inputs),
                "provenance": deepcopy(cell.get("provenance") or {}),
                "commission_rate": tariff.get("commission_rate", inputs.get("commission_rate")),
                "commission_origin": tariff.get("origin") or (cell.get("provenance") or {}).get("commission_rate"),
                "tariff_status": tariff.get("status"),
                "tariff_reason": tariff.get("reason"),
                **{"calc_" + key: calculated.get(key) for key, _label, _kind, _unit in self._calculation_columns()},
                "target_reached": cell.get("target_reached"),
            })
        metadata = {
            "plan_status": "PLANNED",
            "sale_basis": "one_successful_sale",
            "fulfillment_estimate": "FBO",
            "origin_kind": origin.get("kind"),
            "axes": deepcopy(result.get("axes") or {}),
            "source_as_of": deepcopy(result.get("source_as_of") or {}),
            "target_margin_percent": result.get("target_margin_percent"),
            "tariff_scope": result.get("tariff_scope"),
            "cell_count": result.get("cell_count"),
            "available_cell_count": result.get("available_cell_count"),
            "best_checked_cell_id": result.get("best_checked_cell_id"),
            "worst_checked_cell_id": result.get("worst_checked_cell_id"),
            "best_worst_basis": result.get("best_worst_basis"),
            "exported_scope": "all_cells_in_exact_sensitivity_snapshot",
            "source_freshness_status": freshness_status,
            "source_staleness_reason": freshness_reason,
            "source_age_seconds_at_export": freshness.get("source_age_seconds_at_check"),
            "source_ttl_seconds": freshness.get("source_ttl_seconds"),
            "freshness_checked_at_export": freshness.get("freshness_checked") is True,
            "transfer_allowed": fresh,
            "source_warning": "This is a one-sale estimate, not a demand forecast or total store profit.",
        }
        return self.serializer.serialize("unit_price_sensitivity", file_format, columns, rows, metadata)

    def export_plan_fact_comparison(self, snapshot_row, file_format):
        """Export exactly the visible immutable plan/fact comparison snapshot."""
        if not isinstance(snapshot_row, dict):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        comparison = snapshot_row.get("comparison")
        if (
            not isinstance(comparison, dict)
            or comparison.get("comparison_version") != 1
            or not isinstance(comparison.get("rows"), list)
        ):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        columns = [
            self._column("row_id", "ID строки", "text"),
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU каталога", "text"),
            self._column("quantity_status", "Статус фактического количества", "status"),
            self._column("plan_quantity", "Количество по плану", "integer", "шт."),
            self._column("actual_quantity", "Фактическое количество", "integer", "шт."),
            self._column("plan_price_per_unit", "Цена плана", "money", "RUB/шт."),
            self._column("plan_revenue", "Выручка плана", "money", "RUB"),
            self._column("actual_revenue", "Фактическая выручка", "money", "RUB"),
            self._column("revenue_delta", "Разница выручки", "money", "RUB"),
            self._column("quantity_effect", "Арифметический эффект количества", "money", "RUB"),
            self._column("actual_average_revenue_effect", "Остаток по фактической выручке на единицу", "money", "RUB"),
            self._column("actual_average_revenue_per_unit", "Фактическая выручка на единицу", "money", "RUB/шт."),
            self._column("actual_components", "Фактические компоненты", "json"),
        ]
        rows = []
        for row in comparison["rows"]:
            if not isinstance(row, dict) or not isinstance(row.get("identity"), dict):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            identity = row["identity"]
            rows.append({
                "row_id": row.get("row_id"),
                "product_id": identity.get("product_id"),
                "offer_id": identity.get("offer_id"),
                "sku": identity.get("sku"),
                "quantity_status": row.get("quantity_status"),
                "plan_quantity": row.get("plan_quantity"),
                "actual_quantity": row.get("actual_quantity"),
                "plan_price_per_unit": row.get("plan_price_per_unit"),
                "plan_revenue": row.get("plan_revenue"),
                "actual_revenue": row.get("actual_revenue"),
                "revenue_delta": row.get("revenue_delta"),
                "quantity_effect": row.get("quantity_effect"),
                "actual_average_revenue_effect": row.get("actual_average_revenue_effect"),
                "actual_average_revenue_per_unit": row.get("actual_average_revenue_per_unit"),
                "actual_components": deepcopy(row.get("actual_components") or {}),
            })
        metadata = {
            "document_kind": "saved_plan_fact_snapshot",
            "plan_title": snapshot_row.get("document_title"),
            "plan_document_id": snapshot_row.get("document_id"),
            "plan_revision": snapshot_row.get("revision"),
            "comparison_version": comparison.get("comparison_version"),
            "generated_at_utc": comparison.get("generated_at_utc"),
            "plan": deepcopy(comparison.get("plan") or {}),
            "actual": deepcopy(comparison.get("actual") or {}),
            "revenue_comparison": deepcopy(comparison.get("revenue_comparison") or {}),
            "coverage": deepcopy(comparison.get("coverage") or {}),
            "exported_scope": "all_rows_in_exact_saved_plan_fact_snapshot",
            "historical_semantics": "export reads the already-built immutable comparison; it does not refresh Ozon",
        }
        return self.serializer.serialize(
            "plan_fact_comparison", file_format, columns, rows, metadata,
        )

    def export_saved_plan(self, document, file_format, *, sales_mix_projection=None):
        """Export all rows from one owner-scoped historical document revision."""
        if not isinstance(document, dict) or not isinstance(document.get("payload"), dict):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        payload = document["payload"]
        items = payload.get("items")
        if not isinstance(items, list) or len(items) > 10:
            return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
        columns = [
            self._column("row_id", "ID строки", "text"),
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU каталога", "text"),
            self._column("calculation_status", "Статус расчёта", "status"),
            self._column("missing_inputs", "Недостающие поля", "json"),
            self._column("inputs", "Допущения", "json"),
            self._column("provenance", "Происхождение допущений", "json"),
            self._column("commission_rate", "Комиссия Ozon", "decimal", "%"),
            self._column("commission_origin", "Источник комиссии", "status"),
            self._column("tariff_scope", "Область тарифа", "status"),
            self._column("tariff_status", "Статус тарифа", "status"),
            self._column("tariff_reason", "Причина ограничения тарифа", "status"),
            self._column("tariff_effective_date", "Дата тарифа", "text"),
            self._column("tariff_price_basis", "Основа тарифной цены", "status"),
            self._column("projection", "Сохранённая проекция", "json"),
            self._column("sales_quantity", "Подтверждённое количество", "integer", "шт."),
        ]
        cross_docking_enabled = PlanningCrossDockingAdapter.is_current(payload)
        if cross_docking_enabled:
            columns.append(self._column("cross_docking_source", "Источник кросс-докинга", "json"))
        mix = payload.get("sales_mix")
        quantities = mix.get("quantities") if isinstance(mix, dict) else {}
        rows = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            identity = item["identity"]
            row_id = str(item.get("row_id") or identity.get("sku") or "")
            projection = deepcopy(item.get("projection") or {})
            row = {
                "row_id": row_id,
                "product_id": identity.get("product_id"),
                "offer_id": identity.get("offer_id"),
                "sku": identity.get("sku"),
                "calculation_status": projection.get("status") or item.get("status") or "HISTORICAL",
                "missing_inputs": deepcopy(projection.get("missing_inputs") or []),
                "inputs": deepcopy(item.get("inputs") or {}),
                "provenance": deepcopy(item.get("provenance") or {}),
                **self._unit_price_tariff_export_fields(item),
                "projection": projection,
                "sales_quantity": quantities.get(row_id) if isinstance(quantities, dict) else None,
            }
            if cross_docking_enabled:
                row["cross_docking_source"] = deepcopy(
                    (item.get("sources") or {}).get("cross_docking")
                )
            rows.append(row)
        metadata = {
            "document_kind": "saved_planning_plan",
            "document_id": document.get("document_id"),
            "title": document.get("title"),
            "revision": document.get("revision"),
            "current_revision": document.get("current_revision"),
            "status": document.get("status"),
            "plan_kind": payload.get("plan_kind"),
            "schema_version": payload.get("schema_version"),
            "calculation_version": payload.get("calculation_version"),
            "store_scope": document.get("store_id"),
            "source_freshness": "HISTORICAL_ASSUMPTIONS",
            "recalculated_on_export": False,
            "sales_mix_period": mix.get("period_label") if isinstance(mix, dict) else None,
            "sales_mix_confirmed": mix.get("confirmed") if isinstance(mix, dict) else None,
            "sales_mix_projection": deepcopy(sales_mix_projection),
            "exported_scope": "all_rows_in_exact_saved_revision",
        }
        return self.serializer.serialize("saved_plan", file_format, columns, rows, metadata)

    def export_advertising_cap(self, document, caps, file_format):
        if not isinstance(document, dict) or not isinstance(caps, list) or len(caps) > 10:
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        payload = document.get("payload") or {}
        cross_docking_enabled = PlanningCrossDockingAdapter.is_current(payload)
        columns = [
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU каталога", "text"),
            self._column("status", "Статус расчёта", "status"),
            self._column("target_margin_percent", "Целевая маржа", "decimal", "%"),
            self._column("break_even_rate", "Реклама безубыточности", "decimal", "%"),
            self._column("break_even_per_unit", "Реклама безубыточности", "money", "RUB/шт."),
            self._column("target_rate", "Реклама для цели", "decimal", "%"),
            self._column("target_per_unit", "Расход на рекламу для цели", "money", "RUB/шт."),
            self._column("commission_rate", "Комиссия Ozon", "decimal", "%"),
            self._column("commission_origin", "Источник комиссии", "status"),
            self._column("tariff_scope", "Область тарифа", "status"),
            self._column("tariff_status", "Статус тарифа", "status"),
            self._column("tariff_reason", "Причина ограничения тарифа", "status"),
            self._column("tariff_effective_date", "Дата тарифа", "text"),
            self._column("tariff_price_basis", "Основа тарифной цены", "status"),
            self._column("inputs", "Сохранённые допущения", "json"),
        ]
        if cross_docking_enabled:
            columns.append(self._column("cross_docking_source", "Источник кросс-докинга", "json"))
        rows = []
        for item in caps:
            if not isinstance(item, dict):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            row = {
                "product_id": item.get("product_id"), "offer_id": item.get("offer_id"),
                "sku": item.get("sku"), "status": item.get("status"),
                "target_margin_percent": item.get("target_margin_percent"),
                "break_even_rate": item.get("break_even_rate"),
                "break_even_per_unit": item.get("break_even_per_unit"),
                "target_rate": item.get("target_rate"),
                "target_per_unit": item.get("target_per_unit"),
                "inputs": deepcopy(item.get("inputs") or {}),
                **self._unit_price_tariff_export_fields(item),
            }
            if cross_docking_enabled:
                row["cross_docking_source"] = deepcopy(item.get("cross_docking_source"))
            rows.append(row)
        metadata = {
            "document_id": document.get("document_id"), "revision": document.get("revision"),
            "calculation_version": (document.get("payload") or {}).get("calculation_version"),
            "target_margin_percent": (document.get("payload") or {}).get("target_margin_percent"),
            "source_freshness": "HISTORICAL_ASSUMPTIONS",
            "external_reads": 0, "exported_scope": "all_rows_in_exact_saved_revision",
        }
        return self.serializer.serialize("advertising_cap", file_format, columns, rows, metadata)

    def export_sales_mix(self, document, projection, file_format):
        if (not isinstance(document, dict) or not isinstance(projection, dict)
                or projection.get("kind") != "SALES_MIX_ECONOMICS"):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        payload = document.get("payload") or {}
        mix = payload.get("sales_mix") or {}
        projected = {str(row.get("row_id")): row for row in projection.get("rows") or []
                     if isinstance(row, dict)}
        excluded = {str(row.get("row_id")): row for row in projection.get("excluded_rows") or []
                    if isinstance(row, dict)}
        columns = [
            self._column("row_id", "ID строки", "text"),
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU каталога", "text"),
            self._column("status", "Статус строки", "status"),
            self._column("quantity", "Успешные продажи", "integer", "шт."),
            self._column("price_per_unit", "Цена плана", "money", "RUB/шт."),
            self._column("commission_rate", "Комиссия Ozon", "decimal", "%"),
            self._column("commission_origin", "Источник комиссии", "status"),
            self._column("tariff_scope", "Область тарифа", "status"),
            self._column("tariff_status", "Статус тарифа", "status"),
            self._column("tariff_reason", "Причина ограничения тарифа", "status"),
            self._column("tariff_effective_date", "Дата тарифа", "text"),
            self._column("tariff_price_basis", "Основа тарифной цены", "status"),
            self._column("components", "Компоненты строки", "json"),
            self._column("exclusion_reason", "Причина исключения", "status"),
        ]
        cross_docking_enabled = PlanningCrossDockingAdapter.is_current(payload)
        if cross_docking_enabled:
            columns.append(self._column("cross_docking_source", "Источник кросс-докинга", "json"))
        rows = []
        for item in payload.get("items") or []:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            identity = item["identity"]
            row_id = str(item.get("row_id") or identity.get("sku") or "")
            projected_row = projected.get(row_id)
            excluded_row = excluded.get(row_id)
            row = {
                "row_id": row_id, "product_id": identity.get("product_id"),
                "offer_id": identity.get("offer_id"), "sku": identity.get("sku"),
                "status": "INCLUDED" if projected_row else "EXCLUDED" if excluded_row else "UNKNOWN",
                "quantity": projected_row.get("quantity") if projected_row else mix.get("quantities", {}).get(row_id),
                "price_per_unit": projected_row.get("price_per_unit") if projected_row else None,
                **self._unit_price_tariff_export_fields(item),
                "components": deepcopy(projected_row.get("components") or {}) if projected_row else None,
                "exclusion_reason": excluded_row.get("reason") if excluded_row else None,
            }
            if cross_docking_enabled:
                row["cross_docking_source"] = deepcopy(
                    (item.get("sources") or {}).get("cross_docking")
                )
            rows.append(row)
        metadata = {
            "document_id": document.get("document_id"), "revision": document.get("revision"),
            "calculation_version": payload.get("calculation_version"),
            "period": projection.get("period"), "quantity_status": "EXPLICIT_OR_UNKNOWN_PER_ROW",
            "total_quantity": projection.get("total_quantity"),
            "components": deepcopy(projection.get("components") or {}),
            "fixed_expenses": deepcopy(projection.get("fixed_expenses") or []),
            "fixed_expense_total": projection.get("fixed_expense_total"),
            "tax": projection.get("tax"), "tax_status": projection.get("tax_status"),
            "profit": projection.get("profit"), "margin_percent": projection.get("margin_percent"),
            "coverage_complete": projection.get("coverage_complete"),
            "source_freshness": "HISTORICAL_ASSUMPTIONS", "recalculated_on_export": True,
            "exported_scope": "all_rows_in_exact_saved_revision",
        }
        return self.serializer.serialize("sales_mix", file_format, columns, rows, metadata)

    def export_unit_price_comparison(self, opened, file_format):
        """Export the exact persisted comparison revision without internal IDs."""
        payload = opened.get("payload") if isinstance(opened, dict) else None
        ranking = payload.get("ranking") if isinstance(payload, dict) else None
        identity = payload.get("identity") if isinstance(payload, dict) else None
        references = payload.get("source_references") if isinstance(payload, dict) else None
        if (not isinstance(opened, dict) or opened.get("error") is True
                or not isinstance(payload, dict) or payload.get("schema_version") != 1
                or not isinstance(ranking, dict) or not isinstance(identity, dict)
                or not isinstance(references, list) or len(references) > 10
                or type(opened.get("revision")) is not int
                or type(opened.get("latest_revision")) is not int):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        safe_identity = self._unit_price_identity(identity)
        if safe_identity is None:
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        source_versions = {}
        for reference in references:
            if (not isinstance(reference, dict) or type(reference.get("index")) is not int
                    or type(reference.get("result_revision")) is not int
                    or type(reference.get("source_document_revision")) is not int
                    or reference["index"] in source_versions):
                return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
            source_versions[reference["index"]] = {
                "observation_result_revision": reference["result_revision"],
                "saved_plan_revision": reference["source_document_revision"],
            }
        quality = ranking.get("quality_assessment")
        quality = quality if isinstance(quality, dict) else {}
        common = {
            "comparison_revision": opened["revision"],
            "freshness_status": opened.get("freshness_status"),
            **safe_identity,
            "ranking_status": ranking.get("status"),
            "evidence_basis": ranking.get("evidence_basis"),
            "display_basis": ranking.get("display_basis"),
            "verified": ranking.get("verified") is True,
            "quality_status": quality.get("status"),
            "quality_reasons": self._safe_codes(quality.get("reasons")),
            "quality_warnings": self._safe_codes(quality.get("warnings")),
            "omitted_candidate_count": ranking.get("omitted_candidate_count", 0),
            "omitted_repeated_price_count": ranking.get("omitted_repeated_price_count", 0),
            "best_profit_per_unit": ranking.get("best_profit_per_unit"),
        }
        columns = [
            self._column("comparison_revision", "Версия сравнения", "integer"),
            self._column("freshness_status", "Актуальность сохранённой версии", "status"),
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU", "text"),
            self._column("store_id", "Магазин", "text"),
            self._column("sale_schema", "Схема продаж", "status"),
            self._column("ranking_status", "Статус сравнения", "status"),
            self._column("evidence_basis", "Основание результата", "status"),
            self._column("display_basis", "Основание отображения", "status"),
            self._column("verified", "Результат подтверждён", "boolean"),
            self._column("candidate_index", "Индекс варианта", "integer"),
            self._column("result_revision", "Версия наблюдения", "integer"),
            self._column("saved_plan_revision", "Версия исходного плана", "integer"),
            self._column("ranking_position", "Место среди проверенных", "integer"),
            self._column("seller_price", "Цена продавца", "money", "RUB"),
            self._column("profit_per_unit", "Прибыль на единицу", "money", "RUB/шт."),
            self._column("delta_vs_baseline", "Изменение к базе", "money", "RUB/шт."),
            self._column("delta_percent_vs_baseline", "Изменение к базе", "decimal", "%"),
            self._column("is_best", "Максимум среди проверенных", "boolean"),
            self._column("best_profit_per_unit", "Максимальная прибыль", "money", "RUB/шт."),
            self._column("quality_status", "Статус качества данных", "status"),
            self._column("quality_reasons", "Причины ограничения", "json"),
            self._column("quality_warnings", "Предупреждения", "json"),
            self._column("omitted_candidate_count", "Не проверено вариантов", "integer"),
            self._column("omitted_repeated_price_count", "Повторных цен исключено", "integer"),
        ]
        rank_rows = ranking.get("ranking")
        if not isinstance(rank_rows, list) or len(rank_rows) > 10:
            return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
        rows = []
        for position, candidate in enumerate(rank_rows, start=1):
            if not isinstance(candidate, dict) or type(candidate.get("index")) is not int:
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            versions = source_versions.get(candidate["index"])
            if versions is None:
                return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
            rows.append({
                **common,
                "candidate_index": candidate["index"],
                "result_revision": versions["observation_result_revision"],
                "saved_plan_revision": versions["saved_plan_revision"],
                "ranking_position": position,
                "seller_price": self._cents_money(candidate.get("seller_price_cents")),
                "profit_per_unit": candidate.get("profit_per_unit"),
                "delta_vs_baseline": candidate.get("delta_vs_baseline"),
                "delta_percent_vs_baseline": candidate.get("delta_percent_vs_baseline"),
                "is_best": candidate.get("is_best") is True,
            })
        if not rows:
            rows.append({
                **common, "candidate_index": None, "result_revision": None,
                "saved_plan_revision": None, "ranking_position": None,
                "seller_price": None, "profit_per_unit": None,
                "delta_vs_baseline": None, "delta_percent_vs_baseline": None,
                "is_best": False,
            })
        metadata = {
            "comparison_revision": opened["revision"],
            "latest_revision": opened["latest_revision"],
            "freshness_status": opened.get("freshness_status"),
            "identity": safe_identity,
            "ranking_status": ranking.get("status"),
            "evidence_basis": ranking.get("evidence_basis"),
            "display_basis": ranking.get("display_basis"),
            "verified": ranking.get("verified") is True,
            "baseline_index": ranking.get("baseline_index"),
            "checked_candidate_count": ranking.get("checked_candidate_count", 0),
            "best_profit_per_unit": ranking.get("best_profit_per_unit"),
            "quality_status": quality.get("status"),
            "quality_reasons": self._safe_codes(quality.get("reasons")),
            "quality_warnings": self._safe_codes(quality.get("warnings")),
            "omitted_candidate_count": ranking.get("omitted_candidate_count", 0),
            "omitted_repeated_price_count": ranking.get("omitted_repeated_price_count", 0),
            "source_versions": [
                {"candidate_index": index, **source_versions[index]}
                for index in sorted(source_versions)
            ],
            "source_reads": False,
            "recalculated_on_export": False,
        }
        return self.serializer.serialize(
            "unit_price_comparison", file_format, columns, rows, metadata,
        )

    def export_unit_price_observation(self, loaded, quality, file_format):
        """Export one exact immutable observation-result revision."""
        observation = loaded.get("observation") if isinstance(loaded, dict) else None
        result_record = loaded.get("result") if isinstance(loaded, dict) else None
        result = result_record.get("payload") if isinstance(result_record, dict) else None
        identity = observation.get("identity") if isinstance(observation, dict) else None
        if (not isinstance(observation, dict) or not isinstance(result_record, dict)
                or not isinstance(result, dict) or result.get("schema_version") != 1
                or type(result_record.get("revision")) is not int
                or not isinstance(identity, dict) or not isinstance(quality, dict)):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        result_identity = result.get("identity") if isinstance(result.get("identity"), dict) else {}
        safe_identity = self._unit_price_identity({
            **identity,
            "store_id": observation.get("store_id"),
            "sale_schema": identity.get("sale_schema") or result_identity.get("sale_schema"),
        })
        if safe_identity is None:
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        window = result.get("window") if isinstance(result.get("window"), dict) else {}
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        completeness = result.get("completeness") if isinstance(result.get("completeness"), dict) else {}
        metric_keys = (
            "gross_seller_revenue", "discount_points", "net_seller_revenue",
            "attributed_revenue", "finance_net", "acquiring", "commission",
            "logistics", "other_fees", "cpc_spend", "seller_revenue_drr_percent",
            "attributed_revenue_drr_percent", "successful_sale_units",
            "weighted_ad_spend_numerator", "successful_unit_denominator",
            "source_row_count", "duplicate_row_count", "correction_count",
            "sample_days", "window_start", "window_end", "revenue_basis",
            "date_basis", "price_evidence_status", "advertising_status",
            "observed_profit_per_unit", "profit_per_unit", "tax_per_unit", "unit_cost",
        )
        completeness_keys = (
            "price_history", "successful_units", "finance", "advertising", "tariff",
            "tax", "unit_cost", "returns", "analytics", "window", "deduplication",
        )
        metrics_projection = {key: metrics.get(key) for key in metric_keys if key in metrics}
        completeness_projection = {
            key: completeness.get(key) for key in completeness_keys if key in completeness
        }
        if any(
            value is not None and (isinstance(value, (dict, list, tuple, bool))
                                  or not isinstance(value, (str, int, float)))
            for value in metrics_projection.values()
        ) or any(
            value is not None and not isinstance(value, str)
            for value in completeness_projection.values()
        ):
            return self._error("ANALYTICS_EXPORT_VALUE_INVALID")
        sources = result.get("sources")
        if not isinstance(sources, list) or len(sources) > 16:
            return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
        source_keys = (
            "name", "status", "complete", "row_count", "source_date_basis",
            "source_window_start", "source_window_end", "timezone", "as_of",
            "requested_at", "received_at", "reason",
        )
        sources_projection = []
        for source in sources:
            if not isinstance(source, dict):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            sources_projection.append({key: source.get(key) for key in source_keys if key in source})
        candidate_quality = (quality.get("candidates") or [{}])[0]
        if not isinstance(candidate_quality, dict):
            candidate_quality = {}
        quality_projection = {
            "status": quality.get("status"),
            "evidence_basis": quality.get("evidence_basis"),
            "verified": quality.get("verified") is True,
            "reasons": self._safe_codes(quality.get("reasons")),
            "warnings": self._safe_codes(quality.get("warnings")),
            "window_days": candidate_quality.get("window_days"),
            "successful_units": candidate_quality.get("successful_units"),
            "candidate_reasons": self._safe_codes(candidate_quality.get("reasons")),
            "candidate_warnings": self._safe_codes(candidate_quality.get("warnings")),
            "thresholds": {
                key: quality["thresholds"].get(key)
                for key in ("recommended_window_days", "small_sample_units", "max_evidence_age_days")
                if isinstance(quality.get("thresholds"), dict)
                and key in quality["thresholds"]
            },
        }
        columns = [
            self._column("result_revision", "Версия результата", "integer"),
            self._column("result_created_at", "Снимок создан", "text"),
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU", "text"),
            self._column("store_id", "Магазин", "text"),
            self._column("sale_schema", "Схема продаж", "status"),
            self._column("seller_price", "Цена продавца", "money", "RUB"),
            self._column("status", "Статус результата", "status"),
            self._column("evidence_basis", "Основание результата", "status"),
            self._column("window", "Окно наблюдения", "json"),
            self._column("sources", "Состояние источников", "json"),
            self._column("metrics", "Метрики", "json"),
            self._column("completeness", "Полнота данных", "json"),
            self._column("quality", "Сопоставимость и выборка", "json"),
            self._column("reasons", "Причины ограничения", "json"),
            self._column("warnings", "Предупреждения", "json"),
        ]
        row = {
            "result_revision": result_record["revision"],
            "result_created_at": result_record.get("created_at"),
            **safe_identity,
            "seller_price": self._cents_money(result.get("seller_price_cents")),
            "status": result.get("status"),
            "evidence_basis": result.get("evidence_basis"),
            "window": {key: window.get(key) for key in ("from", "to", "timezone", "date_basis") if key in window},
            "sources": sources_projection,
            "metrics": metrics_projection,
            "completeness": completeness_projection,
            "quality": quality_projection,
            "reasons": self._safe_codes(result.get("reasons")),
            "warnings": self._safe_codes(result.get("warnings")),
        }
        metadata = {
            "observation_state_revision": observation.get("state_revision"),
            "result_revision": result_record["revision"],
            "store_scope": safe_identity.get("store_id"),
            "source_reads": False,
            "recalculated_on_export": False,
        }
        return self.serializer.serialize(
            "unit_price_observation", file_format, columns, [row], metadata,
        )

    def export_unit_economics_experiment_snapshot(self, frozen_snapshot, file_format):
        """Export the same exact, privacy-safe projection used by the detail screen."""
        projected = UnitEconomicsExperimentSnapshotViewService.project(frozen_snapshot)
        if projected.get("error") is True:
            return projected
        view = projected["view"]
        columns = [self._column(
            "snapshot", "Снимок экономики и покрытия", "json",
        )]
        metadata = {
            "source_reads": False,
            "recalculated_on_export": False,
            "revisions": deepcopy(view["revisions"]),
        }
        return self.serializer.serialize(
            "unit_economics_experiment_snapshot", file_format,
            columns, [{"snapshot": view}], metadata,
        )

    def export_unit_economics_experiment_history(self, rows, metadata, file_format):
        """Export bounded, already-normalized experiment history without source I/O."""
        if not isinstance(rows, list) or not isinstance(metadata, dict):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        columns = [
            self._column("record_type", "Тип записи", "status"),
            self._column("revision", "Ревизия", "integer"),
            self._column("state", "Статус", "status"),
            self._column("created_at", "Сохранено", "text"),
            self._column("phase", "Фаза", "text"),
            self._column("payload", "Данные записи", "json"),
            self._column("content_hash", "Хэш содержимого", "text"),
        ]
        return self.serializer.serialize(
            "unit_economics_experiment_history", file_format,
            columns, rows, metadata,
        )

    def export_unit_price_tariff_profile(self, scenario_context, file_format):
        """Export only the active scenario's frozen, identity-matched tariff set."""
        result = scenario_context.get("result") if isinstance(scenario_context, dict) else None
        identity = result.get("identity") if isinstance(result, dict) else None
        snapshot = result.get("frozen_tariff_resolution") if isinstance(result, dict) else None
        source_snapshot = result.get("snapshot") if isinstance(result, dict) else None
        if (not isinstance(result, dict) or not isinstance(identity, dict)
                or not isinstance(source_snapshot, dict)
                or type(scenario_context.get("scenario_version")) is not int):
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        safe_identity = self._unit_price_identity({
            **identity,
            "sale_schema": identity.get("sale_schema")
            or (source_snapshot.get("product") or {}).get("scheme"),
        })
        if safe_identity is None:
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        profiles = snapshot.get("profiles", [])
        if not isinstance(profiles, list) or len(profiles) > 20:
            return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
        selected = snapshot.get("selected_profile")
        matched_band = snapshot.get("matched_band")
        scenario_inputs = result.get("inputs") if isinstance(result.get("inputs"), dict) else {}
        scenario_provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
        current_price = snapshot.get("seller_price_cents")
        rows = []
        for profile in profiles:
            if not isinstance(profile, dict) or not isinstance(profile.get("identity"), dict):
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            profile_identity = profile["identity"]
            if any(str(profile_identity.get(key) or "") != safe_identity.get(key) for key in (
                "product_id", "offer_id", "sku",
            )):
                return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
            bands = profile.get("bands")
            if not isinstance(bands, list) or len(bands) > 20:
                return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            is_selected = (
                isinstance(selected, dict)
                and selected.get("profile_id") == profile.get("profile_id")
                and selected.get("revision") == profile.get("revision")
                and selected.get("state_revision") == profile.get("state_revision")
            )
            for band in bands:
                if not isinstance(band, dict):
                    return self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
                selected_band = is_selected and band.get("price_from_cents") == (matched_band or {}).get("price_from_cents") and band.get("price_to_cents") == (matched_band or {}).get("price_to_cents")
                rows.append({
                    **safe_identity,
                    "scenario_version": scenario_context["scenario_version"],
                    "tariff_status": snapshot.get("status", "UNKNOWN"),
                    "tariff_reason": snapshot.get("reason"),
                    "effective_date": profile.get("effective_from"),
                    "effective_to": profile.get("effective_to"),
                    "sale_schema": profile.get("sale_schema"),
                    "price_basis": profile.get("price_basis"),
                    "currency": profile.get("currency"),
                    "profile_revision": profile.get("revision"),
                    "profile_origin": profile.get("origin"),
                    "confirmed_by_owner": profile.get("confirmed_by_owner"),
                    "price_from": self._cents_money(band.get("price_from_cents")),
                    "price_to": self._cents_money(band.get("price_to_cents")),
                    "commission_rate": band.get("commission_rate"),
                    "current_seller_price": self._cents_money(current_price),
                    "current_commission_rate": (
                        band.get("commission_rate") if selected_band else None
                    ),
                    "selected_for_current_price": bool(selected_band),
                })
                if len(rows) > self.MAX_TARIFF_EXPORT_ROWS:
                    return self._error("ANALYTICS_EXPORT_ROW_LIMIT_EXCEEDED")
        if not rows:
            legacy_price = result.get("legacy_tariff_price_cents")
            current_price = current_price or UnitPriceTariffSnapshotAdapter.price_to_cents(
                scenario_inputs.get("price")
            )
            origin = scenario_provenance.get("commission_rate")
            exact_legacy = type(legacy_price) is int and legacy_price == current_price
            known_current = scenario_inputs.get("commission_rate") is not None and origin not in (None, "unknown")
            rows.append({
                **safe_identity,
                "scenario_version": scenario_context["scenario_version"],
                "tariff_status": snapshot.get("status") or (
                    "LEGACY_EXACT_PRICE_ONLY" if exact_legacy
                    else "CURRENT_PRICE_POINT_ONLY" if known_current
                    else "UNKNOWN"
                ),
                "tariff_reason": snapshot.get("reason") or (
                    "LEGACY_RATE_APPLIES_TO_SAVED_PRICE_ONLY" if exact_legacy
                    else "NO_CONFIRMED_TARIFF_PROFILE" if not known_current
                    else None
                ),
                "effective_date": snapshot.get("effective_date"), "effective_to": None,
                "sale_schema": (source_snapshot.get("product") or {}).get("scheme"),
                "price_basis": snapshot.get("price_basis") or "SELLER_PRICE_RUB",
                "currency": "RUB", "profile_revision": None,
                "profile_origin": origin, "confirmed_by_owner": None,
                "price_from": self._cents_money(current_price),
                "price_to": self._cents_money(current_price),
                "commission_rate": scenario_inputs.get("commission_rate") if known_current else None,
                "current_seller_price": self._cents_money(current_price),
                "current_commission_rate": scenario_inputs.get("commission_rate") if known_current else None,
                "selected_for_current_price": bool(known_current),
            })
        columns = [
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU", "text"),
            self._column("store_id", "Магазин", "text"),
            self._column("scenario_version", "Версия сценария", "integer"),
            self._column("tariff_status", "Статус тарифа", "status"),
            self._column("tariff_reason", "Причина ограничения", "status"),
            self._column("effective_date", "Действует с", "text"),
            self._column("effective_to", "Действует по", "text"),
            self._column("sale_schema", "Схема продаж", "status"),
            self._column("price_basis", "Основа цены", "status"),
            self._column("currency", "Валюта", "text"),
            self._column("profile_revision", "Версия профиля", "integer"),
            self._column("profile_origin", "Источник профиля", "status"),
            self._column("confirmed_by_owner", "Подтверждён владельцем", "boolean"),
            self._column("price_from", "Цена от", "money", "RUB"),
            self._column("price_to", "Цена до", "money", "RUB"),
            self._column("commission_rate", "Ставка комиссии", "decimal", "%"),
            self._column("current_seller_price", "Цена сценария", "money", "RUB"),
            self._column("current_commission_rate", "Комиссия при цене сценария", "decimal", "%"),
            self._column("selected_for_current_price", "Применён к текущей цене", "boolean"),
        ]
        metadata = {
            "scenario_version": scenario_context["scenario_version"],
            "identity": safe_identity,
            "tariff_snapshot_version": snapshot.get("snapshot_version"),
            "tariff_status": snapshot.get("status") or "UNKNOWN",
            "tariff_reason": snapshot.get("reason"),
            "effective_date": snapshot.get("effective_date"),
            "price_basis": snapshot.get("price_basis") or "SELLER_PRICE_RUB",
            "uncovered_prices_remain_unknown": True,
            "source_reads": False,
            "recalculated_on_export": False,
        }
        return self.serializer.serialize(
            "unit_price_tariff_profile", file_format, columns, rows, metadata,
        )

    @staticmethod
    def _unit_price_identity(identity):
        if not isinstance(identity, dict):
            return None
        keys = ("product_id", "offer_id", "sku", "store_id", "sale_schema")
        result = {}
        for key in keys:
            value = identity.get(key)
            if key == "sale_schema" and value is None:
                value = identity.get("scheme")
            if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip():
                return None
            result[key] = str(value)[:120]
        return result

    @staticmethod
    def _safe_codes(values):
        if not isinstance(values, (list, tuple)):
            return []
        return [value[:120] for value in values[:32] if isinstance(value, str)]

    @staticmethod
    def _cents_money(value):
        if type(value) is not int or value < 0:
            return None
        return f"{value // 100}.{value % 100:02d}"

    def export_plan_comparison(self, snapshot_row, file_format):
        comparison = snapshot_row.get("comparison") if isinstance(snapshot_row, dict) else None
        if not isinstance(comparison, dict) or comparison.get("comparison_version") != 1:
            return self._error("ANALYTICS_EXPORT_SNAPSHOT_INVALID")
        columns = [
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU каталога", "text"),
            self._column("scope_status", "Изменение состава SKU", "status"),
            self._column("field", "Параметр", "text"),
            self._column("before", "Первый вариант", "json"),
            self._column("after", "Второй вариант", "json"),
            self._column("delta", "Изменение", "json"),
            self._column("unit", "Единица", "text"),
        ]
        cross_docking_enabled = any(
            isinstance(product, dict) and "cross_docking_source_before" in product
            for product in comparison.get("input_changes") or []
        )
        if cross_docking_enabled:
            columns.extend([
                self._column("cross_docking_source_before", "Источник кросс-докинга · вариант 1", "json"),
                self._column("cross_docking_source_after", "Источник кросс-докинга · вариант 2", "json"),
            ])
        rows = []
        for product in comparison.get("input_changes") or []:
            identity = product.get("identity") or {}
            scope_status = product.get("scope_status")
            if scope_status in {"ADDED_IN_SECOND", "REMOVED_FROM_SECOND"}:
                added = scope_status == "ADDED_IN_SECOND"
                rows.append({
                    "product_id": identity.get("product_id"),
                    "offer_id": identity.get("offer_id"),
                    "sku": identity.get("sku"),
                    "scope_status": scope_status,
                    "field": "Состав SKU",
                    "before": "Отсутствовал" if added else "Входил",
                    "after": "Входит" if added else "Отсутствует",
                    "delta": None,
                    "unit": "scope",
                })
                continue
            changes = product.get("changes") or []
            if not changes:
                unchanged_row = {
                    "product_id": identity.get("product_id"),
                    "offer_id": identity.get("offer_id"),
                    "sku": identity.get("sku"),
                    "scope_status": "COMMON",
                    "field": "Допущения",
                    "before": "Без изменений",
                    "after": "Без изменений",
                    "delta": None,
                    "unit": "status",
                }
                if cross_docking_enabled:
                    unchanged_row["cross_docking_source_before"] = deepcopy(product.get("cross_docking_source_before"))
                    unchanged_row["cross_docking_source_after"] = deepcopy(product.get("cross_docking_source_after"))
                rows.append(unchanged_row)
            for change in changes:
                change_row = {
                    "product_id": identity.get("product_id"), "offer_id": identity.get("offer_id"),
                    "sku": identity.get("sku"), "scope_status": "COMMON",
                    "field": change.get("label"),
                    "before": change.get("before"), "after": change.get("after"),
                    "delta": change.get("delta"), "unit": change.get("unit"),
                }
                if cross_docking_enabled:
                    change_row["cross_docking_source_before"] = deepcopy(product.get("cross_docking_source_before"))
                    change_row["cross_docking_source_after"] = deepcopy(product.get("cross_docking_source_after"))
                rows.append(change_row)
        metadata = {
            "document_kind": "saved_plan_comparison",
            "comparison_version": comparison.get("comparison_version"),
            "status": comparison.get("status"), "reason": comparison.get("reason"),
            "first": deepcopy(comparison.get("first") or {}),
            "second": deepcopy(comparison.get("second") or {}),
            "period": deepcopy(comparison.get("period") or {}),
            "metrics": deepcopy(comparison.get("metrics") or {}),
            "expense_changes": deepcopy(comparison.get("expense_changes") or []),
            "changed_dimensions": deepcopy(comparison.get("changed_dimensions") or []),
            "historical": True, "external_reads": 0,
            "exported_scope": "all_rows_in_exact_immutable_comparison_snapshot",
        }
        return self.serializer.serialize("plan_comparison", file_format, columns, rows, metadata)

    def _plan_columns_and_rows(self, plan_rows):
        columns = [
            self._column("row_id", "ID строки", "text"),
            self._column("product_id", "ID товара", "text"),
            self._column("offer_id", "Артикул", "text"),
            self._column("sku", "SKU каталога", "text"),
            self._column("status", "Статус сценария", "status"),
            self._column("snapshot_status", "Статус исходного снимка", "status"),
            self._column("source_freshness_status", "Свежесть источника при выгрузке", "status"),
            self._column("source_age_seconds_at_evaluation", "Возраст источника при выгрузке, сек.", "integer"),
            self._column("source_ttl_seconds", "Срок свежести источника, сек.", "integer"),
            self._column("reason", "Причина", "status"),
            self._column("missing_inputs", "Недостающие допущения", "text"),
            self._column("invalid_inputs", "Некорректные допущения", "text"),
            self._column("inputs", "Допущения", "json"),
            self._column("provenance", "Источники допущений", "json"),
            self._column("commission_rate", "Комиссия Ozon", "decimal", "%"),
            self._column("commission_origin", "Источник комиссии", "status"),
            self._column("tariff_scope", "Область тарифа", "status"),
            self._column("tariff_status", "Статус тарифа", "status"),
            self._column("tariff_reason", "Причина ограничения тарифа", "status"),
            self._column("tariff_effective_date", "Дата тарифа", "text"),
            self._column("tariff_price_basis", "Основа тарифной цены", "status"),
            self._column("manual_assumptions", "Ручные допущения", "json"),
            self._column("source_as_of", "Дата источников", "json"),
            self._column("scheme", "Схема исполнения", "status"),
        ]
        columns.extend([
            self._column("calc_" + key, label, kind, unit)
            for key, label, kind, unit in self._calculation_columns()
        ])
        for group in ("break_even", "target"):
            columns.extend([
                self._column(group + "_status", group + " статус", "status"),
                self._column(group + "_price", group + " цена", "money", "RUB"),
                self._column(group + "_profit", group + " прибыль", "money", "RUB/шт."),
                self._column(group + "_margin", group + " маржа", "decimal", "%"),
                self._column(group + "_tax", group + " налог", "money", "RUB/шт."),
                self._column(group + "_goal_reached", group + " цель достигнута", "boolean"),
            ])
        rows = []
        for row in plan_rows:
            if not isinstance(row, dict):
                return columns, self._error("ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH")
            identity = row.get("identity") or {}
            scenario = row.get("scenario") or {}
            calculated = scenario.get("calculated") or {}
            planning = row.get("planning") or {}
            projected = {
                "row_id": row.get("row_id"),
                "product_id": identity.get("product_id"),
                "offer_id": identity.get("offer_id"),
                "sku": identity.get("catalog_sku"),
                "status": row.get("status"),
                "snapshot_status": row.get("snapshot_status"),
                "source_freshness_status": row.get("source_freshness_status"),
                "source_age_seconds_at_evaluation": row.get("source_age_seconds_at_evaluation"),
                "source_ttl_seconds": row.get("source_ttl_seconds"),
                "reason": row.get("reason"),
                "missing_inputs": "; ".join(row.get("missing_inputs") or []),
                "invalid_inputs": "; ".join(row.get("invalid_inputs") or []),
                "inputs": deepcopy(row.get("inputs") or {}),
                "provenance": deepcopy(row.get("provenance") or {}),
                "manual_assumptions": deepcopy(row.get("manual_assumptions") or {}),
                "source_as_of": deepcopy(row.get("source_as_of") or {}),
                "scheme": row.get("scheme"),
                **self._unit_price_tariff_export_fields({
                    "inputs": row.get("inputs"),
                    "provenance": row.get("provenance"),
                    "tariff_scope": row.get("tariff_scope"),
                    "tariff_resolution_status": row.get("tariff_resolution_status"),
                    "tariff_resolution_reason": row.get("tariff_resolution_reason"),
                    "sources": {"tariff_resolution": row.get("frozen_tariff_resolution")},
                }),
                **{"calc_" + key: calculated.get(key) for key, _label, _kind, _unit in self._calculation_columns()},
            }
            for group in ("break_even", "target"):
                outcome = planning.get(group) or {}
                projected.update({
                    group + "_status": outcome.get("status"),
                    group + "_price": outcome.get("price"),
                    group + "_profit": outcome.get("profit"),
                    group + "_margin": outcome.get("margin_percent"),
                    group + "_tax": outcome.get("tax"),
                    group + "_goal_reached": outcome.get("goal_reached"),
                })
            rows.append(projected)
        return columns, rows

    @staticmethod
    def _period_columns():
        return [
            AnalyticsExportService._column("section", "Раздел", "text"),
            AnalyticsExportService._column("name", "Показатель", "text"),
            AnalyticsExportService._column("sku", "SKU", "text"),
            AnalyticsExportService._column("current_value", "Текущее значение", "decimal"),
            AnalyticsExportService._column("current_status", "Статус текущего", "status"),
            AnalyticsExportService._column("previous_value", "Предыдущее значение", "decimal"),
            AnalyticsExportService._column("previous_status", "Статус предыдущего", "status"),
            AnalyticsExportService._column("delta", "Изменение", "decimal"),
            AnalyticsExportService._column("value", "Сумма", "decimal"),
            AnalyticsExportService._column("count", "Количество", "integer"),
            AnalyticsExportService._column("status", "Статус", "status"),
            AnalyticsExportService._column("unit", "Единица", "text"),
            AnalyticsExportService._column("semantic", "Семантика суммы", "status"),
        ]

    @staticmethod
    def _period_row(section, name, **values):
        row = {key: None for key in (
            "section", "name", "sku", "current_value", "current_status",
            "previous_value", "previous_status", "delta", "value", "count",
            "status", "unit", "semantic",
        )}
        row.update(section=section, name=name, **values)
        return row

    @staticmethod
    def _bridge_semantic(name):
        if "rounding" in name:
            return "rounding_adjustment"
        if name == "authoritative_delta":
            return "authoritative_total"
        return "additive_component"

    @staticmethod
    def _calculation_columns():
        return (
            ("revenue", "Выручка", "money", "RUB/шт."),
            ("discount_points", "Баллы", "money", "RUB/шт."),
            ("taxable_revenue", "Налоговая база", "money", "RUB/шт."),
            ("commission", "Комиссия", "money", "RUB/шт."),
            ("advertising", "Реклама", "money", "RUB/шт."),
            ("fees", "Прочие расходы", "money", "RUB/шт."),
            ("profit_before_tax", "Прибыль до налога", "money", "RUB/шт."),
            ("tax", "Налог", "money", "RUB/шт."),
            ("effective_tax_rate", "Фактическая ставка налога", "decimal", "%"),
            ("profit", "Прибыль после налога", "money", "RUB/шт."),
            ("margin_percent", "Маржа", "decimal", "%"),
        )

    @staticmethod
    def _column(key, label, value_type, unit=None, semantic=None):
        column = {"key": key, "label": label, "type": value_type}
        if unit is not None:
            column["unit"] = unit
        if semantic is not None:
            column["semantic"] = semantic
        return column

    @staticmethod
    def _unit_price_tariff_export_fields(item):
        """Expose the stored commission basis without exporting tenant identity."""
        item = item if isinstance(item, dict) else {}
        inputs = item.get("inputs") if isinstance(item.get("inputs"), dict) else {}
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
        tariff = sources.get("tariff_resolution")
        tariff = tariff if isinstance(tariff, dict) else {}
        origin = provenance.get("commission_rate") or "unknown"
        scope = item.get("tariff_scope")
        status = item.get("tariff_resolution_status")
        reason = item.get("tariff_resolution_reason")
        if tariff:
            scope = scope or "FROZEN_PROFILE_SET"
            status = status or tariff.get("status") or "UNKNOWN"
            reason = reason or tariff.get("reason")
        elif scope == "EXACT_PRICE_ONLY":
            status = status or "LEGACY_EXACT_PRICE_ONLY"
            reason = reason or "LEGACY_RATE_APPLIES_TO_SAVED_PRICE_ONLY"
        elif scope == "FIXED_RATE_ASSUMPTION":
            status = status or "FIXED_RATE_ASSUMPTION"
            reason = reason or "NO_TARIFF_PROFILE_ATTACHED"
        elif scope == "UNKNOWN":
            status = status or "UNKNOWN"
            reason = reason or "COMMISSION_UNCONFIRMED"
        elif scope is None:
            if origin in {
                "manual", "manual_seller_assumption", "manual_unit_economics_input",
                "current_price_point", "ozon_current_fbo_rate", "CURRENT_PRICE_POINT",
                "CONFIRMED_OFFICIAL_SOURCE",
            }:
                scope, status = "EXACT_PRICE_ONLY", status or "LEGACY_EXACT_PRICE_ONLY"
                reason = reason or "LEGACY_RATE_APPLIES_TO_SAVED_PRICE_ONLY"
            elif inputs.get("commission_rate") is not None and origin != "unknown":
                scope, status = "FIXED_RATE_ASSUMPTION", status or "FIXED_RATE_ASSUMPTION"
                reason = reason or "NO_TARIFF_PROFILE_ATTACHED"
            else:
                scope, status = "UNKNOWN", status or "UNKNOWN"
                reason = reason or "COMMISSION_UNCONFIRMED"
        return {
            "commission_rate": inputs.get("commission_rate"),
            "commission_origin": origin,
            "tariff_scope": scope,
            "tariff_status": status,
            "tariff_reason": reason,
            "tariff_effective_date": tariff.get("effective_date"),
            "tariff_price_basis": tariff.get("price_basis"),
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
