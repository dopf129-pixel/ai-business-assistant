import csv
import io
import json

from services.analytics_export_service import AnalyticsExportService
from services.analytics_export_serializer import AnalyticsExportSerializer


def _service():
    return AnalyticsExportService(AnalyticsExportSerializer())


def _comparison():
    return {
        "comparison_id": "internal-comparison-id",
        "revision": 3,
        "latest_revision": 3,
        "freshness_status": "CURRENT",
        "payload": {
            "schema_version": 1,
            "identity": {
                "store_id": "store-a", "product_id": "product-1",
                "offer_id": "hook-2", "sku": "3921245627", "sale_schema": "FBO",
            },
            "source_references": [{
                "index": 0, "observation_id": "internal-observation-id",
                "result_revision": 2, "source_document_id": "internal-plan-id",
                "source_document_revision": 4,
            }],
            "ranking": {
                "status": "RANKED", "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
                "display_basis": "MODELLED_FROM_OBSERVED_INPUTS", "verified": False,
                "baseline_index": 0, "checked_candidate_count": 1,
                "best_profit_per_unit": "0.00", "omitted_candidate_count": 0,
                "omitted_repeated_price_count": 0,
                "quality_assessment": {
                    "status": "COMPARABLE", "reasons": [], "warnings": [],
                },
                "ranking": [{
                    "index": 0, "result_revision": 2, "seller_price_cents": 10000,
                    "profit_per_unit": "0.00", "delta_vs_baseline": "0.00",
                    "delta_percent_vs_baseline": None, "is_best": True,
                }],
            },
        },
    }


def _observation():
    return {
        "observation": {
            "store_id": "store-a", "state_revision": 5,
            "identity": {
                "store_id": "store-a", "product_id": "product-1",
                "offer_id": "hook-2", "sku": "3921245627", "sale_schema": "FBO",
            },
        },
        "result": {
            "revision": 2, "created_at": "2026-10-27T10:00:00Z",
            "payload": {
                "schema_version": 1, "seller_price_cents": 10000,
                "status": "INSUFFICIENT_DATA",
                "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
                "window": {"from": "2026-10-01", "to": "2026-10-07",
                           "timezone": "Europe/Moscow", "date_basis": "SOURCE_CALENDAR_DATE"},
                "sources": [{"name": "FINANCE", "status": "PARTIAL", "complete": False,
                             "row_count": 0, "reason": "WINDOW_INCOMPLETE",
                             "raw_response": "must-not-export"}],
                "metrics": {"finance_net": "0.00", "successful_sale_units": None,
                            "source_row_count": 0, "unsupported_secret": "must-not-export"},
                "completeness": {"finance": "PARTIAL", "successful_units": "UNKNOWN",
                                 "unsupported_secret": "must-not-export"},
                "reasons": ["FINANCE_SOURCE_INCOMPLETE"],
                "warnings": ["PRICE_HISTORY_UNCONFIRMED"],
            },
        },
    }


def _tariff_context(*, rate="14", profiles=True):
    profile_list = []
    if profiles:
        profile_list = [{
            "profile_id": "internal-profile-id", "revision": 2, "state_revision": 3,
            "owner_id": "private-owner", "store_id": "store-a",
            "identity": {"product_id": "product-1", "offer_id": "hook-2", "sku": "3921245627"},
            "origin": "MANUAL_SELLER_ASSUMPTION", "source_ref": "internal-source-ref",
            "effective_from": "2026-10-01", "effective_to": None,
            "sale_schema": "FBO", "price_basis": "SELLER_PRICE_RUB", "currency": "RUB",
            "confirmed_by_owner": True,
            "bands": [
                {"price_from_cents": 1, "price_to_cents": 9999, "commission_rate": "12"},
                {"price_from_cents": 10000, "price_to_cents": 19999, "commission_rate": rate},
            ],
        }]
    return {
        "scenario_version": 4,
        "result": {
            "identity": {"user_id": "private-owner", "store_id": "store-a",
                         "product_id": "product-1", "offer_id": "hook-2", "sku": "3921245627"},
            "snapshot": {"product": {"scheme": "FBO"}},
            "inputs": {"price": "100.00", "commission_rate": rate},
            "provenance": {"commission_rate": "manual_seller_assumption"},
            "legacy_tariff_price_cents": None,
            "frozen_tariff_resolution": {
                "snapshot_version": 1, "status": "MANUAL_RANGE", "reason": None,
                "effective_date": "2026-10-01", "price_basis": "SELLER_PRICE_RUB",
                "seller_price_cents": 10000, "commission_rate": rate,
                "matched_band": {"price_from_cents": 10000, "price_to_cents": 19999},
                "selected_profile": {"profile_id": "internal-profile-id", "revision": 2,
                                     "state_revision": 3},
                "profiles": profile_list,
            },
        },
    }


def _json(document):
    assert document["error"] is False, document
    return json.loads(document["file_content"].decode("utf-8"))


def _csv(document):
    assert document["error"] is False, document
    return list(csv.reader(
        io.StringIO(document["file_content"].decode("utf-8-sig"), newline=""), delimiter=";",
    ))


def _csv_metadata(rows):
    return json.loads(rows[3][1])


def _csv_header(document):
    return [
        column["label"] + (f" ({column['unit']})" if column.get("unit") else "")
        for column in document["columns"]
    ]


