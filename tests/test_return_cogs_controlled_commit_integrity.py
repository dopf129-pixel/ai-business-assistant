import services.return_cogs_accounting_recognition_repository as recognition_module
import services.return_cogs_profit_application_authorization_repository as authorization_module
import services.return_cogs_profit_application_commit_repository as commit_module

from services.return_cogs_accounting_recognition_repository import ReturnCogsAccountingRecognitionRepository
from services.return_cogs_profit_application_authorization_repository import ReturnCogsProfitApplicationAuthorizationRepository
from services.return_cogs_profit_application_commit_repository import ReturnCogsProfitApplicationCommitRepository
from services.return_cogs_profit_application_commit_ledger_integrity_service import ReturnCogsProfitApplicationCommitLedgerIntegrityService


def _repos(tmp_path, monkeypatch):
    db = str(tmp_path / "return-cogs.db")
    monkeypatch.setattr(recognition_module, "DB_NAME", db)
    monkeypatch.setattr(authorization_module, "DB_NAME", db)
    monkeypatch.setattr(commit_module, "DB_NAME", db)
    return (
        ReturnCogsAccountingRecognitionRepository(),
        ReturnCogsProfitApplicationAuthorizationRepository(),
        ReturnCogsProfitApplicationCommitRepository(),
    )


def _recognized(recognition, *, amount=120.5, confirmed_on="2026-09-01"):
    return recognition.record_recognition(
        "ret-1", "post-1", "sku-1", "2026-08-31", "COGS_RECOVERY_RECOGNIZED",
        amount, "RUB", confirmed_on, source="TEST_ACCOUNTING",
    )


def _authorized(authorization, recognition_id, *, amount=120.5, confirmed_on="2026-09-02", state="PROFIT_APPLICATION_AUTHORIZED"):
    revoked = state == "PROFIT_APPLICATION_AUTHORIZATION_REVOKED"
    return authorization.record_application_state(
        recognition_id, "ret-1", "post-1", "sku-1", "2026-08-31", state,
        None if revoked else amount,
        None if revoked else "RUB",
        None if revoked else "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
        None if revoked else True,
        confirmed_on,
        source="TEST_AUTHORIZATION",
    )


def test_controlled_commit_derives_money_from_current_authorization(tmp_path, monkeypatch):
    recognition, authorization, commit = _repos(tmp_path, monkeypatch)
    rec = _recognized(recognition)
    auth = _authorized(authorization, rec["history_id"])
    result = commit.commit_current_authorization(
        rec["history_id"], auth["history_id"], "ret-1", "post-1", "sku-1", "2026-09-03"
    )
    assert result["error"] is False
    assert result["committed_amount"] == 120.5
    assert result["currency"] == "RUB"
    assert result["controlled_commit_authorization_revalidated"] is True
    assert result["controlled_commit_recognition_revalidated"] is True


def test_controlled_commit_rejects_stale_authorization_inside_transaction(tmp_path, monkeypatch):
    recognition, authorization, commit = _repos(tmp_path, monkeypatch)
    rec = _recognized(recognition)
    auth = _authorized(authorization, rec["history_id"])
    assert _authorized(
        authorization, rec["history_id"], confirmed_on="2026-09-03",
        state="PROFIT_APPLICATION_AUTHORIZATION_REVOKED",
    )["error"] is False
    result = commit.commit_current_authorization(
        rec["history_id"], auth["history_id"], "ret-1", "post-1", "sku-1", "2026-09-04"
    )
    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_CONTROLLED_COMMIT_AUTHORIZATION_STALE"
    assert commit.get_application_commit(rec["history_id"])["application_commit_confirmed"] is False


def test_controlled_commit_rejects_stale_recognition_version(tmp_path, monkeypatch):
    recognition, authorization, commit = _repos(tmp_path, monkeypatch)
    rec = _recognized(recognition, confirmed_on="2026-09-01")
    auth = _authorized(authorization, rec["history_id"])
    newer = _recognized(recognition, confirmed_on="2026-09-03")
    assert newer["history_id"] != rec["history_id"]
    result = commit.commit_current_authorization(
        rec["history_id"], auth["history_id"], "ret-1", "post-1", "sku-1", "2026-09-04"
    )
    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_CONTROLLED_COMMIT_RECOGNITION_STALE"


