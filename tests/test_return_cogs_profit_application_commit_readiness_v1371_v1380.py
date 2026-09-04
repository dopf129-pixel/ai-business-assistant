import sqlite3

import pytest

import services.return_cogs_profit_application_commit_repository as repository_module
from services.period_profit_return_cogs_application_commit_readiness_service import (
    PeriodProfitReturnCogsApplicationCommitReadinessService,
)
from services.return_cogs_profit_application_commit_repository import (
    ReturnCogsProfitApplicationCommitRepository,
)


IDENTITY = ("ret-1", "post-1", "42")
RECOGNITION_HISTORY_ID = 7
AUTHORIZATION_HISTORY_ID = 11


class Base:
    def __init__(self, value=None):
        self.value = value

    def analyze(self, return_evidence, products):
        if isinstance(self.value, Exception):
            raise self.value
        return _eligible_base() if self.value is None else self.value


class CommitRepository:
    def __init__(self, value=None):
        self.value = value

    def get_application_commit(self, recognition_history_id):
        if isinstance(self.value, Exception):
            raise self.value
        if self.value is not None:
            return self.value
        return {
            "error": False,
            "status": "RETURN_COGS_PROFIT_APPLICATION_COMMIT_MISSING",
            "recognition_history_id": recognition_history_id,
            "application_commit_confirmed": False,
            "application_already_committed": False,
            "committed_amount": None,
            "currency": None,
        }


