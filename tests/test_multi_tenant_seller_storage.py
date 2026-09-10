from services.expense_repository import ExpenseRepository
from services.return_cogs_accounting_attribution_repository import (
    ReturnCogsAccountingAttributionRepository,
)
from services.return_cogs_accounting_recognition_repository import (
    ReturnCogsAccountingRecognitionRepository,
)
from services.return_cogs_profit_application_authorization_repository import (
    ReturnCogsProfitApplicationAuthorizationRepository,
)
from services.return_inventory_recovery_repository import ReturnInventoryRecoveryRepository
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.tenant_storage import tenant_storage_path


def _run_as(user_id, callback):
    token = set_current_tenant_user_id(user_id)
    try:
        return callback()
    finally:
        reset_current_tenant_user_id(token)


def _repositories():
    return {
        "inventory": ReturnInventoryRecoveryRepository(),
        "attribution": ReturnCogsAccountingAttributionRepository(),
        "recognition": ReturnCogsAccountingRecognitionRepository(),
        "authorization": ReturnCogsProfitApplicationAuthorizationRepository(),
        "expenses": ExpenseRepository(),
    }


def _seed(repositories, amount):
    inventory = repositories["inventory"].record_recovery(
        "ret-1",
        "post-1",
        "sku-1",
        1,
        "SALEABLE_RESTORED",
        "2026-09-10",
    )
    assert inventory["error"] is False

    attribution = repositories["attribution"].record_attribution(
        "ret-1",
        "post-1",
        "sku-1",
        "2026-09-10",
        "NO_COMPENSATION_CONFIRMED",
        True,
        "2026-09-10",
    )
    assert attribution["error"] is False

    recognition = repositories["recognition"].record_recognition(
        "ret-1",
        "post-1",
        "sku-1",
        "2026-09-10",
        "COGS_RECOVERY_RECOGNIZED",
        amount,
        "RUB",
        "2026-09-10",
    )
    assert recognition["error"] is False

    authorization = repositories["authorization"].record_application_state(
        recognition["history_id"],
        "ret-1",
        "post-1",
        "sku-1",
        "2026-09-10",
        "PROFIT_APPLICATION_AUTHORIZED",
        amount,
        "RUB",
        "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
        True,
        "2026-09-10",
    )
    assert authorization["error"] is False

    expense = repositories["expenses"].add_expense(
        "2026-09-10",
        "tenant-check",
        amount,
        "cross-user isolation regression",
    )
    assert expense["error"] is False

    return recognition["history_id"]


def test_seller_accounting_storage_isolated_between_tenants(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    state_a = {}

    def seed_a():
        repositories = _repositories()
        state_a["recognition_id"] = _seed(repositories, 111.0)
        state_a["path"] = tenant_storage_path("ozon_assistant.db")

    _run_as("seller-a", seed_a)

    def assert_b_is_empty_then_seed():
        repositories = _repositories()
        assert repositories["inventory"].get_latest_recovery(
            "ret-1", "post-1", "sku-1"
        )["status"] == "RETURN_INVENTORY_RECOVERY_MISSING"
        assert repositories["attribution"].get_latest_attribution(
            "ret-1", "post-1", "sku-1"
        )["status"] == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_MISSING"
        assert repositories["recognition"].get_latest_recognition(
            "ret-1", "post-1", "sku-1"
        )["status"] == "RETURN_COGS_ACCOUNTING_RECOGNITION_MISSING"
        assert repositories["authorization"].get_application_authorization(
            state_a["recognition_id"], "ret-1", "post-1", "sku-1"
        )["status"] == "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_MISSING"
        assert repositories["expenses"].get_expenses_by_period(
            "2026-09-01", "2026-09-30"
        ) == []

        recognition_id = _seed(repositories, 222.0)
        return recognition_id, tenant_storage_path("ozon_assistant.db")

    recognition_id_b, path_b = _run_as("seller-b", assert_b_is_empty_then_seed)

    assert state_a["path"] != path_b
    assert state_a["recognition_id"] == 1
    assert recognition_id_b == 1

    def assert_a_unchanged():
        repositories = _repositories()
        recovery = repositories["inventory"].get_latest_recovery(
            "ret-1", "post-1", "sku-1"
        )
        recognition = repositories["recognition"].get_latest_recognition(
            "ret-1", "post-1", "sku-1"
        )
        expenses = repositories["expenses"].get_expenses_by_period(
            "2026-09-01", "2026-09-30"
        )
        assert recovery["inventory_recovery_confirmed"] is True
        assert recognition["recognized_amount"] == 111.0
        assert [row["amount"] for row in expenses] == [111.0]

    _run_as("seller-a", assert_a_unchanged)


def test_no_tenant_context_preserves_legacy_global_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repository = ExpenseRepository()
    repository.add_expense("2026-09-10", "legacy", 10.0)

    assert tenant_storage_path("ozon_assistant.db") == "ozon_assistant.db"
    rows = repository.get_expenses_by_period("2026-09-10", "2026-09-10")
    assert len(rows) == 1
    assert rows[0]["amount"] == 10.0
