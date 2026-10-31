import csv
import io
import json

from services.analytics_export_service import AnalyticsExportService
from services.analytics_export_serializer import AnalyticsExportSerializer
from services.unit_economics_experiment_snapshot_view_service import (
    UnitEconomicsExperimentSnapshotViewService,
)


OWNER = "private-owner-id"
STORE = "private-store-id"
PRODUCT = "private-product-id"
OFFER = "private-offer-id"
SKU = "private-sku-id"
PLAN_ID = "d" * 32
SNAPSHOT_ID = "c" * 64


def _frozen_snapshot():
    identity = {
        "owner_id": OWNER, "store_id": STORE, "product_id": PRODUCT,
        "offer_id": OFFER, "sku": SKU, "sale_schema": "FBO",
    }
    readiness = {
        "error": False, "schema_version": 1, "status": "COMPLETE",
        "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
        "window": {
            "from_date": "2026-08-01", "to_date": "2026-09-25",
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
        },
        "coverage_status": "COMPLETE", "coverage_complete": True,
        "denominator": {"units": 10, "kind": "SOLD_UNITS_WINDOW"},
        "component_counts": {"INCLUDED": 1, "EXCLUDED": 0, "UNKNOWN": 0},
        "components": [{
            "component_key": "CROSS_DOCKING", "status": "INCLUDED",
            "source": "CROSS_DOCKING_EVIDENCE", "applicability": "WINDOW_MODEL_INPUT",
            "evidence_status": "COMPLETE", "observed_amount_rub": "7.00",
            "observed_units": 10, "applied_amount_rub": "7.00", "applied_units": 10,
            "unit_amount_rub": "0.70", "reason_codes": [],
        }],
        "read_only": True, "api_calls": 0,
    }
    plan_item = {
        "identity": {
            "product_id": PRODUCT, "offer_id": OFFER, "sku": SKU,
            "product_name": "Private product name", "store_id": STORE, "scheme": "FBO",
        },
        "inputs": {
            "price": "100.00", "cost": "20.00", "commission_rate": "10",
            "advertising_rate": "5", "discount_points_rate": "0",
            "logistics_per_unit": "2.00", "last_mile_per_unit": "3.00",
            "acquiring_per_unit": "1.00", "tax_mode": "NONE",
            "tax_rate": None, "minimum_tax_rate": None,
        },
        "provenance": {
            "price": "owner_input", "cost": "owner_input",
            "commission_rate": "confirmed_official_source",
        },
        "projection": {
            "status": "READY", "available": True, "missing_inputs": [],
            "invalid_inputs": [], "revenue": "100.00", "commission": "-10.00",
            "advertising": "-5.00", "tax": "0.00", "profit": "54.00",
            "margin_percent": "54.00", "additional_unit_expenses": "0.70",
        },
        "extended_scenario": {
            "schema_version": 1, "calculation_mode": "WINDOW_COST_ALLOCATION",
            "expense_snapshot_ref": SNAPSHOT_ID, "quantity_evidence_ref": None,
            "expense_policy_revision": "expense-policy-v1",
            "included_component_keys": ["CROSS_DOCKING"],
            "excluded_component_statuses": {},
            "numerator_and_denominator_basis": {
                "numerator": "WINDOW_EXPENSE_RUB", "denominator": "SOLD_UNITS_WINDOW",
            },
            "source_completeness": "COMPLETE", "assumed_inputs": [],
            "scope": {
                "scope_kind": "REFERENCE_56_COMPLETED_LOCAL_DAYS",
                "from_date": "2026-08-01", "to_date": "2026-09-25",
                "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
            },
            "denominator_units": 10,
            "components": [{
                "component_key": "CROSS_DOCKING", "numerator_rub": "7.00",
                "ownership": "ADDITIONAL",
            }],
        },
    }
    experiment = {
        "experiment_id": "private-experiment-id", **identity,
        "status": "READY", "state_revision": 3, "result_revision": 0,
        "schema_version": 1,
        "config": {
            "schema_version": 1, "identity": identity,
            "title": "Private draft title", "metric": "MAX_RUB_PER_UNIT",
            "calculation_mode": "WINDOW_COST_ALLOCATION",
            "source_references": {
                "plan": {"document_id": PLAN_ID, "revision": 2},
                "expense_snapshot_id": SNAPSHOT_ID, "tariff": None,
                "observation": None,
            },
            "candidate_prices_cents": [9900, 10000],
            "decision_threshold_rub": "0.01", "planned_duration_days": 7,
            "currency": "RUB",
            "control_flags": {key: "UNCHANGED" for key in (
                "inventory", "promotion", "advertising", "card", "cost", "tariff",
            )},
        },
    }
    return {
        "error": False, "experiment": experiment, "read_only": True, "source_io": False,
        "frozen_inputs": {
            "plan": {
                "document_id": PLAN_ID, "revision": 2, "schema_version": 4,
                "calculation_version": 2,
                "payload": {
                    "plan_kind": "single", "schema_version": 4, "calculation_version": 2,
                    "target_margin_percent": "25.00", "items": [plan_item],
                },
            },
            "expense_snapshot": {
                "snapshot_id": SNAPSHOT_ID, "schema_version": 1,
                "payload": {"schema_version": 1, "identity": identity, "readiness": readiness},
            },
            "tariff": None, "quantity": None,
        },
    }