def test_exact_replay_is_idempotent_across_repository_restart(tmp_path, monkeypatch):
    recognition, authorization, commit = _repos(tmp_path, monkeypatch)
    rec = _recognized(recognition)
    auth = _authorized(authorization, rec["history_id"])
    first = commit.commit_current_authorization(
        rec["history_id"], auth["history_id"], "ret-1", "post-1", "sku-1", "2026-09-03"
    )
    restarted = ReturnCogsProfitApplicationCommitRepository()
    replay = restarted.commit_current_authorization(
        rec["history_id"], auth["history_id"], "ret-1", "post-1", "sku-1", "2026-09-04"
    )
    assert first["error"] is False
    assert replay["error"] is False
    assert replay["application_already_committed"] is True
    assert replay["idempotent_replay"] is True
    assert restarted.list_commits()["count"] == 1


def test_low_level_changed_replay_is_conflict_and_first_row_is_immutable(tmp_path, monkeypatch):
    _, _, commit = _repos(tmp_path, monkeypatch)
    first = commit.commit_application(
        11, "ret-1", "post-1", "sku-1", "2026-08-31", 100, "RUB", 21, "2026-09-03", "CONTROLLED"
    )
    changed = commit.commit_application(
        11, "ret-1", "post-1", "sku-1", "2026-08-31", 101, "RUB", 21, "2026-09-04", "CONTROLLED"
    )
    assert first["error"] is False
    assert changed["error"] is True
    assert changed["code"] == "RETURN_COGS_PROFIT_APPLICATION_COMMIT_REPLAY_CONFLICT"
    assert commit.get_application_commit(11)["committed_amount"] == 100.0


def test_authorization_history_id_cannot_be_reused_for_second_recognition(tmp_path, monkeypatch):
    _, _, commit = _repos(tmp_path, monkeypatch)
    assert commit.commit_application(
        11, "ret-1", "post-1", "sku-1", "2026-08-31", 100, "RUB", 21, "2026-09-03", "CONTROLLED"
    )["error"] is False
    second = commit.commit_application(
        12, "ret-2", "post-2", "sku-2", "2026-08-31", 100, "RUB", 21, "2026-09-03", "CONTROLLED"
    )
    assert second["error"] is True
    assert second["code"] == "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_ALREADY_COMMITTED"


def test_commit_repository_rejects_non_finite_money(tmp_path, monkeypatch):
    _, _, commit = _repos(tmp_path, monkeypatch)
    for value in (float("nan"), float("inf"), float("-inf")):
        result = commit.commit_application(
            11, "ret-1", "post-1", "sku-1", "2026-08-31", value, "RUB", 21, "2026-09-03"
        )
        assert result["error"] is True
        assert result["code"] == "RETURN_COGS_PROFIT_APPLICATION_COMMIT_INPUT_INVALID"
    assert commit.list_commits()["count"] == 0


def test_ledger_integrity_reconciles_current_chain(tmp_path, monkeypatch):
    recognition, authorization, commit = _repos(tmp_path, monkeypatch)
    rec = _recognized(recognition)
    auth = _authorized(authorization, rec["history_id"])
    assert commit.commit_current_authorization(
        rec["history_id"], auth["history_id"], "ret-1", "post-1", "sku-1", "2026-09-03"
    )["error"] is False
    audit = ReturnCogsProfitApplicationCommitLedgerIntegrityService(
        commit, recognition, authorization
    ).audit()
    assert audit["error"] is False
    assert audit["integrity_confirmed"] is True
    assert audit["commit_count"] == 1
    assert audit["issue_count"] == 0
    assert audit["read_only"] is True
    assert audit["executed"] is False


def test_ledger_integrity_detects_post_commit_authorization_revocation(tmp_path, monkeypatch):
    recognition, authorization, commit = _repos(tmp_path, monkeypatch)
    rec = _recognized(recognition)
    auth = _authorized(authorization, rec["history_id"])
    commit.commit_current_authorization(
        rec["history_id"], auth["history_id"], "ret-1", "post-1", "sku-1", "2026-09-03"
    )
    _authorized(
        authorization, rec["history_id"], confirmed_on="2026-09-04",
        state="PROFIT_APPLICATION_AUTHORIZATION_REVOKED",
    )
    audit = ReturnCogsProfitApplicationCommitLedgerIntegrityService(
        commit, recognition, authorization
    ).audit()
    assert audit["error"] is False
    assert audit["integrity_confirmed"] is False
    assert audit["issue_count"] == 1
    assert audit["issues"][0]["code"] in {
        "RETURN_COGS_COMMIT_LEDGER_AUTHORIZATION_NOT_CURRENT",
        "RETURN_COGS_COMMIT_LEDGER_AUTHORIZATION_VERSION_STALE",
    }
