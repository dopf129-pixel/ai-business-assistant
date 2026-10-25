import csv
import io
import json

from services.analytics_export_service import AnalyticsExportService


def _json(result):
    assert result["error"] is False
    return json.loads(result["file_content"].decode("utf-8"))


def test_period_export_preserves_comparison_bridge_and_top_k_coverage_semantics():
    snapshot = {
        "schema_version": 1,
        "periods": {"current": {"from": "2026-08-01", "to": "2026-08-31"}},
        "comparison_basis": "previous_equal_period",
        "comparison_status": "PARTIAL",
        "coverage_status": "PARTIAL",
        "generated_at": "2026-10-17T10:00:00Z",
        "comparison_metrics": {
            "profit": {
                "current_value": "100.25", "current_status": "CONFIRMED",
                "previous_value": None, "previous_status": "UNAVAILABLE",
                "delta": None, "unit": "RUB",
            },
        },
        "profit_bridge": {
            "B": {
                "status": "CONFIRMED", "authoritative_delta": "10.00",
                "contributions": {"revenue": "12.00", "rounding_adjustment": "-2.00"},
                "net_accrual_detail": {"status": "REFERENCE_ONLY", "commission": "-1.00"},
            },
            "E": {"status": "UNAVAILABLE"},
        },
        "sku_contribution": {
            "status": "PARTIAL", "coverage_status": "PARTIAL",
            "basis": "matched_catalog_skus", "reconciliation_status": "PARTIAL",
            "top_growth": [{"sku": "SKU-1", "delta": "5.50", "status": "CONFIRMED"}],
            "top_decline": [], "matched_sku_count": 4,
            "unmatched_current_count": 2, "unmatched_previous_count": 1,
            "ambiguous_identity_count": 0, "invalid_row_count": 0,
            "unmatched_rows_are_zero": False,
        },
        "scope": {"owner_id": "must-not-export", "store_id": "private"},
    }

    document = _json(AnalyticsExportService().export_period_profit(snapshot, "json"))
    assert document["metadata"]["sku_contribution"]["top_k_limit"] == 5
    assert document["metadata"]["sku_contribution"]["matched_sku_count"] == 4
    assert document["metadata"]["profit_bridge_semantics"]["net_accrual_detail"].startswith("decomposition")
    assert "scope" not in document["metadata"]
    rows = document["rows"]
    assert any(row["name"] == "profit" and row["previous_value"] is None for row in rows)
    assert any(row["name"] == "B.rounding_adjustment" and row["semantic"] == "rounding_adjustment" for row in rows)
    assert any(row["name"] == "B.net_accrual_detail.commission" and row["semantic"] == "reconciliation_component" for row in rows)
    assert any(row["sku"] == "SKU-1" and row["semantic"] == "top_k_reference_not_additive" for row in rows)


def test_period_export_carries_only_allowlisted_cached_completeness_reasons():
    snapshot = {
        "schema_version": 1,
        "periods": {"current": {"from": "2026-08-01", "to": "2026-08-31"}},
        "completeness": {
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
            "status": "PARTIAL",
            "source_completeness": {
                "cost": "PARTIAL",
                "tax": "UNKNOWN",
                "secret": "SECRET",
            },
            "reason_codes": ["COST_MISSING", "TAX_POLICY_UNCONFIRMED", "SECRET_TOKEN"],
            "amount": "must-not-export",
        },
    }

    json_document = _json(
        AnalyticsExportService().export_period_profit(snapshot, "json")
    )
    csv_result = AnalyticsExportService().export_period_profit(snapshot, "csv")
    csv_rows = list(csv.reader(
        io.StringIO(csv_result["file_content"].decode("utf-8-sig")),
        delimiter=";",
    ))
    csv_metadata = json.loads(csv_rows[3][1])
    expected = {
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "status": "PARTIAL",
        "source_completeness": {"cost": "PARTIAL", "tax": "UNKNOWN"},
        "reason_codes": ["COST_MISSING", "TAX_POLICY_UNCONFIRMED"],
    }

    assert json_document["metadata"]["completeness"] == expected
    assert csv_metadata["completeness"] == expected
    assert "SECRET_TOKEN" not in csv_result["file_content"].decode("utf-8-sig")
    assert "must-not-export" not in json.dumps(json_document, ensure_ascii=False)

    malformed = {
        **snapshot,
        "completeness": {
            "date_from": "2026-02-31",
            "date_to": "2026-03-01",
            "status": [],
            "source_completeness": {"cost": []},
            "reason_codes": ["SECRET_TOKEN"],
        },
    }
    malformed_document = _json(
        AnalyticsExportService().export_period_profit(malformed, "json")
    )
    assert malformed_document["metadata"]["completeness"] == {
        "date_from": None,
        "date_to": None,
        "status": "UNKNOWN",
        "source_completeness": {},
        "reason_codes": [],
    }


