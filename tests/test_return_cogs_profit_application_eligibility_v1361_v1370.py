import inspect
import sqlite3

import pytest

import period_profit_factory
import services.return_cogs_profit_application_authorization_repository as repository_module
from services.period_profit_return_cogs_application_eligibility_service import (
    PeriodProfitReturnCogsApplicationEligibilityService,
)
from services.return_cogs_profit_application_authorization_repository import (
    ReturnCogsProfitApplicationAuthorizationRepository,
)


IDENTITY = ("ret-1", "post-1", "42")
RECOGNITION_HISTORY_ID = 7


class Base:
    def __init__(self, value=None, overrides=None):
        self.value = value
        self.overrides = dict(overrides or {})

    def analyze(self, return_evidence, products):
        if isinstance(self.value, Exception):
            raise self.value
        if self.value is not None:
            return self.value
        result = _recognized_base()
        result.update(self.overrides)
        return result


class AuthorizationRepository:
    def __init__(self, value=None):
        self.value = value

    def get_application_authorization(self, recognition_history_id, return_id, posting_number, sku):
        if isinstance(self.value, Exception):
            raise self.value
        if self.value is not None:
            return self.value
        return _authorization_record()


def _candidate():
    return {"return_id": IDENTITY[0], "posting_number": IDENTITY[1], "sku": IDENTITY[2], "quantity": 2}


def _attribution_record(accounting_date="2026-09-04", period_matches=True, compensation_clear=True):
    return {
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
        "recovery_accounting_date": accounting_date,
        "recovery_accounting_period_matches_request": period_matches,
        "compensation_state": "NO_COMPENSATION_CONFIRMED",
        "compensation_double_count_clear": compensation_clear,
    }


def _recognition_record(amount=150.0, currency="RUB", accounting_date="2026-09-04", history_id=RECOGNITION_HISTORY_ID):
    return {
        "error": False,
        "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
        "history_id": history_id,
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "recovery_accounting_date": accounting_date,
        "recognition_state": "COGS_RECOVERY_RECOGNIZED",
        "recognized_amount": amount,
        "currency": currency,
        "confirmed_on": "2026-09-04",
        "accounting_recognition_confirmed": True,
    }


def _recognized_base():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
        "candidate_records": [_candidate()],
        "accounting_attribution_evidence_records": [_attribution_record()],
        "return_cogs_accounting_recognition_evidence_confirmed": True,
        "return_cogs_accounting_recognition_evidence_records": [_recognition_record()],
        "period_cogs_recovery_confirmed": True,
        "accounting_cogs_recovery_confirmed": True,
        "confirmed_cogs_recovery_amount": 150.0,
        "profit_adjustment_allowed": False,
        "automatic_recovery_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _authorization_record(
    amount=150.0,
    currency="RUB",
    accounting_date="2026-09-04",
    treatment="EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
    authority_clear=True,
    compensation_clear=True,
    state="PROFIT_APPLICATION_AUTHORIZED",
    confirmed=True,
    already_applied=False,
):
    return {
        "error": False,
        "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY",
        "recognition_history_id": RECOGNITION_HISTORY_ID,
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "recovery_accounting_date": accounting_date,
        "application_state": state,
        "authorized_amount": amount,
        "currency": currency,
        "monetary_authority_treatment": treatment,
        "monetary_authority_non_overlap_confirmed": authority_clear,
        "compensation_non_overlap_confirmed": compensation_clear,
        "application_authorization_confirmed": confirmed,
        "application_already_applied": already_applied,
    }


def _analyze(base=None, repository=None):
    return PeriodProfitReturnCogsApplicationEligibilityService(
        base or Base(),
        repository or AuthorizationRepository(),
    ).analyze({}, [])


def test_v1361_explicit_exclusion_authorization_proves_application_eligibility_only():
    result = _analyze()

    assert result["return_cogs_profit_application_eligibility_confirmed"] is True
    assert result["return_cogs_profit_application_eligible_amount"] == 150.0
    assert result["return_cogs_profit_application_eligible_currency"] == "RUB"
    assert result["return_cogs_profit_application_blockers"] == []
    assert result["return_cogs_profit_applied"] is False
    assert result["return_cogs_profit_application_amount"] is None
    assert result["profit_adjustment_allowed"] is False
    assert result["automatic_recovery_allowed"] is False
    assert result["read_only"] is True
    assert result["executed"] is False


