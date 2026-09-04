import sqlite3

import pytest

import services.return_cogs_accounting_recognition_repository as repository_module
from services.period_profit_return_cogs_accounting_recognition_service import (
    PeriodProfitReturnCogsAccountingRecognitionService,
)
from services.return_cogs_accounting_recognition_repository import (
    ReturnCogsAccountingRecognitionRepository,
)


IDENTITY = ("ret-1", "post-1", "42")


class Base:
    def __init__(self, value=None, overrides=None):
        self.value = value
        self.overrides = dict(overrides or {})

    def analyze(self, return_evidence, products):
        if isinstance(self.value, Exception):
            raise self.value
        if self.value is not None:
            return self.value
        result = _eligible_base()
        result.update(self.overrides)
        return result


class RecognitionRepository:
    def __init__(self, value=None):
        self.value = value

    def get_latest_recognition(self, return_id, posting_number, sku):
        if isinstance(self.value, Exception):
            raise self.value
        if self.value is not None:
            return self.value
        return _recognition_record()


def _candidate():
    return {
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "quantity": 2,
    }


def _amount_record(amount=150.0):
    return {
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "status": "RETURN_COGS_AMOUNT_CANDIDATE_READY",
        "staged_recovery_amount": amount,
    }


def _attribution_record(accounting_date="2026-09-04"):
    return {
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
        "recovery_accounting_date": accounting_date,
        "recovery_accounting_period_matches_request": True,
        "compensation_state": "NO_COMPENSATION_CONFIRMED",
        "compensation_double_count_clear": True,
    }


def _eligible_base():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_COGS_RECOGNITION_ELIGIBILITY_READY",
        "candidate_records": [_candidate()],
        "return_cogs_recovery_amount_evidence_records": [_amount_record()],
        "accounting_attribution_evidence_records": [_attribution_record()],
        "return_cogs_recognition_eligibility_confirmed": True,
        "return_cogs_recognition_eligible_amount": 150.0,
        "return_cogs_recognition_eligible_currency": "RUB",
        "period_cogs_recovery_confirmed": False,
        "accounting_cogs_recovery_confirmed": False,
        "confirmed_cogs_recovery_amount": 0.0,
        "profit_adjustment_allowed": False,
        "automatic_recovery_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _recognition_record(
    amount=150.0,
    currency="RUB",
    accounting_date="2026-09-04",
    return_id=IDENTITY[0],
    posting_number=IDENTITY[1],
    sku=IDENTITY[2],
):
    return {
        "error": False,
        "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
        "return_id": return_id,
        "posting_number": posting_number,
        "sku": sku,
        "recovery_accounting_date": accounting_date,
        "recognition_state": "COGS_RECOVERY_RECOGNIZED",
        "recognized_amount": amount,
        "currency": currency,
        "confirmed_on": "2026-09-04",
        "source": "SELLER_ACCOUNTING_BOOKED",
        "accounting_recognition_confirmed": True,
    }


def _analyze(base=None, repository=None):
    service = PeriodProfitReturnCogsAccountingRecognitionService(
        base or Base(),
        repository or RecognitionRepository(),
    )
    return service.analyze({}, [])


def test_v1351_exact_explicit_booking_confirms_accounting_recovery_without_profit_application():
    result = _analyze()

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is True
    assert result["period_cogs_recovery_confirmed"] is True
    assert result["accounting_cogs_recovery_confirmed"] is True
    assert result["confirmed_cogs_recovery_amount"] == 150.0
    assert result["profit_adjustment_allowed"] is False
    assert result["automatic_recovery_allowed"] is False
    assert result["read_only"] is True
    assert result["executed"] is False


def test_v1352_recognition_eligibility_is_required_before_booking_can_confirm():
    result = _analyze(
        base=Base(overrides={"return_cogs_recognition_eligibility_confirmed": False})
    )

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is False
    assert result["confirmed_cogs_recovery_amount"] == 0.0
    assert "RETURN_COGS_RECOGNITION_ELIGIBILITY_REQUIRED" in result[
        "return_cogs_accounting_recognition_blockers"
    ]


def test_v1353_missing_explicit_booking_fails_closed_unknown_is_not_zero_evidence():
    missing = {
        "error": False,
        "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_MISSING",
        "return_id": IDENTITY[0],
        "posting_number": IDENTITY[1],
        "sku": IDENTITY[2],
        "accounting_recognition_confirmed": False,
        "recovery_accounting_date": None,
        "recognition_state": None,
        "recognized_amount": None,
        "currency": None,
    }
    result = _analyze(repository=RecognitionRepository(missing))

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is False
    assert result["accounting_cogs_recovery_confirmed"] is False
    assert result["confirmed_cogs_recovery_amount"] == 0.0
    assert "RETURN_COGS_ACCOUNTING_RECOGNITION_EXPLICIT_CONFIRMATION_REQUIRED" in result[
        "return_cogs_accounting_recognition_blockers"
    ]