def test_product_overview_exports_all_filtered_snapshot_rows_with_active_scope_metadata():
    snapshot = {
        "rows": [
            {"selector": f"offer-{n}", "identity": {"product_id": str(n), "offer_id": f"offer-{n}", "catalog_sku": str(1000 + n)}, "status": "READY", "decision": {"decision_type": "WATCH", "priority": "NORMAL", "confidence": "HIGH", "reasons": [], "missing_data": []}, "metrics": {"decision_profit_per_unit": {"value": str(n)}}}
            for n in range(7)
        ],
        "pagination": {"page": 1, "page_size": 5, "total_pages": 2, "total_rows": 7, "scope_rows": 7, "filter": "existing_priority", "sort_by": "decision_profit_per_unit", "direction": "desc"},
        "coverage": {"selected_count": 7, "decision_ready_count": 7, "selection_scope": {"mode": "selected", "selected_count": 7}},
        "source_freshness": {"captured_at": "2026-10-17T10:00:00Z"},
    }

    document = _json(AnalyticsExportService().export_product_overview(snapshot, "json"))
    assert len(document["rows"]) == 7
    assert document["metadata"]["active_filter"] == "existing_priority"
    assert document["metadata"]["active_sort"] == "decision_profit_per_unit"
    assert document["metadata"]["sort_direction"] == "desc"
    assert document["metadata"]["exported_row_count"] == 7


def test_batch_export_preserves_unknown_inputs_and_marks_plan_as_estimate():
    batch = {
        "kind": "UNIT_PRICE_BATCH_PLAN", "target_margin_percent": "25",
        "rows_selected": 2, "rows_attempted": 2, "rows_completed": 1,
        "evaluation_count": 3, "evaluation_limit": 100,
        "tenant_scope": "private-scope",
        "rows": [
            {"row_id": "r1", "identity": {"offer_id": "offer", "catalog_sku": "sku"}, "status": "READY", "inputs": {"price": "500", "cost": "200"}, "provenance": {"cost": "manual"}, "scenario": {"calculated": {"revenue": "500", "profit": "96", "margin_percent": "19.2"}}, "planning": {"target": {"status": "FOUND", "price": "564.16", "profit": "141.04", "margin_percent": "25", "tax": "27.08", "goal_reached": True}}},
            {"row_id": "r2", "identity": {"offer_id": "offer2", "catalog_sku": "sku2"}, "status": "INCOMPLETE_INPUTS", "inputs": {"price": "500", "cost": None}, "scenario": {"calculated": {}}, "planning": {}},
        ],
    }

    document = _json(AnalyticsExportService().export_unit_price_batch(batch, "json", active_sort="profit"))
    assert len(document["rows"]) == 2
    assert document["rows"][0]["calc_profit"] == "96"
    assert document["rows"][1]["calc_profit"] is None
    assert document["metadata"]["plan_status"] == "PLANNED"
    assert document["metadata"]["sale_basis"] == "one_successful_sale"
    assert document["metadata"]["fulfillment_estimate"] == "FBO"
    assert document["metadata"]["active_sort"] == "profit"
    assert "tenant_scope" not in document["metadata"]


def test_sensitivity_export_contains_all_cells_not_just_visible_page():
    result = {
        "kind": "UNIT_PRICE_SENSITIVITY", "cell_count": 8, "available_cell_count": 7,
        "axes": {"price": {"values": [1, 2, 3]}}, "source_as_of": {"seller_price": "2026-10-17"},
        "cells": [
            {"cell_id": str(index), "status": "AVAILABLE" if index < 8 else "UNKNOWN", "coordinates": {"price": index}, "inputs": {}, "provenance": {}, "scenario": {"calculated": {"profit": str(index - 4), "tax": 0}}}
            for index in range(1, 9)
        ],
    }
    context = {"identity": {"catalog_sku": "sku-1", "offer_id": "offer-1"}, "origin": {"kind": "single"}, "owner_id": "secret"}

    document = _json(AnalyticsExportService().export_unit_price_sensitivity(result, context, "json"))
    assert len(document["rows"]) == 8
    assert document["rows"][0]["calc_profit"] == "-3"
    assert document["rows"][1]["calc_tax"] == "0"
    assert document["metadata"]["exported_scope"] == "all_cells_in_exact_sensitivity_snapshot"
    assert "owner_id" not in document["metadata"]


def test_export_rejects_invalid_snapshot_without_silently_producing_partial_document():
    service = AnalyticsExportService()
    assert service.export_period_profit({"schema_version": 2}, "json")["code"] == "ANALYTICS_EXPORT_SNAPSHOT_INVALID"
    assert service.export_unit_price_batch({"kind": "UNIT_PRICE_BATCH_PLAN", "rows": [None]}, "csv")["code"] == "ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH"