def test_v1362_accounting_recognition_is_required_and_not_reconstructed_from_amount():
    result = _analyze(base=Base(overrides={"return_cogs_accounting_recognition_evidence_confirmed": False}))

    assert result["return_cogs_profit_application_eligibility_confirmed"] is False
    assert "RETURN_COGS_ACCOUNTING_RECOGNITION_REQUIRED" in result["return_cogs_profit_application_blockers"]
    assert result["profit_adjustment_allowed"] is False


def test_v1363_account_net_accrual_exclusion_and_non_overlap_are_both_explicit():
    included = _authorization_record(treatment="INCLUDED_IN_ACCOUNT_NET_ACCRUAL")
    included["monetary_authority_non_overlap_confirmed"] = False
    result = _analyze(repository=AuthorizationRepository(included))

    assert result["return_cogs_profit_application_eligibility_confirmed"] is False
    assert "RETURN_COGS_APPLICATION_MONETARY_AUTHORITY_EXCLUSION_REQUIRED" in result["return_cogs_profit_application_blockers"]
    assert "RETURN_COGS_APPLICATION_MONETARY_AUTHORITY_NON_OVERLAP_REQUIRED" in result["return_cogs_profit_application_blockers"]


def test_v1364_exact_recognition_version_identity_period_amount_and_rub_must_reconcile():
    record = _authorization_record(amount=149.98, currency="USD", accounting_date="2026-09-03")
    record["recognition_history_id"] = 8
    record["posting_number"] = "other-post"
    result = _analyze(repository=AuthorizationRepository(record))

    blockers = result["return_cogs_profit_application_blockers"]
    assert result["return_cogs_profit_application_eligibility_confirmed"] is False
    assert "RETURN_COGS_APPLICATION_RECOGNITION_VERSION_MATCH_REQUIRED" in blockers
    assert "RETURN_COGS_APPLICATION_IDENTITY_MATCH_REQUIRED" in blockers
    assert "RETURN_COGS_APPLICATION_AMOUNT_MISMATCH" in blockers
    assert "RETURN_COGS_APPLICATION_CURRENCY_RUB_REQUIRED" in blockers
    assert "RETURN_COGS_APPLICATION_ACCOUNTING_DATE_MATCH_REQUIRED" in blockers


def test_v1365_compensation_overlap_or_wrong_selected_period_blocks_application():
    attribution = _attribution_record(accounting_date="2026-09-03", period_matches=False, compensation_clear=False)
    result = _analyze(base=Base(overrides={"accounting_attribution_evidence_records": [attribution]}))

    blockers = result["return_cogs_profit_application_blockers"]
    assert result["return_cogs_profit_application_eligibility_confirmed"] is False
    assert "RETURN_COGS_APPLICATION_PERIOD_MATCH_REQUIRED" in blockers
    assert "RETURN_COGS_APPLICATION_PERIOD_RECONCILIATION_REQUIRED" in blockers
    assert "RETURN_COGS_APPLICATION_COMPENSATION_DOUBLE_COUNT_CLEAR_REQUIRED" in blockers


def test_v1366_missing_or_revoked_authorization_fails_closed_unknown_is_not_zero():
    missing = _authorization_record(confirmed=False, state="")
    missing["status"] = "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_MISSING"
    missing["authorized_amount"] = None
    missing["currency"] = None
    revoked = dict(missing, status="RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_REVOKED")

    for source in (missing, revoked):
        result = _analyze(repository=AuthorizationRepository(source))
        assert result["return_cogs_profit_application_eligibility_confirmed"] is False
        assert result["return_cogs_profit_application_eligible_amount"] is None
        assert result["return_cogs_profit_application_amount"] is None
        assert result["profit_adjustment_allowed"] is False


