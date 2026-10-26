"""Synthetic full-path check for persisted daily-use data and backup restore."""

import sqlite3
import zipfile

from cryptography.fernet import Fernet

from period_profit_expense_operation_authorized_mapping import (
    build_period_profit_expense_operation_authorized_mapping,
)
from services.bot_backup_service import BotBackupService
from services.cost_service import ProductCostService
from services.ozon_account_repository import OzonAccountRepository
from services.expense_repository import ExpenseRepository
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.period_profit_mapping_registry_service import PeriodProfitMappingRegistryService
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
        costs = ProductCostService()
        costs.set_cost(
            product_id="synthetic-product", sku="synthetic-sku",
            offer_id="synthetic-offer", cost_price=120,
        )
        first_cost = costs.record_historical_cost(
            "synthetic-product", "synthetic-sku", "synthetic-offer",
            110, "2026-09-01",
        )
        second_cost = costs.record_historical_cost(
            "synthetic-product", "synthetic-sku", "synthetic-offer",
            120, "2026-10-01",
        )
        assert first_cost["error"] is False
        assert second_cost["error"] is False
        expense_repository = ExpenseRepository()
        expense = expense_repository.add_expense(
            "2026-10-20", "synthetic-advertising", 15.5, "synthetic e2e",
        )
        coverage = expense_repository.confirm_coverage(
            "2026-10-01", "2026-10-31", "synthetic complete period",
        )
        assert expense["error"] is False
        assert coverage["error"] is False

        registry_path = project / "data" / "period_profit_mapping_registry.json"
        monkeypatch.setenv("PERIOD_PROFIT_MAPPING_REGISTRY_PATH", str(registry_path))
        registry = PeriodProfitMappingRegistryService(
            str(registry_path), clock=lambda: "synthetic-time",
        )
        mapping = build_period_profit_expense_operation_authorized_mapping({
            "error": False,
            "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED",
            "scope": "ADVERTISING",
            "mapping_authorized": True,
            "financial_evidence_mapping_allowed": True,
            "selected_operations": [{
                "type_id": 77,
                "name": "Synthetic CPC",
                "description": None,
                "source": "OZON_FINANCE_ACCRUAL_TYPES",
            }],
        })
        saved_mapping = registry.save("ADVERTISING", mapping, activate=True)
        assert saved_mapping["error"] is False
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
        restored_costs = ProductCostService()
        assert restored_costs.get_cost("synthetic-product")[3] == 120.0
        assert restored_costs.get_historical_cost_evidence(
            "2026-09-15", product_id="synthetic-product",
        )["cost_price"] == 110.0
        assert restored_costs.get_historical_cost_evidence(
            "2026-10-20", product_id="synthetic-product",
        )["cost_price"] == 120.0
        restored_expenses = ExpenseRepository()
        expenses = restored_expenses.get_expenses_by_period("2026-10-20", "2026-10-20")
        assert len(expenses) == 1
        assert expenses[0]["amount"] == 15.5
        restored_coverage = restored_expenses.get_coverage_by_period(
            "2026-10-01", "2026-10-31",
        )
        assert len(restored_coverage) == 1
        assert restored_coverage[0]["note"] == "synthetic complete period"
        restored_registry = PeriodProfitMappingRegistryService(
            str(target / "project" / "data" / "period_profit_mapping_registry.json"),
        )
        assert restored_registry.load_active("ADVERTISING")["mapping_id"] == (
            mapping["mapping_id"]
        )
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


def test_encrypted_ozon_credentials_survive_backup_restore_and_require_original_key(
    monkeypatch, tmp_path,
):
    project = tmp_path / "synthetic-project"
    source_storage = tmp_path / "synthetic-storage"
    project.mkdir()
    source_storage.mkdir()
    master_key = Fernet.generate_key().decode("ascii")
    wrong_key = Fernet.generate_key().decode("ascii")
    api_key = "synthetic-api-key-must-stay-encrypted"
    telegram_token = "synthetic-telegram-token-must-not-be-backed-up"
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", master_key)
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(source_storage))
    (project / ".env").write_text(
        f"TELEGRAM_BOT_TOKEN={telegram_token}\nOZON_CREDENTIAL_MASTER_KEY={master_key}\n",
        encoding="utf-8",
    )

    source_accounts = OzonAccountRepository(master_key=master_key)
    saved = source_accounts.save("synthetic-owner", "synthetic-client-42", api_key)
    assert saved["error"] is False
    source_db = source_storage / "ozon_assistant.db"
    original_database = source_db.read_bytes()

    backup_service = BotBackupService(
        project_root=project,
        storage_root=source_storage,
        backup_directory=project / ".local-backups",
        lifecycle_token="synthetic-credential-token",
        lifecycle_inspector=lambda _token: {"state": "STOPPED"},
        revision_reader=lambda _root: "syntheticrevision",
    )
    backup = backup_service.backup()
    assert backup["error"] is False, backup
    assert backup_service.verify_archive(backup["backup_path"])["error"] is False
    assert source_db.read_bytes() == original_database

    with zipfile.ZipFile(backup["backup_path"]) as archive:
        database_payload = archive.read("files/storage/ozon_assistant.db")
        archive_payload = b"".join(archive.read(name) for name in archive.namelist())
    assert api_key.encode("utf-8") not in archive_payload
    assert telegram_token.encode("utf-8") not in archive_payload
    assert master_key.encode("utf-8") not in archive_payload

    archived_db = tmp_path / "archived-credentials.db"
    archived_db.write_bytes(database_payload)
    with sqlite3.connect(str(archived_db)) as connection:
        row = connection.execute(
            """SELECT client_id, api_key_encrypted FROM ozon_store_accounts
               WHERE telegram_user_id = ?""",
            ("synthetic-owner",),
        ).fetchone()
    assert row is not None
    assert row[0] == "synthetic-client-42"
    assert row[1] != api_key
    assert api_key not in row[1]

    target = tmp_path / "restored-account"
    dry_run = backup_service.restore_archive(backup["backup_path"], target, dry_run=True)
    assert dry_run["error"] is False
    assert not target.exists()
    restored = backup_service.restore_archive(backup["backup_path"], target)
    assert restored["error"] is False

    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(target / "storage"))
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", master_key)
    correct_key_repository = OzonAccountRepository()
    assert correct_key_repository.get("synthetic-owner", "synthetic-client-42") == {
        "client_id": "synthetic-client-42",
        "api_key": api_key,
    }
    assert correct_key_repository.status("synthetic-owner")["connected"] is True

    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", "")
    missing_key_repository = OzonAccountRepository()
    assert missing_key_repository.get("synthetic-owner", "synthetic-client-42") is None
    assert missing_key_repository.status("synthetic-owner")["code"] == (
        "OZON_ACCOUNT_MASTER_KEY_UNAVAILABLE"
    )

    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", wrong_key)
    wrong_key_repository = OzonAccountRepository()
    assert wrong_key_repository.get("synthetic-owner", "synthetic-client-42") is None
    assert wrong_key_repository.status("synthetic-owner")["code"] == (
        "OZON_ACCOUNT_MASTER_KEY_MISMATCH"
    )
    assert source_db.read_bytes() == original_database