def test_v1354_recognized_amount_must_match_staged_historical_cost_amount():
    result = _analyze(
        repository=RecognitionRepository(_recognition_record(amount=149.99))
    )

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is False
    assert "RETURN_COGS_ACCOUNTING_RECOGNITION_AMOUNT_MISMATCH" in result[
        "return_cogs_accounting_recognition_blockers"
    ]


def test_v1355_recognized_currency_must_be_explicit_rub():
    result = _analyze(
        repository=RecognitionRepository(_recognition_record(currency="USD"))
    )

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is False
    assert "RETURN_COGS_ACCOUNTING_RECOGNITION_CURRENCY_RUB_REQUIRED" in result[
        "return_cogs_accounting_recognition_blockers"
    ]


def test_v1356_recognition_date_must_match_explicit_accounting_attribution():
    result = _analyze(
        repository=RecognitionRepository(
            _recognition_record(accounting_date="2026-09-03")
        )
    )

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is False
    assert "RETURN_COGS_ACCOUNTING_RECOGNITION_DATE_MATCH_REQUIRED" in result[
        "return_cogs_accounting_recognition_blockers"
    ]


def test_v1357_exact_return_posting_sku_identity_is_required():
    result = _analyze(
        repository=RecognitionRepository(
            _recognition_record(posting_number="other-post")
        )
    )

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is False
    assert "RETURN_COGS_ACCOUNTING_RECOGNITION_IDENTITY_MATCH_REQUIRED" in result[
        "return_cogs_accounting_recognition_blockers"
    ]


def test_v1358_repository_exception_is_contained_and_never_changes_profit():
    result = _analyze(repository=RecognitionRepository(RuntimeError("boom")))

    assert result["return_cogs_accounting_recognition_evidence_confirmed"] is False
    assert result["period_cogs_recovery_confirmed"] is False
    assert result["accounting_cogs_recovery_confirmed"] is False
    assert result["confirmed_cogs_recovery_amount"] == 0.0
    assert result["profit_adjustment_allowed"] is False
    assert "RETURN_COGS_ACCOUNTING_RECOGNITION_REPOSITORY_EXCEPTION" in result[
        "return_cogs_accounting_recognition_blockers"
    ]


def test_v1359_malformed_or_exceptional_base_fails_closed():
    malformed = _analyze(base=Base(value=[]))
    exceptional = _analyze(base=Base(value=RuntimeError("boom")))

    for result in (malformed, exceptional):
        assert result["error"] is True
        assert result["period_cogs_recovery_confirmed"] is False
        assert result["accounting_cogs_recovery_confirmed"] is False
        assert result["confirmed_cogs_recovery_amount"] == 0.0
        assert result["profit_adjustment_allowed"] is False
        assert result["automatic_recovery_allowed"] is False


def test_v1360_repository_is_append_only_versioned_and_latest_revocation_fails_closed(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "recognition.db"
    monkeypatch.setattr(repository_module, "DB_NAME", str(db_path))
    repository = ReturnCogsAccountingRecognitionRepository()

    recorded = repository.record_recognition(
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        recognition_state="COGS_RECOVERY_RECOGNIZED",
        recognized_amount=150.0,
        currency="RUB",
        confirmed_on="2026-09-04",
    )
    assert recorded["error"] is False
    assert repository.get_latest_recognition(*IDENTITY)[
        "accounting_recognition_confirmed"
    ] is True

    duplicate = repository.record_recognition(
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        recognition_state="COGS_RECOVERY_RECOGNIZED",
        recognized_amount=150.0,
        currency="RUB",
        confirmed_on="2026-09-04",
    )
    assert duplicate["code"] == "RETURN_COGS_ACCOUNTING_RECOGNITION_VERSION_CONFLICT"

    revoked = repository.record_recognition(
        *IDENTITY,
        recovery_accounting_date="2026-09-04",
        recognition_state="COGS_RECOVERY_RECOGNITION_REVOKED",
        recognized_amount=None,
        currency=None,
        confirmed_on="2026-09-05",
    )
    assert revoked["error"] is False
    latest = repository.get_latest_recognition(*IDENTITY)
    assert latest["status"] == "RETURN_COGS_ACCOUNTING_RECOGNITION_REVOKED"
    assert latest["accounting_recognition_confirmed"] is False
    assert latest["recognized_amount"] is None

    conn = sqlite3.connect(str(db_path))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            UPDATE return_cogs_accounting_recognition_history
            SET recognized_amount = 999
            WHERE return_id = ?
            """,
            (IDENTITY[0],),
        )
    conn.close()