def test_v1367_already_applied_recognition_version_is_idempotently_blocked():
    applied = _authorization_record(confirmed=False, state="PROFIT_APPLICATION_APPLIED", already_applied=True)
    applied["status"] = "RETURN_COGS_PROFIT_APPLICATION_ALREADY_APPLIED"
    result = _analyze(repository=AuthorizationRepository(applied))

    assert result["return_cogs_profit_application_eligibility_confirmed"] is False
    assert "RETURN_COGS_APPLICATION_ALREADY_APPLIED_BLOCKED" in result["return_cogs_profit_application_blockers"]
    assert result["return_cogs_profit_applied"] is False
    assert result["profit_adjustment_allowed"] is False


def test_v1368_repository_and_base_failures_are_contained_without_profit_change():
    exceptional_repository = _analyze(repository=AuthorizationRepository(RuntimeError("boom")))
    malformed_base = _analyze(base=Base(value=[]))
    exceptional_base = _analyze(base=Base(value=RuntimeError("boom")))

    assert exceptional_repository["return_cogs_profit_application_eligibility_confirmed"] is False
    assert "RETURN_COGS_APPLICATION_AUTHORIZATION_REPOSITORY_EXCEPTION" in exceptional_repository["return_cogs_profit_application_blockers"]
    for result in (malformed_base, exceptional_base):
        assert result["error"] is True
        assert result["return_cogs_profit_application_eligibility_confirmed"] is False
        assert result["return_cogs_profit_application_eligible_amount"] is None
        assert result["profit_adjustment_allowed"] is False
        assert result["automatic_recovery_allowed"] is False


def test_v1369_repository_is_append_only_revocable_and_permanently_blocks_applied_version(tmp_path, monkeypatch):
    db_path = tmp_path / "application.db"
    monkeypatch.setattr(repository_module, "DB_NAME", str(db_path))
    repository = ReturnCogsProfitApplicationAuthorizationRepository()

    authorized = repository.record_application_state(
        RECOGNITION_HISTORY_ID,
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        application_state="PROFIT_APPLICATION_AUTHORIZED",
        authorized_amount=150.0,
        currency="RUB",
        monetary_authority_treatment="EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
        compensation_non_overlap_confirmed=True,
        confirmed_on="2026-09-04",
    )
    assert authorized["error"] is False
    assert repository.get_application_authorization(RECOGNITION_HISTORY_ID, *IDENTITY)["application_authorization_confirmed"] is True

    applied = repository.record_application_state(
        RECOGNITION_HISTORY_ID,
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        application_state="PROFIT_APPLICATION_APPLIED",
        authorized_amount=150.0,
        currency="RUB",
        monetary_authority_treatment="EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
        compensation_non_overlap_confirmed=True,
        confirmed_on="2026-09-05",
    )
    assert applied["error"] is False
    latest = repository.get_application_authorization(RECOGNITION_HISTORY_ID, *IDENTITY)
    assert latest["status"] == "RETURN_COGS_PROFIT_APPLICATION_ALREADY_APPLIED"
    assert latest["application_already_applied"] is True
    assert latest["application_authorization_confirmed"] is False

    revoked_after_applied = repository.record_application_state(
        RECOGNITION_HISTORY_ID,
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        application_state="PROFIT_APPLICATION_AUTHORIZATION_REVOKED",
        authorized_amount=None,
        currency=None,
        monetary_authority_treatment=None,
        compensation_non_overlap_confirmed=None,
        confirmed_on="2026-09-06",
    )
    assert revoked_after_applied["error"] is False
    assert repository.get_application_authorization(RECOGNITION_HISTORY_ID, *IDENTITY)["status"] == "RETURN_COGS_PROFIT_APPLICATION_ALREADY_APPLIED"

    conn = sqlite3.connect(str(db_path))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE return_cogs_profit_application_authorization_history SET authorized_amount = 999 WHERE recognition_history_id = ?",
            (RECOGNITION_HISTORY_ID,),
        )
    conn.close()


def test_v1370_factory_wires_application_eligibility_after_accounting_recognition():
    source = inspect.getsource(period_profit_factory.create_period_profit_query)

    recognition_position = source.index("PeriodProfitReturnCogsAccountingRecognitionService")
    application_position = source.index("PeriodProfitReturnCogsApplicationEligibilityService")
    assert recognition_position < application_position
    assert "ReturnCogsProfitApplicationAuthorizationRepository" in source