def test_projection_keeps_frozen_amounts_coverage_and_revisions_without_identity_leak():
    projected = UnitEconomicsExperimentSnapshotViewService.project(_frozen_snapshot())

    assert projected["error"] is False
    view = projected["view"]
    assert view["economics"]["projection"]["profit"] == "54.00"
    assert view["cost_basis"]["per_unit_rub"] == "0.70"
    assert view["cost_basis"]["numerator_rub"] == "7.00"
    assert view["expense_coverage"]["components"][0]["applied_amount_rub"] == "7.00"
    assert view["revisions"] == {
        "experiment_state_revision": 3, "experiment_result_revision": 0,
        "plan_schema_version": 4, "plan_calculation_version": 2, "plan_revision": 2,
        "expense_snapshot_schema_version": 1,
        "expense_snapshot_fingerprint": view["revisions"]["expense_snapshot_fingerprint"],
        "tariff_revision": None, "quantity_result_revision": None,
    }
    assert view["read_only"] is True and view["source_io"] is False
    assert view["recalculated"] is False
    rendered = repr(view)
    for private_value in (OWNER, STORE, PRODUCT, OFFER, SKU, PLAN_ID, SNAPSHOT_ID,
                          "private-experiment-id", "Private product name", "Private draft title"):
        assert private_value not in rendered


def test_export_contains_the_exact_projection_and_does_not_recalculate_or_reload():
    frozen = _frozen_snapshot()
    projection = UnitEconomicsExperimentSnapshotViewService.project(frozen)["view"]
    service = AnalyticsExportService(AnalyticsExportSerializer())
    exported = service.export_unit_economics_experiment_snapshot(frozen, "json")

    assert exported["error"] is False
    payload = json.loads(exported["file_content"].decode("utf-8"))
    assert payload["export_kind"] == "unit_economics_experiment_snapshot"
    assert payload["rows"][0]["snapshot"] == projection
    assert payload["metadata"]["source_reads"] is False
    assert payload["metadata"]["recalculated_on_export"] is False
    assert payload["metadata"]["revisions"] == projection["revisions"]
    assert exported["read_only"] is True and exported["executed"] is False
    assert "private-owner-id" not in exported["file_content"].decode("utf-8")

    csv_export = service.export_unit_economics_experiment_snapshot(frozen, "csv")
    assert csv_export["error"] is False
    rows = list(csv.reader(io.StringIO(csv_export["file_content"].decode("utf-8-sig"))))
    data_row = rows[-1]
    assert json.loads(data_row[0]) == projection
    assert "private-owner-id" not in csv_export["file_content"].decode("utf-8")


def test_projection_fails_closed_for_cross_store_identity_and_revision_replay():
    wrong_scope = _frozen_snapshot()
    wrong_scope["experiment"]["store_id"] = "another-store"
    assert UnitEconomicsExperimentSnapshotViewService.project(wrong_scope)["code"] == (
        "UNIT_ECONOMICS_EXPERIMENT_SCOPE_MISMATCH"
    )

    wrong_revision = _frozen_snapshot()
    wrong_revision["frozen_inputs"]["plan"]["revision"] = 1
    assert UnitEconomicsExperimentSnapshotViewService.project(wrong_revision)["code"] == (
        "UNIT_ECONOMICS_EXPERIMENT_PLAN_INVALID"
    )


def test_unconfirmed_expense_coverage_is_visible_as_a_model_limit():
    frozen = _frozen_snapshot()
    readiness = frozen["frozen_inputs"]["expense_snapshot"]["payload"]["readiness"]
    readiness["coverage_status"] = "PARTIAL"
    readiness["coverage_complete"] = False
    readiness["status"] = "PARTIAL"

    view = UnitEconomicsExperimentSnapshotViewService.project(frozen)["view"]

    assert view["expense_coverage"]["coverage_status"] == "PARTIAL"
    assert "EXPENSE_COVERAGE_INCOMPLETE" in view["model_limits"]


def test_cost_basis_reference_must_match_the_experiment_snapshot():
    frozen = _frozen_snapshot()
    frozen["frozen_inputs"]["plan"]["payload"]["items"][0][
        "extended_scenario"
    ]["expense_snapshot_ref"] = "e" * 64

    view = UnitEconomicsExperimentSnapshotViewService.project(frozen)["view"]

    assert view["cost_basis"]["origin"] == "UNCONFIRMED"
    assert view["cost_basis"]["reference_status"] == "MISMATCH"
    assert "COST_BASIS_REFERENCE_DIFFERS_FROM_EXPERIMENT_SNAPSHOT" in view["model_limits"]


def test_legacy_plan_with_unset_tax_mode_still_projects_as_incomplete():
    frozen = _frozen_snapshot()
    item = frozen["frozen_inputs"]["plan"]["payload"]["items"][0]
    item["inputs"]["tax_mode"] = None
    item["projection"]["available"] = False
    item["projection"]["status"] = "INCOMPLETE_INPUTS"

    view = UnitEconomicsExperimentSnapshotViewService.project(frozen)["view"]

    assert view["economics"]["inputs"]["tax_mode"] is None
    assert view["economics"]["projection"]["available"] is False
    assert "SAVED_PLAN_ECONOMICS_UNAVAILABLE" in view["model_limits"]


def test_projection_enforces_size_limit_without_truncating(monkeypatch):
    monkeypatch.setattr(UnitEconomicsExperimentSnapshotViewService, "MAX_VIEW_BYTES", 128)

    result = UnitEconomicsExperimentSnapshotViewService.project(_frozen_snapshot())

    assert result["error"] is True
    assert result["code"] == "UNIT_ECONOMICS_EXPERIMENT_VIEW_TOO_LARGE"