def _eligible_base():
    return {
        "error": False,
        "return_cogs_profit_application_eligibility_confirmed": True,
        "return_cogs_accounting_recognition_evidence_records": [
            {
                "history_id": RECOGNITION_HISTORY_ID,
                "return_id": IDENTITY[0],
                "posting_number": IDENTITY[1],
                "sku": IDENTITY[2],
                "recovery_accounting_date": "2026-09-04",
                "recognized_amount": 150.0,
                "currency": "RUB",
            }
        ],
        "return_cogs_profit_application_authorization_records": [
            {
                "history_id": AUTHORIZATION_HISTORY_ID,
                "recognition_history_id": RECOGNITION_HISTORY_ID,
                "return_id": IDENTITY[0],
                "posting_number": IDENTITY[1],
                "sku": IDENTITY[2],
                "authorized_amount": 150.0,
                "currency": "RUB",
            }
        ],
        "return_cogs_profit_application_eligible_amount": 150.0,
        "return_cogs_profit_application_amount": None,
        "return_cogs_profit_applied": False,
        "profit_adjustment_allowed": False,
        "automatic_recovery_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _committed_record(**overrides):
    record = {
        "error": False,
        "status": "RETURN_COGS_PROFIT_APPLICATION_ALREADY_COMMITTED",
        "history_id": 3,
        "recognition_history_id": RECOGNITION_HISTORY_ID,
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "recovery_accounting_date": "2026-09-04",
        "committed_amount": 150.0,
        "currency": "RUB",
        "authorization_history_id": AUTHORIZATION_HISTORY_ID,
        "committed_on": "2026-09-04",
        "application_commit_confirmed": True,
        "application_already_committed": True,
    }
    record.update(overrides)
    return record


def _analyze(base=None, repository=None):
    return PeriodProfitReturnCogsApplicationCommitReadinessService(
        base or Base(), repository or CommitRepository()
    ).analyze({}, [])


def test_v1371_eligible_uncommitted_recovery_is_commit_ready_but_not_profit_applied():
    result = _analyze()
    assert result["return_cogs_profit_application_commit_ready"] is True
    assert result["return_cogs_profit_application_commit_confirmed"] is False
    assert result["return_cogs_profit_application_commit_blockers"] == []
    assert result["return_cogs_profit_applied"] is False
    assert result["return_cogs_profit_application_amount"] is None
    assert result["profit_adjustment_allowed"] is False


def test_v1372_ineligible_recovery_cannot_be_commit_ready():
    base = _eligible_base()
    base["return_cogs_profit_application_eligibility_confirmed"] = False
    result = _analyze(base=Base(base))
    assert result["return_cogs_profit_application_commit_ready"] is False
    assert "RETURN_COGS_APPLICATION_ELIGIBILITY_REQUIRED" in result["return_cogs_profit_application_commit_blockers"]


def test_v1373_existing_exact_commit_is_confirmed_without_reapplying_profit():
    result = _analyze(repository=CommitRepository(_committed_record()))
    assert result["return_cogs_profit_application_commit_confirmed"] is True
    assert result["return_cogs_profit_application_commit_ready"] is False
    assert result["return_cogs_profit_applied"] is False
    assert result["profit_adjustment_allowed"] is False


def test_v1374_commit_must_match_recognition_identity_amount_date_currency_and_authorization_version():
    result = _analyze(
        repository=CommitRepository(
            _committed_record(
                posting_number="other-post",
                committed_amount=149.0,
                recovery_accounting_date="2026-09-03",
                currency="USD",
                authorization_history_id=12,
            )
        )
    )
    blockers = result["return_cogs_profit_application_commit_blockers"]
    assert "RETURN_COGS_APPLICATION_COMMIT_IDENTITY_MISMATCH" in blockers
    assert "RETURN_COGS_APPLICATION_COMMIT_AMOUNT_MISMATCH" in blockers
    assert "RETURN_COGS_APPLICATION_COMMIT_ACCOUNTING_DATE_MISMATCH" in blockers
    assert "RETURN_COGS_APPLICATION_COMMIT_CURRENCY_RUB_REQUIRED" in blockers
    assert "RETURN_COGS_APPLICATION_COMMIT_AUTHORIZATION_VERSION_MISMATCH" in blockers


def test_v1375_repository_failure_fails_closed_without_profit_change():
    result = _analyze(repository=CommitRepository(RuntimeError("boom")))
    assert result["return_cogs_profit_application_commit_ready"] is False
    assert "RETURN_COGS_APPLICATION_COMMIT_REPOSITORY_EXCEPTION" in result["return_cogs_profit_application_commit_blockers"]
    assert result["profit_adjustment_allowed"] is False


def test_v1376_commit_repository_is_atomic_exact_once_and_first_writer_wins(tmp_path, monkeypatch):
    db_path = tmp_path / "commit.db"
    monkeypatch.setattr(repository_module, "DB_NAME", str(db_path))
    repository = ReturnCogsProfitApplicationCommitRepository()

    first = repository.commit_application(
        RECOGNITION_HISTORY_ID,
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        committed_amount=150.0,
        currency="RUB",
        authorization_history_id=AUTHORIZATION_HISTORY_ID,
        committed_on="2026-09-04",
    )
    second = repository.commit_application(
        RECOGNITION_HISTORY_ID,
        "ret-other",
        "post-other",
        "99",
        recovery_accounting_date="2026-09-05",
        committed_amount=999.0,
        currency="RUB",
        authorization_history_id=99,
        committed_on="2026-09-05",
    )

    assert first["status"] == "RETURN_COGS_PROFIT_APPLICATION_COMMIT_RECORDED"
    assert first["application_already_committed"] is False
    assert second["status"] == "RETURN_COGS_PROFIT_APPLICATION_ALREADY_COMMITTED"
    assert second["application_already_committed"] is True
    assert second["return_id"] == IDENTITY[0]
    assert second["committed_amount"] == 150.0
    assert second["authorization_history_id"] == AUTHORIZATION_HISTORY_ID


def test_v1377_commit_ledger_is_append_only_for_update_and_delete(tmp_path, monkeypatch):
    db_path = tmp_path / "commit.db"
    monkeypatch.setattr(repository_module, "DB_NAME", str(db_path))
    repository = ReturnCogsProfitApplicationCommitRepository()
    repository.commit_application(
        RECOGNITION_HISTORY_ID,
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        committed_amount=150.0,
        currency="RUB",
        authorization_history_id=AUTHORIZATION_HISTORY_ID,
        committed_on="2026-09-04",
    )

    conn = sqlite3.connect(str(db_path))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE return_cogs_profit_application_commit_history SET committed_amount = 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM return_cogs_profit_application_commit_history")
    conn.close()


def test_v1378_invalid_commit_input_fails_closed_and_unknown_is_not_zero(tmp_path, monkeypatch):
    db_path = tmp_path / "commit.db"
    monkeypatch.setattr(repository_module, "DB_NAME", str(db_path))
    repository = ReturnCogsProfitApplicationCommitRepository()
    result = repository.commit_application(
        RECOGNITION_HISTORY_ID,
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        committed_amount=None,
        currency="RUB",
        authorization_history_id=AUTHORIZATION_HISTORY_ID,
        committed_on="2026-09-04",
    )
    assert result["error"] is True
    assert result["committed_amount"] is None


def test_v1379_commit_readiness_remains_read_only_and_execution_false():
    result = _analyze()
    assert result["read_only"] is True
    assert result["executed"] is False
    assert result["automatic_recovery_allowed"] is False
    assert result["compensation_profit_adjustment_allowed"] is False


def test_v1380_commit_readiness_declares_exact_once_recognition_version_basis():
    result = _analyze()
    assert result["return_cogs_profit_application_exact_once_basis"] == "UNIQUE_RECOGNITION_HISTORY_ID_APPEND_ONLY_COMMIT_LEDGER"
