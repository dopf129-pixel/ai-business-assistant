import sqlite3
from pathlib import Path

import pytest

from database import get_products, save_product
from services.cost_service import ProductCostService
from services.expense_repository import ExpenseRepository
from services.product_decision_history_service import ProductDecisionHistoryService
from services.product_decision_history_storage_service import (
    ProductDecisionHistoryStorageService,
)
from services.product_unit_economics_provider import ProductUnitEconomicsProvider
from services.return_cogs_accounting_attribution_repository import (
    ReturnCogsAccountingAttributionRepository,
)
from services.return_cogs_accounting_recognition_repository import (
    ReturnCogsAccountingRecognitionRepository,
)
from services.return_cogs_profit_application_authorization_repository import (
    ReturnCogsProfitApplicationAuthorizationRepository,
)
from services.return_cogs_profit_application_commit_repository import (
    ReturnCogsProfitApplicationCommitRepository,
)
from services.return_inventory_recovery_repository import (
    ReturnInventoryRecoveryRepository,
)
from services.tax_configuration_service import TaxConfigurationService
from services.tax_service import TaxService
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from services.tenant_storage import tenant_storage_path


def _tenant(user_id, callback):
    token = set_current_tenant_user_id(user_id)
    try:
        return callback()
    finally:
        reset_current_tenant_user_id(token)


RETURN_REPOSITORIES = (
    (
        ReturnInventoryRecoveryRepository,
        "return_inventory_recovery_history",
    ),
    (
        ReturnCogsAccountingAttributionRepository,
        "return_cogs_accounting_attribution_history",
    ),
    (
        ReturnCogsAccountingRecognitionRepository,
        "return_cogs_accounting_recognition_history",
    ),
    (
        ReturnCogsProfitApplicationAuthorizationRepository,
        "return_cogs_profit_application_authorization_history",
    ),
    (
        ReturnCogsProfitApplicationCommitRepository,
        "return_cogs_profit_application_commit_history",
    ),
)


@pytest.mark.parametrize(("repository_type", "table_name"), RETURN_REPOSITORIES)
def test_shared_return_repository_initializes_schema_for_each_tenant(
    tmp_path,
    monkeypatch,
    repository_type,
    table_name,
):
    monkeypatch.chdir(tmp_path)
    repository = repository_type()

    def inspect_schema():
        connection = repository.get_connection()
        try:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            return tenant_storage_path("ozon_assistant.db"), row
        finally:
            connection.close()

    path_a, table_a = _tenant("seller-a", inspect_schema)
    path_b, table_b = _tenant("seller-b", inspect_schema)

    assert table_a == (table_name,)
    assert table_b == (table_name,)
    assert path_a != path_b
    assert Path(path_a).is_file()
    assert Path(path_b).is_file()


def test_tenant_path_lookup_is_pure_and_write_creates_parent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    path = Path(_tenant("seller-a", lambda: tenant_storage_path("state.json")))

    assert "seller-a" not in str(path)
    assert not path.parent.exists()

    configuration = TaxConfigurationService(environment={})
    result = _tenant(
        "seller-a",
        lambda: configuration.save_policy("USN_INCOME", 6.0),
    )

    assert result["saved"] is True
    assert path.parent.is_dir()



def test_core_database_schema_is_initialized_in_active_tenant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    _tenant(
        "seller-a",
        lambda: save_product({"product_id": "a", "offer_id": "A", "sku": "A"}),
    )
    _tenant(
        "seller-b",
        lambda: save_product({"product_id": "b", "offer_id": "B", "sku": "B"}),
    )

    assert _tenant("seller-a", get_products) == [("a", "A", "A")]
    assert _tenant("seller-b", get_products) == [("b", "B", "B")]
    assert get_products() == []


