"""Synthetic full-path check for persisted daily-use data and backup restore."""

from services.bot_backup_service import BotBackupService
from services.cost_service import ProductCostService
from services.expense_repository import ExpenseRepository
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.saved_planning_plan_service import SavedPlanningPlanService
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.unit_price_scenario_service import UnitPriceScenarioService


def _scenario_inputs():
    return {
        "price": "500", "cost": "120", "commission_rate": "15",
        "logistics_per_unit": "40", "last_mile_per_unit": "10",
        "acquiring_per_unit": "5", "advertising_rate": "8",
        "discount_points_rate": "20", "tax_mode": "USN_INCOME",
        "tax_rate": "6", "minimum_tax_rate": "1",
    }


def _plan_payload(store_id, projection):
    return {
        "plan_kind": "single", "schema_version": 1, "calculation_version": 1,
        "target_margin_percent": "25.00",
        "items": [{
            "identity": {
                "product_id": "synthetic-product", "offer_id": "synthetic-offer",
                "sku": "synthetic-sku", "product_name": "Synthetic product",
                "store_id": store_id, "scheme": "FBO",
            },
            "inputs": _scenario_inputs(),
            "provenance": {"price": "synthetic", "cost": "synthetic"},
            "sources": {"periods": {}, "completeness": {}},
            "projection": projection,
        }],
    }


def test_calculation_plan_cost_and_expense_survive_backup_dry_run_and_new_root_restore(
    monkeypatch, tmp_path,
):
    project = tmp_path / "synthetic-project"
    source_storage = tmp_path / "synthetic-storage"
    project.mkdir()
    source_storage.mkdir()
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(source_storage))
    owner_scope = "synthetic-owner::ozon::store-a"
    tenant = set_current_tenant_user_id(owner_scope)
    try:
        scenario_service = UnitPriceScenarioService(TaxService())
        calculation = scenario_service.calculate(
            _scenario_inputs(),
            identity={"user_id": "synthetic-owner", "store_id": "store-a", "sku": "synthetic-sku"},
        )
        assert calculation["available"] is True
        repository = PlanningWorkspaceRepository()
        saved_plans = SavedPlanningPlanService(repository, scenario_service)
        created = repository.save_document(
            title="Synthetic daily plan",
            payload=_plan_payload("store-a", calculation["calculated"]),
            idempotency_key="daily-e2e-plan-create-01",
        )
        assert created["error"] is False
        ProductCostService().set_cost(
            product_id="synthetic-product", sku="synthetic-sku",
            offer_id="synthetic-offer", cost_price=120,
        )
        expense = ExpenseRepository().add_expense(
            "2026-10-20", "synthetic-advertising", 15.5, "synthetic e2e",
        )
        assert expense["error"] is False
        before_restart = saved_plans.get_document(created["document_id"])
        assert before_restart["error"] is False
        assert before_restart["document"]["revision"] == 1
    finally:
        reset_current_tenant_user_id(tenant)

    backup_service = BotBackupService(
        project_root=project,
        storage_root=source_storage,
        backup_directory=project / ".local-backups",
        lifecycle_token="synthetic-e2e-token",
        lifecycle_inspector=lambda _token: {"state": "STOPPED"},
        revision_reader=lambda _root: "syntheticrevision",
    )
    backup = backup_service.backup()
    assert backup["error"] is False
    assert backup_service.verify_archive(backup["backup_path"])["error"] is False
    target = tmp_path / "restored-root"
    dry_run = backup_service.restore_archive(backup["backup_path"], target, dry_run=True)
    assert dry_run["error"] is False
    assert not target.exists()
    restored = backup_service.restore_archive(backup["backup_path"], target)
    assert restored["error"] is False

    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(target / "storage"))
    tenant = set_current_tenant_user_id(owner_scope)
    try:
        restored_plan = PlanningWorkspaceRepository().get_document(created["document_id"])
        assert restored_plan["error"] is False
        assert restored_plan["document"]["revision"] == 1
        assert restored_plan["document"]["payload"]["items"][0]["projection"]["profit"] == "186.0"
        assert ProductCostService().get_cost("synthetic-product")[3] == 120.0
        expenses = ExpenseRepository().get_expenses_by_period("2026-10-20", "2026-10-20")
        assert len(expenses) == 1
        assert expenses[0]["amount"] == 15.5
    finally:
        reset_current_tenant_user_id(tenant)

    other_store = set_current_tenant_user_id("synthetic-owner::ozon::store-b")
    try:
        assert PlanningWorkspaceRepository().get_document(created["document_id"])["error"] is True
        assert ProductCostService().get_cost("synthetic-product") is None
        assert ExpenseRepository().get_expenses_by_period("2026-10-20", "2026-10-20") == []
    finally:
        reset_current_tenant_user_id(other_store)

    assert source_storage.exists()
    assert project.exists()