def test_comparison_csv_and_json_share_exact_revision_and_redact_internal_ids():
    service = _service()
    snapshot = _comparison()
    json_doc = _json(service.export_unit_price_comparison(snapshot, "json"))
    csv_rows = _csv(service.export_unit_price_comparison(snapshot, "csv"))
    metadata = json_doc["metadata"]

    assert json_doc["export_kind"] == "unit_price_comparison"
    assert metadata["comparison_revision"] == 3
    assert metadata["source_versions"] == [{
        "candidate_index": 0, "observation_result_revision": 2, "saved_plan_revision": 4,
    }]
    assert json_doc["rows"][0]["profit_per_unit"] == "0.00"
    assert json_doc["rows"][0]["seller_price"] == "100.00"
    assert _csv_metadata(csv_rows) == metadata
    rendered_rows = csv_rows[csv_rows.index(_csv_header(json_doc)) + 1:]
    assert len(rendered_rows) == 1
    for secret in ("internal-comparison-id", "internal-observation-id", "internal-plan-id", "private-owner"):
        assert secret not in json.dumps(json_doc, ensure_ascii=False)


def test_observation_export_keeps_unknown_distinct_from_zero_and_uses_fixed_allowlist():
    service = _service()
    snapshot = _observation()
    quality = {
        "status": "NOT_READY", "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
        "verified": False, "reasons": ["SUCCESSFUL_UNIT_DENOMINATOR_UNCONFIRMED"],
        "warnings": [], "thresholds": {"recommended_window_days": 7,
                                        "small_sample_units": 30,
                                        "unapproved_secret": "must-not-export"},
        "candidates": [{"window_days": 7, "successful_units": None,
                        "reasons": [], "warnings": [], "raw_response": "must-not-export"}],
    }
    json_doc = _json(service.export_unit_price_observation(snapshot, quality, "json"))
    csv_rows = _csv(service.export_unit_price_observation(snapshot, quality, "csv"))
    row = json_doc["rows"][0]
    assert json_doc["export_kind"] == "unit_price_observation"
    assert row["metrics"]["successful_sale_units"] is None
    assert row["metrics"]["finance_net"] == "0.00"
    assert row["metrics"]["source_row_count"] == 0
    assert row["sources"] == [{"name": "FINANCE", "status": "PARTIAL",
                               "complete": False, "row_count": 0,
                               "reason": "WINDOW_INCOMPLETE"}]
    assert "unsupported_secret" not in json.dumps(json_doc, ensure_ascii=False)
    assert "raw_response" not in json.dumps(json_doc, ensure_ascii=False)
    assert _csv_metadata(csv_rows) == json_doc["metadata"]
    header = _csv_header(json_doc)
    data = csv_rows[csv_rows.index(header) + 1]
    assert data[header.index("Сопоставимость и выборка")]


def test_tariff_export_contains_only_frozen_bands_and_preserves_unknown_vs_zero():
    service = _service()
    context = _tariff_context()
    json_doc = _json(service.export_unit_price_tariff_profile(context, "json"))
    csv_rows = _csv(service.export_unit_price_tariff_profile(context, "csv"))
    assert json_doc["export_kind"] == "unit_price_tariff_profile"
    assert [row["commission_rate"] for row in json_doc["rows"]] == ["12", "14"]
    assert [row["selected_for_current_price"] for row in json_doc["rows"]] == [False, True]
    assert json_doc["metadata"]["uncovered_prices_remain_unknown"] is True
    assert _csv_metadata(csv_rows) == json_doc["metadata"]
    for secret in ("internal-profile-id", "private-owner", "internal-source-ref"):
        assert secret not in json.dumps(json_doc, ensure_ascii=False)

    unknown = _tariff_context(rate=None, profiles=False)
    unknown["result"]["inputs"]["commission_rate"] = None
    unknown["result"]["frozen_tariff_resolution"] = {
        "snapshot_version": 1, "status": "UNKNOWN", "reason": "NO_APPLICABLE_PROFILE",
        "effective_date": "2026-10-01", "price_basis": "SELLER_PRICE_RUB",
        "seller_price_cents": 10000, "commission_rate": None, "matched_band": None,
        "selected_profile": None, "profiles": [],
    }
    unknown_row = _json(service.export_unit_price_tariff_profile(unknown, "json"))["rows"][0]
    assert unknown_row["commission_rate"] is None
    assert unknown_row["selected_for_current_price"] is False

    zero = _tariff_context(rate="0", profiles=False)
    zero["result"]["inputs"]["commission_rate"] = "0"
    zero["result"]["frozen_tariff_resolution"] = {}
    zero_row = _json(service.export_unit_price_tariff_profile(zero, "json"))["rows"][0]
    assert zero_row["commission_rate"] == "0"
    assert zero_row["selected_for_current_price"] is True


def test_tariff_export_rejects_cross_identity_profile_and_oversized_band_schema():
    service = _service()
    context = _tariff_context()
    context["result"]["frozen_tariff_resolution"]["profiles"][0]["identity"]["sku"] = "other-sku"
    assert service.export_unit_price_tariff_profile(context, "json")["code"] == "ANALYTICS_EXPORT_SNAPSHOT_INVALID"
    oversized = _tariff_context()
    oversized["result"]["frozen_tariff_resolution"]["profiles"][0]["bands"] *= 21
    assert service.export_unit_price_tariff_profile(oversized, "json")["code"] == "ANALYTICS_EXPORT_ROW_SCHEMA_MISMATCH"