def test_explicit_expense_database_path_remains_tenant_independent(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "custom" / "expenses.db"
    repository = ExpenseRepository(db_path=path)

    _tenant(
        "seller-a",
        lambda: repository.add_expense("2026-09-10", "custom", 10),
    )

    assert repository.db_path == path
    assert _tenant("seller-b", lambda: repository.db_path) == path
    assert _tenant(
        "seller-b", lambda: repository.get_expenses_by_date("2026-09-10")
    )[0]["amount"] == 10.0

def test_product_unit_economics_provider_resolves_active_tenant_tax_policy(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    configuration = TaxConfigurationService(environment={})
    provider = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_configuration_service=configuration,
    )
    profits = [{
        "product_id": "product",
        "sku": "sku",
        "sales_count": 1,
        "gross_sales": 1000,
        "total_cost": 300,
        "net_accrual": 700,
        "gross_profit": 400,
    }]

    _tenant("seller-a", lambda: configuration.save_policy("USN_INCOME", 6))
    _tenant("seller-b", lambda: configuration.save_policy("USN_INCOME", 15))

    taxes = [
        _tenant("seller-a", lambda: provider.build(profits)[0]["tax"]),
        _tenant("seller-b", lambda: provider.build(profits)[0]["tax"]),
        _tenant("seller-a", lambda: provider.build(profits)[0]["tax"]),
    ]

    assert taxes == [60.0, 150.0, 60.0]
    assert provider.build(profits)[0]["tax"] is None


def test_multi_tenant_seller_state_acceptance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    configuration = TaxConfigurationService(environment={})
    costs = ProductCostService()
    expenses = ExpenseRepository()
    returns = ReturnInventoryRecoveryRepository()
    decision_history = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(),
        clock=lambda: "2026-09-10T12:00:00+00:00",
    )
    economics = ProductUnitEconomicsProvider(
        tax_service=TaxService(),
        tax_configuration_service=configuration,
    )
    profit = [{
        "product_id": "shared-product",
        "sku": "shared-sku",
        "sales_count": 1,
        "gross_sales": 1000,
        "total_cost": 300,
        "net_accrual": 700,
        "gross_profit": 400,
    }]

    def seed(seller, rate, cost, expense, decision_type, priority):
        configuration.save_policy("USN_INCOME", rate)
        costs.set_cost("shared-product", "shared-sku", seller, cost)
        expenses.add_expense("2026-09-10", seller, expense)
        recovery = returns.record_recovery(
            "shared-return",
            "shared-posting",
            "shared-sku",
            1,
            "SALEABLE_RESTORED" if seller == "seller-a" else "NON_SALEABLE",
            "2026-09-10",
        )
        decision_history.record({
            "error": False,
            "sku": "shared-sku",
            "decision_type": decision_type,
            "priority": priority,
        })
        return {
            "db_path": tenant_storage_path("ozon_assistant.db"),
            "tax_path": configuration.file_path,
            "tax": economics.build(profit)[0]["tax"],
            "cost": costs.get_cost("shared-product")[3],
            "expenses": expenses.get_expenses_by_date("2026-09-10"),
            "recovery": recovery,
            "decision": decision_history.latest("shared-sku"),
        }

    state_a = _tenant(
        "seller-a",
        lambda: seed("seller-a", 6, 100, 10, "HOLD_STOCK", "LOW"),
    )
    state_b = _tenant(
        "seller-b",
        lambda: seed("seller-b", 15, 200, 20, "REPRICE", "HIGH"),
    )

    assert state_a["tax"] == 60.0
    assert state_b["tax"] == 150.0
    assert state_a["cost"] == 100.0
    assert state_b["cost"] == 200.0
    assert state_a["expenses"][0]["amount"] == 10.0
    assert state_b["expenses"][0]["amount"] == 20.0
    assert state_a["recovery"]["recovery_state"] == "SALEABLE_RESTORED"
    assert state_b["recovery"]["recovery_state"] == "NON_SALEABLE"
    assert state_a["decision"]["decision_type"] == "HOLD_STOCK"
    assert state_b["decision"]["decision_type"] == "REPRICE"
    assert state_a["db_path"] != state_b["db_path"]
    assert state_a["tax_path"] != state_b["tax_path"]

    assert _tenant("seller-a", lambda: costs.get_cost("shared-product")[3]) == 100.0
    assert _tenant("seller-b", lambda: costs.get_cost("shared-product")[3]) == 200.0
    assert _tenant(
        "seller-a",
        lambda: returns.get_latest_recovery(
            "shared-return", "shared-posting", "shared-sku"
        )["recovery_state"],
    ) == "SALEABLE_RESTORED"
    assert _tenant(
        "seller-b",
        lambda: returns.get_latest_recovery(
            "shared-return", "shared-posting", "shared-sku"
        )["recovery_state"],
    ) == "NON_SALEABLE"
    assert _tenant(
        "seller-a", lambda: decision_history.latest("shared-sku")["decision_type"]
    ) == "HOLD_STOCK"
    assert _tenant(
        "seller-b", lambda: decision_history.latest("shared-sku")["decision_type"]
    ) == "REPRICE"

    assert costs.get_cost("shared-product") is None
    assert expenses.get_expenses_by_date("2026-09-10") == []
    assert returns.get_latest_recovery(
        "shared-return", "shared-posting", "shared-sku"
    )["status"] == "RETURN_INVENTORY_RECOVERY_MISSING"
    assert decision_history.latest("shared-sku") is None
    assert configuration.get_policy()["configured"] is False
    assert economics.build(profit)[0]["tax"] is None

    for path in (state_a["db_path"], state_b["db_path"]):
        connection = sqlite3.connect(path)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM product_costs"
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT COUNT(*) FROM expenses"
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT COUNT(*) FROM return_inventory_recovery_history"
            ).fetchone()[0] == 1
        finally:
            connection.close()
