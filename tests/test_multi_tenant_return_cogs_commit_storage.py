from services.return_cogs_accounting_recognition_repository import (
    ReturnCogsAccountingRecognitionRepository,
)
from services.return_cogs_profit_application_authorization_repository import (
    ReturnCogsProfitApplicationAuthorizationRepository,
)
from services.return_cogs_profit_application_commit_repository import (
    ReturnCogsProfitApplicationCommitRepository,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


def _as_tenant(user_id, callback):
    token = set_current_tenant_user_id(user_id)
    try:
        return callback()
    finally:
        reset_current_tenant_user_id(token)


def _seed_and_commit(amount):
    recognition_repo = ReturnCogsAccountingRecognitionRepository()
    authorization_repo = ReturnCogsProfitApplicationAuthorizationRepository()
    commit_repo = ReturnCogsProfitApplicationCommitRepository()

    recognition = recognition_repo.record_recognition(
        "ret-commit-1",
        "post-commit-1",
        "sku-commit-1",
        "2026-09-10",
        "COGS_RECOVERY_RECOGNIZED",
        amount,
        "RUB",
        "2026-09-10",
    )
    assert recognition["error"] is False

    authorization = authorization_repo.record_application_state(
        recognition["history_id"],
        "ret-commit-1",
        "post-commit-1",
        "sku-commit-1",
        "2026-09-10",
        "PROFIT_APPLICATION_AUTHORIZED",
        amount,
        "RUB",
        "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
        True,
        "2026-09-10",
    )
    assert authorization["error"] is False

    committed = commit_repo.commit_current_authorization(
        recognition["history_id"],
        authorization["history_id"],
        "ret-commit-1",
        "post-commit-1",
        "sku-commit-1",
        "2026-09-10",
    )
    assert committed["error"] is False
    assert committed["application_commit_confirmed"] is True
    return recognition["history_id"], commit_repo


def test_return_cogs_commit_ledger_isolated_between_tenants(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    recognition_a, _ = _as_tenant("seller-a", lambda: _seed_and_commit(111.0))

    def assert_b_empty_then_commit():
        empty_repo = ReturnCogsProfitApplicationCommitRepository()
        missing = empty_repo.get_application_commit(recognition_a)
        assert missing["status"] == "RETURN_COGS_PROFIT_APPLICATION_COMMIT_MISSING"
        recognition_b, repo_b = _seed_and_commit(222.0)
        ledger = repo_b.list_commits()
        assert ledger["error"] is False
        assert ledger["count"] == 1
        assert ledger["records"][0]["committed_amount"] == 222.0
        return recognition_b

    recognition_b = _as_tenant("seller-b", assert_b_empty_then_commit)
    assert recognition_a == 1
    assert recognition_b == 1

    def assert_a_unchanged():
        repo = ReturnCogsProfitApplicationCommitRepository()
        ledger = repo.list_commits()
        assert ledger["error"] is False
        assert ledger["count"] == 1
        assert ledger["records"][0]["committed_amount"] == 111.0

    _as_tenant("seller-a", assert_a_unchanged)
